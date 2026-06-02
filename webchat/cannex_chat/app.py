"""
CannEx Webchat — Chainlit 入口（重写版）

架构：
  Chainlit ←→ AgentLoop ←→ AnthropicClient + WorkerClient
"""
import logging
import os
import sys
from pathlib import Path

# 把项目根加入 sys.path，使 webchat.cannex_chat.* 可被 import
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import chainlit as cl
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from webchat.cannex_chat.agent.anthropic_client import LLMStreamClient  # noqa: E402
from webchat.cannex_chat.agent.loop import AgentLoop  # noqa: E402
from webchat.cannex_chat.agent.worker_client import WorkerClient  # noqa: E402
from webchat.cannex_chat.middleware.logging_setup import setup_logging  # noqa: E402
from webchat.cannex_chat.middleware.rate_limit import RateLimiter  # noqa: E402

# Side-effect import: registers Chainlit @cl.password_auth_callback.
# Skipped when CANNEX_DISABLE_AUTH=1 (e.g. local dev without SQLite DB).
if os.environ.get("CANNEX_DISABLE_AUTH") != "1":
    from webchat.cannex_chat import auth as _auth  # noqa: F401, E402
from webchat.cannex_chat.ui.banners import (  # noqa: E402
    KEY_INVALID_MESSAGE, NO_KEY_PROMPT, QUOTA_EXCEEDED_MESSAGE,
    RATE_LIMIT_MESSAGE, WELCOME_BANNER,
)
from webchat.cannex_chat.ui.byok import make_byok_settings, save_llm_config  # noqa: E402
from webchat.cannex_chat.agent import llm_config  # noqa: E402
from webchat.cannex_chat.agent.providers import resolve  # noqa: E402

_logs_dir = os.environ.get(
    "CANNEX_LOGS_DIR",
    str(Path(__file__).resolve().parents[2] / "logs"),
)
setup_logging(_logs_dir)
log = logging.getLogger("cannex.app")

# 全局单例
_WORKER: WorkerClient | None = None
_ANTHROPIC = LLMStreamClient()
_RATE_LIMITER = RateLimiter(max_per_window=30, window_seconds=60)

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")
    _HAS_TIKTOKEN = True
except ImportError:
    _ENC = None
    _HAS_TIKTOKEN = False

_HISTORY_TOKEN_BUDGET = 8000


async def get_worker() -> WorkerClient:
    global _WORKER
    if _WORKER is None:
        cannex_root = os.environ.get("CANNEX_ROOT", str(Path(__file__).resolve().parents[2]))
        worker_env = {
            "CANNEX_ROOT": cannex_root,
            "PATH": os.environ.get("PATH", ""),
        }
        # 透传 node/nvm 定位变量，供 codegraph_client 解析 codegraph 绝对路径兜底。
        # 不透传 ANTHROPIC_API_KEY 等敏感变量（worker 不需要 LLM 凭证）。
        for _k in ("HOME", "NVM_DIR", "NVM_BIN", "CANNEX_CODEGRAPH_BIN"):
            _v = os.environ.get(_k)
            if _v:
                worker_env[_k] = _v
        _WORKER = WorkerClient(env=worker_env)
        await _WORKER.start()
    return _WORKER


def _count_tokens(msg: dict) -> int:
    if not _HAS_TIKTOKEN:
        c = msg["content"]
        return len(c) // 4 if isinstance(c, str) else 100
    c = msg["content"]
    if isinstance(c, str):
        return len(_ENC.encode(c))
    return sum(len(_ENC.encode(str(b))) for b in c)


def _token_truncate(history: list[dict]) -> list[dict]:
    """Drop oldest turns until total token count <= budget."""
    total = sum(_count_tokens(m) for m in history)
    while history and total > _HISTORY_TOKEN_BUDGET:
        dropped = history.pop(0)
        total -= _count_tokens(dropped)
    return history


def _client_ip() -> str:
    """Use Chainlit session id as rate-limit key (Chainlit doesn't expose client IP directly)."""
    try:
        return cl.context.session.id
    except Exception:
        return "unknown"


@cl.on_chat_start
async def on_start():
    await get_worker()  # 预热 worker
    user = cl.user_session.get("user")
    username = user.identifier if user else None
    cl.user_session.set("username", username)
    cfg = llm_config.load_config(username) if username else None
    if cfg:
        cl.user_session.set("llm_config", cfg)
    await make_byok_settings(cfg).send()
    cl.user_session.set("history", [])
    await cl.Message(content=WELCOME_BANNER).send()


@cl.on_settings_update
async def on_settings(settings: dict):
    username = cl.user_session.get("username")
    res = await save_llm_config(settings, username)
    if res["ok"]:
        await cl.Message(content="✅ LLM 配置已保存").send()
    else:
        await cl.Message(content=f"⚠️ {res['error']}").send()


def _friendly_error(msg: str) -> str:
    """Map a raw provider/LLM error string to a user-facing banner, or "" for generic."""
    low = msg.lower()
    if "401" in msg or "403" in msg or "invalid_api_key" in low or "authentication" in low:
        return KEY_INVALID_MESSAGE
    if ("ratelimit" in low or "rate limit" in low or "quota" in low
            or "429" in msg or "too many requests" in low):
        return QUOTA_EXCEEDED_MESSAGE
    return ""


@cl.on_message
async def on_message(message: cl.Message):
    cfg = cl.user_session.get("llm_config")
    if not cfg or not cfg.get("api_key"):
        await cl.Message(content=NO_KEY_PROMPT).send()
        return
    try:
        litellm_model, api_base = resolve(cfg["provider"], cfg["model"], cfg.get("base_url"))
    except ValueError as e:
        await cl.Message(content=f"⚠️ 配置无效：{e}").send()
        return
    api_key = cfg["api_key"]

    if not _RATE_LIMITER.allow(_client_ip()):
        await cl.Message(content=RATE_LIMIT_MESSAGE).send()
        return

    question = message.content.strip()
    if not question:
        return

    history: list[dict] = cl.user_session.get("history", [])
    history = _token_truncate(history)

    answer_msg = cl.Message(content="")
    await answer_msg.send()

    # 当前气泡缓冲：tool_call 到来时会被快照到「💭 思考」Step 并清空
    bubble_buffer: list[str] = []
    # 历史完整 assistant 文本（含思考），仅写回 history，不展示
    full_assistant_text: list[str] = []
    # 引用来源收集：每次 tool_call 入栈
    sources: list[dict] = []
    worker = await get_worker()
    loop = AgentLoop(anthropic_client=_ANTHROPIC, worker=worker, max_iterations=5)

    log.info("[session=%s] query=%r", _client_ip(), question[:200])

    async def flush_bubble_to_thinking_step():
        """tool_call 到来时调用：把目前为止积累的气泡内容转存到思考 Step，并清空气泡。"""
        if not bubble_buffer:
            return
        thinking_text = "".join(bubble_buffer).strip()
        bubble_buffer.clear()
        if not thinking_text:
            answer_msg.content = ""
            await answer_msg.update()
            return
        async with cl.Step(name="💭 思考", type="run") as s:
            s.output = thinking_text
        # 重置可见气泡
        answer_msg.content = ""
        await answer_msg.update()

    try:
        active_step: cl.Step | None = None
        async for ev in loop.run(question, history, api_key,
                                 model=litellm_model, base_url=api_base):
            if ev["type"] == "text":
                bubble_buffer.append(ev["delta"])
                full_assistant_text.append(ev["delta"])
                await answer_msg.stream_token(ev["delta"])
            elif ev["type"] == "tool_call":
                await flush_bubble_to_thinking_step()
                sources.append({"name": ev["name"], "input": ev["input"]})
                active_step = cl.Step(name=f"🔍 {ev['name']}", type="tool")
                await active_step.__aenter__()
                active_step.input = str(ev["input"])
                await active_step.update()
            elif ev["type"] == "tool_result":
                if active_step:
                    active_step.output = ev["content_preview"]
                    if ev.get("is_error"):
                        active_step.is_error = True
                    await active_step.update()
                    await active_step.__aexit__(None, None, None)
                    active_step = None
            elif ev["type"] == "error":
                banner = _friendly_error(ev["message"]) or f"⚠️ 出错了：{ev['message']}"
                await cl.ErrorMessage(content=banner).send()
    except Exception as e:
        log.exception("Agent loop failure")
        banner = _friendly_error(str(e)) or f"⚠️ 服务暂时不可用：{type(e).__name__}"
        await cl.ErrorMessage(content=banner).send()

    await answer_msg.update()

    # Task C: 答案后追加「📚 引用来源」面板（仅当有检索发生）
    if sources:
        lines = ["| # | 工具 | 关键参数 |", "|---|------|---------|"]
        for i, s in enumerate(sources, 1):
            arg_str = ", ".join(f"`{k}={v}`" for k, v in (s["input"] or {}).items())
            lines.append(f"| {i} | `{s['name']}` | {arg_str or '—'} |")
        sources_md = "\n".join(lines)
        async with cl.Step(name=f"📚 引用来源（{len(sources)} 次检索）", type="run") as s:
            s.output = sources_md

    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": "".join(full_assistant_text)})
    cl.user_session.set("history", history)

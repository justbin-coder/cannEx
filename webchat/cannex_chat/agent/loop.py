"""
Agent Loop: Anthropic tool_use multi-turn orchestration with max 3 iterations.
Yields events: {type: text|tool_call|tool_result|done|error, ...}
"""
import asyncio
import json
import logging
import os
from typing import AsyncIterator

from .tools import TOOLS, TOOL_NAMES
from .prompt_loader import load_system_prompt

log = logging.getLogger(__name__)

MAX_TOKENS = int(os.environ.get("CANNEX_MAX_TOKENS", "8192"))


def _flatten_tool_history(messages: list[dict], original_question: str) -> list[dict]:
    """把 OpenAI 风格的 assistant(tool_calls) + tool messages 扁平化成纯文本对话。

    用于 force final answer 场景：我们需要让模型基于已检索到的真实工具结果给出最终答案，
    但又不希望它继续调用工具。直接传 tool_choice="none" 会导致模型只输出过渡语就停止。
    最稳的做法是把工具调用历史改写成"assistant 的总结"，然后让模型基于这份总结作答。

    返回干净的 messages: [user(原问题), assistant(检索摘要), user(force prompt)]
    """
    tool_call_map: dict[str, dict] = {}  # id -> {name, args}
    # D: 明确标注"外部检索结果"，防止模型把这些当成自有知识放松引用纪律
    timeline: list[str] = [
        "以下是本轮通过工具从外部知识库实际检索到的原始结果（非模型自有知识，"
        "每个 JSON 块均为工具原始返回，未经修改）：\n"
    ]

    for m in messages:
        role = m.get("role")
        if role == "assistant" and m.get("tool_calls"):
            if m.get("content"):
                timeline.append(f"\n（检索过程中的推理：{m['content']}）\n")
            for tc in m["tool_calls"]:
                tool_call_map[tc["id"]] = {
                    "name": tc["function"]["name"],
                    "args": tc["function"]["arguments"],
                }
        elif role == "tool":
            tcid = m.get("tool_call_id", "")
            meta = tool_call_map.get(tcid, {"name": "unknown", "args": "{}"})
            timeline.append(
                f"\n### 外部检索结果：`{meta['name']}({meta['args']})`\n"
                f"```json\n{m.get('content', '')}\n```\n"
            )

    summary = "".join(timeline)
    # C: 反幻觉铁律写入 force prompt，§章节和内容只能来自上方 JSON 原文
    final_prompt = (
        "请基于以上【外部检索结果】，给出完整的最终回答（中文 Markdown）。\n"
        "严格遵守以下铁律，违反任何一条均视为不可接受的输出：\n"
        "1. 不要再调用任何工具，直接给出答案。\n"
        "2. §章节名必须来自本轮 get_document_outline 工具实际返回的标题，"
        "禁止凭记忆或推断编造任何章节号、章节名。\n"
        "3. 每条技术断言必须能在上方 JSON 原文中找到明确依据并标注来源；"
        "在 JSON 原文中找不到依据的断言，一律使用话术"
        "「该细节在当前知识库中信息有限，建议访问昇腾社区官网 "
        "https://www.hiascend.com/document 查阅」，"
        "禁止用预训练知识或推断填补——即使你认为内容是正确的。\n"
        "4. API 名称、参数名、枚举值必须与 JSON 原文完全一致，禁止改写或补全。"
    )

    return [
        {"role": "user", "content": original_question},
        {"role": "assistant", "content": summary},
        {"role": "user", "content": final_prompt},
    ]


class AgentLoop:
    def __init__(self, anthropic_client, worker, max_iterations: int = 5):
        self._client = anthropic_client
        self._worker = worker
        self._max_iter = max_iterations

    async def run(
        self,
        user_message: str,
        history: list[dict],
        api_key: str,
        model: str,
        base_url: str | None = None,
    ) -> AsyncIterator[dict]:
        system = load_system_prompt()
        messages = list(history) + [{"role": "user", "content": user_message}]
        queue: asyncio.Queue = asyncio.Queue()

        async def producer():
            try:
                for iteration in range(self._max_iter):
                    log.info("Agent iter=%d, msgs=%d", iteration, len(messages))
                    full_text, tool_uses, assistant_msg = await self._stream_turn(
                        system=system,
                        messages=messages,
                        tools=TOOLS,
                        api_key=api_key,
                        queue=queue,
                        model=model,
                        base_url=base_url,
                    )
                    messages.append(assistant_msg)

                    if not tool_uses:
                        await queue.put({"type": "done"})
                        return

                    # Execute tools concurrently
                    tool_results = await asyncio.gather(
                        *[self._exec_tool(tu) for tu in tool_uses],
                        return_exceptions=True,
                    )
                    for tu, res in zip(tool_uses, tool_results):
                        await queue.put({"type": "tool_call", "name": tu["name"], "input": tu["input"]})
                        if isinstance(res, Exception):
                            content = json.dumps({"error": str(res)}, ensure_ascii=False)
                            is_error = True
                        else:
                            content = json.dumps(res, ensure_ascii=False)
                            is_error = False
                        await queue.put({"type": "tool_result", "name": tu["name"],
                                         "is_error": is_error, "content_preview": content[:500]})
                        # OpenAI tool message format
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tu["id"],
                            "content": content,
                        })

                # Force final answer: 把 tool_calls/tool history 扁平化成纯文本对话，
                # 不再传 tools 参数，模型自然会给出最终答案而不是过渡语。
                # （之前用 tool_choice="none" 会导致模型只说"让我深入检索..."就停。）
                log.warning("Agent loop reached max_iter=%d, forcing final answer", self._max_iter)
                clean_messages = _flatten_tool_history(messages, user_message)
                log.info("Force final answer: starting stream with flattened history (%d msgs)",
                         len(clean_messages))
                final_text, _, _ = await self._stream_turn(
                    system=system, messages=clean_messages, tools=None,
                    api_key=api_key, queue=queue, model=model, base_url=base_url,
                )
                log.info("Force final answer: completed, text_len=%d", len(final_text))
                await queue.put({"type": "done"})
            except Exception as e:
                log.exception("Agent loop error")
                await queue.put({"type": "error", "message": str(e)})
                await queue.put({"type": "done"})

        task = asyncio.create_task(producer())
        while True:
            ev = await queue.get()
            if ev["type"] == "done":
                break
            yield ev
        await task

    async def _stream_turn(self, system, messages, tools, api_key, queue,
                           model, base_url=None, tool_choice=None):
        full_text = ""
        tool_uses: list[dict] = []

        stream = self._client.create_stream(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
            api_key=api_key,
            tools=tools,
            tool_choice=tool_choice,
            base_url=base_url,
        )
        async for ev in stream:
            t = ev["type"]
            if t == "text_delta":
                full_text += ev["delta"]
                await queue.put({"type": "text", "delta": ev["delta"]})
            elif t == "tool_use_complete":
                tool_uses.append(ev["tool_use"])

        # OpenAI assistant message format. 当有 tool_calls 但无 text 时 content 必须为 None
        # （否则 litellm 转 Anthropic 时会生成空 text block，触发 schema 校验失败）
        assistant_msg: dict = {
            "role": "assistant",
            "content": full_text if full_text else None,
        }
        if tool_uses:
            assistant_msg["tool_calls"] = [
                {
                    "id": tu["id"],
                    "type": "function",
                    "function": {
                        "name": tu["name"],
                        "arguments": json.dumps(tu["input"], ensure_ascii=False),
                    },
                }
                for tu in tool_uses
            ]

        return full_text, tool_uses, assistant_msg

    async def _exec_tool(self, tool_use: dict):
        name = tool_use["name"]
        if name not in TOOL_NAMES:
            raise ValueError(f"Unknown tool: {name}")
        return await self._worker.call(name, tool_use["input"])

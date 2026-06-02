# 多供应商 LLM 配置（BYOK v2）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 webchat 用户登录后自选 LLM 供应商（DeepSeek / OpenAI 兼容端点）、自填 base_url/model/api_key，取消服务端兜底，配置按用户加密持久化到 `cannex.db`。

**Architecture:** 底层 litellm 已供应商无关，agent loop 的流式/工具逻辑零改。改动 = 把 model/base_url 从全局常量改为 per-session 透传（`providers.py` 翻译成 litellm 参数）+ 加密持久化（`llm_config.py`）+ Chainlit 设置面板（`byok.py`）+ app.py 接线。

**Tech Stack:** Python 3.11，pytest（`asyncio_mode=auto`），litellm，cryptography(Fernet)，Chainlit（fork）。

**Spec:** `docs/superpowers/specs/2026-05-30-multi-provider-byok-design.md`

**已校准的依赖契约：**
- 测试从项目根跑，`conftest.py` 已把根 + `lib/` 加入 `sys.path`；webchat 测试 import `webchat.cannex_chat.*`。
- Chainlit `Select(id, label, items={label: value}, initial_value=value)` → 设置更新时回传的是 **value**（即 provider_id），无需反查 label。
- 登录用户：`cl.user_session.get("user")` 返回 `cl.User`，`.identifier` 即 username（见 `auth.py:62`）。auth 关闭（`CANNEX_DISABLE_AUTH=1`）时为 None → 退化为仅会话存储。
- 现有 `loop.run(user_message, history, api_key)` 与 `_stream_turn(system, messages, tools, api_key, queue, tool_choice=None)`（`agent/loop.py:83,158`）。
- 现有 client `create_stream(model, max_tokens, system, messages, api_key, tools=None, tool_choice=None)`（`agent/anthropic_client.py:18`）。

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `webchat/cannex_chat/agent/providers.py` | 供应商注册表 + `resolve()`：用户面概念→litellm 参数（纯函数） | Create |
| `webchat/cannex_chat/agent/llm_config.py` | 配置持久化 + Fernet 加解密（DB IO） | Create |
| `webchat/cannex_chat/agent/anthropic_client.py` | 重命名 `LLMStreamClient` + per-call `base_url` | Modify |
| `webchat/cannex_chat/agent/loop.py` | `run/_stream_turn` 透传 `model`+`base_url`，删全局 `MODEL` | Modify |
| `webchat/cannex_chat/ui/byok.py` | 四控件设置面板 + `validate_settings`(纯) + `save_llm_config` | Modify(重写) |
| `webchat/cannex_chat/app.py` | on_chat_start 载配置、on_message 用配置、无配置引导 | Modify |
| `webchat/cannex_chat/ui/banners.py` | 文案改为多供应商 + 持久化隐私说明 | Modify |
| `webchat/cannex_chat/requirements.txt` | 加 `cryptography` | Modify |
| `deploy/{.env.example,run_local.sh,README.md}` | 补 `CANNEX_CONFIG_SECRET` | Modify |
| `webchat/cannex_chat/tests/test_providers.py` | providers 单测 | Create |
| `webchat/cannex_chat/tests/test_llm_config.py` | llm_config 单测 | Create |
| `webchat/cannex_chat/tests/test_anthropic_client.py` | base_url 透传单测 | Create |
| `webchat/cannex_chat/tests/test_byok.py` | validate_settings 单测 | Create |
| `webchat/cannex_chat/tests/test_loop.py` | 补 model/base_url 透传断言 | Modify |

---

### Task 1: providers.py — 供应商注册表（纯函数）

**Files:**
- Create: `webchat/cannex_chat/agent/providers.py`
- Test: `webchat/cannex_chat/tests/test_providers.py`

- [x] **Step 1: 写失败测试**

```python
# webchat/cannex_chat/tests/test_providers.py
import pytest

from webchat.cannex_chat.agent.providers import PROVIDERS, resolve


def test_registry_has_deepseek_and_openai_compat():
    assert "deepseek" in PROVIDERS
    assert "openai_compat" in PROVIDERS


def test_resolve_deepseek_uses_default_base_url():
    model, api_base = resolve("deepseek", "deepseek-chat")
    assert model == "deepseek/deepseek-chat"
    assert api_base == "https://api.deepseek.com"


def test_resolve_deepseek_allows_base_url_override():
    model, api_base = resolve("deepseek", "deepseek-chat", "https://proxy.example")
    assert model == "deepseek/deepseek-chat"
    assert api_base == "https://proxy.example"


def test_resolve_openai_compat_requires_base_url():
    model, api_base = resolve("openai_compat", "qwen2", "http://localhost:8000/v1")
    assert model == "openai/qwen2"
    assert api_base == "http://localhost:8000/v1"


def test_resolve_openai_compat_without_base_url_raises():
    with pytest.raises(ValueError):
        resolve("openai_compat", "qwen2")


def test_resolve_unknown_provider_raises():
    with pytest.raises(ValueError):
        resolve("grok", "x")


def test_resolve_empty_model_raises():
    with pytest.raises(ValueError):
        resolve("deepseek", "")
```

- [x] **Step 2: 运行验证失败**

Run: `python3 -m pytest webchat/cannex_chat/tests/test_providers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'webchat.cannex_chat.agent.providers'`

- [x] **Step 3: 实现 providers.py**

```python
# webchat/cannex_chat/agent/providers.py
"""供应商注册表：把用户面概念(provider/model/base_url)翻译成 litellm 调用参数。

纯函数、零 IO。litellm 靠 model 前缀路由；通用 OpenAI 兼容端点用 openai/ 前缀 + api_base。
"""

PROVIDERS: dict[str, dict] = {
    "deepseek": {
        "label": "DeepSeek",
        "litellm_prefix": "deepseek",
        "default_base_url": "https://api.deepseek.com",
        "base_url_required": False,
    },
    "openai_compat": {
        "label": "OpenAI 兼容 (自定义端点)",
        "litellm_prefix": "openai",
        "default_base_url": "",
        "base_url_required": True,
    },
}


def resolve(provider: str, model: str, base_url: str | None = None) -> tuple[str, str]:
    """返回 (litellm_model, api_base)。

    - provider 未知 / model 为空 / base_url 必填但缺失 → ValueError。
    - base_url 留空时回落供应商 default_base_url。
    """
    spec = PROVIDERS.get(provider)
    if spec is None:
        raise ValueError(f"unknown provider: {provider!r}")
    if not model:
        raise ValueError("model is required")
    api_base = (base_url or "").strip() or spec["default_base_url"]
    if spec["base_url_required"] and not api_base:
        raise ValueError(f"provider {provider!r} requires base_url")
    return f"{spec['litellm_prefix']}/{model}", api_base
```

- [x] **Step 4: 运行验证通过**

Run: `python3 -m pytest webchat/cannex_chat/tests/test_providers.py -v`
Expected: PASS（7 passed）

- [x] **Step 5: Commit**（若仓库已 git init；否则跳过本步）

```bash
git add webchat/cannex_chat/agent/providers.py webchat/cannex_chat/tests/test_providers.py
git commit -m "feat(webchat): providers.py 供应商注册表 + resolve 路由"
```

---

### Task 2: llm_config.py — 配置持久化 + Fernet 加解密

**Files:**
- Modify: `webchat/cannex_chat/requirements.txt`（加 `cryptography`）
- Create: `webchat/cannex_chat/agent/llm_config.py`
- Test: `webchat/cannex_chat/tests/test_llm_config.py`

- [x] **Step 1: 装依赖 + 写 requirements**

Run: `webchat/cannex_chat/.venv/bin/pip install cryptography`
然后在 `webchat/cannex_chat/requirements.txt` 末尾追加一行：
```
cryptography
```

- [x] **Step 2: 写失败测试**

```python
# webchat/cannex_chat/tests/test_llm_config.py
import importlib

import pytest


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("CANNEX_CONFIG_SECRET", "unit-test-secret")
    mod = importlib.import_module("webchat.cannex_chat.agent.llm_config")
    monkeypatch.setattr(mod, "_DB_PATH", str(tmp_path / "cannex.db"))
    return mod


def test_save_then_load_round_trip(cfg):
    cfg.save_config("alice", "deepseek", "", "deepseek-chat", "sk-secret-123")
    out = cfg.load_config("alice")
    assert out == {"provider": "deepseek", "base_url": "",
                   "model": "deepseek-chat", "api_key": "sk-secret-123"}


def test_load_missing_user_returns_none(cfg):
    assert cfg.load_config("nobody") is None


def test_upsert_overwrites(cfg):
    cfg.save_config("bob", "deepseek", "", "deepseek-chat", "k1")
    cfg.save_config("bob", "openai_compat", "http://x/v1", "qwen", "k2")
    out = cfg.load_config("bob")
    assert out["provider"] == "openai_compat"
    assert out["model"] == "qwen"
    assert out["api_key"] == "k2"


def test_key_is_encrypted_at_rest(cfg):
    import sqlite3
    cfg.save_config("carol", "deepseek", "", "deepseek-chat", "sk-plaintext")
    raw = sqlite3.connect(cfg._DB_PATH).execute(
        "SELECT api_key_enc FROM cannex_llm_config WHERE username='carol'").fetchone()[0]
    assert "sk-plaintext" not in raw


def test_decrypt_failure_returns_none(cfg, monkeypatch):
    cfg.save_config("dave", "deepseek", "", "deepseek-chat", "k")
    # 轮换 secret → 旧密文无法解密
    monkeypatch.setenv("CANNEX_CONFIG_SECRET", "different-secret")
    assert cfg.load_config("dave") is None
```

- [x] **Step 3: 运行验证失败**

Run: `python3 -m pytest webchat/cannex_chat/tests/test_llm_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'webchat.cannex_chat.agent.llm_config'`

- [x] **Step 4: 实现 llm_config.py**

```python
# webchat/cannex_chat/agent/llm_config.py
"""每用户 LLM 配置持久化（SQLite）+ api_key Fernet 加密。

表 cannex_llm_config 与认证表 cannex_users 同库不同表。
加密密钥从 env CANNEX_CONFIG_SECRET 派生（缺失回落 CHAINLIT_AUTH_SECRET）。
⚠️ 轮换该 secret 会使已存 key 无法解密 → load_config 返回 None（按未配置处理）。
"""
from __future__ import annotations

import base64
import hashlib
import os
import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_DB_PATH = os.environ.get("CANNEX_USERS_DB", "/data/cannex.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cannex_llm_config (
    username     TEXT PRIMARY KEY,
    provider     TEXT NOT NULL,
    base_url     TEXT,
    model        TEXT NOT NULL,
    api_key_enc  TEXT NOT NULL,
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _fernet() -> Fernet:
    secret = (os.environ.get("CANNEX_CONFIG_SECRET")
              or os.environ.get("CHAINLIT_AUTH_SECRET") or "")
    if not secret:
        raise RuntimeError("CANNEX_CONFIG_SECRET / CHAINLIT_AUTH_SECRET 未设置，无法加解密")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def _open() -> sqlite3.Connection:
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def save_config(username: str, provider: str, base_url: str,
                model: str, api_key: str) -> None:
    enc = _fernet().encrypt(api_key.encode()).decode()
    conn = _open()
    try:
        conn.execute(
            "INSERT INTO cannex_llm_config(username, provider, base_url, model, api_key_enc) "
            "VALUES(?, ?, ?, ?, ?) "
            "ON CONFLICT(username) DO UPDATE SET "
            "provider=excluded.provider, base_url=excluded.base_url, "
            "model=excluded.model, api_key_enc=excluded.api_key_enc, "
            "updated_at=datetime('now')",
            (username, provider, base_url, model, enc),
        )
        conn.commit()
    finally:
        conn.close()


def load_config(username: str) -> dict | None:
    conn = _open()
    try:
        row = conn.execute(
            "SELECT provider, base_url, model, api_key_enc "
            "FROM cannex_llm_config WHERE username = ?",
            (username,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    provider, base_url, model, enc = row
    try:
        api_key = _fernet().decrypt(enc.encode()).decode()
    except InvalidToken:
        return None
    return {"provider": provider, "base_url": base_url or "",
            "model": model, "api_key": api_key}
```

- [x] **Step 5: 运行验证通过**

Run: `python3 -m pytest webchat/cannex_chat/tests/test_llm_config.py -v`
Expected: PASS（5 passed）

- [x] **Step 6: Commit**（git init 后才执行，下同不再注明）

```bash
git add webchat/cannex_chat/agent/llm_config.py webchat/cannex_chat/tests/test_llm_config.py webchat/cannex_chat/requirements.txt
git commit -m "feat(webchat): llm_config 每用户配置持久化 + Fernet 加密"
```

---

### Task 3: anthropic_client.py — 重命名 LLMStreamClient + per-call base_url

**Files:**
- Modify: `webchat/cannex_chat/agent/anthropic_client.py`
- Test: `webchat/cannex_chat/tests/test_anthropic_client.py`

- [x] **Step 1: 写失败测试**

```python
# webchat/cannex_chat/tests/test_anthropic_client.py
import pytest

import webchat.cannex_chat.agent.anthropic_client as ac


@pytest.mark.asyncio
async def test_create_stream_passes_per_call_base_url_and_model(monkeypatch):
    captured: dict = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)

        async def empty():
            return
            yield  # pragma: no cover  (使函数成为 async generator)

        return empty()

    monkeypatch.setattr(ac.litellm, "acompletion", fake_acompletion)

    client = ac.LLMStreamClient()
    async for _ in client.create_stream(
        model="deepseek/deepseek-chat", max_tokens=16, system="s",
        messages=[{"role": "user", "content": "hi"}], api_key="k",
        base_url="https://api.deepseek.com",
    ):
        pass

    assert captured["model"] == "deepseek/deepseek-chat"
    assert captured["api_base"] == "https://api.deepseek.com"
    assert captured["api_key"] == "k"
```

- [x] **Step 2: 运行验证失败**

Run: `python3 -m pytest webchat/cannex_chat/tests/test_anthropic_client.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'LLMStreamClient'`

- [x] **Step 3: 改实现**

在 `anthropic_client.py`：把类名 `AnthropicStreamClient` 改为 `LLMStreamClient`，并给 `create_stream` 增加 `base_url` 入参。改后头部如下（其余流式解析逻辑不动）：

```python
class LLMStreamClient:
    def __init__(self, base_url: str | None = None):
        self._base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL")

    async def create_stream(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict],
        api_key: str,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        base_url: str | None = None,
    ) -> AsyncIterator[dict]:
        full_messages = [{"role": "system", "content": system}] + messages

        kwargs: dict = dict(
            model=model,
            messages=full_messages,
            max_tokens=max_tokens,
            temperature=0,
            api_key=api_key,
            stream=True,
        )
        effective_base = base_url or self._base_url
        if effective_base:
            kwargs["api_base"] = effective_base
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice

        stream = await litellm.acompletion(**kwargs)
        # ...（以下 chunk 解析逻辑保持原样，不改）
```

- [x] **Step 4: 运行验证通过**

Run: `python3 -m pytest webchat/cannex_chat/tests/test_anthropic_client.py -v`
Expected: PASS（1 passed）

- [x] **Step 5: Commit**

```bash
git add webchat/cannex_chat/agent/anthropic_client.py webchat/cannex_chat/tests/test_anthropic_client.py
git commit -m "refactor(webchat): AnthropicStreamClient→LLMStreamClient + per-call base_url"
```

---

### Task 4: loop.py — 透传 model + base_url（删全局 MODEL）

**Files:**
- Modify: `webchat/cannex_chat/agent/loop.py`
- Test: `webchat/cannex_chat/tests/test_loop.py`（改现有调用 + 加 1 个断言）

- [x] **Step 1: 改测试（先让它们反映新签名）**

把 `test_loop.py` 中三处 `loop.run(...)` 调用补上 `model=`（保持其余不变）：
- `test_loop_terminates_when_no_tool_use`：
  `async for ev in loop.run(user_message="hi", history=[], api_key="sk-test", model="deepseek/deepseek-chat"):`
- `test_loop_executes_tool_then_terminates`：
  `async for ev in loop.run("有几份文档？", [], "sk-test", model="deepseek/deepseek-chat"):`
- `test_loop_caps_at_max_iterations`：
  `async for ev in loop.run("Q", [], "sk-test", model="deepseek/deepseek-chat"):`

并在文件末尾追加透传断言测试：

```python
@pytest.mark.asyncio
async def test_loop_passes_model_and_base_url_to_client():
    """run 收到的 model/base_url 必须原样透传给 create_stream。"""
    captured: dict = {}

    def capture(**kwargs):
        captured.update(kwargs)
        return _mock_stream(text="ok", tool_uses=[])

    fake_anthropic = MagicMock()
    fake_anthropic.create_stream = MagicMock(side_effect=capture)
    worker = FakeWorker({})
    loop = AgentLoop(anthropic_client=fake_anthropic, worker=worker, max_iterations=3)

    async for _ in loop.run("Q", [], "sk-test",
                            model="openai/qwen2", base_url="http://localhost:8000/v1"):
        pass

    assert captured["model"] == "openai/qwen2"
    assert captured["base_url"] == "http://localhost:8000/v1"
```

- [x] **Step 2: 运行验证失败**

Run: `python3 -m pytest webchat/cannex_chat/tests/test_loop.py -v`
Expected: FAIL — `TypeError: run() got an unexpected keyword argument 'model'`

- [x] **Step 3: 改实现**

在 `loop.py`：

1. 删除模块级 `MODEL = os.environ.get("CANNEX_MODEL", "claude-sonnet-4-6")`（第 16 行）。`MAX_TOKENS` 保留。
2. `run` 签名增 `model` + `base_url`：

```python
    async def run(
        self,
        user_message: str,
        history: list[dict],
        api_key: str,
        model: str,
        base_url: str | None = None,
    ) -> AsyncIterator[dict]:
```

3. `producer()` 内两处 `self._stream_turn(...)` 调用都加上 `model=model, base_url=base_url`：

```python
                    full_text, tool_uses, assistant_msg = await self._stream_turn(
                        system=system,
                        messages=messages,
                        tools=TOOLS,
                        api_key=api_key,
                        queue=queue,
                        model=model,
                        base_url=base_url,
                    )
```
```python
                final_text, _, _ = await self._stream_turn(
                    system=system, messages=clean_messages, tools=None,
                    api_key=api_key, queue=queue, model=model, base_url=base_url,
                )
```

4. `_stream_turn` 签名与内部调用：

```python
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
```

- [x] **Step 4: 运行验证通过**

Run: `python3 -m pytest webchat/cannex_chat/tests/test_loop.py -v`
Expected: PASS（全部 passed）

- [x] **Step 5: Commit**

```bash
git add webchat/cannex_chat/agent/loop.py webchat/cannex_chat/tests/test_loop.py
git commit -m "feat(webchat): loop 透传 model/base_url，移除全局 MODEL 常量"
```

---

### Task 5: byok.py — 设置面板 + validate_settings（纯）+ save_llm_config

**Files:**
- Modify: `webchat/cannex_chat/ui/byok.py`（重写）
- Test: `webchat/cannex_chat/tests/test_byok.py`

- [x] **Step 1: 写失败测试（只测纯函数 validate_settings）**

```python
# webchat/cannex_chat/tests/test_byok.py
from webchat.cannex_chat.ui.byok import validate_settings


def test_valid_deepseek_returns_config():
    cfg, err = validate_settings(
        {"provider": "deepseek", "base_url": "", "model": "deepseek-chat", "api_key": "k"},
        existing=None)
    assert err is None
    assert cfg == {"provider": "deepseek", "base_url": "",
                   "model": "deepseek-chat", "api_key": "k"}


def test_openai_compat_without_base_url_errors():
    cfg, err = validate_settings(
        {"provider": "openai_compat", "base_url": "", "model": "qwen", "api_key": "k"},
        existing=None)
    assert cfg is None
    assert "Base URL" in err


def test_missing_model_errors():
    cfg, err = validate_settings(
        {"provider": "deepseek", "base_url": "", "model": "", "api_key": "k"},
        existing=None)
    assert cfg is None
    assert err


def test_empty_key_reuses_existing():
    cfg, err = validate_settings(
        {"provider": "deepseek", "base_url": "", "model": "deepseek-chat", "api_key": ""},
        existing={"provider": "deepseek", "base_url": "", "model": "x", "api_key": "old-key"})
    assert err is None
    assert cfg["api_key"] == "old-key"


def test_empty_key_no_existing_errors():
    cfg, err = validate_settings(
        {"provider": "deepseek", "base_url": "", "model": "deepseek-chat", "api_key": ""},
        existing=None)
    assert cfg is None
    assert err


def test_unknown_provider_errors():
    cfg, err = validate_settings(
        {"provider": "grok", "base_url": "", "model": "m", "api_key": "k"}, existing=None)
    assert cfg is None
    assert err
```

- [x] **Step 2: 运行验证失败**

Run: `python3 -m pytest webchat/cannex_chat/tests/test_byok.py -v`
Expected: FAIL — `ImportError: cannot import name 'validate_settings'`

- [x] **Step 3: 重写 byok.py**

```python
# webchat/cannex_chat/ui/byok.py
"""BYOK v2：用 Chainlit ChatSettings 让用户配置供应商 / base_url / model / key。"""
import chainlit as cl
from chainlit.input_widget import Select, TextInput

from webchat.cannex_chat.agent import llm_config
from webchat.cannex_chat.agent.providers import PROVIDERS


def make_byok_settings(current: dict | None = None) -> cl.ChatSettings:
    current = current or {}
    # items={label: value}，回传的是 value(provider_id)
    items = {spec["label"]: pid for pid, spec in PROVIDERS.items()}
    initial_provider = current.get("provider") or next(iter(PROVIDERS))
    return cl.ChatSettings([
        Select(id="provider", label="🛰️ 供应商", items=items, initial_value=initial_provider),
        TextInput(id="base_url", label="🌐 Base URL（OpenAI 兼容档必填，DeepSeek 可留空）",
                  initial=current.get("base_url") or ""),
        TextInput(id="model", label="🤖 模型名",
                  placeholder="如 deepseek-chat（须支持工具调用，否则检索会失效）",
                  initial=current.get("model") or ""),
        TextInput(id="api_key", label="🔑 API Key",
                  placeholder="已保存则留空沿用，填写则更新", initial=""),
    ])


def validate_settings(settings: dict, existing: dict | None) -> tuple[dict | None, str | None]:
    """纯校验：成功返回 (config, None)，失败返回 (None, error_msg)。

    - provider 必须在 PROVIDERS 内；model 必填；
    - base_url_required 的供应商缺 base_url → 报错；
    - api_key 留空则沿用 existing 的 key，无既存 key → 报错。
    """
    provider = (settings.get("provider") or "").strip()
    if provider not in PROVIDERS:
        return None, "请选择供应商"
    base_url = (settings.get("base_url") or "").strip()
    model = (settings.get("model") or "").strip()
    api_key = (settings.get("api_key") or "").strip()
    if not model:
        return None, "请填写模型名"
    if PROVIDERS[provider]["base_url_required"] and not base_url:
        return None, "该供应商需要填写 Base URL"
    if not api_key:
        if existing and existing.get("api_key"):
            api_key = existing["api_key"]
        else:
            return None, "请填写 API Key"
    return {"provider": provider, "base_url": base_url,
            "model": model, "api_key": api_key}, None


async def save_llm_config(settings: dict, username: str | None) -> dict:
    """校验 + 持久化 + 写会话。返回 {ok, error?}。

    username 为 None（auth 关闭）时仅写会话，不落库。
    """
    existing = cl.user_session.get("llm_config")
    if existing is None and username:
        existing = llm_config.load_config(username)
    cfg, err = validate_settings(settings, existing)
    if err:
        return {"ok": False, "error": err}
    if username:
        llm_config.save_config(username, cfg["provider"], cfg["base_url"],
                               cfg["model"], cfg["api_key"])
    cl.user_session.set("llm_config", cfg)
    return {"ok": True}
```

- [x] **Step 4: 运行验证通过**

Run: `python3 -m pytest webchat/cannex_chat/tests/test_byok.py -v`
Expected: PASS（6 passed）

- [x] **Step 5: Commit**

```bash
git add webchat/cannex_chat/ui/byok.py webchat/cannex_chat/tests/test_byok.py
git commit -m "feat(webchat): BYOK v2 设置面板 + validate_settings + save_llm_config"
```

---

### Task 6: app.py + banners.py 接线（Chainlit 胶水，手工冒烟）

**Files:**
- Modify: `webchat/cannex_chat/app.py`
- Modify: `webchat/cannex_chat/ui/banners.py`

> 说明：app.py 是 Chainlit 装饰器胶水，现有代码也无单测；本 Task 改代码 + 手工冒烟，不写单测（逻辑已在 Task 1/5 的纯函数里覆盖）。

- [x] **Step 1: 改 app.py import**

第 20 行 `from ...anthropic_client import AnthropicStreamClient` 改为：
```python
from webchat.cannex_chat.agent.anthropic_client import LLMStreamClient  # noqa: E402
```
第 33 行 byok import 改为：
```python
from webchat.cannex_chat.ui.byok import make_byok_settings, save_llm_config  # noqa: E402
```
在 import 区补：
```python
from webchat.cannex_chat.agent import llm_config  # noqa: E402
from webchat.cannex_chat.agent.providers import resolve  # noqa: E402
```
第 44 行 `_ANTHROPIC = AnthropicStreamClient()` 改为：
```python
_ANTHROPIC = LLMStreamClient()
```

- [x] **Step 2: 改 on_chat_start（载配置 + 预填面板）**

把 `on_start` 改为：
```python
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
```

- [x] **Step 3: 改 on_settings_update**

```python
@cl.on_settings_update
async def on_settings(settings: dict):
    username = cl.user_session.get("username")
    res = await save_llm_config(settings, username)
    if res["ok"]:
        await cl.Message(content="✅ LLM 配置已保存").send()
    else:
        await cl.Message(content=f"⚠️ {res['error']}").send()
```

- [x] **Step 4: 改 on_message 取配置段**

把第 120-126 行（取 api_key + NO_KEY_PROMPT 那段）替换为：
```python
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
```
并把第 171 行 `loop.run(question, history, api_key)` 改为：
```python
        async for ev in loop.run(question, history, api_key,
                                 model=litellm_model, base_url=api_base):
```

- [x] **Step 5: 改 banners.py 文案**

`WELCOME_BANNER` 末行与隐私段改为多供应商口径；`NO_KEY_PROMPT` 改为：
```python
NO_KEY_PROMPT = """\
🔑 **请先配置大模型**

打开左上角侧边栏 → **Settings** → 选择供应商（DeepSeek / OpenAI 兼容），填写 Base URL（如需）、模型名与 API Key。

⚠️ 模型必须支持工具调用（function calling），否则检索功能无法工作。
"""
```
`WELCOME_BANNER` 的「🔐 隐私」段改为：
```
**🔐 隐私**
- 你的配置（含 API key，加密存储）按账号保存在服务端，重新登录自动沿用
- 仅用于代你向所选供应商发起请求，不作他用
```
并把末行「配置你的 Anthropic API key」改为「选择供应商并配置大模型」。

- [x] **Step 6: 手工冒烟（启动 + 登录 + 配置 + 提问）**

```bash
bash /home/jiazhibin/cannEx/deploy/run_local.sh
```
浏览器开 `http://<本机IP>:8000` → 用 `test/Cannex@2026` 登录 → Settings 选 DeepSeek、填 model=`deepseek-chat`、填 DeepSeek key → 保存应提示「✅ LLM 配置已保存」→ 提一个问题确认能正常检索+回答 → 刷新页面重登，确认 Settings 里 provider/model 已自动回填（key 留空但仍可直接提问）。
Expected: 全流程通；`logs/webchat.log` 无异常堆栈。

- [x] **Step 7: Commit**

```bash
git add webchat/cannex_chat/app.py webchat/cannex_chat/ui/banners.py
git commit -m "feat(webchat): app 接线多供应商配置 + 文案更新"
```

---

### Task 7: deploy 配置 + 全量回归

**Files:**
- Modify: `deploy/.env.example`、`deploy/run_local.sh`、`deploy/README.md`

- [x] **Step 1: deploy/.env.example 补一行**

```
# LLM 配置加密密钥（缺省回落 CHAINLIT_AUTH_SECRET）。轮换会使已存用户 key 失效需重填。
CANNEX_CONFIG_SECRET=
```

- [x] **Step 2: run_local.sh 补 export（可选项，缺省回落 auth secret）**

在 `deploy/run_local.sh` 的 export 区追加（值可与 auth secret 不同；不设则自动回落）：
```bash
# LLM 配置加密密钥；不设则回落 CHAINLIT_AUTH_SECRET。
export CANNEX_CONFIG_SECRET=db07e9611a634ca8f8dc330c8c00889c2097811d4a93c4da3beb6d2c6c3ed133
```

- [x] **Step 3: README「本机实际部署现状」节更新**

在该节的「三个必备环境量」列表补一条 `CANNEX_CONFIG_SECRET`；并把账号表上方说明从「Anthropic key」改为「供应商配置（DeepSeek / OpenAI 兼容，含 key 加密持久化）」。

- [x] **Step 4: 全量回归**

Run: `python3 -m pytest lib/cannex_knowledge/tests/ webchat/cannex_chat/tests/ -q`
Expected: 全 PASS（新增 25 例 + 原有全绿）。

- [x] **Step 5: Commit**

```bash
git add deploy/.env.example deploy/run_local.sh deploy/README.md
git commit -m "docs/deploy: 补 CANNEX_CONFIG_SECRET 与多供应商部署说明"
```

---

## 自审（writing-plans self-review）

- **Spec 覆盖**：§3.1 四控件→Task 5(make_byok_settings)；§3.2 生命周期→Task 6(on_chat_start/settings/message)；§3.3 校验→Task 5(validate_settings)；§4 表+加密→Task 2；§5.1 providers→Task 1；§5.2 llm_config→Task 2；§5.3 改名+base_url→Task 3；§5.4 loop→Task 4；§5.5 app→Task 6；§5.6 byok→Task 5；§5.7 部署→Task 7；§6 测试→各 Task TDD。
- **类型一致**：贯穿四参 `provider/base_url/model/api_key`；`resolve()→(litellm_model, api_base)`；`load_config()/validate_settings()→dict{provider,base_url,model,api_key}|None`；`save_config(username,provider,base_url,model,api_key)`；`loop.run(...,model,base_url=None)`；`create_stream(...,base_url=None)`；`save_llm_config(settings,username)→{ok,error?}` 全程一致。
- **无占位符**：每个改码步骤含完整代码与确切命令；app.py 胶水以手工冒烟替代单测并已说明理由。
- **Git 注记**：本项目当前非 git 仓库；各 Commit 步在 `git init` 后才有效，否则跳过（文件已落盘）。
```

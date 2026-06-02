from types import SimpleNamespace

import pytest

import webchat.cannex_chat.agent.anthropic_client as ac


def _chunk(content=None, tool_calls=None, finish=None):
    """构造一个 litellm 风格的流式 chunk（chunk.choices[0].delta / .finish_reason）。"""
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=delta, finish_reason=finish)
    return SimpleNamespace(choices=[choice])


def _fake_acompletion(chunks, captured=None):
    """返回一个 fake litellm.acompletion，吐出给定 chunks。"""
    async def fake(**kwargs):
        if captured is not None:
            captured.update(kwargs)

        async def gen():
            for c in chunks:
                yield c

        return gen()

    return fake


@pytest.mark.asyncio
async def test_create_stream_passes_model_base_url_and_timeout(monkeypatch):
    captured: dict = {}
    chunks = [_chunk(content="hi", finish=None), _chunk(content=None, finish="stop")]
    monkeypatch.setattr(ac.litellm, "acompletion", _fake_acompletion(chunks, captured))

    out = []
    client = ac.LLMStreamClient()
    async for ev in client.create_stream(
        model="deepseek/deepseek-chat", max_tokens=16, system="s",
        messages=[{"role": "user", "content": "hi"}], api_key="k",
        base_url="https://api.deepseek.com",
    ):
        out.append(ev)

    assert captured["model"] == "deepseek/deepseek-chat"
    assert captured["api_base"] == "https://api.deepseek.com"
    assert captured["api_key"] == "k"
    # 修复 1：每次请求都带 timeout，防止连接后无响应永久挂起
    assert captured["timeout"] == ac.LLM_REQUEST_TIMEOUT
    assert out == [{"type": "text_delta", "delta": "hi"}]


@pytest.mark.asyncio
async def test_empty_response_raises_stream_guard(monkeypatch):
    """端点只返回一个空 stop（如 base_url 漏 /v1 时打到 HTML 首页）→ 明确报错，不静默空回答。"""
    chunks = [_chunk(content=None, finish="stop")]
    monkeypatch.setattr(ac.litellm, "acompletion", _fake_acompletion(chunks))

    client = ac.LLMStreamClient()
    with pytest.raises(ac.StreamGuardError) as ei:
        async for _ in client.create_stream(
            model="openai/claude-sonnet-4-6", max_tokens=8, system="s",
            messages=[{"role": "user", "content": "hi"}], api_key="k",
            base_url="https://how88.top",
        ):
            pass
    assert "/v1" in str(ei.value)


@pytest.mark.asyncio
async def test_output_overflow_raises_stream_guard(monkeypatch):
    """端点忽略 max_tokens 持续吐字 → 累计字符超上限熔断。"""
    monkeypatch.setattr(ac, "STREAM_MAX_CHARS", 5)
    chunks = [_chunk(content="aaaaaaaaaa", finish=None)]  # 10 > 5
    monkeypatch.setattr(ac.litellm, "acompletion", _fake_acompletion(chunks))

    client = ac.LLMStreamClient()
    with pytest.raises(ac.StreamGuardError):
        async for _ in client.create_stream(
            model="openai/x", max_tokens=9999, system="s",
            messages=[{"role": "user", "content": "hi"}], api_key="k",
            base_url="http://x/v1",
        ):
            pass


@pytest.mark.asyncio
async def test_wall_timeout_raises_stream_guard(monkeypatch):
    """流式总时长超限（端点持续吐流不停）→ 熔断。"""
    monkeypatch.setattr(ac, "STREAM_WALL_TIMEOUT", -1)  # 任意 chunk 即视为已超时
    chunks = [_chunk(content="hi", finish=None)]
    monkeypatch.setattr(ac.litellm, "acompletion", _fake_acompletion(chunks))

    client = ac.LLMStreamClient()
    with pytest.raises(ac.StreamGuardError):
        async for _ in client.create_stream(
            model="openai/x", max_tokens=8, system="s",
            messages=[{"role": "user", "content": "hi"}], api_key="k",
            base_url="http://x/v1",
        ):
            pass


@pytest.mark.asyncio
async def test_normal_tool_call_stream_not_guarded(monkeypatch):
    """正常的工具调用流（有 tool_calls）不应被空响应熔断误伤。"""
    tc = SimpleNamespace(index=0, id="call_1",
                         function=SimpleNamespace(name="list_known_resources", arguments="{}"))
    chunks = [
        _chunk(content=None, tool_calls=[tc], finish=None),
        _chunk(content=None, tool_calls=None, finish="tool_calls"),
    ]
    monkeypatch.setattr(ac.litellm, "acompletion", _fake_acompletion(chunks))

    out = []
    client = ac.LLMStreamClient()
    async for ev in client.create_stream(
        model="openai/x", max_tokens=8, system="s",
        messages=[{"role": "user", "content": "hi"}], api_key="k",
        base_url="http://x/v1",
    ):
        out.append(ev)

    assert any(e["type"] == "tool_use_complete" for e in out)

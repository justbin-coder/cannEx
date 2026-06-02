from unittest.mock import AsyncMock, MagicMock

import pytest

from webchat.cannex_chat.agent.loop import AgentLoop, _flatten_tool_history


class FakeWorker:
    def __init__(self, returns: dict):
        self.returns = returns
        self.calls: list[tuple] = []

    async def call(self, method, params):
        self.calls.append((method, params))
        if method in self.returns:
            return self.returns[method]
        raise RuntimeError(f"no mock for {method}")


def _mock_stream(text: str, tool_uses: list[dict]):
    """生成一个 async iterator 模拟 anthropic streaming"""
    async def gen():
        if text:
            yield {"type": "text_delta", "delta": text}
        for tu in tool_uses:
            yield {"type": "tool_use_complete", "tool_use": tu}
    return gen()


@pytest.mark.asyncio
async def test_loop_terminates_when_no_tool_use():
    """Claude 直接给出文本答案，无 tool_use → 立即终止"""
    fake_anthropic = MagicMock()
    fake_anthropic.create_stream = MagicMock(return_value=_mock_stream(text="这是直接答案", tool_uses=[]))
    worker = FakeWorker({})
    loop = AgentLoop(anthropic_client=fake_anthropic, worker=worker, max_iterations=3)

    chunks: list[str] = []
    tool_events: list[dict] = []
    async for ev in loop.run(user_message="hi", history=[], api_key="sk-test", model="deepseek/deepseek-chat"):
        if ev["type"] == "text":
            chunks.append(ev["delta"])
        elif ev["type"] == "tool_call":
            tool_events.append(ev)

    assert "".join(chunks) == "这是直接答案"
    assert tool_events == []
    assert worker.calls == []


@pytest.mark.asyncio
async def test_loop_executes_tool_then_terminates():
    """第 1 轮 tool_use → 调 worker → 第 2 轮文本答案"""
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _mock_stream(text="", tool_uses=[{"id": "tu1", "name": "list_known_resources", "input": {}}])
        return _mock_stream(text="共有 2 份文档", tool_uses=[])

    fake_anthropic = MagicMock()
    fake_anthropic.create_stream = MagicMock(side_effect=side_effect)
    worker = FakeWorker({"list_known_resources": {"docs": [{}, {}], "repos": []}})
    loop = AgentLoop(anthropic_client=fake_anthropic, worker=worker, max_iterations=3)

    tool_events: list[dict] = []
    async for ev in loop.run("有几份文档？", [], "sk-test", model="deepseek/deepseek-chat"):
        if ev["type"] == "tool_call":
            tool_events.append(ev)

    assert len(worker.calls) == 1
    assert worker.calls[0][0] == "list_known_resources"
    assert len(tool_events) == 1


@pytest.mark.asyncio
async def test_loop_caps_at_max_iterations():
    """连续 3 轮都 tool_use → 第 4 轮强制终答"""
    call_count = 0
    tool_use_block = {"id": "x", "name": "list_known_resources", "input": {}}

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 3:
            return _mock_stream("", [tool_use_block])
        return _mock_stream("最终答案", [])

    fake_anthropic = MagicMock()
    fake_anthropic.create_stream = MagicMock(side_effect=side_effect)
    worker = FakeWorker({"list_known_resources": {"docs": [], "repos": []}})
    loop = AgentLoop(anthropic_client=fake_anthropic, worker=worker, max_iterations=3)

    chunks: list[str] = []
    async for ev in loop.run("Q", [], "sk-test", model="deepseek/deepseek-chat"):
        if ev["type"] == "text":
            chunks.append(ev["delta"])

    assert len(worker.calls) == 3
    assert "最终答案" in "".join(chunks)
    assert call_count == 4


def _make_tool_history(tool_name: str, tool_result: str) -> list[dict]:
    """构造一条完整的 tool_call + tool result 消息历史。"""
    return [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "tc1",
                    "type": "function",
                    "function": {"name": tool_name, "arguments": '{"doc_name": "test"}'},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "tc1",
            "content": tool_result,
        },
    ]


def test_flatten_preserves_verbatim_tool_result():
    """_flatten_tool_history 必须原样保留工具返回的 JSON 原文，不得裁剪。"""
    raw_result = '{"pages": [{"page": 42, "content": "SSBuffer 是新增存储单元"}]}'
    messages = _make_tool_history("read_document_pages", raw_result)

    result = _flatten_tool_history(messages, original_question="内存层级有哪几种？")

    # assistant 消息（index 1）里应包含原始 JSON
    assistant_content = result[1]["content"]
    assert raw_result in assistant_content, (
        "工具返回的原始 JSON 必须逐字保留在扁平化结果中"
    )


def test_flatten_force_prompt_contains_anti_hallucination_clauses():
    """force prompt 必须包含反幻觉铁律的关键条款。"""
    messages = _make_tool_history("get_document_outline", '{"outline": []}')

    result = _flatten_tool_history(messages, original_question="内存层级有哪几种？")

    force_prompt = result[2]["content"]
    assert "禁止" in force_prompt, "force prompt 必须包含明确的禁止性约束"
    assert "预训练" in force_prompt, "force prompt 必须禁止用预训练知识填补"
    assert "章节名" in force_prompt, "force prompt 必须约束章节名来源"
    assert "外部检索结果" in result[1]["content"], (
        "assistant 摘要必须标注'外部检索结果'，不得将检索内容包装成模型自有知识"
    )


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

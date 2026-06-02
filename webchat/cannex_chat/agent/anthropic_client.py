"""LLM 流式客户端封装（litellm 实现，兼容 bytego 等第三方代理）。"""
import json
import logging
import os
import time
from typing import AsyncIterator

import litellm

litellm.drop_params = True

log = logging.getLogger(__name__)

# —— BYOK 安全熔断 ——
# 用户可自带任意 LLM 端点，端点的异常行为（无限吐流、忽略 max_tokens、连接后挂起）
# 会直接烧 token 并卡死前端。以下三道防线把这种风险限制在可控范围内。
LLM_REQUEST_TIMEOUT = float(os.environ.get("CANNEX_LLM_TIMEOUT", "120"))     # litellm 连接/读取超时(秒)
STREAM_WALL_TIMEOUT = float(os.environ.get("CANNEX_STREAM_TIMEOUT", "180"))  # 单次流式总时长上限(秒)
STREAM_MAX_CHARS = int(os.environ.get("CANNEX_STREAM_MAX_CHARS", "200000"))  # 单次流式累计输出字符上限


class StreamGuardError(RuntimeError):
    """流式响应触发安全熔断（连接超时 / 总时长超限 / 输出超量 / 空响应）。"""


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
            timeout=LLM_REQUEST_TIMEOUT,  # 防连接后无响应永久挂起
        )
        effective_base = base_url or self._base_url
        if effective_base:
            kwargs["api_base"] = effective_base
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice

        stream = await litellm.acompletion(**kwargs)

        current_tool_calls: dict[int, dict] = {}
        start = time.monotonic()
        total_chars = 0
        produced = False  # 是否产生过任何有效输出（content 或 tool_call）

        async for chunk in stream:
            # 熔断 1：流式总时长（防端点持续吐流不停）
            if time.monotonic() - start > STREAM_WALL_TIMEOUT:
                raise StreamGuardError(
                    f"LLM 流式响应超过 {STREAM_WALL_TIMEOUT:.0f}s 仍未结束，已中断"
                    "（端点可能异常或在无限输出）。"
                )

            delta = chunk.choices[0].delta

            # text delta
            if delta.content:
                produced = True
                total_chars += len(delta.content)
                # 熔断 2：累计输出量（防端点忽略 max_tokens）
                if total_chars > STREAM_MAX_CHARS:
                    raise StreamGuardError(
                        f"LLM 输出已超过 {STREAM_MAX_CHARS} 字符上限，已中断"
                        "（端点可能忽略了 max_tokens）。"
                    )
                yield {"type": "text_delta", "delta": delta.content}

            # tool call delta
            if delta.tool_calls:
                produced = True
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in current_tool_calls:
                        current_tool_calls[idx] = {
                            "id": tc.id or "",
                            "name": tc.function.name or "" if tc.function else "",
                            "arguments": "",
                        }
                    if tc.id:
                        current_tool_calls[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            current_tool_calls[idx]["name"] = tc.function.name
                        if tc.function.arguments:
                            current_tool_calls[idx]["arguments"] += tc.function.arguments

            finish = chunk.choices[0].finish_reason
            if finish in ("tool_calls", "stop") and current_tool_calls:
                for tc in current_tool_calls.values():
                    try:
                        input_data = json.loads(tc["arguments"]) if tc["arguments"] else {}
                    except json.JSONDecodeError:
                        log.warning(
                            "Tool call '%s' had unparseable arguments: %r",
                            tc["name"], tc["arguments"],
                        )
                        input_data = {}
                    yield {
                        "type": "tool_use_complete",
                        "tool_use": {
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": input_data,
                        },
                    }
                current_tool_calls = {}

        # 熔断 3：完全空响应。端点返回了非 LLM-API 内容（如 base_url 漏 /v1 时打到网关首页 HTML，
        # 被 litellm 解析成一个空 stop chunk），否则 agent 会静默给出空白回答。明确报错指引用户。
        if not produced:
            raise StreamGuardError(
                "端点没有返回任何内容——HTTP 响应可能不是有效的 LLM API。"
                "请核对 Base URL 是否与供应商文档完全一致"
                "（不同供应商路径后缀不同：有的是 /v1，有的是 /v4，有的无后缀）。"
            )


# 向后兼容别名；Task 6 完成后删除
AnthropicStreamClient = LLMStreamClient

from webchat.cannex_chat.agent.tools import TOOLS, TOOL_NAMES


def test_tools_count():
    assert len(TOOLS) == 18  # 15 + 2 新增 + 1 lookup_doc_api


def test_tool_names():
    assert "query_code_repo" not in TOOL_NAMES
    assert "lookup_code_symbol" in TOOL_NAMES
    assert "list_known_resources" in TOOL_NAMES
    assert "query_documentation" not in TOOL_NAMES
    # Phase B 新增
    assert "search_code_symbol" in TOOL_NAMES
    assert "find_code_callers" in TOOL_NAMES
    assert "analyze_code_impact" in TOOL_NAMES
    assert "explore_code_symbols" in TOOL_NAMES
    # 2026-05-29 新增
    assert "get_operator_call_chain" in TOOL_NAMES
    assert "get_change_impact_surface" in TOOL_NAMES
    # 2026-06-03 新增
    assert "lookup_doc_api" in TOOL_NAMES


def test_each_tool_is_openai_function_format():
    """喂给 litellm 的 tools 必须是合法 OpenAI 格式（function 嵌套 + parameters）。

    litellm 的输入契约是 OpenAI 格式；anthropic 风格的顶层 input_schema 会被
    透传给 OpenAI 兼容端点并触发 `'name' is a required property - 'tools.*.function'`。
    """
    for t in TOOLS:
        assert t.get("type") == "function", f"tool missing type=function: {t}"
        fn = t.get("function")
        assert isinstance(fn, dict), f"tool missing function object: {t}"
        assert isinstance(fn.get("name"), str) and fn["name"], f"function.name missing: {t}"
        assert isinstance(fn.get("description"), str) and fn["description"], \
            f"function.description missing: {fn.get('name')}"
        params = fn.get("parameters")
        assert isinstance(params, dict) and params.get("type") == "object", \
            f"function.parameters must be a JSON-Schema object: {fn.get('name')}"
        # 不得残留 anthropic 顶层字段
        assert "input_schema" not in t, f"leftover anthropic input_schema: {t}"
        assert "name" not in t, f"leftover anthropic top-level name: {t}"


def test_list_known_resources_has_empty_properties():
    t = next(t for t in TOOLS if t["function"]["name"] == "list_known_resources")
    assert t["function"]["parameters"]["properties"] == {}

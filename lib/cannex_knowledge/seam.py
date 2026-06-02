"""源码接缝(seam)正则检测：识别图谱会失明的宏调用 / 模板实例化点。

纯函数、零依赖。供 retriever_repo.api_call_chain 在 lib 层零 LLM token 预标接缝。
检测 = 语法启发式，不保证零误报；agent 读 span 时做语义确认。
"""
import re

# 全大写标识符(>=3字符) 紧跟 ( ：CANN 宏调用的强信号
_MACRO_CALL = re.compile(r"\b([A-Z][A-Z0-9_]{2,})\s*\(")
# 模板实例化调用：Foo<...>::Bar
_TEMPLATE_CALL = re.compile(r"\b([A-Za-z_]\w*\s*<[^;{}\n]*>\s*::\s*\w+)")
# 模板分发关键字（CANN arch35 双核分离常用）
_TEMPLATE_KEYWORDS = ("std::conditional", "std::enable_if")
# 全大写但非宏的常见误报
_MACRO_FALSE_POSITIVES = frozenset({"NULL", "TRUE", "FALSE", "AIC", "AIV"})


def detect_seams(source: str) -> list[dict]:
    """扫描源码片段，返回去重后的接缝列表 [{kind, token}]。kind ∈ {macro, template}。"""
    seams: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def _add(kind: str, token: str):
        key = (kind, token)
        if key not in seen:
            seen.add(key)
            seams.append({"kind": kind, "token": token})

    for m in _MACRO_CALL.finditer(source):
        name = m.group(1)
        if name not in _MACRO_FALSE_POSITIVES:
            _add("macro", name)
    for m in _TEMPLATE_CALL.finditer(source):
        _add("template", re.sub(r"\s+", "", m.group(1)))
    for kw in _TEMPLATE_KEYWORDS:
        if kw in source:
            _add("template", kw)
    return seams

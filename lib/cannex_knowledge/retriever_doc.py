"""CannEx 文档数据访问层（纯查询，无 prompt/无策略）。

source_type 规则：
  - "original" : 原文抽取（直接给用户）
  - "metadata" : 元信息（来自 _meta.json，非原文）
"""
import json
import re
from pathlib import Path

from .paths import WORKSPACE, META_FILE


def _normalize_doc_name(name: str) -> str:
    """清理 PDF 文件名，得到适合展示给用户的文档逻辑名。
    例：'CANN社区版 9.0.0 Ascend C算子开发指南 技术部分 01_trimmed.pdf'
       → 'CANN社区版 9.0.0 Ascend C算子开发指南 技术部分'
    """
    name = re.sub(r"\.pdf$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[_-]trimmed$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+\d{2}$", "", name)  # 末尾两位编号（如 "01"）
    return name.strip()


def load_meta() -> dict:
    if not META_FILE.exists():
        raise SystemExit(f"_meta.json 不存在: {META_FILE}")
    with open(META_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_doc(meta: dict, key: str) -> dict:
    docs = meta.get("docs", [])
    for d in docs:
        if d["doc_id"] == key:
            return d
    matches = [d for d in docs if key in d.get("doc_name", "")]
    if not matches:
        avail = "\n".join(f"  - {d['doc_name']}" for d in docs)
        raise SystemExit(f"未找到文档 '{key}'\n可用文档:\n{avail}")
    if len(matches) > 1:
        names = "\n".join(f"  - {d['doc_name']}" for d in matches)
        raise SystemExit(f"'{key}' 匹配多个文档:\n{names}")
    return matches[0]


def load_doc_json(doc_entry: dict) -> dict:
    path = WORKSPACE / doc_entry["path"]
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_pages(spec: str) -> set:
    out = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return out


def _deepest_path_for_page(nodes: list, page: int, path: list) -> list | None:
    """返回包含指定页的最深 ToC 节点的标题路径（root→leaf）。
    用于把"读了哪些页"反查成"属于哪个章节路径"，供 LLM 引用时还原目录面包屑。

    注意：PageIndex 树里非叶子节点的 [start_index, end_index] 往往只是其标题所在页
    （start==end），并不覆盖整棵子树；真实页跨度只落在叶子节点上。因此不能"父范围不含
    页就剪枝"，必须遍历全树，取自身范围包含该页的最深节点，路径由递归累积的祖先标题构成。
    """
    best: list | None = None

    def rec(ns: list, cur_path: list) -> None:
        nonlocal best
        for n in ns:
            here = cur_path + [n.get("title", "")]
            s, e = n.get("start_index"), n.get("end_index")
            if s is not None and e is not None and s <= page <= e:
                if best is None or len(here) > len(best):
                    best = here
            rec(n.get("nodes") or [], here)

    rec(nodes, path)
    return best


def _fmt_page_ranges(pages: list) -> str:
    """把离散页号压成紧凑区间：[144,145,146,150] → '144-146,150'。"""
    pages = sorted(set(pages))
    if not pages:
        return ""
    parts, start, prev = [], pages[0], pages[0]
    for p in pages[1:]:
        if p == prev + 1:
            prev = p
            continue
        parts.append(f"{start}-{prev}" if start != prev else f"{start}")
        start = prev = p
    parts.append(f"{start}-{prev}" if start != prev else f"{start}")
    return ",".join(parts)


def _page_breadcrumbs(structure: list, wanted: set) -> list:
    """对一组页号反查目录面包屑路径，按路径聚合。
    返回 [{"path": "编程指南 > 硬件实现 > 基本架构", "pages": "144-152"}, ...]
    供 LLM 引用时照抄 path，避免凭 outline 记忆手工拼接出错。
    """
    crumbs: dict[tuple, list] = {}
    for pg in sorted(wanted):
        p = _deepest_path_for_page(structure, pg, [])
        if p:
            crumbs.setdefault(tuple(p), []).append(pg)
    return [
        {"path": " > ".join(k), "pages": _fmt_page_ranges(v)}
        for k, v in crumbs.items()
    ]


def api_list() -> list:
    """返回文档清单，含 doc_description（来自 PageIndex 离线建树）作为 LLM 选文档的依据。"""
    meta = load_meta()
    out = []
    for d in meta.get("docs", []):
        entry = {
            "doc_id": d["doc_id"],
            "doc_name": d["doc_name"],
            "category": d.get("category", ""),
            "pages": d.get("pages", 0),
            "priority": d.get("priority", ""),
        }
        try:
            doc_json = load_doc_json(d)
            entry["doc_description"] = doc_json.get("doc_description", "")
        except Exception:
            entry["doc_description"] = ""
        out.append(entry)
    return out


def api_outline(name_or_id: str, max_depth: int = 3) -> dict:
    """返回文档的章节大纲（ToC）。
    用于让模型先看目录决定要读哪几页。
    max_depth 限制递归深度避免回包过大。
    返回 {"doc_name", "outline": [{"title", "start_index", "end_index", "nodes": [...]}, ...]}
    """
    meta = load_meta()
    d = resolve_doc(meta, name_or_id)
    doc = load_doc_json(d)

    def _trim(node: dict, depth: int) -> dict:
        out = {
            "title": node.get("title", ""),
            "summary": node.get("summary", ""),  # LLM 推理燃料，不可省略
            "start_index": node.get("start_index"),
            "end_index": node.get("end_index"),
        }
        children = node.get("nodes", [])
        if children and depth < max_depth:
            out["nodes"] = [_trim(c, depth + 1) for c in children]
        elif children:
            out["truncated_children"] = len(children)
        return out

    return {
        "doc_name": _normalize_doc_name(d["doc_name"]),
        "outline": [_trim(n, 1) for n in doc.get("structure", [])],
    }


def api_meta(name_or_id: str) -> dict:
    """返回单文档元数据（含 doc_description）。
    对应 PageIndex 官方范式中的 get_document(doc_id) ——
    tree-walk 第一步：LLM 看 doc_description 决定要不要展开 outline。
    """
    meta = load_meta()
    entry = resolve_doc(meta, name_or_id)
    doc = load_doc_json(entry)
    return {
        "doc_id": entry["doc_id"],
        "doc_name": entry["doc_name"],
        "category": entry.get("category", ""),
        "audience": entry.get("audience", ""),
        "pages": entry.get("pages", 0),
        "priority": entry.get("priority", ""),
        "doc_description": doc.get("doc_description", ""),
    }


def api_pages(name_or_id: str, page_range: str) -> dict:
    """读取指定页范围的原文。
    page_range 格式："5-7" / "3,8" / "12"。
    返回 {"doc_name", "pages": [{"page", "content"}, ...]}
    """
    meta = load_meta()
    d = resolve_doc(meta, name_or_id)
    doc = load_doc_json(d)
    pages = doc.get("pages") or []
    if not pages:
        return {"doc_name": _normalize_doc_name(d["doc_name"]), "pages": [], "error": "该文档无可用页面正文"}

    wanted = parse_pages(page_range)
    out = []
    for p in pages:
        if p.get("page") in wanted:
            out.append({"page": p["page"], "content": p.get("content", "")})

    return {
        "doc_name": _normalize_doc_name(d["doc_name"]),
        "page_range": page_range,
        "pages": out,
        "breadcrumbs": _page_breadcrumbs(doc.get("structure", []), wanted),
    }

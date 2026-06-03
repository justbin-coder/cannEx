#!/usr/bin/env python3
"""
build_api_ref.py — 零 LLM 的 API 参考文档构建器

用 PyMuPDF 提取 PDF 原生 TOC + 逐页文本，生成与 PageIndex 同 schema 的 JSON + api_index。
适用于 docs.yaml 中 build_mode=api_ref 的文档（API 参考类，标题自描述，不需要 LLM summary）。
"""
import json
import re
import uuid
from pathlib import Path

# ── 章节号剥离 ────────────────────────────────────────────────────────────
_SECTION_NUM_RE = re.compile(r"^[\d]+(?:\.[\d]+)*\s+")


def extract_api_name(title: str) -> str:
    """从 TOC 标题提取 API 名称：去掉章节号前缀（如 '2.2.1.8 GetSize' → 'GetSize'）。"""
    return _SECTION_NUM_RE.sub("", title).strip() or title.strip()


# ── TOC → PageIndex 兼容 structure 树 ────────────────────────────────────
def toc_to_structure(toc: list[tuple[int, str, int]], total_pages: int) -> list[dict]:
    """将 PyMuPDF get_toc() 输出转换为 PageIndex 兼容的嵌套 structure 树。

    toc: [(level, title, page), ...]  level 从 1 开始
    total_pages: PDF 总页数，用于计算最后一个条目的 end_index
    """
    if not toc:
        return []

    # 先为每个条目计算 end_index（下一个同级或更高级条目的 page - 1）
    entries = []
    for i, (level, title, page) in enumerate(toc):
        end = total_pages  # 默认到最后一页
        for j in range(i + 1, len(toc)):
            if toc[j][0] <= level:
                end = toc[j][2] - 1
                break
        entries.append({"level": level, "title": title, "start": page, "end": end})

    # 递归构建嵌套树
    node_counter = 0

    def build(items: list[dict], parent_level: int) -> list[dict]:
        nonlocal node_counter
        nodes = []
        i = 0
        while i < len(items):
            item = items[i]
            if item["level"] <= parent_level:
                break
            if item["level"] == parent_level + 1:
                # 收集属于此节点的所有子条目
                children_items = []
                j = i + 1
                while j < len(items) and items[j]["level"] > parent_level + 1:
                    children_items.append(items[j])
                    j += 1
                node = {
                    "title": item["title"],
                    "node_id": f"{node_counter:04d}",
                    "start_index": item["start"],
                    "end_index": item["end"],
                    "summary": "",
                }
                node_counter += 1
                children = build(children_items, parent_level + 1)
                if children:
                    node["nodes"] = children
                nodes.append(node)
                i = j
            else:
                i += 1
        return nodes

    return build(entries, 0)


# ── api_index 构建 ────────────────────────────────────────────────────────
def build_api_index(structure: list[dict], prefix: str = "") -> dict[str, dict]:
    """遍历 structure 树的叶子节点，构建 {api_name: {pages, section}} 倒排索引。"""
    index: dict[str, dict] = {}

    def walk(nodes: list[dict], path: str):
        for node in nodes:
            title = node.get("title", "")
            api_name = extract_api_name(title)
            current_path = f"{path} > {api_name}" if path else api_name
            children = node.get("nodes", [])
            if children:
                walk(children, current_path)
            else:
                # 叶子节点 → 进入索引
                s, e = node.get("start_index"), node.get("end_index")
                if s is None or e is None:
                    continue  # skip malformed TOC entry
                if api_name in index:
                    # 同名 API（重载）：合并页范围
                    existing = index[api_name]
                    existing["pages"] = [
                        min(existing["pages"][0], s),
                        max(existing["pages"][1], e),
                    ]
                else:
                    index[api_name] = {
                        "pages": [s, e],
                        "section": current_path,
                    }

    walk(structure, prefix)
    return index


# ── PDF → JSON 完整构建 ──────────────────────────────────────────────────
def build_one(pdf_path: str, doc_description: str = "") -> dict:
    """读取 PDF，返回 PageIndex 兼容的完整 JSON dict（含 api_index）。

    依赖 PyMuPDF，仅在此函数内 import，使纯函数部分可独立测试。
    """
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    # 提取 TOC
    toc = doc.get_toc()

    # 提取逐页文本
    pages = []
    for i in range(total_pages):
        page = doc[i]
        pages.append({"page": i + 1, "content": page.get_text()})

    doc.close()

    # 构建 structure 树
    structure = toc_to_structure(toc, total_pages)

    # 构建 api_index
    api_index = build_api_index(structure)

    return {
        "id": str(uuid.uuid4()),
        "type": "pdf",
        "path": str(pdf_path),
        "doc_name": Path(pdf_path).name,
        "doc_description": doc_description or f"API 参考文档，共 {total_pages} 页",
        "page_count": total_pages,
        "structure": structure,
        "pages": pages,
        "api_index": api_index,
    }

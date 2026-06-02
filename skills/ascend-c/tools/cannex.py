#!/usr/bin/env python3
"""
CannEx workspace 查询助手

供 Skill 使用，避免把整个 doc JSON（含全部页面）加载到 LLM 上下文。

Usage:
  cannex.py list                          # 列出所有已索引文档
  cannex.py meta <name_or_id>             # 文档元信息（页数、描述）
  cannex.py structure <name_or_id>        # 文档树结构（不含页面正文）
  cannex.py pages <name_or_id> <range>    # 取指定页面正文，range 如 "5-7" / "3,8" / "12"

name_or_id 支持：
  - 完整 doc_id (UUID)
  - doc_name 中的关键字（模糊匹配，如 "算子开发指南"）
"""
import sys
import json
from pathlib import Path

import os
WORKSPACE = Path(os.environ.get("CANNEX_ROOT") or Path(__file__).resolve().parents[3]) / "workspace"
DOCS_DIR = WORKSPACE / "docs"
META_FILE = WORKSPACE / "_meta.json"


def load_meta() -> list[dict]:
    """返回 _meta.json 中 docs 列表，每项包含 doc_id / doc_name / pages / path 等字段。"""
    if not META_FILE.exists():
        return []
    data = json.loads(META_FILE.read_text(encoding="utf-8"))
    return data.get("docs", [])


def resolve_entry(docs: list[dict], key: str) -> dict:
    """支持 doc_id 精确匹配或 doc_name 关键字模糊匹配，返回 meta 条目。"""
    exact = [d for d in docs if d.get("doc_id") == key]
    if exact:
        return exact[0]
    matches = [d for d in docs if key in d.get("doc_name", "")]
    if not matches:
        names = "\n".join(f"  - {d.get('doc_name', d.get('doc_id'))}" for d in docs)
        raise SystemExit(f"未找到文档 '{key}'\n可用文档:\n{names}")
    if len(matches) > 1:
        names = "\n".join(f"  - {d.get('doc_name')}" for d in matches)
        raise SystemExit(f"'{key}' 匹配多个文档，请更精确:\n{names}")
    return matches[0]


def load_full_doc(entry: dict) -> dict:
    """根据 meta 条目中的 path 字段加载完整 doc JSON。"""
    rel_path = entry.get("path")
    if rel_path:
        path = WORKSPACE / rel_path
    else:
        path = DOCS_DIR / f"{entry['doc_id']}.json"
    if not path.exists():
        raise SystemExit(f"文档文件不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def parse_pages(spec: str) -> list[int]:
    """解析 '5-7' / '3,8' / '12' 为页码列表。"""
    out = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return sorted(set(out))


def cmd_list():
    docs = load_meta()
    if not docs:
        print("workspace 中暂无文档。先用 build/build_docs.py 建树。")
        return
    print(f"workspace: {WORKSPACE}\n")
    print(f"{'doc_name':<60}  {'pages':>6}  doc_id")
    print("-" * 100)
    for d in docs:
        name = d.get("doc_name", "?")
        pages = d.get("pages", "?")
        did = d.get("doc_id", "?")
        print(f"{name:<60}  {str(pages):>6}  {did}")


def cmd_meta(key: str):
    docs = load_meta()
    entry = resolve_entry(docs, key)
    doc = load_full_doc(entry)
    out = {
        "doc_id": entry["doc_id"],
        "doc_name": doc.get("doc_name"),
        "doc_description": doc.get("doc_description"),
        "type": doc.get("type"),
        "page_count": doc.get("page_count"),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_structure(key: str):
    docs = load_meta()
    entry = resolve_entry(docs, key)
    doc = load_full_doc(entry)
    out = {
        "doc_id": entry["doc_id"],
        "doc_name": doc.get("doc_name"),
        "doc_description": doc.get("doc_description"),
        "page_count": doc.get("page_count"),
        "structure": doc.get("structure", []),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_pages(key: str, range_spec: str):
    docs = load_meta()
    entry = resolve_entry(docs, key)
    doc = load_full_doc(entry)
    pages = doc.get("pages") or []
    if not pages:
        raise SystemExit("该文档无可用页面正文（可能是 markdown 类型）")
    wanted = set(parse_pages(range_spec))
    out = [p for p in pages if p.get("page") in wanted]
    if not out:
        raise SystemExit(f"指定范围内无页面: {range_spec}")
    print(json.dumps(out, ensure_ascii=False, indent=2))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    args = sys.argv[2:]
    try:
        if cmd == "list":
            cmd_list()
        elif cmd == "meta" and len(args) == 1:
            cmd_meta(args[0])
        elif cmd == "structure" and len(args) == 1:
            cmd_structure(args[0])
        elif cmd == "pages" and len(args) == 2:
            cmd_pages(args[0], args[1])
        else:
            print(__doc__)
            sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:
        print(f"错误: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

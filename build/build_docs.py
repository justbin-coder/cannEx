#!/usr/bin/env python3
"""
build_docs.py — 按 docs.yaml 配置批量建文档树（增量）

行为：
  - 读 build/docs.yaml 中 enabled=true 的文档
  - 对每个文档：若 _meta.json 中已存在同 doc_name 则跳过
  - 否则调用 PageIndex 建树到 workspace/docs/<doc_id>.json
  - 完成后更新 workspace/_meta.json 的 docs[]
"""
import json
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
PAGEINDEX_DIR = Path.home() / "project" / "CANN" / "PageIndex"
load_dotenv(PAGEINDEX_DIR / ".env")
sys.path.insert(0, str(PAGEINDEX_DIR))
from pageindex import PageIndexClient  # noqa: E402

WORKSPACE = ROOT / "workspace"
DOCS_DIR = WORKSPACE / "docs"
META_FILE = WORKSPACE / "_meta.json"
DOCS_YAML = ROOT / "build/docs.yaml"


def load_meta() -> dict:
    if META_FILE.exists():
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    return {"version": "v2.0", "cann_version": "9.0.0", "docs": [], "repos": []}


def save_meta(meta: dict):
    META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def existing_doc_id(meta: dict, doc_name: str) -> str | None:
    for d in meta.get("docs", []):
        if d.get("doc_name") == doc_name:
            return d["doc_id"]
    return None


def move_built_json_to_docs_subdir(doc_id: str):
    src = WORKSPACE / f"{doc_id}.json"
    dst = DOCS_DIR / f"{doc_id}.json"
    if src.exists() and not dst.exists():
        src.rename(dst)


def build_one(doc_cfg: dict, meta: dict) -> dict | None:
    local_path = doc_cfg["local_path"]
    pdf_path = Path(local_path) if Path(local_path).is_absolute() else ROOT / local_path
    if not pdf_path.exists():
        print(f"[skip] PDF 不存在: {pdf_path}")
        return None

    doc_name = pdf_path.name
    eid = existing_doc_id(meta, doc_name)
    if eid:
        print(f"[skip] 已存在 doc_name='{doc_name}' (doc_id={eid})")
        return None

    print(f"[build] {doc_name}")
    client = PageIndexClient(workspace=str(WORKSPACE))
    t0 = time.time()
    doc_id = client.index(str(pdf_path))
    print(f"[done] {doc_name} → {doc_id}  用时 {(time.time()-t0)/60:.1f} 分钟")

    move_built_json_to_docs_subdir(doc_id)

    entry = {
        "doc_id": doc_id,
        "doc_name": doc_name,
        "category": doc_cfg.get("category"),
        "audience": doc_cfg.get("audience", []),
        "pages": None,
        "priority": doc_cfg.get("priority"),
        "path": f"docs/{doc_id}.json",
    }
    json_data = json.loads((DOCS_DIR / f"{doc_id}.json").read_text(encoding="utf-8"))
    entry["pages"] = json_data.get("page_count")
    return entry


def main():
    cfg = yaml.safe_load(DOCS_YAML.read_text(encoding="utf-8"))
    meta = load_meta()
    added = 0
    for d in cfg.get("docs", []):
        if not d.get("enabled"):
            continue
        entry = build_one(d, meta)
        if entry:
            meta["docs"].append(entry)
            added += 1
    if added:
        save_meta(meta)
        print(f"\n[summary] 新增 {added} 份文档")
    else:
        print("\n[summary] 无新增")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
build_docs.py — 按 docs.yaml 配置批量建文档树（增量）

行为：
  - 读 build/docs.yaml 中 enabled=true 的文档
  - 对每个文档：若 _meta.json 中已存在同 doc_name 则跳过
  - build_mode=api_ref → 调 build_api_ref（零 LLM，PyMuPDF 直提）
  - build_mode=pageindex（默认）→ 调 PageIndex 建树
  - 完成后更新 workspace/_meta.json 的 docs[]
"""
import json
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "workspace"
DOCS_DIR = WORKSPACE / "docs"
META_FILE = WORKSPACE / "_meta.json"
DOCS_YAML = ROOT / "build/docs.yaml"

# PageIndex 隔离 staging（避免 META_INDEX 撞名）
PI_STAGING = WORKSPACE / ".pi_staging"


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


def _build_pageindex(pdf_path: Path) -> tuple[str, Path]:
    """PageIndex 建树，返回 (doc_id, json_path)。"""
    from dotenv import load_dotenv

    pageindex_dir = Path.home() / "project" / "CANN" / "PageIndex"
    load_dotenv(pageindex_dir / ".env")
    sys.path.insert(0, str(pageindex_dir))
    from pageindex import PageIndexClient  # noqa: E402

    PI_STAGING.mkdir(parents=True, exist_ok=True)
    client = PageIndexClient(workspace=str(PI_STAGING))
    doc_id = client.index(str(pdf_path))
    # 搬到 docs/ 目录
    src = PI_STAGING / f"{doc_id}.json"
    dst = DOCS_DIR / f"{doc_id}.json"
    if src.exists() and not dst.exists():
        src.rename(dst)
    return doc_id, dst


def _build_api_ref(pdf_path: Path, doc_cfg: dict) -> tuple[str, Path]:
    """零 LLM API 参考构建，返回 (doc_id, json_path)。"""
    sys.path.insert(0, str(ROOT / "build"))
    from build_api_ref import build_one  # noqa: E402

    desc = doc_cfg.get("doc_description", "")
    result = build_one(str(pdf_path), doc_description=desc)
    doc_id = result["id"]
    dst = DOCS_DIR / f"{doc_id}.json"
    dst.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc_id, dst


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

    build_mode = doc_cfg.get("build_mode", "pageindex")
    print(f"[build] {doc_name} (mode={build_mode})")
    t0 = time.time()

    if build_mode == "api_ref":
        doc_id, json_path = _build_api_ref(pdf_path, doc_cfg)
    else:
        doc_id, json_path = _build_pageindex(pdf_path)

    elapsed = (time.time() - t0) / 60
    print(f"[done] {doc_name} → {doc_id}  用时 {elapsed:.1f} 分钟")

    entry = {
        "doc_id": doc_id,
        "doc_name": doc_name,
        "category": doc_cfg.get("category"),
        "audience": doc_cfg.get("audience", []),
        "pages": None,
        "priority": doc_cfg.get("priority"),
        "path": f"docs/{doc_id}.json",
    }
    json_data = json.loads(json_path.read_text(encoding="utf-8"))
    entry["pages"] = json_data.get("page_count")
    return entry


def main():
    cfg = yaml.safe_load(DOCS_YAML.read_text(encoding="utf-8"))
    meta = load_meta()
    added = 0
    failed: list[str] = []
    for d in cfg.get("docs", []):
        if not d.get("enabled"):
            continue
        try:
            entry = build_one(d, meta)
        except Exception as e:  # noqa: BLE001
            print(f"[error] 建树失败 name='{d.get('name')}': {type(e).__name__}: {e}")
            failed.append(d.get("name"))
            continue
        if entry:
            meta["docs"].append(entry)
            save_meta(meta)
            added += 1
            print(f"[saved] _meta.json 已登记 '{entry['doc_name']}'（累计新增 {added}）")

    print(f"\n[summary] 新增 {added} 份文档" + (f"；失败 {len(failed)} 份: {failed}" if failed else ""))


if __name__ == "__main__":
    main()

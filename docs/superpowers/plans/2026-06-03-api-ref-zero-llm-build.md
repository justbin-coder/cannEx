# API 参考文档零 LLM 构建 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 operator_api_ref（3301 页 API 参考）实现零 LLM 构建管线（PyMuPDF 直提 TOC + 页内容 + API 名称索引），并接通 retriever / CLI / Webchat 的精确查找路径。

**Architecture:** `build/build_api_ref.py` 用 PyMuPDF 提取 PDF 原生 TOC + 逐页文本，生成与 PageIndex 同 schema 的 JSON + `api_index` 倒排索引。`retriever_doc.py` 新增 `api_lookup_api()` 做名称查找，精确查找跳过 outline 推理直达 `api_pages()`。现有 `api_outline()` / `api_pages()` 路径不变，探索场景仍可用。

**Tech Stack:** Python 3.11, PyMuPDF (fitz), pytest

**Spec:** `docs/specs/2026-06-03-api-ref-zero-llm-build-design.md`

**工作目录：** `/Users/justbin/project/CANN/cannEx`

---

### Task 1: build_api_ref.py — TOC 转换与索引构建（纯函数）

**Files:**
- Create: `build/build_api_ref.py`
- Create: `build/tests/test_build_api_ref.py`

- [ ] **Step 1: 写失败测试**

```python
# build/tests/test_build_api_ref.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_api_ref as m


# ── toc_to_structure ──────────────────────────────────────────────────────

def test_toc_to_structure_nested():
    """PyMuPDF get_toc() 返回 [(level, title, page), ...]，转成 PageIndex 兼容的嵌套树。"""
    toc = [
        (1, "1 SIMD API", 10),
        (2, "1.1 通用说明", 10),
        (2, "1.2 基础数据结构", 15),
        (3, "1.2.1 LocalTensor", 15),
        (3, "1.2.2 GlobalTensor", 20),
        (1, "2 Cube API", 25),
    ]
    tree = m.toc_to_structure(toc, total_pages=30)
    # 顶层 2 个节点
    assert len(tree) == 2
    assert tree[0]["title"] == "1 SIMD API"
    assert tree[0]["start_index"] == 10
    assert tree[0]["end_index"] == 24  # 下一个 level-1 的 page - 1
    assert tree[1]["title"] == "2 Cube API"
    assert tree[1]["end_index"] == 30  # 最后一个，end = total_pages
    # 嵌套: SIMD API 有 2 个子节点
    children = tree[0]["nodes"]
    assert len(children) == 2
    assert children[1]["title"] == "1.2 基础数据结构"
    # 再嵌套: 基础数据结构有 2 个子节点
    grandchildren = children[1]["nodes"]
    assert len(grandchildren) == 2
    assert grandchildren[0]["title"] == "1.2.1 LocalTensor"
    assert grandchildren[0]["start_index"] == 15
    assert grandchildren[0]["end_index"] == 19


def test_toc_to_structure_node_ids_sequential():
    toc = [(1, "A", 1), (2, "B", 2), (1, "C", 5)]
    tree = m.toc_to_structure(toc, total_pages=10)
    ids = []

    def collect(nodes):
        for n in nodes:
            ids.append(n["node_id"])
            collect(n.get("nodes", []))

    collect(tree)
    assert ids == ["0000", "0001", "0002"]


def test_toc_to_structure_summary_is_empty_string():
    toc = [(1, "A", 1)]
    tree = m.toc_to_structure(toc, total_pages=5)
    assert tree[0]["summary"] == ""


# ── build_api_index ───────────────────────────────────────────────────────

def test_build_api_index_extracts_api_name():
    """从叶子节点标题提取 API 名称（去章节号前缀）。"""
    structure = [
        {
            "title": "SIMD API", "node_id": "0000",
            "start_index": 1, "end_index": 30, "summary": "",
            "nodes": [
                {
                    "title": "数据搬运接口", "node_id": "0001",
                    "start_index": 10, "end_index": 25, "summary": "",
                    "nodes": [
                        {"title": "2.3.1 DataCopy", "node_id": "0002",
                         "start_index": 10, "end_index": 15, "summary": ""},
                        {"title": "2.3.2 DataCopyPad", "node_id": "0003",
                         "start_index": 16, "end_index": 25, "summary": ""},
                    ],
                },
            ],
        },
    ]
    idx = m.build_api_index(structure)
    assert "DataCopy" in idx
    assert idx["DataCopy"]["pages"] == [10, 15]
    assert idx["DataCopy"]["section"] == "SIMD API > 数据搬运接口 > DataCopy"
    assert "DataCopyPad" in idx
    assert idx["DataCopyPad"]["pages"] == [16, 25]


def test_build_api_index_skips_non_leaf():
    """非叶子节点（有 children）不进入 api_index。"""
    structure = [
        {
            "title": "SIMD API", "node_id": "0000",
            "start_index": 1, "end_index": 10, "summary": "",
            "nodes": [
                {"title": "2.1 Intro", "node_id": "0001",
                 "start_index": 1, "end_index": 10, "summary": ""},
            ],
        },
    ]
    idx = m.build_api_index(structure)
    assert "SIMD API" not in idx
    assert "Intro" in idx


def test_build_api_index_chinese_title():
    """中文标题：整个标题作为 key（无章节号前缀可剥）。"""
    structure = [
        {"title": "附录", "node_id": "0000",
         "start_index": 1, "end_index": 5, "summary": ""},
    ]
    idx = m.build_api_index(structure)
    assert "附录" in idx


# ── extract_api_name ──────────────────────────────────────────────────────

def test_extract_api_name_strips_section_number():
    assert m.extract_api_name("2.2.1.8 GetSize") == "GetSize"
    assert m.extract_api_name("4.10.11 TRACE_STOP") == "TRACE_STOP"


def test_extract_api_name_no_number():
    assert m.extract_api_name("附录") == "附录"
    assert m.extract_api_name("LocalTensor简介") == "LocalTensor简介"


def test_extract_api_name_with_parens():
    assert m.extract_api_name("2.2.1.5 operator[]") == "operator[]"
```

- [ ] **Step 2: 运行验证失败**

Run: `cd /Users/justbin/project/CANN/cannEx && python3 -m pytest build/tests/test_build_api_ref.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'build_api_ref'`

- [ ] **Step 3: 实现 build_api_ref.py 的纯函数部分**

```python
# build/build_api_ref.py
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
    counter = {"n": 0}

    def build(items: list[dict], parent_level: int) -> list[dict]:
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
                    "node_id": f"{counter['n']:04d}",
                    "start_index": item["start"],
                    "end_index": item["end"],
                    "summary": "",
                }
                counter["n"] += 1
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
```

- [ ] **Step 4: 运行验证通过**

Run: `cd /Users/justbin/project/CANN/cannEx && python3 -m pytest build/tests/test_build_api_ref.py -v`
Expected: PASS（10 passed）

- [ ] **Step 5: Commit**

```bash
cd /Users/justbin/project/CANN/cannEx
git add build/build_api_ref.py build/tests/test_build_api_ref.py
git commit -m "feat(build): build_api_ref 零 LLM 构建器 — TOC 转换 + api_index 纯函数"
```

---

### Task 2: build_docs.py — 按 build_mode 分发 + docs.yaml 配置

**Files:**
- Modify: `build/build_docs.py`
- Modify: `build/docs.yaml`

- [ ] **Step 1: 修改 build_docs.py — 延迟 PageIndex 导入 + build_mode 分发**

当前 `build_docs.py` 在模块顶层 `from pageindex import PageIndexClient`，如果机器没装 PageIndex 会直接崩溃。改为：按 `build_mode` 分发，`api_ref` 模式调 `build_api_ref.build_one()`，`pageindex` 模式才导入 PageIndexClient。

```python
# build/build_docs.py — 替换整个文件
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
    from build_api_ref import build_one

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
```

- [ ] **Step 2: 修改 docs.yaml — operator_api_ref 加 build_mode + doc_description**

在 `operator_api_ref` 条目加两个字段：

```yaml
  - name: operator_api_ref
    file: "CANN社区版 9.1.0-beta.1 Ascend C算子开发接口参考 01.pdf"
    local_path: "raw/docs/CANN社区版 9.1.0-beta.1 Ascend C算子开发接口参考 01.pdf"
    version: 9.1.0-beta.1
    category: operator_api_ref
    audience: [A, F]
    priority: P0
    build_mode: api_ref
    doc_description: "CANN 9.1.0-beta.1 Ascend C 算子开发接口参考。涵盖 SIMD、Cube、Vector、AI CPU 四大类 API 的完整接口说明，包括函数签名、参数说明、使用约束和代码示例。"
    enabled: true
```

- [ ] **Step 3: Commit**

```bash
cd /Users/justbin/project/CANN/cannEx
git add build/build_docs.py build/docs.yaml
git commit -m "feat(build): build_docs 按 build_mode 分发 + operator_api_ref 切 api_ref 模式"
```

---

### Task 3: retriever_doc.py — api_lookup_api()

**Files:**
- Modify: `lib/cannex_knowledge/retriever_doc.py`
- Modify: `lib/cannex_knowledge/tests/test_retriever_doc.py`

- [ ] **Step 1: 写失败测试**

```python
# 追加到 lib/cannex_knowledge/tests/test_retriever_doc.py 末尾

# ── api_lookup_api ────────────────────────────────────────────────────────

def _make_mock_doc_json_with_index(tmp_path):
    """创建一个带 api_index 的 mock 文档 JSON + _meta.json，返回 workspace 路径。"""
    import json
    doc_id = "test-api-ref-doc"
    doc_json = {
        "id": doc_id,
        "type": "pdf",
        "doc_name": "test_api_ref.pdf",
        "doc_description": "Test API ref",
        "page_count": 100,
        "structure": [{"title": "Root", "node_id": "0000",
                        "start_index": 1, "end_index": 100, "summary": ""}],
        "pages": [{"page": i, "content": f"page {i}"} for i in range(1, 101)],
        "api_index": {
            "DataCopy": {"pages": [10, 15], "section": "SIMD > DataCopy"},
            "DataCopyPad": {"pages": [16, 20], "section": "SIMD > DataCopyPad"},
            "MatmulApiStaticTiling": {"pages": [50, 55], "section": "Cube > Matmul > MatmulApiStaticTiling"},
            "GetSize": {"pages": [30, 31], "section": "SIMD > LocalTensor > GetSize"},
        },
    }
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / f"{doc_id}.json").write_text(json.dumps(doc_json, ensure_ascii=False))
    meta = {
        "version": "v2.0", "docs": [
            {"doc_id": doc_id, "doc_name": "test_api_ref.pdf",
             "category": "api_ref", "pages": 100, "path": f"docs/{doc_id}.json"}
        ], "repos": []
    }
    (tmp_path / "_meta.json").write_text(json.dumps(meta, ensure_ascii=False))
    return tmp_path


def test_api_lookup_exact_match(tmp_path, monkeypatch):
    ws = _make_mock_doc_json_with_index(tmp_path)
    monkeypatch.setattr(d, "WORKSPACE", ws)
    monkeypatch.setattr(d, "META_FILE", ws / "_meta.json")
    res = d.api_lookup_api("test_api_ref.pdf", "DataCopy")
    assert len(res["matches"]) == 1
    assert res["matches"][0]["api_name"] == "DataCopy"
    assert res["matches"][0]["pages"] == [10, 15]
    assert res["fallback_hint"] is None


def test_api_lookup_case_insensitive(tmp_path, monkeypatch):
    ws = _make_mock_doc_json_with_index(tmp_path)
    monkeypatch.setattr(d, "WORKSPACE", ws)
    monkeypatch.setattr(d, "META_FILE", ws / "_meta.json")
    res = d.api_lookup_api("test_api_ref.pdf", "datacopy")
    assert len(res["matches"]) == 1
    assert res["matches"][0]["api_name"] == "DataCopy"


def test_api_lookup_substring_match(tmp_path, monkeypatch):
    ws = _make_mock_doc_json_with_index(tmp_path)
    monkeypatch.setattr(d, "WORKSPACE", ws)
    monkeypatch.setattr(d, "META_FILE", ws / "_meta.json")
    res = d.api_lookup_api("test_api_ref.pdf", "DataCopy")
    # 精确命中 DataCopy，子串命中 DataCopyPad
    names = [m["api_name"] for m in res["matches"]]
    assert "DataCopy" in names
    assert "DataCopyPad" in names
    # 精确匹配排在前面
    assert names[0] == "DataCopy"


def test_api_lookup_no_match_gives_hint(tmp_path, monkeypatch):
    ws = _make_mock_doc_json_with_index(tmp_path)
    monkeypatch.setattr(d, "WORKSPACE", ws)
    monkeypatch.setattr(d, "META_FILE", ws / "_meta.json")
    res = d.api_lookup_api("test_api_ref.pdf", "NonExistentAPI")
    assert res["matches"] == []
    assert res["fallback_hint"] is not None


def test_api_lookup_no_index_gives_hint(tmp_path, monkeypatch):
    """PageIndex 建的文档无 api_index → 返回空 + fallback_hint。"""
    import json
    doc_id = "no-index-doc"
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / f"{doc_id}.json").write_text(json.dumps({
        "id": doc_id, "doc_name": "old.pdf", "doc_description": "",
        "page_count": 10, "structure": [], "pages": [],
    }))
    meta = {"version": "v2.0", "docs": [
        {"doc_id": doc_id, "doc_name": "old.pdf", "pages": 10, "path": f"docs/{doc_id}.json"}
    ], "repos": []}
    (tmp_path / "_meta.json").write_text(json.dumps(meta))
    monkeypatch.setattr(d, "WORKSPACE", tmp_path)
    monkeypatch.setattr(d, "META_FILE", tmp_path / "_meta.json")
    res = d.api_lookup_api("old.pdf", "Anything")
    assert res["matches"] == []
    assert "不支持" in res["fallback_hint"]
```

- [ ] **Step 2: 运行验证失败**

Run: `cd /Users/justbin/project/CANN/cannEx && python3 -m pytest lib/cannex_knowledge/tests/test_retriever_doc.py -k "api_lookup" -v`
Expected: FAIL — `AttributeError: module 'cannex_knowledge.retriever_doc' has no attribute 'api_lookup_api'`

- [ ] **Step 3: 实现 api_lookup_api**

在 `lib/cannex_knowledge/retriever_doc.py` 末尾（`api_pages` 函数之后）追加：

```python
# ── API 名称精确查找（api_ref 文档专用快速通道）──────────────────────────
_LOOKUP_MAX_RESULTS = 10


def api_lookup_api(name_or_id: str, query: str) -> dict:
    """按 API 名称查找，返回匹配条目 + 页码范围。

    匹配策略（按优先级）：
    1. 精确匹配（大小写不敏感）
    2. 子串匹配（query 是 api_name 的子串，大小写不敏感）
    3. 无命中 → 返回空 + fallback_hint

    不引入 score / rank / top_k 语义——遵守 CLAUDE.md §九文档侧约束。
    """
    meta = load_meta()
    d = resolve_doc(meta, name_or_id)
    doc = load_doc_json(d)
    api_index = doc.get("api_index")
    if not api_index:
        return {
            "doc_name": _normalize_doc_name(d["doc_name"]),
            "matches": [],
            "fallback_hint": "该文档不支持 API 名称查找，请用 api_outline 按分类浏览",
        }

    query_lower = query.lower()
    exact = []
    substring = []
    for api_name, info in api_index.items():
        name_lower = api_name.lower()
        if name_lower == query_lower:
            exact.append({"api_name": api_name, **info})
        elif query_lower in name_lower:
            substring.append({"api_name": api_name, **info})

    # 精确匹配优先，子串按名称长度升序（越短越精确）
    substring.sort(key=lambda x: len(x["api_name"]))
    matches = (exact + substring)[:_LOOKUP_MAX_RESULTS]

    return {
        "doc_name": _normalize_doc_name(d["doc_name"]),
        "matches": matches,
        "fallback_hint": "未找到精确匹配，建议用 api_outline 按分类浏览" if not matches else None,
    }
```

- [ ] **Step 4: 运行验证通过**

Run: `cd /Users/justbin/project/CANN/cannEx && python3 -m pytest lib/cannex_knowledge/tests/test_retriever_doc.py -k "api_lookup" -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 回归测试**

Run: `cd /Users/justbin/project/CANN/cannEx && python3 -m pytest lib/cannex_knowledge/tests/test_retriever_doc.py -v`
Expected: 全 PASS（原有测试 + 新增 5 个）

- [ ] **Step 6: Commit**

```bash
cd /Users/justbin/project/CANN/cannEx
git add lib/cannex_knowledge/retriever_doc.py lib/cannex_knowledge/tests/test_retriever_doc.py
git commit -m "feat(lib): api_lookup_api 按 API 名称精确查找（api_ref 文档快速通道）"
```

---

### Task 4: Phase 1 CLI — cannex_doc.py 加 lookup 子命令

**Files:**
- Modify: `skills/ascend-c/tools/cannex_doc.py`

- [ ] **Step 1: 在 cannex_doc.py 添加 lookup 命令**

在 `cmd_pages` 函数之后追加：

```python
def cmd_lookup(key, query):
    _print(D.api_lookup_api(key, query))
```

在 `main()` 的 dispatch 区追加一行（在 `cmd_pages` 那行之后、`else:` 之前）：

```python
    elif cmd == "lookup"    and len(args) == 2: cmd_lookup(args[0], args[1])
```

更新文件头部 docstring 的 Usage 区：

```python
"""CannEx 文档查询 CLI（薄 wrapper）。

本文件只负责 argparse/命令行分发 → 调用 lib api_* → 打印 JSON。

Usage:
  cannex_doc.py list
  cannex_doc.py meta <name_or_id>
  cannex_doc.py structure <name_or_id>
  cannex_doc.py pages <name_or_id> <range>
  cannex_doc.py lookup <name_or_id> <api_name>
"""
```

- [ ] **Step 2: 冒烟验证**

Run: `cd /Users/justbin/project/CANN/cannEx && python3 skills/ascend-c/tools/cannex_doc.py lookup operator_api_ref DataCopy 2>&1 | head -20`
Expected: 如果 operator_api_ref 已构建 → 返回 JSON 含 matches；如果未构建 → 报错"未找到文档"（正常，PDF 还没建）

- [ ] **Step 3: Commit**

```bash
cd /Users/justbin/project/CANN/cannEx
git add skills/ascend-c/tools/cannex_doc.py
git commit -m "feat(cli): cannex_doc.py 新增 lookup 子命令（API 名称查找）"
```

---

### Task 5: Webchat 接通 — worker handler + agent 工具定义

**Files:**
- Modify: `webchat/cannex_chat/worker/server.py`
- Modify: `webchat/cannex_chat/agent/tools.py`
- Modify: `webchat/cannex_chat/tests/test_tools.py`
- Modify: `webchat/cannex_chat/tests/test_worker_server.py`

- [ ] **Step 1: 改测试计数与断言（test_tools.py）**

```python
# test_tools.py 改动：

def test_tools_count():
    assert len(TOOLS) == 18  # 17 + 1 新增

def test_tool_names():
    # ... 保留原有断言 ...
    # 2026-06-03 新增
    assert "lookup_doc_api" in TOOL_NAMES
```

- [ ] **Step 2: 写 worker 测试（test_worker_server.py 追加）**

```python
# 追加到 test_worker_server.py 末尾

def test_rpc_lookup_doc_api():
    proc = _make_worker()
    try:
        # 用一个已建的文档测试（即使无 api_index 也应返回 fallback_hint）
        resp = _send(proc, {
            "id": "lookup-1",
            "method": "lookup_doc_api",
            "params": {"doc": "install", "query": "anything"},
        })
        assert resp["ok"] is True
        assert "matches" in resp["result"]
        assert "fallback_hint" in resp["result"]
    finally:
        proc.terminate()
        proc.wait(timeout=2)
```

- [ ] **Step 3: 运行验证失败**

Run: `cd /Users/justbin/project/CANN/cannEx && python3 -m pytest webchat/cannex_chat/tests/test_tools.py -v`
Expected: FAIL — `assert len(TOOLS) == 18` (actual 17)

- [ ] **Step 4: 实现 — worker server.py HANDLERS 追加**

在 `server.py` 的 HANDLERS 字典 `}` 之前追加：

```python
    # ── API 名称查找（2026-06-03 新增）───────────────────────────────────────
    "lookup_doc_api": lambda p: doc_mod.api_lookup_api(
        name_or_id=p["doc"], query=p["query"]),
```

- [ ] **Step 5: 实现 — tools.py _TOOL_SPECS 追加**

在 `_TOOL_SPECS` 列表的 `]` 之前追加：

```python
    # ── API 名称查找（2026-06-03 新增）─────────────────────────────────────────
    {
        "name": "lookup_doc_api",
        "description": (
            "★ Look up an API by name in API reference documents. Use when the user asks about "
            "a specific Ascend C API (e.g. 'how to use DataCopy', 'what are the params for "
            "MatmulApiStaticTiling'). Returns matching API entries with page ranges — follow up "
            "with read_document_pages to get the full content. PREFER this over get_document_outline "
            "when the user already knows (or you can infer) a specific API name. Falls back "
            "gracefully for non-API-reference documents."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "doc": {"type": "string", "description": "Document name or ID (use 'operator_api_ref' for the API reference)"},
                "query": {"type": "string", "description": "API name or fragment to search, e.g. 'DataCopy', 'Matmul'"},
            },
            "required": ["doc", "query"],
        },
    },
```

- [ ] **Step 6: 运行验证通过**

Run: `cd /Users/justbin/project/CANN/cannEx && python3 -m pytest webchat/cannex_chat/tests/test_tools.py webchat/cannex_chat/tests/test_worker_server.py -v`
Expected: 全 PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/justbin/project/CANN/cannEx
git add webchat/cannex_chat/worker/server.py webchat/cannex_chat/agent/tools.py webchat/cannex_chat/tests/test_tools.py webchat/cannex_chat/tests/test_worker_server.py
git commit -m "feat(webchat): lookup_doc_api 工具 + worker handler 接通 API 名称查找"
```

---

### Task 6: Prompt playbook 更新

**Files:**
- Modify: `webchat/cannex_chat/prompts/system_prompt.md`
- Modify: `skills/ascend-c/SKILL.md`

- [ ] **Step 1: system_prompt.md 加 API 查找决策分支**

在 system_prompt.md 的工具使用指引区追加段落：

```markdown
### API 名称查找（精确查找快速通道）

当用户问到一个**具体 API 名称**（如 "DataCopy 怎么用"、"MatmulApiStaticTiling 的参数"）时：

1. **先 `lookup_doc_api`**：用 API 名称查询 `operator_api_ref` 文档
   - 命中 → 拿到 pages 范围 → `read_document_pages` 读原文 → 直接回答
   - 未命中 → fallback_hint 会引导走 outline 探索
2. **不要**先 `get_document_outline` 再在 1696 个条目里推理——对精确查找来说太慢且浪费 token

当用户在**按功能探索**（如 "有哪些数据搬运 API"）时：
- 走现有 `get_document_outline`(max_depth=2) → 推理选章节 → `read_document_pages`
```

- [ ] **Step 2: SKILL.md 同步**

在 SKILL.md 的决策树和 Appendix CLI 表做对应更新：

决策树加分支：
```
用户问具体 API → lookup <doc> <api_name> → 命中 → pages → 回答
                                          → 未命中 → 走 structure 探索
```

Appendix CLI 表加一行：
```
| lookup    | lookup <doc> <api_name>    | API 名称精确查找           |
```

- [ ] **Step 3: Commit**

```bash
cd /Users/justbin/project/CANN/cannEx
git add webchat/cannex_chat/prompts/system_prompt.md skills/ascend-c/SKILL.md
git commit -m "docs: prompt playbook 加 API 名称查找决策分支"
```

---

### Task 7: 全量回归 + 构建冒烟测试

**Files:** 无新增

- [ ] **Step 1: 全量回归测试**

Run: `cd /Users/justbin/project/CANN/cannEx && python3 -m pytest lib/cannex_knowledge/tests/ webchat/cannex_chat/tests/ build/tests/ tests/ -v --tb=short 2>&1 | tail -30`
Expected: 全 PASS

- [ ] **Step 2: 构建冒烟测试（需要 PDF 在 raw/docs/）**

如果 `raw/docs/` 下有 operator_api_ref PDF：

Run: `cd /Users/justbin/project/CANN/cannEx && python3 build/build_docs.py 2>&1 | tail -20`
Expected:
- 已建的 9 份文档 → `[skip]`
- operator_api_ref → `[build] ... (mode=api_ref)` → `[done] ... 用时 0.x 分钟` → `[saved]`
- `workspace/_meta.json` 新增一条 operator_api_ref 条目

如果 PDF 不在本地（gitignored），跳过此步，标记待手工验证。

- [ ] **Step 3: 查找冒烟测试（需要上一步构建成功）**

Run: `cd /Users/justbin/project/CANN/cannEx && python3 skills/ascend-c/tools/cannex_doc.py lookup operator_api_ref DataCopy`
Expected: JSON 输出含 `"api_name": "DataCopy"` + `"pages"` + `"section"`

Run: `cd /Users/justbin/project/CANN/cannEx && python3 skills/ascend-c/tools/cannex_doc.py lookup operator_api_ref Matmul`
Expected: 多个匹配（MatmulApiStaticTiling 等），按名称长度排序

---

## 自审

- **Spec 覆盖**：§2 构建侧 → Task 1/2；§3 运行时 → Task 3；§4 接通层 → Task 4/5/6；§5 配置 → Task 2；§9 成功标准 → Task 7 冒烟测试。全覆盖。
- **占位符扫描**：无 TBD / TODO / "implement later"。所有 step 含完整代码。
- **类型一致**：`build_api_ref.build_one()` 返回 dict（含 `id`, `api_index`）；`retriever_doc.api_lookup_api()` 读 `doc.get("api_index")`；`_TOOL_SPECS` 参数 `doc` + `query` 对应 worker handler `p["doc"]` + `p["query"]`。全链路一致。
- **test_tools_count**：17→18（+1 lookup_doc_api）。

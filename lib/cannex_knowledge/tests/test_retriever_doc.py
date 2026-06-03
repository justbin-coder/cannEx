from cannex_knowledge import retriever_doc as d


def test_api_list_returns_docs():
    docs = d.api_list()
    assert isinstance(docs, list)
    assert len(docs) >= 1
    assert "doc_name" in docs[0]
    assert "doc_id" in docs[0]
    # 新增断言：每个文档必须包含 doc_description（LLM 推理燃料）
    assert "doc_description" in docs[0]
    assert isinstance(docs[0]["doc_description"], str)
    assert len(docs[0]["doc_description"]) > 0


def test_api_outline_returns_structure():
    docs = d.api_list()
    name = docs[0]["doc_name"]
    res = d.api_outline(name, max_depth=2)
    assert "doc_name" in res
    assert "outline" in res
    assert isinstance(res["outline"], list)
    # 新增断言：节点必须包含 summary（LLM 在 tree 上推理的燃料）
    assert len(res["outline"]) > 0
    first_node = res["outline"][0]
    assert "summary" in first_node
    assert isinstance(first_node["summary"], str)


def test_api_meta_returns_single_doc_metadata():
    docs = d.api_list()
    name = docs[0]["doc_name"]
    meta = d.api_meta(name)
    assert meta["doc_id"] == docs[0]["doc_id"]
    assert meta["doc_name"] == name
    assert "doc_description" in meta
    assert "pages" in meta
    assert "category" in meta


def _doc_with_pages():
    """挑一个有正文页的文档，返回其逻辑名。"""
    for doc in d.api_list():
        if doc.get("pages", 0) > 0:
            return doc["doc_name"]
    return d.api_list()[0]["doc_name"]


def test_api_pages_returns_breadcrumbs():
    name = _doc_with_pages()
    res = d.api_pages(name, "1-3")
    assert "breadcrumbs" in res
    assert isinstance(res["breadcrumbs"], list)
    # 有正文页时应能反查到至少一条目录路径
    if res["pages"]:
        assert len(res["breadcrumbs"]) >= 1
        crumb = res["breadcrumbs"][0]
        assert "path" in crumb and isinstance(crumb["path"], str)
        assert "pages" in crumb and isinstance(crumb["pages"], str)


def test_breadcrumb_path_is_full_hierarchy_not_leaf_only():
    # 嵌套文档里，被多级标题包裹的页应还原成 "a > b > c" 的完整路径，而非单个叶子标题。
    # 选页数最多的文档（结构最深），扫一段页范围确认至少出现一条多级路径。
    docs = [x for x in d.api_list() if x.get("pages", 0) > 0]
    deepest = max(docs, key=lambda x: x["pages"])
    name = deepest["doc_name"]
    found_multilevel = False
    for pg in range(1, min(deepest["pages"], 200) + 1):
        crumbs = d.api_pages(name, str(pg))["breadcrumbs"]
        if crumbs and " > " in crumbs[0]["path"]:
            found_multilevel = True
            break
    assert found_multilevel, "未发现任何多级目录路径，breadcrumb 反查可能退化为叶子标题"


def test_fmt_page_ranges_compacts_consecutive():
    assert d._fmt_page_ranges([144, 145, 146, 150]) == "144-146,150"
    assert d._fmt_page_ranges([5]) == "5"
    assert d._fmt_page_ranges([]) == ""
    assert d._fmt_page_ranges([3, 1, 2]) == "1-3"


# ── api_lookup_api ────────────────────────────────────────────────────────

def _make_mock_doc_with_index(tmp_path):
    """创建一个带 api_index 的 mock 文档 JSON + _meta.json。"""
    import json as _json
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
    (docs_dir / f"{doc_id}.json").write_text(_json.dumps(doc_json, ensure_ascii=False))
    meta = {
        "version": "v2.0", "docs": [
            {"doc_id": doc_id, "doc_name": "test_api_ref.pdf",
             "category": "api_ref", "pages": 100, "path": f"docs/{doc_id}.json"}
        ], "repos": []
    }
    (tmp_path / "_meta.json").write_text(_json.dumps(meta, ensure_ascii=False))
    return tmp_path


def test_api_lookup_exact_match(tmp_path, monkeypatch):
    ws = _make_mock_doc_with_index(tmp_path)
    monkeypatch.setattr(d, "WORKSPACE", ws)
    monkeypatch.setattr(d, "META_FILE", ws / "_meta.json")
    res = d.api_lookup_api("test_api_ref.pdf", "DataCopy")
    assert len(res["matches"]) >= 1
    exact = [m for m in res["matches"] if m["api_name"] == "DataCopy"]
    assert len(exact) == 1
    assert exact[0]["pages"] == [10, 15]
    assert res["fallback_hint"] is None


def test_api_lookup_case_insensitive(tmp_path, monkeypatch):
    ws = _make_mock_doc_with_index(tmp_path)
    monkeypatch.setattr(d, "WORKSPACE", ws)
    monkeypatch.setattr(d, "META_FILE", ws / "_meta.json")
    res = d.api_lookup_api("test_api_ref.pdf", "datacopy")
    exact = [m for m in res["matches"] if m["api_name"] == "DataCopy"]
    assert len(exact) == 1


def test_api_lookup_substring_returns_prefix_and_exact(tmp_path, monkeypatch):
    ws = _make_mock_doc_with_index(tmp_path)
    monkeypatch.setattr(d, "WORKSPACE", ws)
    monkeypatch.setattr(d, "META_FILE", ws / "_meta.json")
    res = d.api_lookup_api("test_api_ref.pdf", "DataCopy")
    names = [m["api_name"] for m in res["matches"]]
    assert "DataCopy" in names
    assert "DataCopyPad" in names
    # exact match must appear before substring match
    assert names.index("DataCopy") < names.index("DataCopyPad")


def test_api_lookup_no_match_gives_fallback_hint(tmp_path, monkeypatch):
    ws = _make_mock_doc_with_index(tmp_path)
    monkeypatch.setattr(d, "WORKSPACE", ws)
    monkeypatch.setattr(d, "META_FILE", ws / "_meta.json")
    res = d.api_lookup_api("test_api_ref.pdf", "NonExistentAPI")
    assert res["matches"] == []
    assert res["fallback_hint"] is not None


def test_api_lookup_no_index_gives_fallback_hint(tmp_path, monkeypatch):
    """PageIndex 建的文档无 api_index → 返回空 + fallback_hint 含'不支持'。"""
    import json as _json
    doc_id = "no-index-doc"
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / f"{doc_id}.json").write_text(_json.dumps({
        "id": doc_id, "doc_name": "old.pdf", "doc_description": "",
        "page_count": 10, "structure": [], "pages": [],
    }))
    meta = {"version": "v2.0", "docs": [
        {"doc_id": doc_id, "doc_name": "old.pdf", "pages": 10, "path": f"docs/{doc_id}.json"}
    ], "repos": []}
    (tmp_path / "_meta.json").write_text(_json.dumps(meta))
    monkeypatch.setattr(d, "WORKSPACE", tmp_path)
    monkeypatch.setattr(d, "META_FILE", tmp_path / "_meta.json")
    res = d.api_lookup_api("old.pdf", "Anything")
    assert res["matches"] == []
    assert "不支持" in res["fallback_hint"]

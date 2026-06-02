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

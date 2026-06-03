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

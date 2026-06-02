import json
from pathlib import Path

from cannex_knowledge import retriever_repo as r
from cannex_knowledge import retriever_repo as repo_mod
from cannex_knowledge import codegraph_client as cgc

_FIXTURES = Path(__file__).parent / "fixtures" / "codegraph" / "ops_transformer"


def _load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _stub_call_cli(monkeypatch, fixture_name: str):
    """monkeypatch codegraph_client.call_cli 返回指定 fixture 内容。"""
    data = _load_fixture(fixture_name)
    def fake(*args, **kwargs):
        return data
    monkeypatch.setattr(cgc, "call_cli", fake)


def test_api_list_returns_ops_transformer():
    repos = r.api_list()
    names = [x["name"] for x in repos]
    assert "ops-transformer" in names


def test_api_list_files_root_shows_attention_dir():
    res = r.api_list_files("ops-transformer", "", max_depth=1)
    names = [e["name"] for e in res["entries"]]
    assert "attention/" in names
    assert res["source_type"] == "metadata"


def test_api_read_file_reads_header():
    res = r.api_read_file(
        "ops-transformer",
        "attention/flash_attention_score/op_kernel/flash_attention_score.cpp",
        start_line=1, end_line=10,
    )
    assert res["source_type"] == "original"
    assert "Huawei" in res["content"]
    assert res["total_lines"] > 100


def test_api_symbol_backwards_compat_delegates_to_search(monkeypatch):
    """api_symbol 应该委托给 api_search_symbol，旧 schema 返回 matches。"""
    _stub_call_cli(monkeypatch, "query_FlashAttentionScoreKernelBase_kind_class.json")
    res = r.api_symbol("ops-transformer", "FlashAttentionScoreKernelBase", kind="class")
    assert "matches" in res
    assert len(res["matches"]) >= 1
    assert res["source_type"] == "original"


def test_api_list_samples_returns_metadata():
    res = r.api_list_samples("ops-transformer")
    assert res["source_type"] == "metadata"
    assert res["count"] >= 1


def test_api_read_file_rejects_path_traversal():
    res = r.api_read_file("ops-transformer", "../../../etc/passwd")
    assert "error" in res


# ── Task 3: api_search_symbol ──────────────────────────────────────────────────

def test_api_search_symbol_returns_envelope_with_evidence(monkeypatch):
    _stub_call_cli(monkeypatch, "query_FlashAttention.json")
    res = r.api_search_symbol("ops-transformer", "FlashAttention", limit=5)

    assert res["source_type"] == "original"
    assert "matches" in res["data"]
    assert len(res["data"]["matches"]) >= 1

    first = res["data"]["matches"][0]
    assert "file_path" in first
    assert "start_line" in first
    assert "qualified_name" in first
    assert "score" in first

    assert len(res["evidence"]) == len(res["data"]["matches"])
    assert res["evidence"][0]["file_path"] == first["file_path"]
    assert res["evidence"][0]["start_line"] == first["start_line"]


def test_api_search_symbol_with_kind_filter(monkeypatch):
    _stub_call_cli(monkeypatch, "query_FlashAttentionScoreKernelBase_kind_class.json")
    res = r.api_search_symbol(
        "ops-transformer", "FlashAttentionScoreKernelBase", kind="class", limit=3,
    )
    assert res["source_type"] == "original"
    assert all(m["kind"] == "class" for m in res["data"]["matches"])


def test_api_search_symbol_propagates_error_envelope(monkeypatch):
    def fake(*args, **kwargs):
        return {"error": "repo 'foo' has no codegraph index",
                "fallback_hint": "运行 build_repos.py"}
    monkeypatch.setattr(cgc, "call_cli", fake)
    res = r.api_search_symbol("foo", "X")
    assert res["error"] is not None
    assert res["fallback_hint"] is not None
    assert res["data"] == {}


# ── Task 4: api_node ────────────────────────────────────────────────────────────

def test_api_node_returns_single_node(monkeypatch):
    _stub_call_cli(monkeypatch, "query_DataCopy_limit_1.json")
    res = r.api_node("ops-transformer", "DataCopy")

    assert res["source_type"] == "original"
    assert "node" in res["data"]
    node = res["data"]["node"]
    assert node["name"] == "DataCopy" or "DataCopy" in node.get("qualified_name", "")
    assert "file_path" in node
    assert "start_line" in node
    assert len(res["evidence"]) == 1


def test_api_node_missing_returns_error(monkeypatch):
    def fake(*args, **kwargs):
        return []
    monkeypatch.setattr(cgc, "call_cli", fake)
    res = r.api_node("ops-transformer", "NonExistentXYZ")
    assert res["data"] == {}
    assert res["error"] is not None
    assert "未找到" in res["error"]
    assert res["fallback_hint"] is not None


# ── Task 5: api_callers / api_callees ──────────────────────────────────────────

def test_api_callers_returns_list_with_evidence(monkeypatch):
    _stub_call_cli(monkeypatch, "callers_FlashAttentionScore.json")
    res = r.api_callers("ops-transformer", "FlashAttentionScore", limit=5)

    assert res["source_type"] == "original"
    assert res["data"]["symbol"] == "FlashAttentionScore"
    assert len(res["data"]["callers"]) >= 1

    first = res["data"]["callers"][0]
    assert "name" in first
    assert "kind" in first
    assert "file_path" in first
    assert "start_line" in first

    assert len(res["evidence"]) == len(res["data"]["callers"])


def test_api_callees_returns_list(monkeypatch):
    _stub_call_cli(monkeypatch, "callees_FlashAttentionScore.json")
    res = r.api_callees("ops-transformer", "FlashAttentionScore", limit=5)

    assert res["source_type"] == "original"
    assert res["data"]["symbol"] == "FlashAttentionScore"
    assert "callees" in res["data"]


def test_api_callers_empty_returns_hint(monkeypatch):
    def fake(*args, **kwargs):
        return {"symbol": "X", "callers": []}
    monkeypatch.setattr(cgc, "call_cli", fake)
    res = r.api_callers("ops-transformer", "X")
    assert res["data"]["callers"] == []
    assert res["fallback_hint"] is not None


# ── Task 6: api_impact ─────────────────────────────────────────────────────────

def test_api_impact_returns_radius(monkeypatch):
    _stub_call_cli(monkeypatch, "impact_FlashAttentionScore.json")
    res = r.api_impact("ops-transformer", "FlashAttentionScore", depth=2)

    assert res["source_type"] == "original"
    d = res["data"]
    assert d["symbol"] == "FlashAttentionScore"
    assert d["depth"] == 2
    assert "node_count" in d
    assert "edge_count" in d
    assert "affected" in d
    assert len(d["affected"]) >= 1

    first = d["affected"][0]
    assert "file_path" in first
    assert "start_line" in first

    assert len(res["evidence"]) == len(d["affected"])


# ── Task 7: api_explore_symbols ────────────────────────────────────────────────

def test_api_explore_symbols_returns_symbols_no_source(monkeypatch):
    _stub_call_cli(monkeypatch, "context_flashattention_pipeline_nocode.json")
    res = r.api_explore_symbols("ops-transformer", "FlashAttention pipeline", max_symbols=5)

    assert res["source_type"] == "original"
    d = res["data"]
    assert d["query"] == "FlashAttention pipeline"
    assert "summary" in d
    assert "entry_points" in d
    assert "symbols" in d

    for sym in d["symbols"]:
        assert "source_code" not in sym
        assert "code" not in sym
        assert "content" not in sym
        assert "file_path" in sym
        assert "start_line" in sym

    assert len(res["evidence"]) >= 1


# ── Task 9: api_list_samples 过滤 + no recommendation_reason ──────────────────

def test_api_list_samples_filter_by_computation_pattern():
    res = r.api_list_samples("ops-transformer", computation_pattern="cube")
    assert res["count"] >= 1
    assert all(s["computation_pattern"] == "cube" for s in res["samples"])


def test_api_list_samples_no_recommendation_reason_field():
    res = r.api_list_samples("ops-transformer")
    for s in res["samples"]:
        assert "recommendation_reason" not in s


# ── api_call_chain tests ────────────────────────────────────────────────────

def _stub_search_single(monkeypatch, file_path="root.cpp", start=1, end=40):
    monkeypatch.setattr(repo_mod, "api_search_symbol",
        lambda name, sym, kind=None, limit=10: {"data": {"matches": [
            {"name": sym, "file_path": file_path, "start_line": start, "end_line": end,
             "score": 100}]}, "error": None})


def test_api_call_chain_graph_only(monkeypatch):
    """全是普通方法调用：树全 graph，零接缝（root 读源码但无宏/模板）。"""
    graph = {"A": ["B", "C"], "B": [], "C": []}
    monkeypatch.setattr(repo_mod, "api_callees",
        lambda name, sym, limit=20: {"data": {"callees": [
            {"name": n, "file_path": f"{n}.h", "start_line": 1} for n in graph.get(sym, [])]},
            "error": None})
    _stub_search_single(monkeypatch)
    monkeypatch.setattr(repo_mod, "api_read_file",
        lambda *a, **k: {"content": "return b + c;", "error": None})

    res = repo_mod.api_call_chain("ops-transformer", "A", max_depth=3, read_budget=8)
    tree = res["data"]["tree"]
    assert tree["symbol"] == "A"
    assert {c["symbol"] for c in tree["children"]} == {"B", "C"}
    assert res["data"]["coverage"]["seams_entry"] == 0
    assert res["data"]["coverage"]["seams_interior"] == 0


def test_api_call_chain_entry_seam_priority(monkeypatch):
    """root 是死入口（callees 空）+ 源码含宏 → 标 entry_seam，priority=entry。"""
    monkeypatch.setattr(repo_mod, "api_callees",
        lambda name, sym, limit=20: {"data": {"callees": []}, "error": None})
    _stub_search_single(monkeypatch, file_path="entry.cpp", start=10, end=30)
    monkeypatch.setattr(repo_mod, "api_read_file",
        lambda *a, **k: {"content": "INVOKE_FA_GENERAL_OP_IMPL(op, tiling);", "error": None})

    res = repo_mod.api_call_chain("ops-transformer", "FlashAttentionScore", max_depth=2, read_budget=8)
    seams = res["data"]["seams"]
    assert any(s["token"] == "INVOKE_FA_GENERAL_OP_IMPL" and s["priority"] == "entry" for s in seams)
    assert res["data"]["tree"]["provenance"] == "entry_seam"
    assert res["data"]["coverage"]["seams_entry"] == 1
    assert res["fallback_hint"]


def test_api_call_chain_surfaces_root_ambiguity(monkeypatch):
    """root 泛名解析到多个不同文件 → root_ambiguous=True + root_candidates 列出。"""
    monkeypatch.setattr(repo_mod, "api_callees",
        lambda name, sym, limit=20: {"data": {"callees": []}, "error": None})
    monkeypatch.setattr(repo_mod, "api_search_symbol",
        lambda name, sym, kind=None, limit=10: {"data": {"matches": [
            {"name": "Process", "file_path": "a.h", "start_line": 1, "score": 113},
            {"name": "Process", "file_path": "b.h", "start_line": 9, "score": 113}]}, "error": None})
    monkeypatch.setattr(repo_mod, "api_read_file",
        lambda *a, **k: {"content": "x();", "error": None})

    res = repo_mod.api_call_chain("ops-transformer", "Process", max_depth=1, read_budget=4)
    assert res["data"]["coverage"]["root_ambiguous"] is True
    assert len(res["data"]["root_candidates"]) == 2


def test_api_call_chain_respects_read_budget(monkeypatch):
    """read_budget=0：不读源码、不产生 seam（连入口都不扫）。"""
    monkeypatch.setattr(repo_mod, "api_callees",
        lambda n, s, limit=20: {"data": {"callees": []}, "error": None})
    _stub_search_single(monkeypatch)
    called = {"reads": 0}
    def fake_read(*a, **k):
        called["reads"] += 1
        return {"content": "FOO_BAR(x);", "error": None}
    monkeypatch.setattr(repo_mod, "api_read_file", fake_read)

    res = repo_mod.api_call_chain("ops-transformer", "Init", max_depth=1, read_budget=0)
    assert called["reads"] == 0
    assert res["data"]["coverage"]["reads_used"] == 0


def test_api_call_chain_interior_suspect_leaf(monkeypatch):
    """内部可疑叶子（干活名 + callees=0）→ 扫缝 priority=interior，provenance=suspect_leaf。"""
    # root "Wrapper" → child "ComputeKernel"(suspect) → no callees
    def fake_callees(name, sym, limit=20):
        if sym == "Wrapper":
            return {"data": {"callees": [{"name": "ComputeKernel", "file_path": "k.h", "start_line": 1}]}, "error": None}
        return {"data": {"callees": []}, "error": None}

    monkeypatch.setattr(repo_mod, "api_callees", fake_callees)
    # search returns different location for Wrapper vs ComputeKernel
    def fake_search(name, sym, kind=None, limit=10):
        return {"data": {"matches": [{"name": sym, "file_path": f"{sym}.cpp", "start_line": 1, "end_line": 20, "score": 100}]}, "error": None}
    monkeypatch.setattr(repo_mod, "api_search_symbol", fake_search)
    monkeypatch.setattr(repo_mod, "api_read_file",
        lambda *a, **k: {"content": "INVOKE_INNER_MACRO(x);", "error": None})

    res = repo_mod.api_call_chain("ops-transformer", "Wrapper", max_depth=2, read_budget=8)
    seams = res["data"]["seams"]
    # ComputeKernel is a suspect leaf → interior seam scan
    interior_seams = [s for s in seams if s.get("priority") == "interior"]
    assert any(s["at_symbol"] == "ComputeKernel" for s in interior_seams)
    assert res["data"]["coverage"]["seams_interior"] >= 1
    # root Wrapper scan may or may not produce seams depending on content, but interior must
    child_node = res["data"]["tree"]["children"][0]
    assert child_node["provenance"] == "suspect_leaf"


def test_api_impact_surface_diffs_ripgrep_against_graph(monkeypatch):
    """ripgrep 命中但图谱 callers 没覆盖的文件 → 进 to_classify。"""
    monkeypatch.setattr(repo_mod, "api_callers",
        lambda n, s, limit=20: {"data": {"callers": [
            {"name": "X", "file_path": "graph_seen.cpp", "start_line": 5}]}, "error": None})
    monkeypatch.setattr(repo_mod._cgc, "_get_repo_path", lambda repo: __import__("pathlib").Path("/repo"))
    monkeypatch.setattr(repo_mod._rg, "find_refs",
        lambda rp, sym, timeout=10: {"refs": [
            {"file_path": "/repo/graph_seen.cpp", "line": 5, "text": "call"},
            {"file_path": "/repo/macro_hidden.h", "line": 9, "text": "MACRO(sym)"}],
            "error": None})

    res = repo_mod.api_impact_surface("ops-transformer", "sym", read_budget=8)
    paths = {c["file_path"] for c in res["data"]["to_classify"]}
    assert "/repo/macro_hidden.h" in paths
    assert "/repo/graph_seen.cpp" not in paths
    assert res["data"]["coverage"]["ripgrep_only"] == 1
    assert res["fallback_hint"]


def test_api_impact_surface_no_index(monkeypatch):
    monkeypatch.setattr(repo_mod, "api_callers", lambda n, s, limit=20: {"data": {"callers": []}, "error": None})
    monkeypatch.setattr(repo_mod._cgc, "_get_repo_path", lambda repo: None)
    res = repo_mod.api_impact_surface("ops-transformer", "sym")
    assert res["error"]

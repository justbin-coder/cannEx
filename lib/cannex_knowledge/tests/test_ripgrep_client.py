import subprocess
from cannex_knowledge import ripgrep_client as rgc


def _fake_rg_output():
    import json
    lines = [
        {"type": "match", "data": {"path": {"text": "/repo/a.cpp"},
         "lines": {"text": "REGIST_MATMUL_OBJ(x);\n"}, "line_number": 12}},
        {"type": "begin", "data": {"path": {"text": "/repo/a.cpp"}}},
        {"type": "match", "data": {"path": {"text": "/repo/b.h"},
         "lines": {"text": "  foo(Bar);\n"}, "line_number": 88}},
    ]
    return "\n".join(json.dumps(x) for x in lines)


def test_find_refs_parses_matches(monkeypatch):
    def fake_run(cmd, **kw):
        class R:
            returncode = 0
            stdout = _fake_rg_output()
            stderr = ""
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run)
    out = rgc.find_refs("/repo", "REGIST_MATMUL_OBJ")
    assert out["error"] is None
    assert len(out["refs"]) == 2
    assert out["refs"][0] == {"file_path": "/repo/a.cpp", "line": 12,
                              "text": "REGIST_MATMUL_OBJ(x);"}


def test_find_refs_rg_missing(monkeypatch):
    def fake_run(cmd, **kw):
        raise FileNotFoundError("rg")
    monkeypatch.setattr(subprocess, "run", fake_run)
    out = rgc.find_refs("/repo", "X")
    assert out["refs"] == []
    assert "not found" in out["error"]


def test_find_refs_no_match_is_not_error(monkeypatch):
    def fake_run(cmd, **kw):
        class R:
            returncode = 1  # rg 无命中时退出码 1，非错误
            stdout = ""
            stderr = ""
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run)
    out = rgc.find_refs("/repo", "X")
    assert out == {"refs": [], "error": None}


def test_find_refs_malformed_json_skipped(monkeypatch):
    """Malformed / incomplete match records are silently skipped, not crashing."""
    import json
    bad_lines = [
        {"type": "match"},                                    # no "data"
        {"type": "match", "data": {}},                       # no "path"/"lines"
        {"type": "match", "data": {"path": {"text": "/ok.cpp"}, "lines": {"text": "x;\n"}, "line_number": 1}},
    ]
    raw = "\n".join(json.dumps(x) for x in bad_lines)

    def fake_run(cmd, **kw):
        class R:
            returncode = 0
            stdout = raw
            stderr = ""
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run)
    out = rgc.find_refs("/repo", "x")
    assert out["error"] is None
    assert len(out["refs"]) == 1
    assert out["refs"][0]["file_path"] == "/ok.cpp"

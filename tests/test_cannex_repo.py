import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "skills/ascend-c/tools/cannex_repo.py"


def run(*args):
    r = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True)
    assert r.returncode == 0, f"CLI failed:\nSTDOUT={r.stdout}\nSTDERR={r.stderr}"
    return r.stdout


def test_list_shows_ops_transformer():
    out = run("list")
    assert "ops-transformer" in out


def test_card_returns_metadata():
    out = run("card", "ops-transformer")
    data = json.loads(out)
    assert data["source_type"] == "metadata"
    assert data["repo_name"] == "ops-transformer"
    assert "tagline" in data


def test_list_samples_filter_by_pattern():
    out = run("list_samples", "ops-transformer", "--pattern", "vector")
    data = json.loads(out)
    assert data["source_type"] == "metadata"
    assert len(data["samples"]) >= 1
    for s in data["samples"]:
        assert "vector" in s["computation_pattern"]


def test_list_samples_filter_by_complexity():
    out = run("list_samples", "ops-transformer", "--complexity", "beginner")
    data = json.loads(out)
    assert len(data["samples"]) >= 1
    for s in data["samples"]:
        assert s["complexity"] == "beginner"


def test_code_returns_original_source():
    out = run("code", "ops-transformer", "ffn-glu")
    data = json.loads(out)
    assert data["source_type"] == "original"
    assert len(data["files"]) >= 1
    assert "content" in data["files"][0]


def test_symbol_query_returns_results():
    out = run("symbol", "ops-transformer", "FlashAttentionScore")
    data = json.loads(out)
    assert data["source_type"] == "original"
    assert len(data["results"]) >= 1
    assert "file_path" in data["results"][0]

import json
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).parent.parent / "skills/ascend-c/tools/cannex_doc.py"


def run(*args):
    r = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True)
    assert r.returncode == 0, f"CLI failed:\nSTDOUT={r.stdout}\nSTDERR={r.stderr}"
    return r.stdout


def test_list_outputs_audience_and_category():
    out = run("list")
    payload = json.loads(out)
    assert "docs" in payload, "list 必须返回含 docs 的 JSON"
    categories = [d.get("category", "") for d in payload["docs"]]
    assert "operator_dev" in categories, "list 必须包含 operator_dev category"


def test_meta_returns_source_type_original():
    out = run("meta", "算子开发指南")
    payload = json.loads(out)
    assert payload["source_type"] == "original", "meta 必须标 source_type=original"


def test_pages_returns_pages_list():
    out = run("pages", "软件安装", "5-6")
    payload = json.loads(out)
    assert isinstance(payload, dict), "pages 应返回 dict"
    assert "pages" in payload, "pages 返回值必须含 pages 字段"
    assert isinstance(payload["pages"], list)


def test_unknown_doc_helpful_error():
    r = subprocess.run([sys.executable, str(CLI), "meta", "不存在的文档名"], capture_output=True, text=True)
    assert r.returncode != 0
    assert "可用文档" in r.stderr or "可用文档" in r.stdout

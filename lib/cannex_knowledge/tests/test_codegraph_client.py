"""codegraph_client 单元测试。"""
import json
import shutil
import subprocess
from unittest.mock import patch

import pytest

from cannex_knowledge import codegraph_client as cgc


def test_check_version_returns_tuple(monkeypatch):
    """check_codegraph_version 解析 `codegraph --version` 输出为 (major, minor, patch) tuple。"""
    def fake_run(cmd, **kwargs):
        class R:
            returncode = 0
            stdout = "0.9.6\n"
            stderr = ""
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert cgc.check_codegraph_version() == (0, 9, 6)


def test_check_version_returns_none_when_cli_missing(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("codegraph: command not found")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert cgc.check_codegraph_version() is None


def test_normalize_keys_camel_to_snake():
    raw = {"filePath": "a.cpp", "startLine": 1, "qualifiedName": "ns::F",
           "nested": {"endLine": 10, "isExported": True}}
    out = cgc._normalize_keys(raw)
    assert out == {
        "file_path": "a.cpp",
        "start_line": 1,
        "qualified_name": "ns::F",
        "nested": {"end_line": 10, "is_exported": True},
    }


def test_normalize_keys_preserves_unknown_fields():
    raw = {"custom_field": "x", "filePath": "y"}
    out = cgc._normalize_keys(raw)
    assert out == {"custom_field": "x", "file_path": "y"}


def test_normalize_keys_handles_list():
    raw = [{"filePath": "a"}, {"filePath": "b"}]
    out = cgc._normalize_keys(raw)
    assert out == [{"file_path": "a"}, {"file_path": "b"}]


# ── _resolve_codegraph_bin ─────────────────────────────────────────────────────

def test_resolve_bin_prefers_explicit_override(monkeypatch, tmp_path):
    fake = tmp_path / "codegraph"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setenv("CANNEX_CODEGRAPH_BIN", str(fake))
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/codegraph")
    assert cgc._resolve_codegraph_bin() == str(fake)


def test_resolve_bin_falls_back_to_which(monkeypatch):
    monkeypatch.delenv("CANNEX_CODEGRAPH_BIN", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/local/bin/codegraph")
    assert cgc._resolve_codegraph_bin() == "/usr/local/bin/codegraph"


def test_resolve_bin_probes_nvm_bin_when_path_misses(monkeypatch, tmp_path):
    nvm_bin = tmp_path / "nvm_bin"
    nvm_bin.mkdir()
    fake = nvm_bin / "codegraph"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.delenv("CANNEX_CODEGRAPH_BIN", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _: None)
    monkeypatch.setenv("NVM_BIN", str(nvm_bin))
    assert cgc._resolve_codegraph_bin() == str(fake)


def test_resolve_bin_probes_nvm_versions_dir(monkeypatch, tmp_path):
    nvm_dir = tmp_path / ".nvm"
    bin_dir = nvm_dir / "versions" / "node" / "v24.0.0" / "bin"
    bin_dir.mkdir(parents=True)
    fake = bin_dir / "codegraph"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.delenv("CANNEX_CODEGRAPH_BIN", raising=False)
    monkeypatch.delenv("NVM_BIN", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _: None)
    monkeypatch.setenv("NVM_DIR", str(nvm_dir))
    assert cgc._resolve_codegraph_bin() == str(fake)


def test_resolve_bin_returns_bare_name_when_nothing_found(monkeypatch, tmp_path):
    monkeypatch.delenv("CANNEX_CODEGRAPH_BIN", raising=False)
    monkeypatch.delenv("NVM_BIN", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _: None)
    monkeypatch.setenv("NVM_DIR", str(tmp_path / "nonexistent"))
    assert cgc._resolve_codegraph_bin() == "codegraph"


# ── call_cli "symbol not found" 非 JSON 输出处理 ───────────────────────────────

def test_call_cli_symbol_not_found_returns_clean_envelope(monkeypatch):
    """符号未索引时 codegraph 打印 `ℹ Symbol "X" not found`（非 JSON），
    应转成干净的 error + fallback_hint，而不是 'output not JSON'。"""
    monkeypatch.setattr(cgc, "_resolve_codegraph_bin", lambda: "codegraph")
    monkeypatch.setattr(cgc, "_get_repo_path", lambda repo: __import__("pathlib").Path("/tmp/x"))

    def fake_run(cmd, **kwargs):
        class R:
            returncode = 0
            stdout = 'ℹ Symbol "REGIST_MATMUL_OBJ" not found'
            stderr = ""
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run)

    out = cgc.call_cli("ops-transformer", "callers", "REGIST_MATMUL_OBJ")
    assert "not found in code graph" in out["error"]
    assert out["fallback_hint"]
    assert "output not JSON" not in out["error"]

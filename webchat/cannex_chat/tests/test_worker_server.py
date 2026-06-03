import json
import os
import subprocess
import sys
from pathlib import Path

CANNEX_ROOT = Path(__file__).resolve().parents[3]
WORKER = CANNEX_ROOT / "webchat/cannex_chat/worker/server.py"


def _send(worker_proc, request: dict) -> dict:
    worker_proc.stdin.write((json.dumps(request) + "\n").encode())
    worker_proc.stdin.flush()
    line = worker_proc.stdout.readline()
    return json.loads(line.decode())


def _make_worker():
    env = os.environ.copy()
    env["CANNEX_ROOT"] = str(CANNEX_ROOT)
    return subprocess.Popen(
        [sys.executable, str(WORKER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


def test_ping():
    proc = _make_worker()
    try:
        resp = _send(proc, {"id": "1", "method": "ping"})
        assert resp == {"id": "1", "ok": True, "result": "pong"}
    finally:
        proc.terminate()
        proc.wait(timeout=2)


def test_list_known_resources():
    proc = _make_worker()
    try:
        resp = _send(proc, {"id": "2", "method": "list_known_resources"})
        assert resp["ok"] is True
        assert "docs" in resp["result"] and "repos" in resp["result"]
    finally:
        proc.terminate()
        proc.wait(timeout=2)


def test_unknown_method_returns_error():
    proc = _make_worker()
    try:
        resp = _send(proc, {"id": "3", "method": "no_such_method"})
        assert resp["ok"] is False
        assert "UnknownMethod" in resp["error"]["type"]
    finally:
        proc.terminate()
        proc.wait(timeout=2)


def test_handler_exception_returned_as_error():
    proc = _make_worker()
    try:
        resp = _send(proc, {"id": "4", "method": "lookup_code_symbol",
                            "params": {"symbol": "X", "repo": "nonexistent_repo"}})
        # Should return ok=True with empty matches OR ok=False with error
        # Either is acceptable as long as process doesn't crash
        assert "id" in resp
        assert "ok" in resp
    finally:
        proc.terminate()
        proc.wait(timeout=2)


# ── Phase B 新 RPC 方法测试 ───────────────────────────────────────────────────

def test_rpc_search_code_symbol_returns_envelope():
    proc = _make_worker()
    try:
        resp = _send(proc, {"id": "b1", "method": "search_code_symbol",
                            "params": {"repo": "ops-transformer", "query": "FlashAttention", "limit": 2}})
        assert resp["ok"] is True
        assert resp["result"]["source_type"] == "original"
        assert "matches" in resp["result"]["data"]
        assert len(resp["result"]["data"]["matches"]) >= 1
    finally:
        proc.terminate()
        proc.wait(timeout=2)


def test_rpc_find_code_callers():
    proc = _make_worker()
    try:
        resp = _send(proc, {"id": "b2", "method": "find_code_callers",
                            "params": {"repo": "ops-transformer", "symbol": "FlashAttentionScore", "limit": 3}})
        assert resp["ok"] is True
        assert resp["result"]["source_type"] == "original"
        assert "callers" in resp["result"]["data"]
    finally:
        proc.terminate()
        proc.wait(timeout=2)


def test_rpc_analyze_code_impact():
    proc = _make_worker()
    try:
        resp = _send(proc, {"id": "b3", "method": "analyze_code_impact",
                            "params": {"repo": "ops-transformer", "symbol": "FlashAttentionScore", "depth": 1}})
        assert resp["ok"] is True
        d = resp["result"]["data"]
        assert "affected" in d
        assert "node_count" in d
    finally:
        proc.terminate()
        proc.wait(timeout=2)


def test_rpc_explore_code_symbols_strips_source():
    proc = _make_worker()
    try:
        resp = _send(proc, {"id": "b4", "method": "explore_code_symbols",
                            "params": {"repo": "ops-transformer",
                                       "query": "FlashAttention pipeline", "max_symbols": 3}})
        assert resp["ok"] is True
        for sym in resp["result"]["data"].get("symbols", []):
            assert "source_code" not in sym
            assert "code" not in sym
    finally:
        proc.terminate()
        proc.wait(timeout=2)


def test_rpc_get_call_chain():
    proc = _make_worker()
    try:
        resp = _send(proc, {"id": "c1", "method": "get_operator_call_chain",
                            "params": {"repo": "ops-transformer", "root": "FlashAttentionScore"}})
        assert resp["ok"] is True
        assert "tree" in resp["result"]["data"]
        assert "coverage" in resp["result"]["data"]
    finally:
        proc.terminate()
        proc.wait(timeout=2)


def test_rpc_get_impact_surface():
    proc = _make_worker()
    try:
        resp = _send(proc, {"id": "c2", "method": "get_change_impact_surface",
                            "params": {"repo": "ops-transformer", "symbol": "DataCopy"}})
        assert resp["ok"] is True
        assert "coverage" in resp["result"]["data"]
    finally:
        proc.terminate()
        proc.wait(timeout=2)


def test_rpc_lookup_doc_api():
    proc = _make_worker()
    try:
        # 用软件安装文档测 (无 api_index 也应 gracefully 返回 fallback_hint)
        resp = _send(proc, {
            "id": "lookup-1",
            "method": "lookup_doc_api",
            "params": {"doc": "软件安装", "query": "anything"},
        })
        assert resp["ok"] is True
        assert "matches" in resp["result"]
        assert "fallback_hint" in resp["result"]
    finally:
        proc.terminate()
        proc.wait(timeout=2)

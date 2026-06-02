"""
CannEx Webchat Knowledge Worker

JSON Lines RPC server over stdin/stdout.
Imports cannex_doc / cannex_repo and dispatches semantic queries.
"""
import json
import os
import sys
from pathlib import Path


def _setup_path():
    """把 <CANNEX_ROOT>/lib 加入 sys.path，使 cannex_knowledge 可 import。"""
    root = os.environ.get("CANNEX_ROOT")
    if not root:
        sys.stderr.write("ERROR: CANNEX_ROOT env var not set\n")
        sys.exit(1)
    sys.path.insert(0, str(Path(root) / "lib"))
    if not (Path(root) / "workspace" / "_meta.json").exists():
        sys.stderr.write(f"ERROR: workspace/_meta.json not found under {root}\n")
        sys.exit(1)


_setup_path()

import logging  # noqa: E402

from cannex_knowledge import retriever_doc as doc_mod  # noqa: E402
from cannex_knowledge import retriever_repo as repo_mod  # noqa: E402
from cannex_knowledge.codegraph_client import check_codegraph_version, MIN_CODEGRAPH_VERSION  # noqa: E402

log = logging.getLogger(__name__)


def _check_codegraph_at_startup() -> None:
    """非致命版本校验：CLI 缺失或版本不足时只记 warning，worker 仍启动。
    L0（samples/overview/files）不依赖 codegraph，仍可正常服务。
    L1-L4 工具在实际调用时返回 error envelope + fallback_hint。
    """
    v = check_codegraph_version()
    if v is None:
        log.warning(
            "codegraph CLI not found in PATH — L1-L4 code-graph APIs will return error envelopes. "
            "Install with: npm i -g @colbymchenry/codegraph@latest"
        )
        return
    if v < MIN_CODEGRAPH_VERSION:
        need = ".".join(map(str, MIN_CODEGRAPH_VERSION))
        cur = ".".join(map(str, v))
        log.warning(
            "codegraph CLI %s < %s — callers/callees/impact APIs will return error envelopes. "
            "Upgrade with: npm i -g @colbymchenry/codegraph@latest",
            cur, need,
        )


HANDLERS = {
    "ping": lambda _: "pong",
    "lookup_code_symbol": lambda p: repo_mod.api_symbol(
        name=p.get("repo", "ops-transformer"), symbol=p["symbol"], kind=p.get("kind", "any")),
    "list_known_resources": lambda _: {
        "docs": doc_mod.api_list(),
        "repos": repo_mod.api_list(),
    },
    # Phase 2 补齐：与 Phase 1 CLI 能力对齐
    "get_document_outline": lambda p: doc_mod.api_outline(
        name_or_id=p["doc_name"], max_depth=p.get("max_depth", 3)),
    "read_document_pages": lambda p: doc_mod.api_pages(
        name_or_id=p["doc_name"], page_range=p["page_range"]),
    "get_repo_overview": lambda p: repo_mod.api_overview(name=p["repo"]),
    "list_repo_samples": lambda p: repo_mod.api_list_samples(
        name=p["repo"], pattern=p.get("pattern"), complexity=p.get("complexity"),
        computation_pattern=p.get("computation_pattern")),
    "read_sample_code": lambda p: repo_mod.api_read_sample(
        name=p["repo"], sample_id=p["sample_id"], skeleton=p.get("skeleton", False)),
    "read_repo_file": lambda p: repo_mod.api_read_file(
        name=p["repo"], file_path=p["file_path"],
        start_line=p.get("start_line", 1), end_line=p.get("end_line")),
    "list_repo_files": lambda p: repo_mod.api_list_files(
        name=p["repo"], dir_path=p.get("dir_path", ""), max_depth=p.get("max_depth", 2)),
    # ── L1 符号定位（新增）──────────────────────────────────────────────────
    "search_code_symbol": lambda p: repo_mod.api_search_symbol(
        p["repo"], p["query"],
        kind=p.get("kind"),
        limit=p.get("limit", 10),
    ),
    "lookup_code_node": lambda p: repo_mod.api_node(
        p["repo"], p["symbol"],
        kind=p.get("kind"),
    ),
    # ── L2 图关系反查（新增）────────────────────────────────────────────────
    "find_code_callers": lambda p: repo_mod.api_callers(
        p["repo"], p["symbol"],
        limit=p.get("limit", 20),
    ),
    "find_code_callees": lambda p: repo_mod.api_callees(
        p["repo"], p["symbol"],
        limit=p.get("limit", 20),
    ),
    "analyze_code_impact": lambda p: repo_mod.api_impact(
        p["repo"], p["symbol"],
        depth=p.get("depth", 2),
    ),
    # ── L4 阙割版探索（新增）────────────────────────────────────────────────
    "explore_code_symbols": lambda p: repo_mod.api_explore_symbols(
        p["repo"], p["query"],
        max_symbols=p.get("max_symbols", 30),
    ),
    # ── 完整调用链 / 影响面（2026-05-29 新增）──────────────────────────────
    "get_operator_call_chain": lambda p: repo_mod.api_call_chain(
        p["repo"], p["root"],
        max_depth=p.get("max_depth", 4), read_budget=p.get("read_budget", 8)),
    "get_change_impact_surface": lambda p: repo_mod.api_impact_surface(
        p["repo"], p["symbol"], read_budget=p.get("read_budget", 8)),
}


def _handle(req: dict) -> dict:
    rid = req.get("id", "?")
    method = req.get("method")
    params = req.get("params", {})
    if method not in HANDLERS:
        return {"id": rid, "ok": False,
                "error": {"type": "UnknownMethod", "message": f"method '{method}' not registered"}}
    try:
        result = HANDLERS[method](params)
        return {"id": rid, "ok": True, "result": result}
    except Exception as e:
        return {"id": rid, "ok": False,
                "error": {"type": type(e).__name__, "message": str(e)}}


def main():
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    _check_codegraph_at_startup()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            sys.stdout.write(json.dumps({
                "id": None, "ok": False,
                "error": {"type": "ParseError", "message": str(e)}
            }) + "\n")
            sys.stdout.flush()
            continue
        resp = _handle(req)
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()

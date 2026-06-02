#!/usr/bin/env python3
"""CannEx 代码仓查询 CLI（薄 wrapper）。

本文件只负责 argparse → 调用 lib api_* → 打印 JSON。

Usage:
  cannex_repo.py list
  cannex_repo.py card <repo_name>
  cannex_repo.py list_samples <repo_name> [--pattern X] [--complexity Y]
  cannex_repo.py code <repo_name> <sample_id> [--skeleton]
  cannex_repo.py symbol <repo_name> <symbol_name> [--kind function|class|struct]
  cannex_repo.py list_files <repo_name> [dir_path] [--max_depth N]
  cannex_repo.py read_file <repo_name> <file_path> [--start_line N] [--end_line N]
"""
import argparse
import json
import os
import sys
from pathlib import Path

# 把 <root>/lib 加入 sys.path，使 cannex_knowledge 可 import
_ROOT = Path(os.environ.get("CANNEX_ROOT") or Path(__file__).resolve().parents[3])
sys.path.insert(0, str(_ROOT / "lib"))

from cannex_knowledge import retriever_repo as R  # noqa: E402


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_list():
    repos = R.api_list()
    _print({"source_type": "metadata", "repos": repos})


def cmd_card(name):
    _print({"source_type": "metadata", **R.api_card(name)})


def cmd_list_samples(name, pattern, complexity):
    _print(R.api_list_samples(name, pattern=pattern, complexity=complexity))


def cmd_code(name, sample_id, skeleton):
    _print(R.api_read_sample(name, sample_id, skeleton=skeleton))


def cmd_symbol(name, symbol, kind):
    result = R.api_symbol(name, symbol, kind=kind or "any")
    # 将 lib 返回的 "matches" 字段映射为 CLI 约定的 "results"（向后兼容）
    matches = result.pop("matches", [])
    _print({
        **result,
        "repo": name,
        "query": symbol,
        "count": len(matches),
        "results": matches,
    })


def cmd_list_files(name, dir_path, max_depth):
    _print(R.api_list_files(name, dir_path, max_depth))


def cmd_read_file(name, file_path, start_line, end_line):
    _print(R.api_read_file(name, file_path, start_line, end_line))


def cmd_search_symbol(name, query, kind, limit):
    _print(R.api_search_symbol(name, query, kind=kind, limit=limit))


def cmd_node(name, symbol, kind):
    _print(R.api_node(name, symbol, kind=kind))


def cmd_callers(name, symbol, limit):
    _print(R.api_callers(name, symbol, limit=limit))


def cmd_callees(name, symbol, limit):
    _print(R.api_callees(name, symbol, limit=limit))


def cmd_impact(name, symbol, depth):
    _print(R.api_impact(name, symbol, depth=depth))


def cmd_explore_symbols(name, query, max_symbols):
    _print(R.api_explore_symbols(name, query, max_symbols=max_symbols))


def cmd_call_chain(name, root, max_depth, read_budget):
    _print(R.api_call_chain(name, root, max_depth=max_depth, read_budget=read_budget))


def cmd_impact_surface(name, symbol, read_budget):
    _print(R.api_impact_surface(name, symbol, read_budget=read_budget))


def main():
    p = argparse.ArgumentParser(description="CannEx 代码仓查询 CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")

    s = sub.add_parser("card")
    s.add_argument("repo")

    s = sub.add_parser("list_samples")
    s.add_argument("repo")
    s.add_argument("--pattern")
    s.add_argument("--complexity")

    s = sub.add_parser("code")
    s.add_argument("repo")
    s.add_argument("sample_id")
    s.add_argument("--skeleton", action="store_true")

    s = sub.add_parser("symbol")
    s.add_argument("repo")
    s.add_argument("symbol_name")
    s.add_argument("--kind")

    s = sub.add_parser("list_files")
    s.add_argument("repo")
    s.add_argument("dir_path", nargs="?", default="")
    s.add_argument("--max_depth", type=int, default=2)

    s = sub.add_parser("read_file")
    s.add_argument("repo")
    s.add_argument("file_path")
    s.add_argument("--start_line", type=int, default=1)
    s.add_argument("--end_line", type=int, default=None)

    # === L1 符号定位（新增）===
    s = sub.add_parser("search_symbol", help="FTS5 + ranking 符号搜索")
    s.add_argument("repo")
    s.add_argument("query")
    s.add_argument("--kind", default=None,
                   help="过滤 kind: function / class / struct / method / ...")
    s.add_argument("--limit", type=int, default=10)

    s = sub.add_parser("node", help="精确单符号详情（query --limit 1 等价）")
    s.add_argument("repo")
    s.add_argument("symbol")
    s.add_argument("--kind", default=None)

    # === L2 图关系反查（新增）===
    s = sub.add_parser("callers", help="反查谁调用了 symbol")
    s.add_argument("repo")
    s.add_argument("symbol")
    s.add_argument("--limit", type=int, default=20)

    s = sub.add_parser("callees", help="反查 symbol 调用了谁")
    s.add_argument("repo")
    s.add_argument("symbol")
    s.add_argument("--limit", type=int, default=20)

    s = sub.add_parser("impact", help="symbol 修改影响半径")
    s.add_argument("repo")
    s.add_argument("symbol")
    s.add_argument("--depth", type=int, default=2)

    # === L4 阙割版探索（新增）===
    s = sub.add_parser("explore_symbols", help="任务相关符号清单（不含源码）")
    s.add_argument("repo")
    s.add_argument("query")
    s.add_argument("--max_symbols", type=int, default=30)

    # === 完整调用链 / 影响面（2026-05-29 新增）===
    s = sub.add_parser("call_chain", help="算子完整调用链（图谱主干+接缝补全）")
    s.add_argument("repo")
    s.add_argument("root", help="根符号（kernel方法符号，非算子自然名）")
    s.add_argument("--max-depth", type=int, default=4, dest="max_depth")
    s.add_argument("--read-budget", type=int, default=8, dest="read_budget")

    s = sub.add_parser("impact_surface", help="改动影响面（图谱callers∪ripgrep）")
    s.add_argument("repo")
    s.add_argument("symbol")
    s.add_argument("--read-budget", type=int, default=8, dest="read_budget")

    args = p.parse_args()

    if   args.cmd == "list":           cmd_list()
    elif args.cmd == "card":           cmd_card(args.repo)
    elif args.cmd == "list_samples":   cmd_list_samples(args.repo, args.pattern, args.complexity)
    elif args.cmd == "code":           cmd_code(args.repo, args.sample_id, args.skeleton)
    elif args.cmd == "symbol":         cmd_symbol(args.repo, args.symbol_name, args.kind)
    elif args.cmd == "list_files":     cmd_list_files(args.repo, args.dir_path, args.max_depth)
    elif args.cmd == "read_file":      cmd_read_file(args.repo, args.file_path, args.start_line, args.end_line)
    elif args.cmd == "search_symbol":  cmd_search_symbol(args.repo, args.query, args.kind, args.limit)
    elif args.cmd == "node":           cmd_node(args.repo, args.symbol, args.kind)
    elif args.cmd == "callers":        cmd_callers(args.repo, args.symbol, args.limit)
    elif args.cmd == "callees":        cmd_callees(args.repo, args.symbol, args.limit)
    elif args.cmd == "impact":         cmd_impact(args.repo, args.symbol, args.depth)
    elif args.cmd == "explore_symbols": cmd_explore_symbols(args.repo, args.query, args.max_symbols)
    elif args.cmd == "call_chain":     cmd_call_chain(args.repo, args.root, args.max_depth, args.read_budget)
    elif args.cmd == "impact_surface": cmd_impact_surface(args.repo, args.symbol, args.read_budget)


if __name__ == "__main__":
    main()

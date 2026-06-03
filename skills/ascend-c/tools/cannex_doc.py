#!/usr/bin/env python3
"""CannEx 文档查询 CLI（薄 wrapper）。

本文件只负责 argparse/命令行分发 → 调用 lib api_* → 打印 JSON。

Usage:
  cannex_doc.py list
  cannex_doc.py meta <name_or_id>
  cannex_doc.py structure <name_or_id>
  cannex_doc.py pages <name_or_id> <range>
  cannex_doc.py lookup <name_or_id> <api_name>
"""
import json
import os
import sys
from pathlib import Path

_ROOT = Path(os.environ.get("CANNEX_ROOT") or Path(__file__).resolve().parents[3])
sys.path.insert(0, str(_ROOT / "lib"))

from cannex_knowledge import retriever_doc as D  # noqa: E402


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_list():
    docs = D.api_list()
    _print({"source_type": "metadata", "docs": docs})


def cmd_meta(key):
    result = D.api_meta(key)
    result["source_type"] = "original"
    _print(result)


def cmd_structure(key):
    _print(D.api_outline(key))


def cmd_pages(key, range_spec):
    _print(D.api_pages(key, range_spec))


def cmd_lookup(key, query):
    _print(D.api_lookup_api(key, query))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd, args = sys.argv[1], sys.argv[2:]
    if   cmd == "list":                          cmd_list()
    elif cmd == "meta"       and len(args) == 1: cmd_meta(args[0])
    elif cmd == "structure"  and len(args) == 1: cmd_structure(args[0])
    elif cmd == "pages"      and len(args) == 2: cmd_pages(args[0], args[1])
    elif cmd == "lookup"    and len(args) == 2: cmd_lookup(args[0], args[1])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()

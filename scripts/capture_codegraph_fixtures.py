#!/usr/bin/env python3
"""一次性脚本：真跑 codegraph CLI 捕获 fixture，存到 lib/cannex_knowledge/tests/fixtures/codegraph/。

用法：
  python3 scripts/capture_codegraph_fixtures.py

要求：
  - codegraph CLI ≥ 0.9.4 已装
  - ops-transformer 已索引（raw/repos/ops-transformer/.codegraph/ 存在）

会覆盖现有 fixture（这是有意的——升级 CodeGraph 后重跑此脚本刷新基线）。
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_PATH = ROOT / "raw" / "repos" / "ops-transformer"
FIXTURE_DIR = ROOT / "lib" / "cannex_knowledge" / "tests" / "fixtures" / "codegraph" / "ops_transformer"

# (filename, [cmd args after "codegraph"]) 列表
CAPTURES = [
    ("query_FlashAttention.json",
     ["query", "FlashAttention", "--limit", "5", "--json"]),
    ("query_FlashAttentionScoreKernelBase_kind_class.json",
     ["query", "FlashAttentionScoreKernelBase", "--limit", "3", "--kind", "class", "--json"]),
    ("query_DataCopy_limit_1.json",
     ["query", "DataCopy", "--limit", "1", "--json"]),
    ("callers_FlashAttentionScore.json",
     ["callers", "FlashAttentionScore", "--limit", "5", "--json"]),
    ("callees_FlashAttentionScore.json",
     ["callees", "FlashAttentionScore", "--limit", "5", "--json"]),
    ("impact_FlashAttentionScore.json",
     ["impact", "FlashAttentionScore", "--depth", "2", "--json"]),
    ("context_flashattention_pipeline_nocode.json",
     ["context", "FlashAttention pipeline", "-n", "5", "--no-code", "-f", "json"]),
]


def main() -> int:
    if not (REPO_PATH / ".codegraph").exists():
        print(f"ERROR: 索引不存在: {REPO_PATH}/.codegraph", file=sys.stderr)
        return 1

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR.parent / "__init__.py").touch(exist_ok=True)
    (FIXTURE_DIR.parent.parent / "__init__.py").touch(exist_ok=True)

    for fname, args in CAPTURES:
        cmd = ["codegraph", *args, "-p", str(REPO_PATH)]
        print(f"→ {fname}: {' '.join(cmd[:4])}...")
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            print(f"  FAIL: timeout after 60s", file=sys.stderr)
            return 1
        if r.returncode != 0:
            print(f"  FAIL: {r.stderr[:300]}", file=sys.stderr)
            return 1
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError as e:
            print(f"  FAIL: 输出非 JSON: {e}; head={r.stdout[:200]}", file=sys.stderr)
            return 1
        (FIXTURE_DIR / fname).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  ✓ saved ({len(json.dumps(data))} bytes)")

    print(f"\nDone. {len(CAPTURES)} fixtures saved to {FIXTURE_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

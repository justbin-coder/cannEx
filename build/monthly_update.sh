#!/usr/bin/env bash
# CannEx 月度更新管线
#
# 用法：bash build/monthly_update.sh [--dry-run]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$HOME/project/CANN/PageIndex/.venv/bin/python"
REPORT_DIR="$ROOT/reports"
REPORT="$REPORT_DIR/$(date +%Y%m).md"

DRY=""
if [[ "${1:-}" == "--dry-run" ]]; then DRY="--dry-run"; fi

mkdir -p "$REPORT_DIR"

{
  echo "# CannEx 月度更新报告"
  echo
  echo "- 日期：$(date +%Y-%m-%d)"
  echo "- 工作目录：$ROOT"
  echo
  echo "## 1. sync_sources"
  echo '```'
  $VENV_PY "$ROOT/build/sync_sources.py" $DRY 2>&1
  echo '```'
  echo
  echo "## 2. build_docs"
  echo '```'
  $VENV_PY "$ROOT/build/build_docs.py" 2>&1
  echo '```'
  echo
  echo "## 3. build_repos（仅 codegraph 索引，不触发 LLM bootstrap）"
  echo '```'
  $VENV_PY "$ROOT/build/build_repos.py" 2>&1
  echo '```'
  echo
  echo "## 4. 后续人工动作"
  echo "- 检查 workspace/repos/*/{repo_card,samples}.yaml 是否有需要更新的条目"
  echo "- review 并提交 workspace/ 与 reports/ 下变更"
} | tee "$REPORT"

echo
echo "[done] 报告：$REPORT"

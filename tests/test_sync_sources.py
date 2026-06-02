import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "build/sync_sources.py"


def test_dry_run_lists_enabled_repos_and_docs():
    """--dry-run 只打印不执行；列出 enabled=true 的项目"""
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert r.returncode == 0, r.stderr
    assert "ops-transformer" in r.stdout
    assert "cann-ops-adv" not in r.stdout, "enabled=false 的仓不应出现"
    assert "install" in r.stdout
    assert "operator_dev" in r.stdout


def test_reports_missing_docs_clearly():
    """docs 文件不存在时报告清楚（不报错退出，提示用户手动放置）"""
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--docs-only", "--dry-run"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert r.returncode == 0
    assert "install" in r.stdout

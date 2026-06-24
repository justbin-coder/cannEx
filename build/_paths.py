"""离线构建脚本共用的外部依赖路径解析。

集中此处，避免各构建脚本各写一份硬编码路径。
"""
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def pageindex_dir() -> Path:
    """解析 PageIndex 安装目录，按优先级：

      1. 环境变量 CANNEX_PAGEINDEX_DIR（显式覆盖）
      2. 仓内 3rd/pageindex/PageIndex（3rd/pageindex/setup.sh 的默认安装位置）
      3. 旧默认 ~/project/CANN/PageIndex（历史位置，向后兼容）
    """
    env = os.environ.get("CANNEX_PAGEINDEX_DIR")
    if env:
        return Path(env).expanduser()
    vendored = _REPO_ROOT / "3rd" / "pageindex" / "PageIndex"
    if vendored.exists():
        return vendored
    return Path.home() / "project" / "CANN" / "PageIndex"

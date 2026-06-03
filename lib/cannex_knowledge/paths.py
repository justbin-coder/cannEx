"""集中路径解析。优先 CANNEX_ROOT 环境变量，否则回退到仓库根（搜索上层目录找到名为 CannEx 的目录）。"""
import os
from pathlib import Path


def _resolve_root() -> Path:
    env = os.environ.get("CANNEX_ROOT")
    if env:
        return Path(env).resolve()
    # 从 paths.py 往上搜索，找到名为 cannex 的目录（大小写不敏感）
    current = Path(__file__).resolve()
    while current != current.parent:  # 不是根目录
        if current.name.lower() == "cannex":
            return current
        current = current.parent
    # 回退：取 paths.py 的上两层（lib/cannex_knowledge 结构）
    return Path(__file__).resolve().parents[2]


CANNEX_ROOT = _resolve_root()
WORKSPACE = CANNEX_ROOT / "workspace"
META_FILE = WORKSPACE / "_meta.json"
REPOS_DIR = WORKSPACE / "repos"

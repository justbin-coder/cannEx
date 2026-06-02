"""读取 Phase 2 自己的 system prompt（prompts/system_prompt.md）。

与 Phase 1 完全解耦：webchat 直接读取自己的 system_prompt.md，不做正则裁剪。
"""
import os
from functools import lru_cache
from pathlib import Path


def _prompt_path() -> Path:
    override = os.environ.get("CANNEX_SYSTEM_PROMPT_PATH")
    if override:
        return Path(override)
    # prompt_loader.py: webchat/cannex_chat/agent/ → parents[1] = cannex_chat
    return Path(__file__).resolve().parents[1] / "prompts" / "system_prompt.md"


@lru_cache(maxsize=1)
def load_system_prompt() -> str:
    path = _prompt_path()
    if not path.exists():
        raise FileNotFoundError(f"system_prompt.md not found at {path}")
    return path.read_text(encoding="utf-8")

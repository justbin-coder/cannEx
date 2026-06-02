"""CodeGraph CLI 包装层。

负责：
  - subprocess 调用 codegraph CLI 并解析 JSON
  - camelCase → snake_case 字段 normalize
  - 版本检测（启动期）
  - 失败兜底 envelope（error + fallback_hint）

不负责：
  - 业务语义（哪些字段保留、组装方式）→ 由 retriever_repo.py 决定
  - SQL 直查 → 已废弃，本 Phase 全切到 CLI
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .paths import CANNEX_ROOT as ROOT, META_FILE


# ── 模块常量 ──────────────────────────────────────────────────────────────────

MIN_CODEGRAPH_VERSION = (0, 9, 4)  # callers/callees/impact 引入版本


# ── codegraph 绝对路径解析 ─────────────────────────────────────────────────────
# 不依赖多层进程透传出来的 PATH：worker 子进程（chainlit -w / 非登录 shell 启动）
# 的 PATH 常缺 nvm bin 目录。按优先级显式探测，返回可执行文件的绝对路径。

def _resolve_codegraph_bin() -> str:
    """按优先级解析 codegraph 可执行文件路径，找不到时返回裸名 'codegraph'。

    顺序：CANNEX_CODEGRAPH_BIN 覆盖 → PATH(shutil.which) → $NVM_BIN → nvm versions 目录。
    每次调用都重新解析，避免缓存掉环境变化（worker 长驻进程友好）。
    """
    override = os.environ.get("CANNEX_CODEGRAPH_BIN")
    if override and Path(override).is_file():
        return override

    found = shutil.which("codegraph")
    if found:
        return found

    nvm_bin = os.environ.get("NVM_BIN")
    if nvm_bin:
        cand = Path(nvm_bin) / "codegraph"
        if cand.is_file():
            return str(cand)

    nvm_dir = os.environ.get("NVM_DIR") or str(Path.home() / ".nvm")
    versions = Path(nvm_dir) / "versions" / "node"
    if versions.is_dir():
        for v in sorted(versions.iterdir(), reverse=True):
            cand = v / "bin" / "codegraph"
            if cand.is_file():
                return str(cand)

    return "codegraph"  # 兜底：交给 subprocess 抛 FileNotFoundError

_FIELD_MAP = {
    "filePath": "file_path",
    "startLine": "start_line",
    "endLine": "end_line",
    "startColumn": "start_column",
    "endColumn": "end_column",
    "qualifiedName": "qualified_name",
    "isExported": "is_exported",
    "isAsync": "is_async",
    "isStatic": "is_static",
    "isAbstract": "is_abstract",
    "updatedAt": "updated_at",
    "nodeCount": "node_count",
    "edgeCount": "edge_count",
    "entryPoints": "entry_points",
}


# ── 版本检测 ──────────────────────────────────────────────────────────────────

_VER_RE = re.compile(r"^\s*(\d+)\.(\d+)\.(\d+)")


def check_codegraph_version() -> tuple[int, int, int] | None:
    """返回 (major, minor, patch) 或 None（CLI 缺失/无法解析）。"""
    try:
        r = subprocess.run(
            [_resolve_codegraph_bin(), "--version"],
            capture_output=True, timeout=5, text=True,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    m = _VER_RE.match(r.stdout)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def assert_codegraph_ready() -> None:
    """worker 启动期调用。CLI 缺失或版本不足时抛 SystemExit。"""
    v = check_codegraph_version()
    if v is None:
        raise SystemExit(
            "ERROR: codegraph CLI 未安装或不可用。"
            "请运行 `npm i -g @colbymchenry/codegraph@latest` 后重试。"
        )
    if v < MIN_CODEGRAPH_VERSION:
        cur = ".".join(map(str, v))
        need = ".".join(map(str, MIN_CODEGRAPH_VERSION))
        raise SystemExit(
            f"ERROR: codegraph CLI 版本 {cur} 太旧（callers/callees/impact 在 {need}+ 引入）。"
            f"请运行 `npm i -g @colbymchenry/codegraph@latest` 升级。"
        )


# ── 字段 normalize ────────────────────────────────────────────────────────────

def _normalize_keys(obj):
    """递归把 CodeGraph 返回的 camelCase 字段映射到 snake_case。

    只重命名 _FIELD_MAP 里登记过的字段，其他字段原样保留。
    """
    if isinstance(obj, dict):
        return {_FIELD_MAP.get(k, k): _normalize_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_keys(x) for x in obj]
    return obj


# ── 主调用函数 ────────────────────────────────────────────────────────────────

def _get_repo_path(repo: str) -> Path | None:
    """从 _meta.json 拿到 repo 的 local_path 绝对路径，索引缺失时返回 None。"""
    meta = json.loads(META_FILE.read_text(encoding="utf-8"))
    entry = next((r for r in meta.get("repos", []) if r["name"] == repo), None)
    if not entry:
        return None
    local = (ROOT / entry["local_path"]).resolve()
    if not (local / ".codegraph").exists():
        return None
    return local


def call_cli(
    repo: str,
    subcommand: str,
    positional: str,
    flags: list[str] = (),
    json_flag="--json",
    timeout: int = 10,
) -> dict:
    """统一调用 codegraph CLI 子命令，返回解析后的 JSON dict 或 error envelope。

    json_flag: 对 query/callers/callees/impact 用 "--json"；
               对 context 子命令传 ["-f", "json"]。

    返回的 dict 还未经 _normalize_keys；调用方按需 normalize。
    """
    repo_path = _get_repo_path(repo)
    if repo_path is None:
        return {
            "error": f"repo '{repo}' has no codegraph index",
            "fallback_hint": (
                f"运行 `python3 build/build_repos.py` 建索引，"
                f"或用 api_list_files('{repo}') 浏览原始目录结构"
            ),
        }

    json_tokens = [json_flag] if isinstance(json_flag, str) else list(json_flag)
    cmd = [_resolve_codegraph_bin(), subcommand, positional,
           "-p", str(repo_path), *flags, *json_tokens]

    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, text=True)
    except subprocess.TimeoutExpired:
        return {
            "error": f"codegraph cli timeout after {timeout}s (cmd={cmd[:3]}...)",
            "fallback_hint": "尝试更窄的 query 范围或用更轻量的 api_node",
        }
    except FileNotFoundError:
        return {
            "error": "codegraph cli not found in PATH",
            "fallback_hint": "运行 `npm i -g @colbymchenry/codegraph@latest`",
        }

    if r.returncode != 0:
        return {
            "error": f"codegraph cli failed: {r.stderr[:500]}",
            "fallback_hint": "尝试用 api_list_files / api_read_file 直接探索",
        }

    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError as e:
        # codegraph 对未索引符号（宏、部分模板特化）会往 stdout 打印人类可读提示
        # `ℹ Symbol "X" not found` 而非 JSON，需转成干净的 envelope 而非解析错误。
        if "not found" in r.stdout.lower():
            return {
                "error": f"symbol not found in code graph: {positional}",
                "fallback_hint": (
                    "该符号未被 CodeGraph 索引（宏/模板特化是已知盲区）。"
                    "先用 api_search_symbol 确认符号名，或用 api_read_file 直接读源码定位。"
                ),
            }
        return {
            "error": f"codegraph cli output not JSON: {e}; head={r.stdout[:200]}",
            "fallback_hint": None,
        }

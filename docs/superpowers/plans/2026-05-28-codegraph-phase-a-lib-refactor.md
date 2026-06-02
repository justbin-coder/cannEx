# CodeGraph 接入 + lib 重构 Implementation Plan（Phase A）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `lib/cannex_knowledge/retriever_repo.py` 中接入 CodeGraph CLI v0.9.6，新增 `search_symbol / node / callers / callees / impact / explore_symbols` 六个 API；废弃 SQL 直查 `api_symbol` / `api_context`；简化 `samples.yaml` schema（删 `recommendation_reason`，`apis_used` 改半自动）。Phase A 完成后 lib 层完整可用，不动 CLI 子命令 / SKILL / prompt（这些在 Phase B）。

**Architecture:** subprocess 调 CodeGraph CLI（`-j --json` 或 `-f json`），lib 包一层 envelope（`{source_type, evidence, data, error, fallback_hint}`）+ camelCase→snake_case normalize。Record-replay 测试：首次真跑 codegraph 捕获 JSON 存 fixtures/，CI 用 monkeypatch subprocess 回放。

**Tech Stack:** Python 3.11, pytest（`asyncio_mode=auto`），CodeGraph CLI ≥ 0.9.4（实测 0.9.6），SQLite（仅保留给文档侧 PageIndex，本 Phase 不动）。

**Spec reference:** `docs/superpowers/specs/2026-05-28-codegraph-integration-redesign.md`

---

## File Structure

**新建：**
- `lib/cannex_knowledge/codegraph_client.py` — CodeGraph CLI 包装层（`_codegraph_call` + 字段 normalize + 版本检测）
- `lib/cannex_knowledge/tests/test_codegraph_client.py`
- `lib/cannex_knowledge/tests/fixtures/codegraph/__init__.py`
- `lib/cannex_knowledge/tests/fixtures/codegraph/ops_transformer/` 目录 + 多个 `.json` fixture
- `scripts/capture_codegraph_fixtures.py` — 一次性 fixture 捕获脚本
- `build/prompts/ascend_c_apis.yaml` — Ascend C 已知 API 字典（半自动提取 `apis_used` 用）

**修改：**
- `lib/cannex_knowledge/retriever_repo.py` — 新增 6 个 api_*；废弃旧 `api_symbol` SQL 实现（改委托）；删除 `api_context`（如存在）；改造 `api_list_samples` 移除 `recommendation_reason`；统一 envelope schema
- `lib/cannex_knowledge/tests/test_retriever_repo.py` — 新增 6 个 api_* 测试；删除 SQL 直查相关测试
- `lib/cannex_knowledge/__init__.py` — re-export 新模块
- `workspace/repos/ops-transformer/samples.yaml` — 删除每条目的 `recommendation_reason` 字段
- `build/prompts/bootstrap_samples.md` — 删除 `recommendation_reason` 字段定义；`apis_used` 改半自动说明

**不动：**
- `skills/ascend-c/tools/cannex_repo.py`（Phase B 处理）
- `skills/ascend-c/SKILL.md`（Phase B 处理）
- `skills/ascend-c/references/codegraph-guide.md`（Phase B 处理）
- `webchat/cannex_chat/prompts/system_prompt.md`（Phase B 处理）
- `webchat/cannex_chat/worker/server.py`（Phase B 处理）
- `lib/cannex_knowledge/retriever_doc.py`（文档侧不动）

---

## Task 1: 前置检查 + codegraph_client 骨架 + 版本检测

**Files:**
- Create: `lib/cannex_knowledge/codegraph_client.py`
- Create: `lib/cannex_knowledge/tests/test_codegraph_client.py`

### Step 1: 验证 codegraph CLI ≥ 0.9.4 可用

Run:
```bash
which codegraph && codegraph --version
```
Expected: 输出路径 + 版本号 ≥ 0.9.4。若 < 0.9.4 或缺失，先 `npm i -g @colbymchenry/codegraph@latest` 再继续。

### Step 2: 验证 ops-transformer 索引可用

Run:
```bash
ls /Users/justbin/Desktop/CannEx/raw/repos/ops-transformer/.codegraph/codegraph.db
codegraph callers FlashAttentionScore -p /Users/justbin/Desktop/CannEx/raw/repos/ops-transformer --limit 1 --json
```
Expected: db 文件存在；callers 输出 JSON `{symbol, callers: [...]}`。

### Step 3: 写 codegraph_client 失败测试

创建 `lib/cannex_knowledge/tests/test_codegraph_client.py`：

```python
"""codegraph_client 单元测试。"""
import json
import subprocess
from unittest.mock import patch

import pytest

from cannex_knowledge import codegraph_client as cgc


def test_check_version_returns_tuple(monkeypatch):
    """check_codegraph_version 解析 `codegraph --version` 输出为 (major, minor, patch) tuple。"""
    def fake_run(cmd, **kwargs):
        class R:
            returncode = 0
            stdout = "0.9.6\n"
            stderr = ""
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert cgc.check_codegraph_version() == (0, 9, 6)


def test_check_version_returns_none_when_cli_missing(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("codegraph: command not found")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert cgc.check_codegraph_version() is None


def test_normalize_keys_camel_to_snake():
    raw = {"filePath": "a.cpp", "startLine": 1, "qualifiedName": "ns::F",
           "nested": {"endLine": 10, "isExported": True}}
    out = cgc._normalize_keys(raw)
    assert out == {
        "file_path": "a.cpp",
        "start_line": 1,
        "qualified_name": "ns::F",
        "nested": {"end_line": 10, "is_exported": True},
    }


def test_normalize_keys_preserves_unknown_fields():
    raw = {"custom_field": "x", "filePath": "y"}
    out = cgc._normalize_keys(raw)
    assert out == {"custom_field": "x", "file_path": "y"}


def test_normalize_keys_handles_list():
    raw = [{"filePath": "a"}, {"filePath": "b"}]
    out = cgc._normalize_keys(raw)
    assert out == [{"file_path": "a"}, {"file_path": "b"}]
```

### Step 4: 跑测试确认失败

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/test_codegraph_client.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'cannex_knowledge.codegraph_client'`）

### Step 5: 实现 codegraph_client 骨架

创建 `lib/cannex_knowledge/codegraph_client.py`：

```python
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
import re
import subprocess
from pathlib import Path

from .paths import CANNEX_ROOT as ROOT, META_FILE


# ── 模块常量 ──────────────────────────────────────────────────────────────────

MIN_CODEGRAPH_VERSION = (0, 9, 4)  # callers/callees/impact 引入版本

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
            ["codegraph", "--version"],
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
    json_flag = "--json",
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
    cmd = ["codegraph", subcommand, positional,
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
        return {
            "error": f"codegraph cli output not JSON: {e}; head={r.stdout[:200]}",
            "fallback_hint": None,
        }
```

### Step 6: 跑测试确认通过

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/test_codegraph_client.py -v`
Expected: PASS（5 passed）

### Step 7: Commit

```bash
cd ~/Desktop/CannEx
git add lib/cannex_knowledge/codegraph_client.py lib/cannex_knowledge/tests/test_codegraph_client.py
git commit -m "$(cat <<'EOF'
feat(lib): 新增 codegraph_client 包装层 + 版本检测 + camelCase normalize

为 Phase A 的 CodeGraph CLI 接入打底：
- check_codegraph_version / assert_codegraph_ready
- _normalize_keys: filePath→file_path 等 14 个字段映射
- call_cli: 统一 subprocess 调用 + 错误兜底 envelope

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Record-replay fixtures 捕获脚本

**Files:**
- Create: `scripts/capture_codegraph_fixtures.py`
- Create: `lib/cannex_knowledge/tests/fixtures/codegraph/__init__.py`
- Create: `lib/cannex_knowledge/tests/fixtures/codegraph/ops_transformer/*.json`（通过脚本生成）

### Step 1: 写 fixture 捕获脚本

创建 `scripts/capture_codegraph_fixtures.py`：

```python
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

# (filename, [cmd args]) 列表
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

    for fname, args in CAPTURES:
        cmd = ["codegraph", *args, "-p", str(REPO_PATH)]
        # 注意：args 末尾的 --json / -f json 在 -p 前还是后都可以，CLI 都接受
        print(f"→ {fname}: {' '.join(cmd[:4])}...")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
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
```

### Step 2: 跑脚本捕获 fixtures

Run:
```bash
cd ~/Desktop/CannEx
chmod +x scripts/capture_codegraph_fixtures.py
python3 scripts/capture_codegraph_fixtures.py
```
Expected: 输出 7 条 `✓ saved`，结尾 `Done. 7 fixtures saved to ...`。

### Step 3: 验证 fixtures 文件齐全且非空

Run:
```bash
ls -l lib/cannex_knowledge/tests/fixtures/codegraph/ops_transformer/ | awk '{print $5, $9}'
```
Expected: 7 个 .json 文件，每个 size > 100 字节。

### Step 4: 创建 __init__.py 让 fixtures 目录可作为包子目录

Run:
```bash
cd ~/Desktop/CannEx
touch lib/cannex_knowledge/tests/fixtures/__init__.py
touch lib/cannex_knowledge/tests/fixtures/codegraph/__init__.py
```

### Step 5: Commit

```bash
cd ~/Desktop/CannEx
git add scripts/capture_codegraph_fixtures.py lib/cannex_knowledge/tests/fixtures/
git commit -m "$(cat <<'EOF'
feat(lib): 添加 codegraph fixture 捕获脚本 + 7 条 ops-transformer 基线

scripts/capture_codegraph_fixtures.py: 一次性脚本，真跑 codegraph CLI
捕获 query/callers/callees/impact/context 典型输出存盘。
CI 用 monkeypatch subprocess 回放这些 fixtures。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `api_search_symbol` TDD 接入

**Files:**
- Modify: `lib/cannex_knowledge/retriever_repo.py`（新增 `api_search_symbol`）
- Modify: `lib/cannex_knowledge/tests/test_retriever_repo.py`（新增测试）

### Step 1: 写 api_search_symbol 失败测试

在 `lib/cannex_knowledge/tests/test_retriever_repo.py` 末尾追加：

```python
import json
from pathlib import Path

from cannex_knowledge import retriever_repo as r
from cannex_knowledge import codegraph_client as cgc


_FIXTURES = Path(__file__).parent / "fixtures" / "codegraph" / "ops_transformer"


def _load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _stub_call_cli(monkeypatch, fixture_name: str):
    """monkeypatch codegraph_client.call_cli 返回指定 fixture 内容。"""
    data = _load_fixture(fixture_name)
    def fake(*args, **kwargs):
        return data
    monkeypatch.setattr(cgc, "call_cli", fake)


def test_api_search_symbol_returns_envelope_with_evidence(monkeypatch):
    _stub_call_cli(monkeypatch, "query_FlashAttention.json")
    res = r.api_search_symbol("ops-transformer", "FlashAttention", limit=5)

    assert res["source_type"] == "original"
    assert "matches" in res["data"]
    assert len(res["data"]["matches"]) >= 1

    first = res["data"]["matches"][0]
    # 字段已 normalize 到 snake_case
    assert "file_path" in first
    assert "start_line" in first
    assert "qualified_name" in first
    assert "score" in first  # ranking 字段透传给 LLM

    # evidence 列表与 matches 对齐
    assert len(res["evidence"]) == len(res["data"]["matches"])
    assert res["evidence"][0]["file_path"] == first["file_path"]
    assert res["evidence"][0]["start_line"] == first["start_line"]


def test_api_search_symbol_with_kind_filter(monkeypatch):
    _stub_call_cli(monkeypatch, "query_FlashAttentionScoreKernelBase_kind_class.json")
    res = r.api_search_symbol(
        "ops-transformer", "FlashAttentionScoreKernelBase", kind="class", limit=3,
    )
    assert res["source_type"] == "original"
    assert all(m["kind"] == "class" for m in res["data"]["matches"])


def test_api_search_symbol_propagates_error_envelope(monkeypatch):
    def fake(*args, **kwargs):
        return {"error": "repo 'foo' has no codegraph index",
                "fallback_hint": "运行 build_repos.py"}
    monkeypatch.setattr(cgc, "call_cli", fake)
    res = r.api_search_symbol("foo", "X")
    assert res["error"] is not None
    assert res["fallback_hint"] is not None
    assert res["data"] == {}
```

### Step 2: 跑测试确认失败

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/test_retriever_repo.py::test_api_search_symbol_returns_envelope_with_evidence -v`
Expected: FAIL（`AttributeError: module 'cannex_knowledge.retriever_repo' has no attribute 'api_search_symbol'`）

### Step 3: 实现 api_search_symbol + envelope helper

在 `lib/cannex_knowledge/retriever_repo.py` 顶部 import 区追加：

```python
from . import codegraph_client as _cgc
```

然后在文件末尾追加：

```python
# ── envelope helper（本 Phase 新增）─────────────────────────────────────────

def _envelope(
    source_type: str,
    data: dict,
    evidence: list = None,
    error: str | None = None,
    fallback_hint: str | None = None,
) -> dict:
    """统一返回 schema：{source_type, evidence, data, error, fallback_hint}。"""
    return {
        "source_type": source_type,
        "evidence": evidence or [],
        "data": data,
        "error": error,
        "fallback_hint": fallback_hint,
    }


def _evidence_from_matches(matches: list) -> list:
    """从 normalize 后的 matches 抽出 evidence 列表。"""
    out = []
    for m in matches:
        if "file_path" in m and "start_line" in m:
            out.append({
                "file_path": m["file_path"],
                "start_line": m["start_line"],
                "end_line": m.get("end_line", m["start_line"]),
            })
    return out


# ── L1 符号定位（CodeGraph CLI 接入）────────────────────────────────────────

def api_search_symbol(
    name: str,
    query: str,
    kind: str | None = None,
    limit: int = 10,
) -> dict:
    """FTS5 + ranking 符号搜索。包装 `codegraph query`。

    返回 envelope，data = {matches: [...]}，每个 match 含 score（CodeGraph 内部 ranking）。
    """
    flags = ["-l", str(limit)]
    if kind:
        flags.extend(["-k", kind])
    raw = _cgc.call_cli(name, "query", query, flags=flags)

    if "error" in raw and raw["error"]:
        return _envelope("original", {}, error=raw["error"],
                         fallback_hint=raw.get("fallback_hint"))

    # codegraph query 返回 list: [{node: {...}, score: float}, ...]
    matches = []
    for item in _cgc._normalize_keys(raw):
        n = item.get("node", {}) if isinstance(item, dict) else {}
        if not n:
            continue
        matches.append({**n, "score": item.get("score")})

    return _envelope(
        "original",
        {"matches": matches},
        evidence=_evidence_from_matches(matches),
    )
```

### Step 4: 跑测试确认通过

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/test_retriever_repo.py -v -k search_symbol`
Expected: PASS（3 passed）

### Step 5: 跑现有全套测试确认无回归

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/ -v`
Expected: 全部 PASS（含之前的 paths / retriever_doc / retriever_repo 老测试）。

### Step 6: Commit

```bash
cd ~/Desktop/CannEx
git add lib/cannex_knowledge/retriever_repo.py lib/cannex_knowledge/tests/test_retriever_repo.py
git commit -m "$(cat <<'EOF'
feat(lib): api_search_symbol 接入 codegraph query --json + envelope schema

- 引入统一 _envelope helper：{source_type, evidence, data, error, fallback_hint}
- _evidence_from_matches：从 matches 抽 file:line 引用列表
- api_search_symbol：包装 codegraph query，透传 score 字段给 LLM

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `api_node` TDD 接入

**Files:**
- Modify: `lib/cannex_knowledge/retriever_repo.py`
- Modify: `lib/cannex_knowledge/tests/test_retriever_repo.py`

### Step 1: 写 api_node 失败测试

在 `test_retriever_repo.py` 追加：

```python
def test_api_node_returns_single_node(monkeypatch):
    _stub_call_cli(monkeypatch, "query_DataCopy_limit_1.json")
    res = r.api_node("ops-transformer", "DataCopy")

    assert res["source_type"] == "original"
    assert "node" in res["data"]
    node = res["data"]["node"]
    assert node["name"] == "DataCopy" or "DataCopy" in node.get("qualified_name", "")
    assert "file_path" in node
    assert "start_line" in node
    assert len(res["evidence"]) == 1


def test_api_node_missing_returns_error(monkeypatch):
    def fake(*args, **kwargs):
        return []  # codegraph query 找不到时返回空 list
    monkeypatch.setattr(cgc, "call_cli", fake)
    res = r.api_node("ops-transformer", "NonExistentXYZ")
    assert res["data"] == {}
    assert res["error"] is not None
    assert "未找到" in res["error"] or "not found" in res["error"].lower()
    assert res["fallback_hint"] is not None
```

### Step 2: 跑测试确认失败

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/test_retriever_repo.py -v -k api_node`
Expected: FAIL（`AttributeError: ...api_node`）

### Step 3: 实现 api_node

在 `retriever_repo.py` 的 L1 节追加：

```python
def api_node(name: str, symbol: str, kind: str | None = None) -> dict:
    """精确查单个符号（拿第一条 query 结果的完整 node info）。

    CodeGraph CLI 不暴露独立 `node` 子命令；用 `query --limit 1` 等价。
    """
    flags = ["-l", "1"]
    if kind:
        flags.extend(["-k", kind])
    raw = _cgc.call_cli(name, "query", symbol, flags=flags)

    if isinstance(raw, dict) and raw.get("error"):
        return _envelope("original", {}, error=raw["error"],
                         fallback_hint=raw.get("fallback_hint"))

    items = _cgc._normalize_keys(raw)
    if not items:
        return _envelope(
            "original", {},
            error=f"未找到符号 '{symbol}'（repo={name}）",
            fallback_hint=(
                f"用 api_search_symbol('{name}', '{symbol}', kind=None) "
                f"模糊查找，或用 api_list_files 探索目录"
            ),
        )

    first = items[0]
    node = first.get("node", {}) if isinstance(first, dict) else {}
    if "score" in first:
        node["score"] = first["score"]

    return _envelope(
        "original",
        {"node": node},
        evidence=_evidence_from_matches([node]) if node else [],
    )
```

### Step 4: 跑测试确认通过

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/test_retriever_repo.py -v -k api_node`
Expected: PASS（2 passed）

### Step 5: Commit

```bash
cd ~/Desktop/CannEx
git add lib/cannex_knowledge/retriever_repo.py lib/cannex_knowledge/tests/test_retriever_repo.py
git commit -m "$(cat <<'EOF'
feat(lib): api_node 精确符号查询（codegraph query --limit 1 等价）

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `api_callers` + `api_callees` TDD 接入

两个 API schema 几乎一致，一起做。

**Files:**
- Modify: `lib/cannex_knowledge/retriever_repo.py`
- Modify: `lib/cannex_knowledge/tests/test_retriever_repo.py`

### Step 1: 写 callers/callees 失败测试

追加到 `test_retriever_repo.py`：

```python
def test_api_callers_returns_list_with_evidence(monkeypatch):
    _stub_call_cli(monkeypatch, "callers_FlashAttentionScore.json")
    res = r.api_callers("ops-transformer", "FlashAttentionScore", limit=5)

    assert res["source_type"] == "original"
    assert res["data"]["symbol"] == "FlashAttentionScore"
    assert len(res["data"]["callers"]) >= 1

    first = res["data"]["callers"][0]
    assert "name" in first
    assert "kind" in first
    assert "file_path" in first
    assert "start_line" in first

    # evidence 反映每个 caller 的位置
    assert len(res["evidence"]) == len(res["data"]["callers"])


def test_api_callees_returns_list(monkeypatch):
    _stub_call_cli(monkeypatch, "callees_FlashAttentionScore.json")
    res = r.api_callees("ops-transformer", "FlashAttentionScore", limit=5)

    assert res["source_type"] == "original"
    assert res["data"]["symbol"] == "FlashAttentionScore"
    assert "callees" in res["data"]


def test_api_callers_empty_returns_hint(monkeypatch):
    def fake(*args, **kwargs):
        return {"symbol": "X", "callers": []}
    monkeypatch.setattr(cgc, "call_cli", fake)
    res = r.api_callers("ops-transformer", "X")
    assert res["data"]["callers"] == []
    # 空结果也是合法成功（不一定 error），但必须有引导
    assert res["fallback_hint"] is not None
```

### Step 2: 跑测试确认失败

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/test_retriever_repo.py -v -k "callers or callees"`
Expected: FAIL（找不到 `api_callers`）

### Step 3: 实现 api_callers / api_callees

在 `retriever_repo.py` 追加（放在 L1 之后作为 L2 节）：

```python
# ── L2 图关系反查（CodeGraph CLI v0.9.4+）─────────────────────────────────────

def _call_graph_query(name: str, subcommand: str, symbol: str, limit: int) -> dict:
    """callers / callees 共享实现，差异只在 subcommand。"""
    flags = ["-l", str(limit)]
    raw = _cgc.call_cli(name, subcommand, symbol, flags=flags)
    if isinstance(raw, dict) and raw.get("error"):
        return _envelope("original", {}, error=raw["error"],
                         fallback_hint=raw.get("fallback_hint"))

    data = _cgc._normalize_keys(raw)
    items_key = "callers" if subcommand == "callers" else "callees"
    items = data.get(items_key, [])

    fallback = None
    if not items:
        fallback = (
            f"未找到 '{symbol}' 的 {items_key}。"
            f"CodeGraph 无法穿透宏展开/模板特化，"
            f"建议 api_read_file 直读源码定位调用点。"
        )

    return _envelope(
        "original",
        data,
        evidence=_evidence_from_matches(items),
        fallback_hint=fallback,
    )


def api_callers(name: str, symbol: str, limit: int = 20) -> dict:
    """反查谁调用了 symbol。包装 `codegraph callers`。"""
    return _call_graph_query(name, "callers", symbol, limit)


def api_callees(name: str, symbol: str, limit: int = 20) -> dict:
    """反查 symbol 调用了谁。包装 `codegraph callees`。"""
    return _call_graph_query(name, "callees", symbol, limit)
```

### Step 4: 跑测试确认通过

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/test_retriever_repo.py -v -k "callers or callees"`
Expected: PASS（3 passed）

### Step 5: Commit

```bash
cd ~/Desktop/CannEx
git add lib/cannex_knowledge/retriever_repo.py lib/cannex_knowledge/tests/test_retriever_repo.py
git commit -m "$(cat <<'EOF'
feat(lib): api_callers/api_callees 接入 codegraph CLI（L2 图关系反查）

- 共享 _call_graph_query 实现，subcommand 区分
- 空结果带 fallback_hint 引导 read_file 兜底（应对宏/模板特化）

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `api_impact` TDD 接入

**Files:**
- Modify: `lib/cannex_knowledge/retriever_repo.py`
- Modify: `lib/cannex_knowledge/tests/test_retriever_repo.py`

### Step 1: 写 api_impact 失败测试

追加到 `test_retriever_repo.py`：

```python
def test_api_impact_returns_radius(monkeypatch):
    _stub_call_cli(monkeypatch, "impact_FlashAttentionScore.json")
    res = r.api_impact("ops-transformer", "FlashAttentionScore", depth=2)

    assert res["source_type"] == "original"
    d = res["data"]
    assert d["symbol"] == "FlashAttentionScore"
    assert d["depth"] == 2
    # CodeGraph 的 nodeCount/edgeCount 已 normalize 为 snake_case
    assert "node_count" in d
    assert "edge_count" in d
    assert "affected" in d
    assert len(d["affected"]) >= 1

    first = d["affected"][0]
    assert "file_path" in first
    assert "start_line" in first

    # evidence 应该是 affected 列表的位置
    assert len(res["evidence"]) == len(d["affected"])
```

### Step 2: 跑测试确认失败

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/test_retriever_repo.py -v -k api_impact`
Expected: FAIL

### Step 3: 实现 api_impact

追加到 `retriever_repo.py` L2 节：

```python
def api_impact(name: str, symbol: str, depth: int = 2) -> dict:
    """分析修改 symbol 会波及哪些代码。包装 `codegraph impact`。

    超时 20s（impact 比 search 重）。
    """
    flags = ["-d", str(depth)]
    raw = _cgc.call_cli(name, "impact", symbol, flags=flags, timeout=20)
    if isinstance(raw, dict) and raw.get("error"):
        return _envelope("original", {}, error=raw["error"],
                         fallback_hint=raw.get("fallback_hint"))

    data = _cgc._normalize_keys(raw)
    return _envelope(
        "original",
        data,
        evidence=_evidence_from_matches(data.get("affected", [])),
    )
```

### Step 4: 跑测试确认通过

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/test_retriever_repo.py -v -k api_impact`
Expected: PASS（1 passed）

### Step 5: Commit

```bash
cd ~/Desktop/CannEx
git add lib/cannex_knowledge/retriever_repo.py lib/cannex_knowledge/tests/test_retriever_repo.py
git commit -m "$(cat <<'EOF'
feat(lib): api_impact 接入 codegraph impact（修改影响半径分析）

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `api_explore_symbols` TDD 接入

**Files:**
- Modify: `lib/cannex_knowledge/retriever_repo.py`
- Modify: `lib/cannex_knowledge/tests/test_retriever_repo.py`

### Step 1: 写 api_explore_symbols 失败测试

追加：

```python
def test_api_explore_symbols_returns_symbols_no_source(monkeypatch):
    _stub_call_cli(monkeypatch, "context_flashattention_pipeline_nocode.json")
    res = r.api_explore_symbols("ops-transformer", "FlashAttention pipeline", max_symbols=5)

    assert res["source_type"] == "original"
    d = res["data"]
    assert d["query"] == "FlashAttention pipeline"
    assert "summary" in d
    assert "entry_points" in d
    assert "symbols" in d  # 全量符号清单

    # 关键：不应该包含 source code 字段
    for sym in d["symbols"]:
        assert "source_code" not in sym
        assert "code" not in sym
        assert "content" not in sym
        # 但 file:line 必须有，让 LLM 后续 read_file
        assert "file_path" in sym
        assert "start_line" in sym

    # evidence 反映 entry_points + symbols 全集（去重）
    assert len(res["evidence"]) >= 1
```

### Step 2: 跑测试确认失败

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/test_retriever_repo.py -v -k explore_symbols`
Expected: FAIL

### Step 3: 实现 api_explore_symbols

追加到 `retriever_repo.py`：

```python
# ── L4 阙割版探索（context + --no-code）────────────────────────────────────

def api_explore_symbols(name: str, query: str, max_symbols: int = 30) -> dict:
    """任务相关的符号清单（CodeGraph context 输出，源码已剥除）。

    用 `codegraph context "<task>" -n <max> --no-code -f json`：
    - CodeGraph 内置 --no-code 不返回 code blocks
    - context 命令 JSON flag 是 `-f json` 不是 `--json`
    """
    flags = ["-n", str(max_symbols), "--no-code"]
    raw = _cgc.call_cli(
        name, "context", query,
        flags=flags,
        json_flag=["-f", "json"],
        timeout=20,
    )
    if isinstance(raw, dict) and raw.get("error"):
        return _envelope("original", {}, error=raw["error"],
                         fallback_hint=raw.get("fallback_hint"))

    data = _cgc._normalize_keys(raw)

    # 防御性：即使 CodeGraph 升级后回归带源码字段，lib 主动剥
    def _strip_code(items):
        for it in items or []:
            for k in ("source_code", "code", "content", "body"):
                it.pop(k, None)
        return items
    data["symbols"] = _strip_code(data.get("nodes") or data.get("symbols") or [])
    if "nodes" in data:
        del data["nodes"]
    data["entry_points"] = _strip_code(data.get("entry_points", []))

    # evidence: entry_points + symbols 去重（file_path+start_line 作 key）
    seen = set()
    evidence = []
    for item in (data["entry_points"] + data["symbols"]):
        key = (item.get("file_path"), item.get("start_line"))
        if key[0] and key not in seen:
            seen.add(key)
            evidence.append({
                "file_path": item["file_path"],
                "start_line": item["start_line"],
                "end_line": item.get("end_line", item["start_line"]),
            })

    return _envelope("original", data, evidence=evidence)
```

### Step 4: 跑测试确认通过

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/test_retriever_repo.py -v -k explore_symbols`
Expected: PASS（1 passed）

### Step 5: 全套回归

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/ -v`
Expected: 全部 PASS。

### Step 6: Commit

```bash
cd ~/Desktop/CannEx
git add lib/cannex_knowledge/retriever_repo.py lib/cannex_knowledge/tests/test_retriever_repo.py
git commit -m "$(cat <<'EOF'
feat(lib): api_explore_symbols 接入 codegraph context --no-code -f json

L4 阙割版：返回符号清单 + file:line 引用，不返回源码。
- CodeGraph 内置 --no-code 直接过滤
- 防御性二次剥除 source_code/code/content 字段
- evidence 去重 entry_points + symbols 的位置

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: 废弃 SQL 直查 `api_symbol` / `api_context`

**Files:**
- Modify: `lib/cannex_knowledge/retriever_repo.py`（删 SQL 实现、改委托）
- Modify: `lib/cannex_knowledge/tests/test_retriever_repo.py`（移除/替换 SQL 测试）

### Step 1: 列出 lib 中所有 sqlite3 / SELECT 引用作为 baseline

Run:
```bash
cd ~/Desktop/CannEx
grep -n "sqlite3\|SELECT \|FROM nodes" lib/cannex_knowledge/retriever_repo.py
```
Expected: 当前应该有几行（`api_symbol` 旧实现 + 任何遗留 `api_context`）。记下来。

### Step 2: 修改 `api_symbol` 委托给 `api_search_symbol`（保留以向后兼容 CLI）

在 `retriever_repo.py` 中找到现有的 `api_symbol` 函数（用 `SELECT FROM nodes WHERE name=?`），整段替换为：

```python
def api_symbol(name: str, symbol: str, kind: str = "any") -> dict:
    """[DEPRECATED] 向后兼容包装：委托给 api_search_symbol。

    旧 envelope: {matches, source_type}
    新 envelope: {source_type, evidence, data: {matches}, error, fallback_hint}

    为了 webchat worker handler 不破坏，仍按旧 schema 返回 matches。
    Phase B 中 worker handler 切到新 API 后此函数可彻底删除。
    """
    k = None if kind == "any" else kind
    res = api_search_symbol(name, symbol, kind=k, limit=10)
    if res.get("error"):
        return {"matches": [], "error": res["error"]}
    return {
        "matches": res["data"].get("matches", []),
        "source_type": "original",
    }
```

### Step 3: 删除 `api_context`（如存在）

```bash
cd ~/Desktop/CannEx
grep -n "def api_context" lib/cannex_knowledge/retriever_repo.py
```
若有，整段删除该函数。

### Step 4: 更新现有 `api_symbol` 测试（如果之前测了 SQL 实现细节）

打开 `lib/cannex_knowledge/tests/test_retriever_repo.py`，找到 `test_api_symbol_finds_kernel_base_via_sqlite` 等老测试。改为：

```python
def test_api_symbol_backwards_compat_delegates_to_search(monkeypatch):
    """api_symbol 应该委托给 api_search_symbol，旧 schema 返回 matches。"""
    _stub_call_cli(monkeypatch, "query_FlashAttentionScoreKernelBase_kind_class.json")
    res = r.api_symbol("ops-transformer", "FlashAttentionScoreKernelBase", kind="class")
    assert "matches" in res
    assert len(res["matches"]) >= 1
    assert res["source_type"] == "original"
```

删除任何依赖 `sqlite3.connect` 的旧测试。

### Step 5: 跑测试确认旧 + 新都通过

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/test_retriever_repo.py -v`
Expected: 全部 PASS。

### Step 6: 防回归 grep 验证

Run:
```bash
cd ~/Desktop/CannEx
echo "=== sqlite3 残留 ==="
grep -n "sqlite3\|sqlite3\.connect" lib/cannex_knowledge/retriever_repo.py || echo "CLEAN"
echo "=== nodes 表 SQL 残留 ==="
grep -n "FROM nodes\|FROM edges\|nodes_fts" lib/cannex_knowledge/retriever_repo.py || echo "CLEAN"
```
Expected: 两次都输出 `CLEAN`。

### Step 7: Commit

```bash
cd ~/Desktop/CannEx
git add lib/cannex_knowledge/retriever_repo.py lib/cannex_knowledge/tests/test_retriever_repo.py
git commit -m "$(cat <<'EOF'
refactor(lib): 废弃 api_symbol/api_context 直查 sqlite，全切到 codegraph CLI

- api_symbol：保留旧 schema 包装，内部委托 api_search_symbol（webchat 切换后可删）
- api_context：彻底删除（已是反模式，由 api_explore_symbols 替代）
- lib 内 sqlite3/FROM nodes/FROM edges 残留为 0（已 grep 验证）

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: samples.yaml schema 简化 + Ascend C API 字典

**Files:**
- Create: `build/prompts/ascend_c_apis.yaml`
- Modify: `build/prompts/bootstrap_samples.md`
- Modify: `workspace/repos/ops-transformer/samples.yaml`
- Modify: `lib/cannex_knowledge/retriever_repo.py`（`api_list_samples` 移除 `recommendation_reason`）
- Modify: `lib/cannex_knowledge/tests/test_retriever_repo.py`

### Step 1: 新建 Ascend C API 字典

创建 `build/prompts/ascend_c_apis.yaml`：

```yaml
# Ascend C 已知公开 API 字典，用于 bootstrap_samples 的 apis_used 半自动提取。
# 维护规则：CANN 官方新增 API 时追加；不再使用的 API 不要删除（历史样例可能仍引用）。

memory_management:
  - TPipe
  - TQue
  - TBuf
  - GlobalTensor
  - LocalTensor

data_movement:
  - DataCopy
  - DataCopyPad
  - DataCopyExt
  - GetSysWorkSpacePtr
  - Gather
  - Scatter

compute_cube:
  - Matmul
  - MatmulType
  - TCubeTiling
  - MatmulImpl
  - Mmad

compute_vector:
  - Add
  - Sub
  - Mul
  - Div
  - Max
  - Min
  - Abs
  - Cast
  - Exp
  - Log
  - Sqrt
  - Relu
  - Softmax
  - LayerNorm
  - TopK
  - Sort
  - Reduce
  - ReduceSum
  - ReduceMax

sync_pipeline:
  - PipeBarrier
  - SetFlag
  - WaitFlag
  - CrossCoreSetFlag
  - CrossCoreWaitFlag

distributed:
  - HCCL
  - AllReduce
  - AllGather
  - ReduceScatter
```

### Step 2: 改 bootstrap_samples.md

打开 `build/prompts/bootstrap_samples.md`，把整个 YAML schema 输出区段（从 ` ```yaml ` 开始到 ` ``` ` 结束）替换为：

````markdown
## 输出要求

严格按以下 YAML schema 输出 samples: 列表，包裹在 ```yaml 中。
每条字段都必须填；不确定的填 "TBD: <你的猜测>"，便于人工 review。

`apis_used` 字段从 entry_files 的代码内容自动提取：
扫每个 entry_files 的源码，凡是匹配下方 Ascend C API 字典中任一条目的标识符，
都加入 apis_used（去重）。若代码不可获取，置为空列表 [] 并标注 "TBD: 代码未提取"。

### Ascend C API 字典（仅匹配以下名字）

{ascend_c_apis}

### 输出 schema

```yaml
samples:
  - id: <kebab-case 唯一 ID，如 flash-attention-score>
    name: <可读名，中英文均可>
    path: <相对仓根路径，如 attention/flash_attention_score>
    entry_files: [<核心 .cpp 或 .h 文件名>]
    computation_pattern: <vector | cube | vector_to_cube | cube_to_vector | fusion | TBD>
    apis_used: [<从 Ascend C API 字典自动匹配，去重>]
    complexity: <beginner | intermediate | expert | TBD>
    teaches:
      - <学习要点>
    limitations:
      - <已知局限或 "TBD">
    related_docs: []     # 关联文档章节，初稿留空，人工补
```

不要解释，只输出 YAML。
不要包含 recommendation_reason 字段。
````

### Step 3: 修改 ops-transformer samples.yaml 删除 recommendation_reason

Run:
```bash
cd ~/Desktop/CannEx
python3 - <<'EOF'
import re
from pathlib import Path

f = Path("workspace/repos/ops-transformer/samples.yaml")
src = f.read_text(encoding="utf-8")
# 匹配整行: `    recommendation_reason: "..."`（缩进 4 空格）
new = re.sub(r'^ {4}recommendation_reason:.*$\n?', '', src, flags=re.MULTILINE)
f.write_text(new, encoding="utf-8")
print(f"removed {src.count(chr(10)) - new.count(chr(10))} lines")
EOF
```
Expected: 输出 `removed N lines`（应该约等于 samples 条目数，本仓 12 条）。

### Step 4: 验证 samples.yaml 仍是合法 YAML

Run:
```bash
cd ~/Desktop/CannEx
python3 -c "
import yaml
data = yaml.safe_load(open('workspace/repos/ops-transformer/samples.yaml'))
samples = data['samples']
print(f'samples count: {len(samples)}')
print(f'first sample keys: {list(samples[0].keys())}')
assert all('recommendation_reason' not in s for s in samples), 'still has recommendation_reason'
print('OK')
"
```
Expected: `OK`，且 `first sample keys` 不含 `recommendation_reason`。

### Step 5: 修改 api_list_samples 移除该字段

打开 `lib/cannex_knowledge/retriever_repo.py`，找到 `api_list_samples` 函数。它当前返回的 samples 列表里**没有** `recommendation_reason` 字段（核对一下），如果有则移除。

当前 `api_list_samples` 返回的 sample dict 包含：`id / name / path / entry_files / computation_pattern / complexity / apis_used / teaches`。**不动**。

> 实际上现有 `api_list_samples` 没暴露 `recommendation_reason`，所以这步只是 sanity check。

补充一个**按 computation_pattern 过滤**的参数（spec §五要求）：

修改 `api_list_samples` 签名：

```python
def api_list_samples(name: str, pattern: str | None = None,
                     complexity: str | None = None,
                     computation_pattern: str | None = None) -> dict:
    """列出仓库的精选样例。

    过滤参数：
      pattern: 模糊匹配 name/id/computation_pattern（向后兼容字段）
      complexity: 严格匹配（beginner/intermediate/expert）
      computation_pattern: 严格匹配（vector/cube/vector_to_cube/cube_to_vector/fusion）
    """
    samples = load_samples(name)
    if pattern:
        p = pattern.lower()
        samples = [s for s in samples
                   if p in s.get("name", "").lower()
                   or p in s.get("id", "").lower()
                   or p in s.get("computation_pattern", "").lower()]
    if complexity:
        samples = [s for s in samples if s.get("complexity") == complexity]
    if computation_pattern:
        samples = [s for s in samples if s.get("computation_pattern") == computation_pattern]
    return {
        "repo": name,
        "count": len(samples),
        "samples": [
            {
                "id": s.get("id"),
                "name": s.get("name"),
                "path": s.get("path"),
                "entry_files": s.get("entry_files", []),
                "computation_pattern": s.get("computation_pattern"),
                "complexity": s.get("complexity"),
                "apis_used": s.get("apis_used", []),
                "teaches": s.get("teaches", []),
                # 注意：recommendation_reason 已永久删除，不再 expose
            }
            for s in samples
        ],
        "source_type": "metadata",
    }
```

### Step 6: 写 api_list_samples 新 filter 测试

追加到 `test_retriever_repo.py`：

```python
def test_api_list_samples_filter_by_computation_pattern():
    res = r.api_list_samples("ops-transformer", computation_pattern="vector_to_cube")
    assert res["count"] >= 1
    assert all(s["computation_pattern"] == "vector_to_cube" for s in res["samples"])


def test_api_list_samples_no_recommendation_reason_field():
    res = r.api_list_samples("ops-transformer")
    for s in res["samples"]:
        assert "recommendation_reason" not in s
```

### Step 7: 跑测试确认通过

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/test_retriever_repo.py -v -k list_samples`
Expected: PASS。

### Step 8: Commit

```bash
cd ~/Desktop/CannEx
git add build/prompts/ascend_c_apis.yaml build/prompts/bootstrap_samples.md \
        workspace/repos/ops-transformer/samples.yaml \
        lib/cannex_knowledge/retriever_repo.py \
        lib/cannex_knowledge/tests/test_retriever_repo.py
git commit -m "$(cat <<'EOF'
refactor(lib): samples.yaml schema 简化 + apis_used 半自动

- 删除 recommendation_reason 字段（lib API + bootstrap prompt + ops-transformer 仓数据）
- bootstrap_samples.md 改 apis_used 为"从代码 + Ascend C API 字典自动提取"
- 新建 build/prompts/ascend_c_apis.yaml 字典（5 类约 50 个 API）
- api_list_samples 新增 computation_pattern 过滤参数

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: 全量回归 + 防回归 grep + Phase A 收口

**Files:** 无（仅验证）

### Step 1: 全量测试

Run: `cd ~/Desktop/CannEx && python3 -m pytest -v`
Expected: 全部 PASS。如果 webchat 测试 fail，说明 Phase B 还没接 worker——记下 fail 项作为 Phase B Task 列表，**本 Phase 不修复**（webchat 改动是 Phase B 的事）。

### Step 2: lib 内 SQL 残留防回归

Run:
```bash
cd ~/Desktop/CannEx
echo "=== sqlite3 in lib/cannex_knowledge/retriever_repo.py ==="
grep -n "sqlite3\|sqlite3\.connect\|FROM nodes\|FROM edges\|nodes_fts" lib/cannex_knowledge/retriever_repo.py || echo "CLEAN"
```
Expected: `CLEAN`。

### Step 3: lib 内相关性排序防回归

Run:
```bash
cd ~/Desktop/CannEx
echo "=== suspicious ranking patterns in retriever_repo.py ==="
grep -nE "sorted\(.*score|sorted\(.*key=|\.sort\(.*key=|top_k\b|similarity\b" lib/cannex_knowledge/retriever_repo.py | grep -v "^.*#" || echo "CLEAN"
```
Expected: `CLEAN`（lib 不二次排序，CodeGraph 返回的 score 透传即可）。

### Step 4: lib 公共 API 自检

Run:
```bash
cd ~/Desktop/CannEx
python3 -c "
from cannex_knowledge import retriever_repo as r
expected = [
    'api_list', 'api_card', 'api_overview',
    'api_list_samples', 'api_read_sample',
    'api_list_files', 'api_read_file',
    'api_symbol',  # 旧兼容
    'api_search_symbol', 'api_node',
    'api_callers', 'api_callees', 'api_impact',
    'api_explore_symbols',
]
missing = [n for n in expected if not hasattr(r, n)]
print('missing:', missing if missing else 'NONE')
print('all good!' if not missing else 'FIX MISSING APIS')
"
```
Expected: `missing: NONE` 和 `all good!`。

### Step 5: 测试覆盖率检查（informational，不强制）

Run:
```bash
cd ~/Desktop/CannEx
python3 -m pytest lib/cannex_knowledge/tests/ --cov=lib/cannex_knowledge --cov-report=term-missing 2>&1 | tail -30
```
Expected: `retriever_repo.py` 覆盖率 ≥ 70%；`codegraph_client.py` 覆盖率 ≥ 80%。若不达标，补单元测试再 commit。

### Step 6: Phase A 收口 commit（若有零碎修复）

```bash
cd ~/Desktop/CannEx
git status
# 若有未 commit 的修复：
git add -A
git commit -m "$(cat <<'EOF'
test: Phase A 全量回归通过 + 防回归 grep 验证

- lib/cannex_knowledge/retriever_repo.py 无 sqlite3 / FROM nodes 残留
- lib 内无相关性二次排序（CodeGraph score 透传）
- 14 个 api_* 全部可 import

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Step 7: 标记 Phase A 完成

在本 plan 顶部添加（手工编辑）：

```markdown
**Status:** ✅ COMPLETED on YYYY-MM-DD
```

或在 `docs/superpowers/plans/` 目录追加一行日志笔记。Phase B 实施前回到此 plan 查 Task 10 Step 1 记录的 webchat 失败项。

---

## Self-Review

**Spec coverage:**
- ✅ §五 L0 元数据：api_overview / api_list_samples（filter+computation_pattern）/ api_read_sample → 现有实现 + Task 9 补 filter
- ✅ §五 L1 符号定位：api_search_symbol（Task 3）+ api_node（Task 4）
- ✅ §五 L2 图关系反查：api_callers + api_callees（Task 5）+ api_impact（Task 6）
- ✅ §五 L3 文件级：api_list_files / api_read_file（保留现状）
- ✅ §五 L4 阙割版探索：api_explore_symbols（Task 7，含 --no-code 内置剥源码）
- ✅ §五 统一 envelope（_envelope helper，Task 3）
- ✅ §六 _codegraph_call → codegraph_client.call_cli（Task 1）
- ✅ §六 CamelCase → snake_case normalize（Task 1）
- ✅ §六 启动期 CLI 可用性检测：assert_codegraph_ready（Task 1，worker 接入是 Phase B）
- ✅ §四 samples 简化：删 recommendation_reason + apis_used 半自动（Task 9）
- ✅ §七 失败兜底：每个 API 的 error/fallback_hint（Task 3-7 各自实现）
- ✅ §八 测试 record-replay：捕获脚本 + fixtures（Task 2）+ 各 task 单元测试
- ✅ §八 防回归 grep：Task 10 Step 2-3

**Spec 中明确"Phase A 范围"未在此 plan 覆盖的项：**
- ⚠️ CLI 子命令新增（`callers/callees/impact/explore_symbols/node/search_symbol`）→ **Phase B Task 1**
- ⚠️ worker/server.py HANDLERS 注册新 API → **Phase B Task 2**
- ⚠️ codegraph-guide.md / SKILL.md / system_prompt.md / CLAUDE.md §九 → **Phase B**

**Placeholder scan:** 无 TBD/TODO；所有代码块完整可执行。

**Type consistency:**
- `api_search_symbol` 返回 `{matches: [...]}`（snake_case），Task 4 `api_node` 内部用 `api_search_symbol` 类似的字段 ✓
- `api_callers/api_callees` 共享 `_call_graph_query`，subcommand 区分 ✓
- envelope schema 在所有 L1-L4 API 一致：`{source_type, evidence, data, error, fallback_hint}` ✓
- `_normalize_keys` 在 codegraph_client 实现，retriever_repo 通过 `_cgc._normalize_keys` 访问 ✓

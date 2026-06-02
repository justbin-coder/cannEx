# CodeGraph 教学语境贯通 Implementation Plan（Phase B）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让教学侧（Skill / webchat）真正用上 Phase A 的 6 个新 lib API。改造 CLI 子命令、worker HANDLERS、SKILL.md / system_prompt.md 工具决策树、`codegraph-guide.md` 大改、CLAUDE.md §九 拆分（文档侧 + 代码侧约束并列），最后做 webchat E2E 冒烟。

**Architecture:** Phase B 不动 lib 实现，只动「lib API → 教学 Agent 决策」之间的所有接线：CLI wrapper / worker RPC / prompt 决策树 / 项目级范式约束。`webchat E2E` 验证 Agent 能在「callers / callees / impact / explore_symbols」上做出合理调用。

**Tech Stack:** Python 3.11 (CLI wrapper / worker)，Markdown（prompt / SKILL / 项目文档），Chainlit（webchat），pytest（worker 黑盒测试）。

**Spec reference:** `docs/superpowers/specs/2026-05-28-codegraph-integration-redesign.md`

**Phase A prerequisite:** `docs/superpowers/plans/2026-05-28-codegraph-phase-a-lib-refactor.md` 全部 Task PASS，lib 14 个 `api_*` 可用，`codegraph_client.assert_codegraph_ready` 可调。

---

## File Structure

**修改：**
- `skills/ascend-c/tools/cannex_repo.py` — 新增 6 个 CLI 子命令；旧 `symbol` 委托新 API；删除任何残留 context
- `webchat/cannex_chat/worker/server.py` — 启动期 `assert_codegraph_ready`；HANDLERS 新增 6 个 RPC 方法；旧 `lookup_code_symbol` 委托新 API
- `webchat/cannex_chat/tests/test_worker_server.py` — 新增 RPC 方法的黑盒测试
- `skills/ascend-c/references/codegraph-guide.md` — **整篇重写**：删 SQL 查询节、加"按问题类型选 lib API"决策树
- `skills/ascend-c/SKILL.md` — 工具清单新增 6 项 + 决策树
- `webchat/cannex_chat/prompts/system_prompt.md` — 同 SKILL.md 决策树（webchat 工具命名）
- `CLAUDE.md` — §九 拆分：文档侧（不动）+ 代码侧（新增）；废弃名册补登

**不动：**
- `lib/cannex_knowledge/`（Phase A 已完成）
- `build/`（Phase A Task 9 已改）
- `workspace/repos/*/samples.yaml`（Phase A Task 9 已改）

---

## Task 1: cannex_repo.py CLI 新增 6 个子命令

**Files:**
- Modify: `skills/ascend-c/tools/cannex_repo.py`

### Step 1: 浏览现有 CLI 结构作为 baseline

Run:
```bash
cd ~/Desktop/CannEx
grep -nE "^def cmd_|sub\.add_parser\(\"" skills/ascend-c/tools/cannex_repo.py
```
Expected: 看到 7 个旧子命令：list / card / list_samples / code / symbol / list_files / read_file。

### Step 2: 新增 6 个 cmd_* 函数

在 `skills/ascend-c/tools/cannex_repo.py` 中现有 `cmd_*` 区块末尾追加：

```python
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
```

### Step 3: 注册 argparse 子命令 + dispatch

在 `main()` 函数（或 argparse 设置区块）的 `sub.add_parser(...)` 块中追加：

```python
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
s = sub.add_parser("explore_symbols",
                   help="任务相关符号清单（不含源码）")
s.add_argument("repo")
s.add_argument("query")
s.add_argument("--max_symbols", type=int, default=30)
```

在 `main()` 的 dispatch 区块（`if args.cmd == "list": ...` 链）追加：

```python
elif args.cmd == "search_symbol":
    cmd_search_symbol(args.repo, args.query, args.kind, args.limit)
elif args.cmd == "node":
    cmd_node(args.repo, args.symbol, args.kind)
elif args.cmd == "callers":
    cmd_callers(args.repo, args.symbol, args.limit)
elif args.cmd == "callees":
    cmd_callees(args.repo, args.symbol, args.limit)
elif args.cmd == "impact":
    cmd_impact(args.repo, args.symbol, args.depth)
elif args.cmd == "explore_symbols":
    cmd_explore_symbols(args.repo, args.query, args.max_symbols)
```

### Step 4: CLI 冒烟所有新子命令

Run:
```bash
cd ~/Desktop/CannEx
echo "=== search_symbol ==="; python3 skills/ascend-c/tools/cannex_repo.py search_symbol ops-transformer FlashAttention --limit 2 | head -20
echo "=== node ==="; python3 skills/ascend-c/tools/cannex_repo.py node ops-transformer DataCopy | head -15
echo "=== callers ==="; python3 skills/ascend-c/tools/cannex_repo.py callers ops-transformer FlashAttentionScore --limit 3 | head -20
echo "=== callees ==="; python3 skills/ascend-c/tools/cannex_repo.py callees ops-transformer FlashAttentionScore --limit 3 | head -15
echo "=== impact ==="; python3 skills/ascend-c/tools/cannex_repo.py impact ops-transformer FlashAttentionScore --depth 1 | head -20
echo "=== explore_symbols ==="; python3 skills/ascend-c/tools/cannex_repo.py explore_symbols ops-transformer "FlashAttention pipeline" --max_symbols 3 | head -20
```
Expected: 6 个子命令各自输出合法 JSON envelope（含 `source_type`/`data`），无 traceback。

### Step 5: 旧 `symbol` 仍可用（Phase A 已做兼容包装）

Run:
```bash
cd ~/Desktop/CannEx
python3 skills/ascend-c/tools/cannex_repo.py symbol ops-transformer FlashAttentionScoreKernelBase --kind class | head -15
```
Expected: 旧 schema `{matches, source_type}` 仍返回，不报错（Phase A Task 8 已经做了委托）。

### Step 6: Commit

```bash
cd ~/Desktop/CannEx
git add skills/ascend-c/tools/cannex_repo.py
git commit -m "$(cat <<'EOF'
feat(skill): cannex_repo CLI 新增 6 子命令接入 Phase A lib API

- search_symbol / node / callers / callees / impact / explore_symbols
- 旧 symbol 子命令保留（lib 已委托新 API）
- 所有新子命令输出统一 envelope schema

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: worker/server.py HANDLERS 注册新 RPC + 启动期版本校验

**Files:**
- Modify: `webchat/cannex_chat/worker/server.py`
- Modify: `webchat/cannex_chat/tests/test_worker_server.py`

### Step 1: 阅读现有 HANDLERS 与 _setup_path

Run:
```bash
cd ~/Desktop/CannEx
grep -nE "_setup_path|HANDLERS\s*=|^\s*\"\w+\":" webchat/cannex_chat/worker/server.py | head -25
```
Expected: 看到 `_setup_path()` 启动期检查 workspace；HANDLERS 字典含 10 个方法。

### Step 2: 启动期接入 assert_codegraph_ready

打开 `webchat/cannex_chat/worker/server.py`，在 `_setup_path` 之后、`from cannex_knowledge import ...` 之后追加：

```python
from cannex_knowledge.codegraph_client import assert_codegraph_ready  # noqa: E402

assert_codegraph_ready()  # CLI 缺失或 < 0.9.4 时 SystemExit
```

### Step 3: HANDLERS 字典追加 6 个新 RPC

在 `HANDLERS = { ... }` 字典中追加（在现有 `"list_repo_files"` 之后）：

```python
    # ── L1 符号定位（新增）─────────────────────────────────
    "search_code_symbol": lambda p: repo_mod.api_search_symbol(
        p["repo"], p["query"],
        kind=p.get("kind"),
        limit=p.get("limit", 10),
    ),
    "lookup_code_node": lambda p: repo_mod.api_node(
        p["repo"], p["symbol"],
        kind=p.get("kind"),
    ),

    # ── L2 图关系反查（新增 - L2+ 用户最关心）─────────────
    "find_code_callers": lambda p: repo_mod.api_callers(
        p["repo"], p["symbol"],
        limit=p.get("limit", 20),
    ),
    "find_code_callees": lambda p: repo_mod.api_callees(
        p["repo"], p["symbol"],
        limit=p.get("limit", 20),
    ),
    "analyze_code_impact": lambda p: repo_mod.api_impact(
        p["repo"], p["symbol"],
        depth=p.get("depth", 2),
    ),

    # ── L4 阙割版探索（新增）─────────────────────────────
    "explore_code_symbols": lambda p: repo_mod.api_explore_symbols(
        p["repo"], p["query"],
        max_symbols=p.get("max_symbols", 30),
    ),
```

### Step 4: 旧 `lookup_code_symbol` 保留（已委托新 API）

确认 `"lookup_code_symbol"` 行**保持不动** —— Phase A Task 8 已让 `repo_mod.api_symbol` 委托 `api_search_symbol`，向后兼容。

### Step 5: 写 RPC 黑盒测试

打开 `webchat/cannex_chat/tests/test_worker_server.py`，在末尾追加：

```python
import json
import subprocess
import sys
from pathlib import Path


def _rpc(method: str, params: dict) -> dict:
    """启动 worker 子进程，发一条请求，读响应。"""
    root = Path(__file__).resolve().parents[3]
    env = {"PATH": __import__("os").environ.get("PATH", ""),
           "CANNEX_ROOT": str(root)}
    p = subprocess.Popen(
        [sys.executable, "webchat/cannex_chat/worker/server.py"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=str(root), env=env,
    )
    req = json.dumps({"id": "t1", "method": method, "params": params}) + "\n"
    out, err = p.communicate(req.encode(), timeout=30)
    if not out.strip():
        raise AssertionError(f"empty output, stderr={err.decode()[:500]}")
    return json.loads(out.decode().splitlines()[0])


def test_rpc_search_code_symbol_returns_envelope():
    res = _rpc("search_code_symbol",
               {"repo": "ops-transformer", "query": "FlashAttention", "limit": 2})
    assert res["id"] == "t1"
    assert "result" in res
    assert res["result"]["source_type"] == "original"
    assert "matches" in res["result"]["data"]
    assert len(res["result"]["data"]["matches"]) >= 1


def test_rpc_find_code_callers():
    res = _rpc("find_code_callers",
               {"repo": "ops-transformer", "symbol": "FlashAttentionScore", "limit": 3})
    assert "result" in res
    assert res["result"]["source_type"] == "original"
    assert "callers" in res["result"]["data"]


def test_rpc_analyze_code_impact():
    res = _rpc("analyze_code_impact",
               {"repo": "ops-transformer", "symbol": "FlashAttentionScore", "depth": 1})
    assert "result" in res
    d = res["result"]["data"]
    assert "affected" in d
    assert "node_count" in d


def test_rpc_explore_code_symbols_strips_source():
    res = _rpc("explore_code_symbols",
               {"repo": "ops-transformer", "query": "FlashAttention pipeline",
                "max_symbols": 3})
    assert "result" in res
    for sym in res["result"]["data"].get("symbols", []):
        assert "source_code" not in sym
        assert "code" not in sym


def test_rpc_unknown_method_returns_error():
    res = _rpc("nonexistent_method", {})
    assert "error" in res
```

### Step 6: 跑测试确认通过

Run: `cd ~/Desktop/CannEx && python3 -m pytest webchat/cannex_chat/tests/test_worker_server.py -v`
Expected: 全部 PASS（旧 4 个 + 新 5 个）。

> 若 RPC 启动失败（worker `assert_codegraph_ready` 报错），先确认 codegraph CLI ≥ 0.9.4 已装。

### Step 7: Commit

```bash
cd ~/Desktop/CannEx
git add webchat/cannex_chat/worker/server.py webchat/cannex_chat/tests/test_worker_server.py
git commit -m "$(cat <<'EOF'
feat(webchat): worker 注册 6 个 codegraph RPC + 启动期版本校验

新 RPC 方法（命名风格统一"动词_code_对象"）：
- search_code_symbol / lookup_code_node
- find_code_callers / find_code_callees / analyze_code_impact
- explore_code_symbols（已剥源码）
启动期 assert_codegraph_ready：CLI 缺失或 < 0.9.4 时拒绝启动。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: codegraph-guide.md 整篇重写

**Files:**
- Modify: `skills/ascend-c/references/codegraph-guide.md`（**整篇重写**）

### Step 1: 读旧文档确认要删的内容

Run:
```bash
cd ~/Desktop/CannEx
head -100 skills/ascend-c/references/codegraph-guide.md
echo "..."
wc -l skills/ascend-c/references/codegraph-guide.md
```
Expected: 看到当前文档里教 LLM 写裸 SQL（`SELECT FROM nodes WHERE ...`、`nodes_fts MATCH ...`）。

### Step 2: 整篇重写

把 `skills/ascend-c/references/codegraph-guide.md` **整篇内容**替换为：

````markdown
# CodeGraph 工具使用指南

> 供 agent（Skill / Webchat）内部参考。理解 CodeGraph 在 CannEx 里承担什么、不承担什么，以及按问题类型选择哪个工具。

---

## 一、CodeGraph 在 CannEx 里的角色

CodeGraph 是 **CannEx 代码侧的事实层**：回答"代码在哪、符号是什么、谁调谁、改这里影响哪里"这类**客观事实**问题。

它**不**承担：
- 领域语义判断（"这个算子是 vector+cube 融合"由 samples.yaml 标注）
- 教学切面（"这段代码教什么"由 samples.teaches 标注）
- 文档侧检索（PageIndex 文档树负责）

> **历史包袱已废弃**：早期 CodeGraph 使用方式是「lib 直查 SQLite `nodes` / `edges` 表 + 自己写 SQL」。这已经在 2026-05-28 Phase A 重构中完整废弃——**禁止在 lib / Skill / webchat 里出现 SQLite 直查代码或裸 SQL 字符串**。所有代码事实问答必须走 `lib/cannex_knowledge` 提供的 `api_*` 函数（其内部调用 CodeGraph CLI）。

---

## 二、CodeGraph CLI 实际能力（v0.9.4+）

| CLI 子命令 | lib API 对应 | 用途 | JSON flag |
|---|---|---|---|
| `query <search>` | `api_search_symbol` / `api_node` | FTS5 + ranking 符号搜索 | `-j --json` |
| `callers <symbol>` | `api_callers` | 反查谁调用了 symbol | `-j --json` |
| `callees <symbol>` | `api_callees` | 反查 symbol 调用了谁 | `-j --json` |
| `impact <symbol>` | `api_impact` | 修改 symbol 的影响半径 | `-j --json` |
| `context <task>` | `api_explore_symbols`（剥源码版） | 任务相关符号清单 | `-f json --no-code` |
| `files` | （由 `api_list_files` 用 filesystem 直读替代） | — | — |

**CLI 不暴露**（仅 MCP 工具）：`node` / `explore` / `status`。`node` 用 `query --limit 1` 等价，`explore` 用 `context --no-code` 覆盖。

**关键事实**：
- CodeGraph 内部用 graph distance / FTS5 / edge weight 做 ranking。**这是 trusted source**——lib 不做二次排序、不打分、不阈值过滤
- `score` 字段透传给 LLM，仅供参考
- JSON 字段命名 camelCase（`filePath` / `startLine`），lib 已统一 normalize 为 snake_case

---

## 三、按问题类型选 lib API 的决策树

> **不要直接调 CodeGraph CLI**——所有调用走 `lib/cannex_knowledge.retriever_repo` 的 `api_*`，它已经处理了 envelope / 错误兜底 / fallback_hint。

```
用户问题
│
├── 「这仓是干嘛的 / 仓属性」
│   → api_overview(repo)                     [L0 - repo_card.yaml]
│
├── 「推荐 X 模式 / Y 难度的算子」
│   → api_list_samples(repo, computation_pattern=..., complexity=...)
│                                            [L0 - samples.yaml]
│
├── 「教我 ffn-glu / 精读 X 算子」
│   → api_read_sample(repo, sample_id)       [L0 - 教学起点]
│   ↓ 配合
│   → api_search_symbol / api_node           [L1 - 深入符号]
│
├── 「DataCopy 在 X 仓哪些地方用 / 谁调用了 Y」
│   → api_callers(repo, "Y")                 [L2 - 反查调用者]
│
├── 「Y 函数都调了哪些 API」
│   → api_callees(repo, "Y")                 [L2 - 正查被调用]
│
├── 「改了 Tiling 函数影响哪些算子 / 影响半径」
│   → api_impact(repo, "Tiling", depth=2)    [L2 - 影响半径]
│
├── 「某场景涉及哪些关键代码」（横向探索）
│   → api_explore_symbols(repo, "FlashAttention pipeline")
│                                            [L4 - 符号清单，不含源码]
│   ↓ 拿到 file:line 后
│   → api_read_file(repo, path, start, end)  [L3 - 按需读源码]
│
├── 「找一个名字像 X 的符号但不确定全名」
│   → api_search_symbol(repo, "X", limit=10) [L1 - 带 ranking]
│
└── 「直接读某个文件 / 浏览目录」
    → api_list_files / api_read_file         [L3 - filesystem]
```

---

## 四、Score 字段处理约定

CodeGraph CLI `query` 返回的每个 match 含 `score` 字段（float，越大越相关，CodeGraph 内部 ranking 计算）。

**Agent 处理原则**：
1. **score 透传**：lib 不裁剪、不阈值切分、不二次排序
2. **score 是参考不是决策**：高 score 不代表必然相关；低 score 不代表无用
3. **优先看 file_path + qualified_name 上下文**：用户问 FlashAttention 时 score=143 的 `attention/flash_attention_score/op_kernel/flash_attention_score.cpp` 大概率比 score=200 但来自 `experimental/.../old.cpp` 的更相关
4. **callers / callees / impact 没有 score**：边的方向性是确定的，结果按数据库内部顺序返回，由 LLM 判断相关性

---

## 五、失败场景与降级

每个 `api_*` 失败时返回 envelope 含 `error` 和 `fallback_hint`。`fallback_hint` 总是指向另一个 lib API，agent 应按提示链式降级：

| 失败 | fallback_hint 示例 |
|---|---|
| 索引缺失 | "运行 `build/build_repos.py` 建索引，或用 `api_list_files` 浏览原始仓" |
| 符号未找到 | "用 api_search_symbol(kind=None) 模糊查找，或 api_list_files 探索目录" |
| callers/callees 空结果 | "CodeGraph 无法穿透宏展开/模板特化，建议 api_read_file 直读源码定位" |
| CLI timeout | "尝试更窄的 query 范围或更轻量的 api_node" |

**Agent 行为约定**：拿到 `error` 时**不要直接放弃**，按 `fallback_hint` 切换工具继续探索；只有所有降级路径都失败时才告诉用户"暂时回答不了"。

---

## 六、CANN 仓特有的查询技巧

### 多架构版本发现

CANN 算子常有 arch32 / arch35 / arch38 多版本实现。`api_search_symbol` 同一个符号名通常返回多条 match，注意 `file_path` 中的 `archXX`：

```
class | FlashAttentionScoreKernelBase | attention/.../arch35/...kernel_base.h
class | FlashAttentionScoreKernelBase | attention/.../arch38/...kernel_base.h
```

**arch 编号越大通常对应越新硬件**（arch35 → 910B/C/D，arch38 更新）。教学时应主动覆盖用户硬件相关的 arch 实现。

### CRTP 继承链追踪

CRTP（Curiously Recurring Template Pattern）在 CANN 仓里很常见。用 `api_callers(BaseClassName, limit=20)` 找出所有继承/特化点；CodeGraph 已经在 resolution 阶段处理了 `extends` 边。

### op_kernel vs op_host 对照

完整解读一个算子需要看两侧：`api_list_files(repo, "algorithm_dir/op_kernel")` + `api_list_files(repo, "algorithm_dir/op_host")`，分别用 `api_read_file` 读。

### 宏展开盲区

CodeGraph 基于 AST 静态分析，**无法追踪 `#define` 产生的符号**。callers/callees 返回空时常常是这种情况——用 `api_read_file` 直读源码定位调用点。

---

## 七、约束总结（实施期 self-check）

- ✅ 所有代码事实回答走 `api_*`，不直查 SQLite
- ✅ `score` 透传不二次处理
- ✅ 失败时按 `fallback_hint` 链式降级
- ✅ samples.yaml 精选 12 条不覆盖全仓，未标注算子由 `api_search_symbol` + `api_list_files` 兜底，并提示用户"未经精选审阅"
- ✅ 文档侧 PageIndex 范式（tree-walk + 无排序）与代码侧 CodeGraph 范式（CLI ranking + envelope）并存，互不污染
````

### Step 3: 验证 markdown 渲染正常

Run:
```bash
cd ~/Desktop/CannEx
wc -l skills/ascend-c/references/codegraph-guide.md
grep -c "SELECT \|FROM nodes\|sqlite3" skills/ascend-c/references/codegraph-guide.md || echo "ZERO SQL"
```
Expected: 行数显著大于零；SQL 残留数应为 `ZERO SQL`（除了"历史包袱已废弃"那段提到的字符串外）。

如有意外 SQL 残留，回 Step 2 检查替换是否完整。

### Step 4: Commit

```bash
cd ~/Desktop/CannEx
git add skills/ascend-c/references/codegraph-guide.md
git commit -m "$(cat <<'EOF'
docs(skill): codegraph-guide.md 整篇重写：从教写 SQL 改为教选 lib API

- 删除全部裸 SQL / SQLite 直查内容
- 新增按问题类型选 api_* 的决策树
- 明确 CodeGraph 是事实层、samples.yaml 是领域语义层、PageIndex 是文档层
- score 透传约定 / 失败降级链 / CANN 仓 archXX-CRTP-宏盲区技巧

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: CLAUDE.md §九 拆分（文档侧 + 代码侧 约束并列）

**Files:**
- Modify: `/Users/justbin/Desktop/CannEx/CLAUDE.md`（§九 整段重写）

### Step 1: 读旧 §九 定位精确边界

Run:
```bash
cd ~/Desktop/CannEx
grep -n "^## 九" CLAUDE.md
sed -n "/^## 九/,/^---/p" CLAUDE.md | head -80
```
Expected: 看到旧 §九 通篇是「PageIndex 使用约束」+「禁止 search/rank/score」+「反模式废弃名册」。

### Step 2: 整段重写 §九

打开 `CLAUDE.md`，把 `## 九、PageIndex 使用约束` 到该节末尾（下一节 `---` 之前）的全部内容替换为：

```markdown
## 九、双知识源使用约束（文档侧 + 代码侧 并列）

CannEx 有两个独立的知识源，**各自的检索范式不同，必须分开约束，不能互相污染**。

### 9.1 文档侧约束（PageIndex - 不变）

**哲学**：PageIndex 是 *vectorless, reasoning-based RAG*——relevance 由 LLM 在 ToC tree 上推理产生，**工具层不做打分排序**。

**工具能力契约**（`lib/cannex_knowledge/retriever_doc.py` 只允许这五类 API）：

| 能力类型 | API | 关键不变量 |
|---|---|---|
| 列出可用文档 | `api_list()` | **必须**含 `doc_description` |
| 单文档元数据 | `api_meta(doc)` | LLM 推理燃料 |
| 结构索引 | `api_outline(doc)` | **每节点必须含 summary**，工具不排序 |
| 读原文 | `api_pages(doc, range)` | LLM 决定范围 |

**禁止出现的语义**（文档侧）：`search` / `rank` / `score` / `top_k` / `similarity` / SQL `LIKE '%query%' LIMIT N`——这些是 LLM 在 tree 上的推理活，不是工具该做的事。

**反模式（✅ 已废弃，commits a76b245 / 881a704）**：
- `retriever_doc.api_search` — title +2 / summary +1 keyword 打分 → **已删除**

**燃料缺位（✅ 已补全，commits bba5fc7 / ad11ea2 / 7b676f9）**：
- `api_list()` 现已暴露 `doc_description`
- `api_outline()` 现已暴露 node `summary`
- `lib` 层已有 `api_meta(doc)` 函数

**触发条件**（命中任一即按文档侧约束行事）：
- 改 `lib/cannex_knowledge/retriever_doc.py` 或新增文档侧 API
- 加文档侧检索工具
- 引入 FAISS / Lance / Milvus / BM25 / sentence-transformers 等"匹配"类库
- 新增文档侧 CLI 子命令名含 `search` / `find` / `query` / `lookup`

### 9.2 代码侧约束（CodeGraph - 2026-05-28 新增）

**哲学**：代码侧承认 CodeGraph CLI 的内部 ranking（FTS5 + graph distance + edge weight）是 **trusted source**。lib 是工程化包装层，不做二次排序，但允许透传 score 给 LLM 参考。

**工具能力契约**（`lib/cannex_knowledge/retriever_repo.py` 只允许下列 API；分四层）：

| 层 | API | 数据源 |
|---|---|---|
| L0 人工策展 | `api_overview` / `api_list_samples` / `api_read_sample` | repo_card.yaml + samples.yaml |
| L1 符号定位 | `api_search_symbol` / `api_node` | CodeGraph CLI `query` |
| L2 图关系反查 | `api_callers` / `api_callees` / `api_impact` | CodeGraph CLI 同名子命令 |
| L3 文件级 | `api_list_files` / `api_read_file` | filesystem 直读 |
| L4 阙割版探索 | `api_explore_symbols` | CodeGraph CLI `context --no-code -f json` |

**统一 envelope**：所有 `api_*` 返回 `{source_type, evidence, data, error, fallback_hint}`。

**允许出现的语义**（代码侧）：
- ✅ `score` 字段透传（不裁剪、不阈值、不重排）
- ✅ `limit` / `depth` 参数透传给 CodeGraph CLI
- ✅ `--no-code` / `--kind` 等 CLI flag 等价透传

**禁止出现的语义**（代码侧）：
- ❌ lib 内 SQLite 直查（`sqlite3.connect` / `SELECT FROM nodes` / `SELECT FROM edges` / `nodes_fts MATCH`）
- ❌ lib 内相关性二次排序（`sorted(matches, key=lambda x: x['score'])`）
- ❌ lib 内阈值过滤（`if score > threshold: ...`）
- ❌ 教 LLM 写裸 SQL（旧 `codegraph-guide.md` 模式，已废弃）

**反模式（✅ 已废弃，commits 待 Phase A 实施）**：
- `retriever_repo.api_symbol` — `SELECT FROM nodes WHERE name=?` → **改为委托 `api_search_symbol`，保留向后兼容包装**
- `retriever_repo.api_context` — SQL `LIKE '%query%' LIMIT 5` → **彻底删除**（由 `api_explore_symbols` 替代）
- `samples.yaml` 字段 `recommendation_reason` → **删除**（语义重叠 `teaches`）

**燃料能力到位（✅ Phase A 新增）**：
- L2 图关系反查（callers / callees / impact）—— L2+ 用户最大痛点，CodeGraph CLI 0.9.4+ 直接覆盖
- L4 阙割版探索（explore_symbols）—— CodeGraph 内置 `--no-code`，无需 lib 后处理剥源码
- envelope `fallback_hint` —— 失败时形成工具间引导链，agent graceful degrade

**触发条件**（命中任一即按代码侧约束行事）：
- 改 `lib/cannex_knowledge/retriever_repo.py` 或新增代码侧 API
- 加 `skills/ascend-c/` 或 `webchat/` 的代码侧检索工具
- 新增 lib / CLI / RPC 涉及 `nodes` / `edges` / 符号 / 调用关系 / 影响半径 / 任务相关性

### 9.3 跨范式接线（教学 Agent 用法）

教学 Agent 在回答用户问题时通常需要跨两个范式：
- 用户问「FlashAttention 怎么实现 + 算子开发指南怎么说」→ 先 `api_explore_symbols`（代码侧） + `api_outline`（文档侧），再交叉给用户
- 严格遵守：**文档侧调用不要带 score 概念**（PageIndex 不返回 score）；**代码侧调用接受 score 透传**

> 参考：PageIndex README L48-71、`~/project/CANN/PageIndex/examples/agentic_vectorless_rag_demo.py`；CodeGraph README "MCP Tools" 节、本仓 `skills/ascend-c/references/codegraph-guide.md`。
```

### Step 3: 验证 §九 结构正确

Run:
```bash
cd ~/Desktop/CannEx
grep -nE "^### 9\." CLAUDE.md
```
Expected: 输出三条子节：`### 9.1 文档侧约束（PageIndex - 不变）` / `### 9.2 代码侧约束（CodeGraph - 2026-05-28 新增）` / `### 9.3 跨范式接线（教学 Agent 用法）`。

### Step 4: Commit

```bash
cd ~/Desktop/CannEx
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(claude): §九 拆分为「文档侧 + 代码侧」双范式并列约束

9.1 文档侧（PageIndex）：tree-walk + 无排序，保持原约束
9.2 代码侧（CodeGraph）：CLI ranking 是 trusted source，
    lib 不二次排序但 score 透传；新增 L0-L4 工具契约
9.3 跨范式接线：教学 Agent 不能把 score 概念带到文档侧
代码侧废弃名册补登：api_symbol/api_context/recommendation_reason

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: SKILL.md 工具清单 + 决策树更新

**Files:**
- Modify: `skills/ascend-c/SKILL.md`

### Step 1: 定位 SKILL.md 工具清单节

Run:
```bash
cd ~/Desktop/CannEx
grep -nE "^##|^###|tools|工具" skills/ascend-c/SKILL.md | head -25
```
Expected: 看到现有工具节标题（如「## 二、知识源与检索工具」或类似）。

### Step 2: 在工具节追加 Phase A 新工具说明 + 决策树

打开 `skills/ascend-c/SKILL.md`，在代码类工具的现有 `lookup_code_symbol` 描述**之后**追加：

````markdown
#### `search_code_symbol(repo, query, kind?, limit?)` — FTS5 + ranking 符号搜索

代码侧 L1。包装 `codegraph query`，返回 `{matches: [{name, kind, qualified_name, file_path, start_line, end_line, score}]}`。

- 何时用：用户问"找一个名字像 X 的符号但不确定全名"；或想看相关性 ranking 前几名
- `score` 字段透传 CodeGraph 内部 ranking，越大相关性越高（但**仅供参考**——优先看 file_path + qualified_name）
- `kind` 可选：`function` / `method` / `class` / `struct` / `enum` 等
- ⚠️ 不要用本工具回答"算子推荐"问题（用 `list_repo_samples`）

#### `lookup_code_node(repo, symbol, kind?)` — 精确单符号详情

代码侧 L1。本质是 `search_code_symbol(limit=1)` 拿第一条 + 完整字段。

- 何时用：已经知道符号全名，想拿单个符号的所有元信息（visibility / is_static / start_line / end_line）
- 找不到时 envelope `error` + `fallback_hint` 指引 `search_code_symbol(kind=None)` 模糊查

#### `find_code_callers(repo, symbol, limit?)` ★ **L2+ 用户高频** — 反查谁调用了 symbol

代码侧 L2。包装 `codegraph callers`，返回 `{symbol, callers: [{name, kind, file_path, start_line}]}`。

- 何时用：用户问"DataCopy 在 X 仓哪些地方用"、"哪些算子用了 TPipe.InitBuffer"
- 当前 CLI 默认深度 1；多层链路由 LLM 链式调用
- 空结果常因宏展开/模板特化，`fallback_hint` 引导 `read_repo_file` 直读

#### `find_code_callees(repo, symbol, limit?)` — 反查 symbol 调用了谁

代码侧 L2。与 `find_code_callers` 对称，结果方向相反。

- 何时用：用户问"FlashAttention 的 Process 方法都调了什么"

#### `analyze_code_impact(repo, symbol, depth?)` ★ **改动评估** — 修改 symbol 的影响半径

代码侧 L2。包装 `codegraph impact`，返回 `{symbol, depth, node_count, edge_count, affected: [...]}`。

- 何时用：用户问"改了这个 Tiling 模板会影响哪些算子"、"这个 base class 修改的风险半径"
- `depth` 默认 2（二度邻居），加深会变慢

#### `explore_code_symbols(repo, query, max_symbols?)` ★ **横向场景探索** — 任务相关符号清单（不含源码）

代码侧 L4。包装 `codegraph context --no-code -f json`，返回 `{query, summary, entry_points, symbols: [{name, file_path, start_line, kind}]}`。**已剥源码**。

- 何时用：用户问"某场景（pipeline / KVCache / 量化）涉及哪些代码"——LLM 用本工具拿符号清单后，按相关性挑几个用 `read_repo_file` 读
- ⚠️ **不要**为了节省工具调用次数就盲目调本工具——它内部跑 CodeGraph context（重型），频繁调用会拉高延迟。优先 `search_code_symbol` / `find_code_callers` 等轻量工具

### 工具决策树（代码侧 + 文档侧并列）

```
用户问题
│
├── 仓属性 / 仓边界                 → get_repo_overview
├── 算子推荐 / 学习起点             → list_repo_samples（按 computation_pattern / complexity）
├── 教学精读某算子                   → read_sample_code → search_code_symbol / read_repo_file
├── 找符号但名字不全                 → search_code_symbol
├── 已知符号全名拿详情               → lookup_code_node
├── 反查谁调用了 X                  → find_code_callers
├── 正查 X 调用了谁                  → find_code_callees
├── 改 X 影响半径                    → analyze_code_impact
├── 某场景涉及哪些代码（横向）       → explore_code_symbols → read_repo_file
├── 读源码                          → read_repo_file
├── 浏览目录                        → list_repo_files
├── 文档结构 / 章节定位              → get_document_outline
└── 读文档原文                      → read_document_pages
```
````

### Step 3: 在 SKILL.md 开头/任何"工具命名风格"附录中（如有）更新废弃说明

定位 SKILL.md 是否有"已废弃工具"或类似清单。若有，追加：

```markdown
- `lookup_code_symbol` — ⚠️ 旧 API，2026-05-28 起内部委托 `search_code_symbol`。新代码请直接用 `search_code_symbol`。
- `lookup_code_context` — ✅ 已废弃。语义已被 `explore_code_symbols` + `find_code_callers` 替代。
```

### Step 4: 验证 SKILL.md 仍能完整渲染（markdown 完整性）

Run:
```bash
cd ~/Desktop/CannEx
wc -l skills/ascend-c/SKILL.md
grep -c "^####" skills/ascend-c/SKILL.md
```
Expected: 行数增加；`####` 工具节数量增加 6 个。

### Step 5: Commit

```bash
cd ~/Desktop/CannEx
git add skills/ascend-c/SKILL.md
git commit -m "$(cat <<'EOF'
docs(skill): SKILL.md 工具清单新增 6 项代码侧 API + 决策树

- search_code_symbol / lookup_code_node（L1）
- find_code_callers / find_code_callees / analyze_code_impact（L2）
- explore_code_symbols（L4 阙割版，标记重型工具）
- 工具决策树覆盖代码侧 + 文档侧 14 个分支
- 旧 lookup_code_symbol 标 deprecated（已内部委托）

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: webchat system_prompt.md 同步更新

**Files:**
- Modify: `webchat/cannex_chat/prompts/system_prompt.md`

### Step 1: 定位 system_prompt.md 工具清单节

Run:
```bash
cd ~/Desktop/CannEx
grep -nE "^####|^###|工具" webchat/cannex_chat/prompts/system_prompt.md | head -25
```
Expected: 看到与 SKILL.md 类似的工具节结构（`#### lookup_code_symbol` 等）。

### Step 2: 在「### 代码类」节追加新工具说明

打开 `webchat/cannex_chat/prompts/system_prompt.md`，找到现有 `#### lookup_code_symbol(...)` 节。在该节之后追加 Task 5 Step 2 的同样 6 段（`search_code_symbol` / `lookup_code_node` / `find_code_callers` / `find_code_callees` / `analyze_code_impact` / `explore_code_symbols`）。

**注意 webchat 版本与 SKILL 的差异**：
- system_prompt 里通常会标注「webchat 运行时约束」节，比如"重型工具不要连续调用"——把 `explore_code_symbols` 加入这类警告
- webchat 当前 anthropic_client 是单线 agent loop（没有 sub-agent），在 `explore_code_symbols` 描述里强调：**单次回答中最多调用一次 explore_code_symbols**，避免主上下文打满

### Step 3: 更新工具决策树

在 system_prompt.md 现有的"## 检索工作流"或"工具选择决策树"节末尾追加 Task 5 Step 2 的决策树（同样的 14 个分支）。

### Step 4: 更新已废弃工具说明

在 system_prompt.md 末尾（"运行时约束"或类似节内）追加：

```markdown
### 已废弃 / 兼容工具

- `lookup_code_symbol` — 旧 API，2026-05-28 起内部委托 `search_code_symbol`。新对话请直接用 `search_code_symbol`，旧名仅保留兼容性
- `lookup_code_context` — 已废弃，由 `explore_code_symbols` + `find_code_callers` 接管

### 重型工具调用预算

webchat 当前是单线 agent loop（无 sub-agent 隔离）。以下工具一次回答中**最多调用 1 次**：
- `explore_code_symbols`（CodeGraph context 重型）
- `analyze_code_impact`（depth ≥ 3 时）

轻量工具（`search_code_symbol` / `find_code_callers` / `find_code_callees` / `lookup_code_node` / 文档工具）按需调用，无次数上限。
```

### Step 5: Commit

```bash
cd ~/Desktop/CannEx
git add webchat/cannex_chat/prompts/system_prompt.md
git commit -m "$(cat <<'EOF'
docs(webchat): system_prompt.md 同步新增 6 工具 + 决策树 + 调用预算

- 6 个新代码侧工具描述（与 SKILL.md 对齐）
- 工具决策树覆盖 14 个分支
- 重型工具调用预算（explore_code_symbols / analyze_code_impact 最多 1 次/回答）
- 旧 lookup_code_symbol / lookup_code_context 废弃说明

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: webchat E2E 冒烟（手工验收）

**Files:** 无（仅验证）

### Step 1: 全量测试再跑一次

Run: `cd ~/Desktop/CannEx && python3 -m pytest -v`
Expected: 全部 PASS（含 Phase A 的 lib 测试 + Phase B 的 worker RPC 测试）。

### Step 2: 启动 webchat

Run:
```bash
cd ~/Desktop/CannEx/webchat/cannex_chat
source .venv/bin/activate 2>/dev/null || python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
CANNEX_ROOT=~/Desktop/CannEx chainlit run app.py -w
```
Expected: 浏览器自动打开 http://localhost:8000，无启动错误。worker 启动期 `assert_codegraph_ready` 通过。

### Step 3: 手工 E2E 场景验收清单

在浏览器逐项测试，确认 agent 选对工具：

| 问题 | 期望 agent 调用 | 关键验证点 |
|---|---|---|
| "ops-transformer 仓是干嘛的？" | `get_repo_overview` | 答出 tagline + scenarios + not_for |
| "推荐一个 vector_to_cube 融合的中等难度算子" | `list_repo_samples(computation_pattern='vector_to_cube', complexity='intermediate')` | 推 ffn-glu 或同类，引用 samples.yaml `teaches` |
| "教我 ffn-glu" | `read_sample_code` 起步 + `search_code_symbol` / `read_repo_file` 深入 | 教学节奏（先骨架、再细节） |
| "DataCopy 在 ops-transformer 哪些地方被调用？" | **`find_code_callers`** | 不能用 `read_repo_file` 暴力 grep |
| "FlashAttentionScoreKernelBase 谁继承了？" | `find_code_callers` | 返回继承 caller |
| "改了 FlashAttentionScore 这个符号会影响哪些代码？" | **`analyze_code_impact`** | 答出 affected 列表 + node_count/edge_count |
| "FlashAttention 流水线涉及哪些关键代码？" | **`explore_code_symbols`** | 返回符号清单，不含源码；agent 后续用 `read_repo_file` 按需读 |
| "找一个名字像 'Tiling' 的类" | `search_code_symbol(query='Tiling', kind='class')` | ranking 结果 |
| "Tiling 模板被定义在哪？" | `lookup_code_node` | 单符号详情 |

### Step 4: 记录 webchat E2E 观察到的问题

新建 `docs/superpowers/plans/2026-05-28-codegraph-phase-b-e2e-notes.md` 记录：
- 哪些场景 agent 选对工具
- 哪些场景 agent 选错工具（如该调 `find_code_callers` 却走了 `read_repo_file`）
- prompt 是否需要调整

> 若选错率 > 30%，回到 Task 6 改 system_prompt.md 决策树措辞，重新跑 E2E。

### Step 5: 终止 webchat 进程

按 `Ctrl+C` 停掉 chainlit。

### Step 6: Commit E2E 笔记（若有产出）

```bash
cd ~/Desktop/CannEx
git add docs/superpowers/plans/2026-05-28-codegraph-phase-b-e2e-notes.md
git commit -m "$(cat <<'EOF'
docs(plan): Phase B webchat E2E 冒烟验收笔记

记录 9 个 E2E 场景下 agent 工具选择情况，
作为未来 prompt 微调的基线。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Step 7: Phase B 收口标记

在 `2026-05-28-codegraph-phase-b-docs-prompt-sync.md`（本 plan 文件）顶部追加：

```markdown
**Status:** ✅ COMPLETED on YYYY-MM-DD
```

---

## Self-Review

**Spec coverage：**
- ✅ §九 影响面：cannex_repo.py 新增 6 子命令（Task 1）
- ✅ §九 影响面：worker HANDLERS 注册 6 新 RPC（Task 2）
- ✅ §九 影响面：codegraph-guide.md 大改（Task 3）
- ✅ §九 影响面：CLAUDE.md §九 拆分（Task 4）
- ✅ §九 影响面：SKILL.md 工具清单 + 决策树（Task 5）
- ✅ §九 影响面：webchat system_prompt.md 同步（Task 6）
- ✅ §十 Phase B 收口：webchat E2E 冒烟（Task 7）
- ✅ §二 设计原则 5（重量级工具阙割暴露）→ system_prompt.md 调用预算约束（Task 6 Step 4）
- ✅ §二 设计原则 6（失败兜底显式化）→ codegraph-guide.md §五 + Task 5 工具描述里的 fallback_hint 说明

**Placeholder scan：** 无 TBD/TODO；所有命令、代码、commit message 完整。

**Type consistency：**
- RPC 方法名风格统一：「动词_code_对象」（search_code_symbol / find_code_callers / analyze_code_impact / explore_code_symbols / lookup_code_node）
- SKILL.md / system_prompt.md / cannex_repo.py CLI 三处工具名映射：
  - CLI `search_symbol` ↔ RPC `search_code_symbol` ↔ lib `api_search_symbol`
  - CLI `node` ↔ RPC `lookup_code_node` ↔ lib `api_node`
  - CLI `callers` ↔ RPC `find_code_callers` ↔ lib `api_callers`
  - CLI `callees` ↔ RPC `find_code_callees` ↔ lib `api_callees`
  - CLI `impact` ↔ RPC `analyze_code_impact` ↔ lib `api_impact`
  - CLI `explore_symbols` ↔ RPC `explore_code_symbols` ↔ lib `api_explore_symbols`
- decision tree 在 Task 5/6 措辞一致

**已知遗留（Phase C 跟踪）：**
- 监控 webchat E2E 中 samples 未覆盖算子的命中率
- 评估常驻 codegraph 进程的收益（vs 每次 subprocess 启动 ~100ms）
- repo_card / samples 扩展字段（key_symbols / entry_points / starter_operators 等）

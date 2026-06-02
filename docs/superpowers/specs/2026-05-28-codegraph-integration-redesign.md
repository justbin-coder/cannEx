# CodeGraph 集成重构设计

**Date:** 2026-05-28
**Status:** Approved（brainstorming 阶段完成，待 plan 实施）
**Owner:** justbin
**Related:**
- `docs/superpowers/plans/2026-05-28-knowledge-layer-decoupling.md`（前置：lib 抽取已完成）
- `docs/specs/2026-05-23-codegraph-spike-report.md`（早期 spike）
- `skills/ascend-c/references/codegraph-guide.md`（本次大改）

---

## 一、背景与问题

> **事实校准（2026-05-28 实测）**：本 spec 假设 CodeGraph CLI **>= v0.9.6**。v0.9.3 不暴露 `callers` / `callees` / `impact`，0.9.4 起补齐。`node` / `explore` 在 CLI 中始终不暴露（仅 MCP 工具），本方案用 `query --limit 1` 和 `context --no-code` 等价覆盖。

CannEx 当前对 CodeGraph 的使用方式有两层结构性问题：

### 1. 误把工程化产品当底层索引库用

CodeGraph 上游（`/Users/justbin/project/CANN/codeIndex/codegraph`，colbymchenry/codegraph）实际是为 AI agent 设计的完整 MCP 产品，自带 9 个 MCP 工具（`search` / `node` / `callers` / `callees` / `impact` / `context` / `explore` / `files` / `status`）。**其中 CLI 暴露 6 个**（query 即 search，加上 callers / callees / impact / context / files），另 3 个仅 MCP 协议（node / explore / status 部分）。CodeGraph 经过 7 个真实开源仓的 benchmark（35% 便宜 / 70% 少工具调用 / 59% 少 token）。

CannEx 当前用法：
- 直查它产出的 SQLite `nodes` / `edges` 表
- `api_symbol` = `SELECT WHERE name=?`（精确匹配，无 ranking / 无 FTS5）
- `api_context` = SQL `LIKE '%query%' LIMIT 5`（已废弃为反模式，但替代方案缺位）
- `codegraph-guide.md` 教 LLM 直接写裸 SQL —— **官方 README 明确反对的用法**
- 完全缺失 `callers` / `callees` / `impact` 这三类 L2+ 用户最需要的图关系反查能力

### 2. 范式约束跟 CodeGraph 设计冲突

项目 `CLAUDE.md §九` 当前的"PageIndex 使用约束"明确写：禁止 `search` / `rank` / `score` / `top_k` / `similarity` 语义；工具不打分、不排序，由 LLM 在 tree 上推理。

这是 PageIndex 文档侧的范式，但 **CodeGraph 天然是带 ranking 的语义检索**（graph distance / edge weight）。强行套用 tree-walk 约束等于把 CodeGraph 阉割成 SQL 查询器，扔掉它的核心价值。

### 3. samples.yaml / repo_card.yaml 的真实角色被模糊

实际上这两个 yaml 是"**人工策展的领域语义层**"，承载 CodeGraph 永远填不上的洞：
- `not_for` / `audience` / `scenarios` —— 仓库级 negative information 和市场定位
- `computation_pattern` / `complexity` / `teaches` / `limitations` —— 算子级领域判断

不是教学教案，是"在生产代码上叠的可推荐 / 可过滤的元数据"。

---

## 二、设计原则

1. **代码侧解除"无排序"约束**：文档侧（PageIndex）继续 tree-walk + 无排序范式；代码侧（CodeGraph）承认其工程化 ranking 是 trusted source。CLAUDE.md §九 需要拆分为两套约束并存。

2. **人工策展元数据 + 自动提取代码事实 的双层互补**：
   - L0 = `repo_card.yaml` + `samples.yaml`（人工/半自动策展，回答"该看什么 / 教什么 / 为什么")
   - L1-L4 = CodeGraph 工程化能力（机器提取，回答"代码事实 / 关系 / 影响")

3. **lib 是教学语境包装层，不是 ranking 层**：所有 CodeGraph CLI 返回字段透传，lib 只做 schema 统一（envelope）、失败兜底、教学元数据组合。**lib 不二次排序、不过滤、不打分**。

4. **subprocess CLI 是最稳定的集成边界**：拒绝直挂 MCP server（会跟 CannEx 教学 prompt 打架）；拒绝直查 SQLite（绕过 CodeGraph 工程化成果，升级即崩）；用 `subprocess.run(["codegraph", ...])` + `--json`，CodeGraph 团队对 CLI 输出有 backward compat 承诺。

5. **重量级工具阙割暴露**：`codegraph_explore` / `codegraph_context` 在 README 中明确警告"不要在主 session 直接调"，但 webchat 没有 sub-agent 机制 → 阙割版只返回符号清单 + 引用，不返回源码。

6. **失败兜底显式化**：每个 API 失败时返回 `fallback_hint`，指向另一个 lib API，形成"工具间引导链"。

7. **samples 接受"精选推荐"定位**：不强求全量覆盖；未标注算子由 LLM 用 CodeGraph 兜底探索 + 明确提示用户"未经精选审阅"。

---

## 三、架构总览

```
┌─────────────────────────────────────────────────────────────┐
│  教学 Agent (Claude Sonnet 4.6 via bytego)                  │
│  - samples.yaml 决定教什么、按什么顺序                        │
│  - CodeGraph 工具回答代码事实                                 │
└──────────────────────┬──────────────────────────────────────┘
                       │ tool_use
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  webchat anthropic_client + worker/server.py               │
│  - JSON-RPC 路由到 lib                                       │
└──────────────────────┬──────────────────────────────────────┘
                       │ import
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  lib/cannex_knowledge/retriever_repo.py                    │
│                                                             │
│  L0 人工策展元数据（保留+简化）                                │
│    api_overview          → repo_card.yaml (不动)            │
│    api_list_samples      → samples.yaml (filter)            │
│    api_read_sample       → entry_files + samples 字段       │
│                                                             │
│  L1 符号定位（CodeGraph CLI 接入）                            │
│    api_search_symbol     → codegraph search                 │
│    api_node              → codegraph node                   │
│                                                             │
│  L2 图关系反查（新增 - 本次最大补足）                          │
│    api_callers           → codegraph callers                │
│    api_callees           → codegraph callees                │
│    api_impact            → codegraph impact                 │
│                                                             │
│  L3 文件级（保留现状）                                         │
│    api_list_files / api_read_file                           │
│                                                             │
│  L4 阙割版探索（新增）                                         │
│    api_explore_symbols   → codegraph context → 剥源码        │
└──────────────────────┬──────────────────────────────────────┘
                       │ subprocess
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  CodeGraph CLI (Node, 全局安装)                              │
│  $ codegraph -p <repo_path> <subcommand> --json             │
│  - SQLite + tree-sitter + FTS5 + ranking + resolution       │
│  - 索引: workspace/repos/<name>/.codegraph/codegraph.db     │
└─────────────────────────────────────────────────────────────┘
```

**模块边界**：

| 层 | 职责 | 谁实现 | 接口稳定性 |
|---|---|---|---|
| L0 元数据 | 仓库 / 算子的领域语义 | 人工策展 + bootstrap LLM | YAML schema |
| L1-L4 代码事实 | 符号、关系、影响、探索 | CodeGraph 上游 | CLI `--json` 契约 |
| lib | envelope 统一 + 失败兜底 + 教学语境包装 | 本项目 | Python API |
| worker | JSON-RPC 路由 | 本项目 | RPC schema |

---

## 四、samples.yaml 简化方案

### 字段保留 / 删除决策

| 字段 | 当前状态 | 新状态 | 理由 |
|---|---|---|---|
| `id` / `name` / `path` / `entry_files` | 人工 | 人工保留 | 定位必需，CodeGraph 不知道"入口是哪几个文件" |
| `computation_pattern` | 人工 | 人工保留 | samples 的杀手字段，CodeGraph 永远给不出领域语义 |
| `complexity` | 人工 | 人工保留 | beginner/intermediate/expert 过滤入口，需要 CANN 专家判断 |
| `teaches` | 人工 | 人工保留 | 教学要点，价值最高字段 |
| `limitations` | 人工 | 人工保留 | 重要 caveat 提醒 |
| `apis_used` | 人工 | **半自动**：build 时 LLM 扫 entry_files + 已知 Ascend C API 字典提取，人工 spot check | 降低维护成本，准确性可控 |
| `recommendation_reason` | 人工 | **删除** | 跟 `teaches` 语义重叠，纯人工字段 |
| `related_docs` | 留空 | 保留留空 | 未来双知识源关联使用 |

### 覆盖度策略

- 当前 ops-transformer 12 条覆盖（约占仓里所有算子的 1/3）—— **维持精选推荐定位，不强求全量覆盖**
- 未标注算子的兜底路径（写入 SKILL.md / system_prompt）：
  1. LLM 用 CodeGraph 工具（`api_search_symbol` → `api_list_files` → `api_read_file`）探索
  2. 回答中明确告知用户："此算子未经 CannEx 精选审阅，理解可能不全面，建议结合官方文档验证"

### Bootstrap 流程调整

`build/prompts/bootstrap_samples.md` 同步修改：
- 删除 `recommendation_reason` 字段定义
- `apis_used` 改为"从 entry_files 代码内容 + 已知 Ascend C API 字典（附在 prompt 内）自动提取"
- Ascend C API 字典作为 prompt 资源放在 `build/prompts/ascend_c_apis.yaml`（首次创建）

---

## 五、lib API 契约

### 统一 Envelope

所有 `api_*` 返回：

```python
{
    "source_type": "original" | "metadata",
    "evidence": [
        {"file_path": str, "start_line": int, "end_line": int}
    ],
    "data": {...},           # API 特定字段
    "error": str | None,
    "fallback_hint": str | None,
}
```

**字段语义**：
- `source_type` = "original"：CodeGraph 索引或代码原文（可信度高，直接给用户）
- `source_type` = "metadata"：repo_card / samples 等人工加工内容（需要在回答中标注"基于 CannEx 团队的标注"）
- `evidence`：可追溯引用清单（file_path + 行号），是 CannEx 立项底线"引用源可追溯"的载体
- `fallback_hint`：失败 / 部分成功时引导 LLM 切换工具的提示

### API 清单

#### L0 人工策展元数据

| API | 输入 | 返回 data 字段 | 备注 |
|---|---|---|---|
| `api_overview(repo)` | repo: str | `{tagline, audience, scenarios, not_for, key_paths, contribution, last_reviewed}` | source_type=metadata |
| `api_list_samples(repo, pattern=None, complexity=None, computation_pattern=None)` | 过滤条件 | `{count, samples: [...]}` | 删除 recommendation_reason 字段；新增 computation_pattern filter |
| `api_read_sample(repo, sample_id, skeleton=False)` | sample id | `{sample_meta, files: [{file, content, total_lines, truncated}], sibling_archs_covered, sibling_archs_missing, next_action_required?}` | 保留 sibling_archs hint 机制 |

#### L1 符号定位（CodeGraph CLI）

| API | 输入 | 返回 data 字段 | CLI 命令 |
|---|---|---|---|
| `api_search_symbol(repo, query, kind=None, limit=10)` | 查询字符串 + 可选 kind 过滤 | `{matches: [{name, kind, qualified_name, file_path, start_line, end_line, score, ...}]}` | `codegraph query "<query>" -p <path> -k <kind> -l <n> --json` |
| `api_node(repo, symbol, kind=None)` | 符号名 + 可选 kind | `{node: {<query 返回的 node 字段全集>}}` | `codegraph query "<symbol>" -p <path> -l 1 -k <kind> --json` 取第一条 `node` |

> **CLI flag 实测**：`query` 用 `-j / --json`；不接受 `--limit`，要用 `-l <n>`。字段命名 camelCase（`filePath` / `startLine` / `qualifiedName`），lib 层在 envelope 组装时统一 normalize 到 snake_case。

#### L2 图关系反查（新增 - CLI v0.9.4+）

| API | 输入 | 返回 data 字段 | CLI 命令 |
|---|---|---|---|
| `api_callers(repo, symbol, limit=20)` | 符号 + 上限 | `{symbol, callers: [{name, kind, file_path, start_line}]}` | `codegraph callers "<symbol>" -p <path> -l <n> --json` |
| `api_callees(repo, symbol, limit=20)` | 同上 | `{symbol, callees: [...]}` 同结构 | `codegraph callees "<symbol>" -p <path> -l <n> --json` |
| `api_impact(repo, symbol, depth=2)` | 符号 + 影响半径深度 | `{symbol, depth, node_count, edge_count, affected: [{name, kind, file_path, start_line}]}` | `codegraph impact "<symbol>" -p <path> -d <n> --json` |

> **注意**：callers/callees 当前 CLI 不暴露 depth 参数（默认深度 1）。如需多层调用链，由 LLM 多次调用 + 链式组合。

#### L3 文件级（保留现状）

| API | 输入 | 备注 |
|---|---|---|
| `api_list_files(repo, dir_path="", max_depth=2)` | 路径 + 深度 | 不变，filesystem 直读 |
| `api_read_file(repo, file_path, start_line=1, end_line=None)` | 文件路径 + 行范围 | 不变，filesystem 直读 |

#### L4 阙割版探索（新增）

| API | 输入 | 返回 data 字段 | CLI 命令 |
|---|---|---|---|
| `api_explore_symbols(repo, query, max_symbols=30)` | 自然语言任务 | `{query, summary, entry_points: [...], symbols: [{name, qualified_name, file_path, start_line, end_line, kind, ...}]}` **不包含源码（CodeGraph 内置过滤）** | `codegraph context "<query>" -p <path> -n <max_symbols> --no-code -f json` |

> **关键发现**：CodeGraph `context` 子命令**内置 `--no-code` 选项**，可直接告诉 CodeGraph 不返回 code blocks。lib 不需要后处理剥源码——直接传 `--no-code` 即可。比原计划简洁。

### Ranking 字段处理

CodeGraph 返回的 `score` 字段**透传**给 LLM。System prompt 必须包含：

> "工具返回的 `score` 字段仅供参考，来自 CodeGraph 内部的 graph distance + edge weight ranking。是否相关由你根据用户问题判断；不要因为 score 低就忽略，也不要因为 score 高就盲信。"

lib 层：**不二次排序、不过滤、不阈值切分**。

---

## 六、CodeGraph CLI 调用约定

### 统一调用函数

**关键细节**：`-p <path>` 参数位置在不同 CodeGraph 子命令上不同——所有子命令都接受 `-p` 作为 option，但 `<symbol>` 是 positional argument。**统一构造 `[subcommand, positional_arg, "-p", repo_path, *flags, json_flag]` 形式**，避免 flag 顺序错误。

```python
def _codegraph_call(
    repo: str,
    subcommand: str,
    positional: str,
    flags: list[str] = (),
    json_flag: str = "--json",   # query/callers/callees/impact 用 --json；context 用 ["-f", "json"]
    timeout: int = 10,
) -> dict:
    """统一的 CodeGraph CLI 调用，返回 JSON dict 或 error envelope。

    json_flag: 对 context 子命令传 "-f json"（注意是两个 token），其他传 "--json"。
              实现中接受 list[str] 或单 str，统一展开到 cmd。
    """
    repo_meta = get_repo_meta(repo)
    repo_path = (ROOT / repo_meta["local_path"]).resolve()

    if not (repo_path / ".codegraph").exists():
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
        r = subprocess.run(
            cmd, capture_output=True, timeout=timeout, text=True
        )
        if r.returncode != 0:
            return {
                "error": f"codegraph cli failed: {r.stderr[:500]}",
                "fallback_hint": "尝试用 api_list_files / api_read_file 直接探索",
            }
        return json.loads(r.stdout)
    except subprocess.TimeoutExpired:
        return {
            "error": f"codegraph cli timeout after {timeout}s",
            "fallback_hint": "尝试更窄的 query 范围",
        }
    except json.JSONDecodeError as e:
        return {
            "error": f"codegraph cli output not JSON: {e}",
            "fallback_hint": None,
        }
```

### CamelCase → snake_case normalize

CodeGraph 返回字段命名为 camelCase（`filePath` / `startLine` / `qualifiedName` / `endLine`）。lib 层在装入 envelope 时统一映射：

```python
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

def _normalize_keys(obj):
    """递归把 camelCase 字段重命名为 snake_case（只对在 _FIELD_MAP 的字段生效）。"""
    if isinstance(obj, dict):
        return {_FIELD_MAP.get(k, k): _normalize_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_keys(x) for x in obj]
    return obj
```

### 超时策略

- 默认：`search` / `node` / `callers` / `callees` = 10s
- 加长：`impact` / `context`（explore_symbols）= 20s
- 启动开销 ~100ms/call，不缓存进程（常驻进程引入状态管理复杂度，未来 Phase C 再评估）

### 多仓管理

- `workspace/repos/<name>/.codegraph/codegraph.db` 由 `build_repos.py` 生成
- 运行时通过 `_meta.json` 查 `local_path`，传给 `codegraph -p`
- 索引缺失时 lib 返回 error + fallback_hint，不静默失败

### CLI 可用性检测

worker 启动期检测 `which codegraph` + `codegraph --version`：
- 缺失 → worker 启动失败 + 明确错误消息（不让 LLM 看到这种系统级错误）
- 版本 < 0.9.4 → worker 启动失败（callers/callees/impact 不可用），提示 `npm i -g @colbymchenry/codegraph@latest`
- 存在且版本 OK → 正常启动

---

## 七、失败兜底与降级路径

### 典型失败场景

| 场景 | lib 行为 | fallback_hint 内容 |
|---|---|---|
| CodeGraph CLI 不在 PATH | worker 启动期 fail-fast | (用户不可见) |
| 索引不存在（`.codegraph/` 缺失） | error envelope | "运行 `build/build_repos.py` 建索引，或用 `api_list_files` 浏览" |
| 符号未找到 | 空 matches + hint | "未找到精确符号，建议 `api_search_symbol(kind=None)` 模糊查找，或 `api_list_files` 探索目录" |
| 调用链断裂（宏 / 模板特化） | 空 callers + hint | "CodeGraph 无法穿透宏展开 / 模板特化，建议 `api_read_file` 直读源码定位调用点" |
| subprocess timeout | error + hint | "尝试更窄的 query 范围或用更轻量的 `api_node`" |
| CLI 输出非 JSON（罕见） | error + 原始 stderr 截断 500 字符 | None（指示工程问题，需要人介入） |

### "工具间引导链"原则

所有 `fallback_hint` 必须指向**另一个 lib API**，不能只说"失败了"。这让 LLM 在工具失败时不需要 ground from scratch，能 graceful degrade 到下一个工具。

---

## 八、测试策略

### Record-Replay 模式

```
lib/cannex_knowledge/tests/fixtures/codegraph/
  └── ops-transformer/
      ├── search_FlashAttention.json
      ├── search_DataCopy.json
      ├── node_FlashAttentionScoreKernelBase.json
      ├── callers_DataCopy.json
      ├── callees_Process.json
      ├── impact_TilingFunc.json
      └── context_attention_pipeline.json
```

- **首次开发**：真跑 codegraph 捕获 JSON 输出存入 fixture
- **CI / 回归**：`monkeypatch` `subprocess.run` 返回 fixture 内容
- **集成测试**：单独 `@pytest.mark.integration` tag，仅本地跑（需要 codegraph CLI + 已索引仓）

### 测试用例覆盖

| 测试类型 | 覆盖范围 |
|---|---|
| 单元测试 | 每个 `api_*` 的正常返回、空返回、error envelope |
| 失败兜底 | 索引缺失、CLI 失败、timeout、非 JSON 输出 |
| Schema 一致性 | 所有 API 返回的 envelope 字段完整性 |
| 集成测试 | 真跑 codegraph CLI，验证 fixture 与实际输出 schema 一致 |

### 防回归

- **禁止 lib 写 SQL**：测试用 `grep -rn "sqlite3\|SELECT" lib/cannex_knowledge/retriever_repo.py` 必须为空（除非有明确豁免注释）
- **禁止 lib 内部排序**：测试用 grep 检查 `sorted(`、`key=lambda` 等模式，确认只用于 deterministic ordering 不是相关性排序

---

## 九、影响面清单

### 修改的文件

| 文件 | 动作 |
|---|---|
| `lib/cannex_knowledge/retriever_repo.py` | 删 `api_symbol` / `api_context` 的 SQL 实现；新增 `_codegraph_call` 与 L1-L2-L4 共 6 个 API；保留 L0-L3 现有实现并按新 envelope 改造 |
| `lib/cannex_knowledge/tests/test_retriever_repo.py` | 删 SQL 直查相关测试；新增 CodeGraph CLI mock 测试 + record-replay fixtures |
| `skills/ascend-c/tools/cannex_repo.py` | 新增 CLI 子命令：`search_symbol` / `node` / `callers` / `callees` / `impact` / `explore_symbols`；旧 `symbol` 子命令委托给 `api_search_symbol`；`context` 子命令删除（v1 反模式归档） |
| `skills/ascend-c/references/codegraph-guide.md` | **大改**：删除"裸 SQL 查询"全节；新增"按问题类型选 lib API"决策树；说明 CodeGraph CLI 是 trusted ranking source |
| `skills/ascend-c/SKILL.md` | 工具清单 + 决策树更新（新工具的使用建议） |
| `webchat/cannex_chat/prompts/system_prompt.md` | 同步 SKILL.md 的工具决策树调整 |
| `webchat/cannex_chat/worker/server.py` | 启动期检测 `codegraph` CLI 可用性 |
| `CLAUDE.md` | §九 拆分：文档侧 tree-walk 无排序约束 + 代码侧 CodeGraph 工程化约束 并列 |
| `build/prompts/bootstrap_samples.md` | 删 `recommendation_reason`；`apis_used` 改半自动提取 |
| `build/build_repos.py` | bootstrap_samples 步骤同步修改（半自动 apis_used） |
| `workspace/repos/*/samples.yaml` | 删除 `recommendation_reason` 字段（人工 review 一次） |

### 新增的文件

| 文件 | 内容 |
|---|---|
| `build/prompts/ascend_c_apis.yaml` | Ascend C 已知 API 字典（首次创建，bootstrap_samples 用） |
| `lib/cannex_knowledge/tests/fixtures/codegraph/ops-transformer/*.json` | Record-replay fixtures |

### 不动的文件

- `lib/cannex_knowledge/retriever_doc.py`（文档侧 PageIndex 范式不变）
- `lib/cannex_knowledge/paths.py`
- `workspace/repos/*/repo_card.yaml`（完整保留）
- `workspace/docs/*.json`

### 删除的概念

- "lib 直查 SQLite nodes/edges 表" —— 进 §九 废弃名册
- `api_symbol` / `api_context`（SQL 实现） —— 进废弃名册
- `recommendation_reason` 字段 —— 进废弃名册

---

## 十、Phase 分解

### Phase A · CodeGraph 接入 + lib 重构（一个 plan）

**目标**：lib 完成范式切换，CodeGraph CLI 完整接入，6 个新 API 可用，旧 SQL 路径完整废弃。

**关键 Task**：
1. `_codegraph_call` 工具函数 + 启动期 CLI 可用性检测 + 测试
2. record-replay 测试基础设施 + fixtures 捕获脚本
3. `api_search_symbol` / `api_node`（L1）
4. `api_callers` / `api_callees` / `api_impact`（L2，本次最大补足）
5. `api_explore_symbols`（L4 阙割版）
6. samples.yaml schema 简化：删 `recommendation_reason`，`apis_used` 改半自动（同步 bootstrap prompt + Ascend C API 字典）
7. 废弃 `api_symbol`（SQL）/ `api_context`（SQL）—— 完全切到 CodeGraph CLI
8. 全量回归 + 单元测试覆盖率检查

### Phase B · 文档 / Prompt / 教学语境贯通（一个 plan）

**目标**：教学 LLM 真正用上新能力；文档体系与新架构对齐。

**关键 Task**：
1. `codegraph-guide.md` 大改（删 SQL 节、加"按问题类型选工具"决策树）
2. CLAUDE.md §九 拆分（文档侧 / 代码侧 约束并列；废弃名册新增 SQL 直查 + recommendation_reason）
3. SKILL.md 工具清单 + 决策树更新
4. webchat `system_prompt.md` 工具清单 + 决策树更新
5. `cannex_repo.py` CLI 新增子命令 + 旧子命令委托
6. webchat E2E 冒烟（真跑，验证 LLM 在 callers / callees / impact / explore_symbols 上的调用合理性）

### Phase C · 可选优化（未来）

- 监控 samples 未覆盖算子在用户问题中的命中率，决定是否补充人工标注
- 评估常驻 codegraph 进程的收益（vs 启动开销）
- samples.yaml 扩展 `key_symbols` 字段，让 LLM 在精读时优先用 callers 探索这些符号
- repo_card.yaml 扩展 `entry_points` 字段，引导 LLM 起步符号

---

## 十一、Escape Hatch（未来回退点）

如果实施后发现：
- LLM 现场推断 `computation_pattern` 太不准
- 用户体验比有 samples 时明显降级

可以**增量加回**：

- `api_overview` envelope 预留 `curated_operators` 可选字段（默认 None）
- 加回时只需新文件 + lib 多读一行，不动其他架构

这样彻底简化与保留人工策展两种路径兼容。

---

## 十二、不在本 spec 范围内（明确排除）

- **不改 PageIndex 文档侧**：`retriever_doc.py` 完全不动，文档侧范式继续 tree-walk + 无排序
- **不改 CodeGraph 上游**：所有改动局限在 CannEx 项目内，CodeGraph 当作外部 trusted dependency
- **不引入 sub-agent 机制**：webchat 当前 anthropic_client 是单线 agent loop；引入 sub-agent 是独立改造，超出本 spec 范围
- **不引入 MCP 协议**：lib 走 subprocess CLI，不改 webchat 走 MCP server 集成
- **不做 samples 全量覆盖**：保持精选推荐定位
- **不做"代码↔文档"自动关联映射表预构建**：维持项目 §二 的"Agent 在线动态完成"约定

---

## 十三、关键事实速查（实施时回查）

- CodeGraph 上游：`/Users/justbin/project/CANN/codeIndex/codegraph`
- CodeGraph npm 包：`@colbymchenry/codegraph`，**最低版本要求 0.9.4**（callers/callees/impact 引入）
- CodeGraph 9 个 MCP 工具：`search` / `node` / `callers` / `callees` / `impact` / `context` / `explore` / `files` / `status`
- **CLI 暴露 6 个**：`query` (= MCP search) / `callers` / `callees` / `impact` / `context` / `files`（node 和 explore 仅 MCP）
- CLI JSON 输出 flag：`query/callers/callees/impact` 用 `-j/--json`；`context` 用 `-f json`
- `context` 子命令支持 `--no-code` 直接过滤源码（lib 不需后处理）
- CodeGraph JSON 字段命名：camelCase（`filePath` / `startLine` / `qualifiedName`），lib 层 normalize 到 snake_case
- 当前已索引仓：ops-transformer（`.codegraph/codegraph.db` ~422 MB）
- 索引规模：~6,200 文件 / ~109,000 符号 / ~222,000 边
- ops-transformer samples.yaml 当前条目：12 条覆盖 Attention/FFN/GMM/MoE/MC2/PosEmbedding/Experimental
- 测试入口：`cd ~/Desktop/CannEx && python3 -m pytest`
- pytest 配置：`asyncio_mode=auto`，`conftest.py` 把 root + lib 加入 sys.path

---

## 十四、Self-Review

- ✅ 无 TBD / TODO / 占位符
- ✅ 内部一致：架构图、API 表、Phase 分解、影响面清单互相对齐
- ✅ 范围聚焦：Phase A + B 是一次实施周期（约 2 个 plan）能消化的粒度
- ✅ 歧义消除：lib 不打分 / fallback_hint 必须指向另一个 API / samples 精选不全量覆盖 / 范式拆分文档代码两套 —— 都已明确
- ✅ 风险标识：差异化降级 / 准确率下降 / 响应延迟 已在前期讨论中评估，escape hatch 已留

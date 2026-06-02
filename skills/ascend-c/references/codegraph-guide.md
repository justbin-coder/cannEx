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
- ✅ samples.yaml 精选不覆盖全仓，未标注算子由 `api_search_symbol` + `api_list_files` 兜底，并提示用户"未经精选审阅"
- ✅ 文档侧 PageIndex 范式（tree-walk + 无排序）与代码侧 CodeGraph 范式（CLI ranking + envelope）并存，互不污染

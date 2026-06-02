# 后续关键任务清单 · 2026-05-28

> 状态：**待启动**（仅作记录，未排期）
> 来源：webchat redesign 验收阶段暴露的可靠度缺口 + 对外服务化前置工作
> 关联 plan：`2026-05-24-webchat-redesign.md`（Phase 2 主线，已完成 15 Tasks）

---

## 任务一：CodeGraph 使用可靠度优化

### 现状

- CodeGraph 实际产物在 `raw/repos/<name>/.codegraph/codegraph.db`（ops-transformer 422MB），含 **109,524 nodes** 与 **222,171 edges**（calls 87,461 · contains 103,282 · extends 1,207 · instantiates 4,376 · imports 25,835）
- `skills/ascend-c/tools/cannex_repo.py` 当前只查 `FROM nodes WHERE name = ?`（line 286/340/346），**edges 表完全闲置**
- 等价于把 CodeGraph 当作"符号名索引"用，这部分能力与 grep 大面积重叠 → 422MB 投入未兑现独有价值
- `workspace/repos/ops-transformer/codegraph.db` 曾存在 0 字节空文件（已在 c406702 清掉），路径混淆隐患
- `raw/repos/` 被 `.gitignore` 排除，对外部署时必须配套发布或在服务器侧重建

### 价值假设

CodeGraph 不可被 grep 替代的能力集中在 **关系层（edges）**：

1. **调用链反查**：grep 只能找定义/字面引用，无法判定真实调用关系（C++ 模板/重载/宏会大量误伤）；CodeGraph 的 `calls` 边是经语义分析得到的
2. **继承树/虚函数族**：`extends` 边可直接列出某基类的所有子类、某接口的全部实现
3. **影响面评估**：改一个 API 前先反查 callers，避免遗漏
4. **跨文件语义跳转**：grep 给行号，CodeGraph 给精确 symbol range + file_path（自动消歧 arch32 vs arch35 同名实现）

源码 + CodeGraph 的协同方式：CodeGraph 作"地图与索引"（WHERE + 关系），源码作"内容"（WHAT）→ 用更少 token、更少 round-trip 落在 3-5 iter 预算内。

### 待做

- [ ] **设计 edges 类工具**（cannex_repo.py 新子命令）：
  - `find_callers <symbol>` — 反查调用方
  - `find_callees <symbol>` — 顺查被调用方
  - `get_class_hierarchy <class>` — 列出父类/子类树
  - `find_implementations <interface>` — 列接口实现者
- [ ] **SKILL.md 同步**：把新工具列入「检索工作流」语义动作表，标清适用场景（改 API 前评估影响面、读懂某算子的协作子模块、查继承族）
- [ ] **webchat tools.py 注册**：把新工具映射成 Anthropic tool_use 定义
- [ ] **路径一致性**：`_get_codegraph_db()` 统一走 `_meta.json` 配置，防止再出现空文件路径误读
- [ ] **部署形态评估**：对外服务时 raw/repos/ 与 .codegraph/ 的发布策略（CI 重建 vs 制品库分发 vs OSS 拉取）
- [ ] **刷新策略**：CANN 季度更新时 CodeGraph 索引重建窗口与失败回滚

### 验收

至少跑通 1 个真实 case：例如「FlashAttention 的 Tiling 逻辑改了，谁会受影响」→ 应通过 `find_callers` 一步定位调用方而不是 grep 全仓。

---

## 任务二：PageIndex 使用可靠度优化

### 现状

- 文档侧主推 PageIndex（DeepSeek v4-flash 建树），webchat 侧通过 `cannex_doc.py {structure, pages, search}` 走它
- 已知补丁 5 处记录在 `CLAUDE.md §五`：trailing comma、tiktoken 本地计数、max_tokens/timeout/json_object、5 处 KeyError → .get()、physical_index 缺失返回 None
- 现网未覆盖的可靠度问题：
  - 大文档建树偶发 DeepSeek 服务端断连（靠重试自愈，但失败会让某些章节 physical_index 为 None → 后续 page 检索拿不到内容）
  - 复杂排版 PDF 的 PyMuPDF 解析质量天花板低，未接 OCR 兜底
  - search 是关键词匹配，对中文同义词与术语缩写（如 "TQue" vs "Tile Queue"）召回有限
  - 缺监控：哪些文档建树降级、哪些章节 physical_index 为 None、search 零召回比例

### 待做

- [ ] **建树质量巡检**：写 `build/audit_docs.py` 输出每篇文档的 `coverage_rate`（有 physical_index 的节点占比）、`depth_mean`、`empty_section_count`
- [ ] **失败兜底**：建树失败时把 `raw/docs/<id>.pdf` 标记为 `degraded`，检索层降级到 PyMuPDF 直接抽页 + 模糊匹配
- [ ] **复杂排版 PDF 二级方案**：评估外部 OCR（如 PaddleOCR / Marker）作为 PyMuPDF 不能胜任时的备选解析器
- [ ] **检索召回提升**：term-level 同义词表（arch32/Ascend 910B、TQue/TileQueue、UB/Unified Buffer 等），在 search 之前做 query 扩展
- [ ] **监控指标**：webchat 侧记录每次 query_documentation 的命中率，定期回查 0 召回 query 集
- [ ] **PageIndex 升级流程**：把 §五 5 处补丁封装成可重放的 patch 集（patch/ 目录或 fork 维护），升级时一键 reapply + 回归测试

### 验收

至少 3 篇大文档（FlashAttention 白皮书、Ascend C 编程手册、CANN 部署指南）跑过 coverage_rate ≥ 90% + degraded fallback 路径手测通过。

---

## 任务三：Webchat 多租户配置（LLM 服务自助配置）

### 现状

- 当前 webchat 已实现 **BYOK（用户自带 Anthropic API Key）**，浏览器 sessionStorage 暂存，单租户对接固定模型
- 模型由 `cannex_chat/agent/teacher.py` 硬编码（Sonnet 4.6 via bytego 代理）
- 教学侧 LLM 与文档建树 LLM（DeepSeek）解耦，但都对租户不可见

### 目标

把"自带 Anthropic Key"扩展为"自带 LLM 服务"，让租户在 webchat 内直接配置：模型 ID、endpoint base_url、API Key、可选的代理/auth header。

### 待做

- [ ] **配置 schema 设计**：租户级配置（provider、model、base_url、api_key、extra_headers、temperature、max_tokens）
- [ ] **配置存储**：浏览器 sessionStorage（沿用 BYOK 做法）vs 服务端加密存储 二选一 — 默认 session-only 零持久化，避免承担 key 托管责任
- [ ] **litellm 适配**：teacher.py 从硬编码模型 → 读取租户配置注入 litellm 调用参数（litellm 天然多家 provider，几乎零改）
- [ ] **配置 UI**：Chainlit settings panel 加表单（provider 下拉 + key/url 输入 + 测试连通按钮）
- [ ] **rate limit 维度**：从"全局 + 每 session" → "每租户 key" 维度限流，避免一个租户拖垮共享额度
- [ ] **prompt 兼容性**：当前 system prompt 与 cache_control 都是 Anthropic 语义；切换到 OpenAI/Gemini provider 时 cache_control 自动降级（litellm 已处理，需回归）
- [ ] **观测**：每次会话记录使用的 provider/model（不记录 key），便于事后分析模型差异下的教学质量

### 验收

至少跑通 3 个 provider：Anthropic（默认）、OpenAI（gpt-4.x）、本地 OpenAI 兼容服务（vLLM/Ollama）→ 同一个 6 类意图测试集都能完成基本回答。

---

---

## 任务四：多模型兼容能力抽象（接第二个 LLM 前必做）

> 登记时间：2026-05-28  
> 背景：当前 `AgentLoop` 强依赖原生 function-calling，未考虑弱工具模型的兜底路径。接入第二个模型（如 DeepSeek）前需完成以下抽象，否则逐个模型打补丁成本高。  
> **触发时机：接入第二个 LLM 厂商/模型之前，而非现在。**

### F-1：per-model 能力配置层

内容：
- 新增 `model_capabilities.py`（或 env 配置），声明每个 model 的：
  - `supports_tool_use: bool`
  - `supports_streaming_tools: bool`
  - `max_output_tokens: int`
  - `tool_call_format: "anthropic" | "openai"`
- `AgentLoop.__init__` 按 `MODEL` env 读取能力配置，按配置决定策略（工具轮次、format 选择等）

### F-2：弱工具模型 ReAct 兜底路径

内容：
- 在 `AgentLoop` 里加 `use_react_fallback` 模式：用 prompt 驱动 ReAct（思考→行动→观察纯文本格式），解析 action 文本后调 worker
- 与原生 tool_use 路径并存，按 F-1 能力配置切换，调用方无感知

### F-3：prompt 纪律多模型验证

内容：用标准问题集（含枚举类、代码定位、跨章节类各 5 题）在新模型上跑一次，验证：
1. 枚举类问题是否触发迁移章节补读（A 层启发式是否被遵守）
2. force prompt 反幻觉铁律（§章节来源、禁用预训练知识）是否被遵守
3. §章节引用是否与实际 `get_document_outline` 返回一致

把验证结果记录在对应模型的接入 ADR 里（`docs/decisions/YYYY-MM-DD-model-<name>.md`）。

### 已知技术债（不阻塞当前功能）

3 个 webchat async 测试（`test_loop_terminates_when_no_tool_use` 等）在 PageIndex venv 下因缺 `pytest-asyncio` 无法运行——需在 webchat 独立 venv 里补 `pytest + pytest-asyncio`，或在项目根 venv 统一管理测试依赖。

---

## 优先级建议

1. **任务一 CodeGraph edges 工具** — 投入最小、收益最直接（解锁现有 422MB 索引的核心能力），webchat 教学质量天花板可见提升
2. **任务三 多租户 LLM 配置** — 对外服务化必选项，但需先把"对外开放"的产品节奏定下来再排
3. **任务二 PageIndex 可靠度** — 内功活，建议在某次大文档批量建树失败之后顺势启动
4. **任务四 多模型能力抽象** — 接第二个厂商模型时再做，现在过度设计是 YAGNI

具体排期等 webchat E2E 验收（Task 14）通过后再决定。

# CannEx — CANN 开发者学习导师 Agent

> 本文件为 Claude Code 项目级上下文（自动加载）。只承载**稳定**项目知识；动态进度查 plans/。

---

## 一、项目身份

**CannEx** = 面向 Ascend C 算子开发者的 AI 学习导师 Agent。

一句话定位：**让开发者学会 Ascend C，不替他完成任务**。

**两阶段路线**：
- **Phase 1 · Skill 形态**：在 Claude Code 内通过 `ascend-c` Skill 提供 CANN 知识问答 + 学习向导（双知识源：PageIndex 文档 + CodeGraph 代码仓）
- **Phase 2 · Webchat 形态**：把 Phase 1 的教学能力衍生到独立 Web 应用（Chainlit），面向更广开发者

---

## 二、产品功能定位

CannEx 是昇腾算子开发者的双知识源 AI 学习助手，服务两类并列场景：

**场景 A · 官方技术文档对话式问答**
基于 CANN 官方文档（已建成 PageIndex 知识树）的自然语言问答与学习，把上千页晦涩文档变成 LLM 可推理的结构化知识。面向 **L0-L4 全光谱开发者**：入门用户用它代替翻文档建立概念，中高阶用户用它做精准章节定位。

**场景 B · 官方算子仓样例搜索、精读与二开辅助**
基于 CANN 官方算子仓（已建成 CodeGraph 代码图谱）的算子样例推荐与代码精读，按计算模式找参考实现、按函数边界讲解代码段。主要面向 **L2 以上中高阶开发者**，**包含基于昇腾官方算子做魔改 / 二开（secondary development）的开发者**——他们需要看懂算子完整调用链与执行逻辑、评估改动影响面后再动手。

**两场景协同**：读文档遇陌生概念可跳到代码看真实用法，读代码遇陌生 API 可跳到文档看规范。市面上没有人把官方文档和官方代码打通做——这是 CannEx 的差异化。

**核心约束**：
- 所有回答 grounded 在真实文档/代码片段，引用源可追溯（文档章节+页码、代码文件+行号）
- 文档检索严格按 PageIndex 原生 reasoning 范式（reasoning over ToC tree），不退化为关键词/向量召回
- "代码↔文档"关联由 Agent 在线动态完成，不预构建映射表，不依赖 LLM 自由发挥

**做调用链反查与影响面分析（2026-05-29 修订）**：服务二开/魔改场景的完整调用链梳理与改动影响面评估。**硬约束**：必须标注图谱盲区与 coverage 信号（CANN 宏 + CRTP 模板是静态图谱盲区，详见 `docs/superpowers/specs/2026-05-29-operator-call-chain-design.md`）、不替用户做改动决策，仍守"让开发者学会、不替他完成任务"底线。

**不做**：代码生成 / 代码补全、性能诊断、预构建概念对照表、预写精读导读、关键词/向量检索

---

## 三、进度速查

详细进度查 `docs/superpowers/plans/` 下**日期最新**的 plan。当前活跃 plan：

- `docs/superpowers/plans/2026-05-24-webchat-redesign.md`（Phase 2 webchat 架构重构 → 社区 demo 形态，**已完成全部 15 Tasks**）

历史已完成的 plan 同目录平铺，按文件名日期排序即可。

> 新会话回答"项目当前进展"时：webchat 重构已完成，所有组件就绪（tools/worker/agent loop/BYOK/rate limit），等待 E2E 手工验收（Task 14）。

---

## 四、目录地图

```
./                                           ← 项目根（仓库根目录，下文路径均相对于此）
├── CLAUDE.md                                ← 本文件（项目级上下文）
├── conftest.py / pytest.ini                 ← pytest 配置
├── chainlit.md                              ← Chainlit 说明文档
├── trim_pdf.py                              ← PDF 裁剪脚本
│
├── docs/                                    ← 文档中心
│   ├── CannEx-PRD.md / CannEx-SDD.md        ← 原始设计文档（历史）
│   ├── developer-needs.md                   ← 开发者需求分析
│   ├── specs/                               ← 设计契约
│   │   ├── 2026-05-22-skill-robustness.md
│   │   ├── 2026-05-23-cannex-v2-design.md
│   │   ├── 2026-05-23-codegraph-spike-report.md
│   │   └── 2026-05-24-webchat-architecture-design.md
│   └── superpowers/plans/                   ← 进度跟踪（YYYY-MM-DD-<feature>.md）
│       └── 日期最新的 plan 即为当前活跃计划
│
├── build/                                   ← 离线管道脚本
│   ├── sync_sources.py                      ← 拉取原始素材（按 docs.yaml / repos.yaml）
│   ├── build_docs.py                        ← 建文档树（调 PageIndex）
│   ├── build_repos.py                       ← 建代码仓索引（CodeGraph）
│   ├── monthly_update.sh                    ← 月度全量编排 + 报告归档
│   ├── docs.yaml / repos.yaml               ← 配置驱动（源地址清单）
│   └── prompts/                             ← 构建脚本的 prompt 模板
│       ├── bootstrap_repo_card.md
│       └── bootstrap_samples.md
│
├── lib/cannex_knowledge/                    ← 知识层（Phase 2 后独立）
│   ├── __init__.py
│   ├── paths.py                             ← workspace 路径常量
│   ├── retriever_doc.py                     ← 文档检索 API（PageIndex）
│   ├── retriever_repo.py                    ← 代码仓检索 API（CodeGraph）
│   └── tests/
│
├── skills/ascend-c/                         ← Phase 1 Skill（Claude Code 集成）
│   ├── SKILL.md                             ← 教学规则 + 双知识源路由
│   ├── __init__.py
│   ├── tools/
│   │   ├── cannex_doc.py                    ← 文档检索 CLI（PageIndex）
│   │   └── cannex_repo.py                   ← 代码仓检索 CLI（CodeGraph）
│   └── references/                          ← Skill 上下文（按需 Read）
│       └── codegraph-guide.md
│
├── workspace/                               ← 静态检索产物（phase 1/2 共用）
│   ├── _meta.json                           ← 版本 + 文档/仓清单
│   ├── docs/                                ← PageIndex 输出
│   │   └── <doc_id>.json                    ← 文档树 JSON
│   └── repos/                               ← 代码仓索引
│       └── <name>/                          ← 仓名目录
│           ├── repo_card.yaml               ← 仓元数据（自动生成 + 人工编辑）
│           ├── samples.yaml                 ← 样例标注（人工编辑）
│           └── .codegraph/                  ← CodeGraph 索引输出
│
├── webchat/                                 ← Phase 2 Chainlit 应用
│   ├── __init__.py
│   ├── cannex_chat/                         ← 主应用
│   │   ├── README.md
│   │   ├── app.py                           ← Chainlit 应用入口
│   │   ├── chainlit.md                      ← Chainlit 约定文件
│   │   ├── requirements.txt
│   │   ├── agent/                           ← Agent 逻辑
│   │   │   └── teacher.py                   ← 教学 Agent（复用 Phase 1 CLI）
│   │   ├── worker/                          ← 后台 worker
│   │   ├── middleware/                      ← Chainlit 中间件
│   │   ├── prompts/                         ← system_prompt.md 等
│   │   ├── ui/                              ← 前端组件
│   │   ├── public/                          ← 静态资源
│   │   └── tests/
│   └── chainlit/                            ← Chainlit fork（自定义修改）
│       ├── CLAUDE.md / AGENTS.md            ← fork 项目文档
│       ├── backend/                         ← Python 后端
│       ├── frontend/                        ← React 前端
│       └── [其他 Chainlit 源码结构]
│
├── raw/                                     ← 原始素材存放
│   ├── docs/                                ← PDF 文件
│   │   ├── CANN社区版 9.0.0 Ascend C算子开发指南 技术部分 01_trimmed.pdf
│   │   └── CANN社区版 9.0.0 软件安装 01.pdf
│   └── repos/                               ← Git clone 的代码仓
│       ├── ops-cv/
│       ├── ops-math/
│       ├── ops-nn/
│       └── ops-transformer/
│
├── tests/                                   ← 项目级测试
│   ├── __init__.py
│   ├── test_cannex_doc.py / test_cannex_doc_api.py
│   ├── test_cannex_repo.py / test_cannex_repo_api.py
│   └── test_sync_sources.py
│
├── reports/                                 ← monthly_update.sh 定期归档
│   └── YYYYMM.md                            ← 月度报告
│
├── logs/                                    ← 构建日志
│   ├── build_*.log / build_*.pid
│   └── webchat.log
│
└── .claude/                                 ← Claude Code 配置（.gitignored）

**外部依赖**（非项目目录树）：
~/project/CANN/PageIndex/                    ← PageIndex 开源仓（含 5 处补丁，见 §五）
  ├── .venv/                                 ← Python 3.11 虚拟环境
  └── [PageIndex 源码]
```

---

## 五、关键技术决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 文档建树 LLM | DeepSeek v4-flash | 中文友好、便宜（小文档 ~$0.05）、litellm 兼容 |
| 教学侧 LLM | Claude Sonnet 4.6（经 bytego 代理）| Phase 2 webchat 主推理模型 |
| PDF 解析 | PyMuPDF（PageIndex 默认）| 暂可接受；复杂排版后续考虑外部 OCR |
| 代码仓索引 | CodeGraph + 手写 repo_card.yaml/samples.yaml | 自动提取 + 人工标注混合 |
| Webchat 集成方式 | subprocess 调 Phase 1 的 CLI | 零侵入，知识层完全解耦 |
| 进度跟踪 | superpowers writing-plans 约定 | 命名 `YYYY-MM-DD-<feature>.md`，平铺在 plans/ |

---

## 六、PageIndex 源码补丁（已应用于 ~/project/CANN/PageIndex/）

| 来源 | 文件 | 修复内容 |
|---|---|---|
| issue #195 第 1 项 | `utils.py: extract_json` | 正则 `re.sub(r',\s*([}\]])', r'\1', s)` 处理嵌套 trailing comma |
| issue #195 第 2 项 | `utils.py: count_tokens` | 改 tiktoken 本地计数（cl100k_base），避免远程 token_counter 慢 |
| 我们的诊断 | `utils.py: llm_completion/acompletion` | `max_tokens=8192` + `timeout=60` + 条件 `response_format=json_object`；重试 10→5 + 指数退避 |
| 我们的诊断 | `page_index.py`（5 处）| `json_content['xxx']` → `.get('xxx', default)`，避免空响应 KeyError |
| 我们的诊断 | `page_index.py: single_toc_item_index_fixer` | 缺 physical_index 时返回 None 而非崩溃 |

> **PageIndex 升级时必须复审这些补丁**。

---

## 七、操作命令

### 激活环境
```bash
cd ~/project/CANN/PageIndex && source .venv/bin/activate
```

### 离线管道（建知识库）
```bash
# 拉取/更新原始素材（按 build/{docs,repos}.yaml）
python3 build/sync_sources.py

# 增量建文档树（PageIndex）
python3 build/build_docs.py
# 后台跑大文档：
nohup python3 -u build/build_docs.py > logs/build_<tag>.log 2>&1 &

# 代码仓 CodeGraph 索引
python3 build/build_repos.py

# 月度全量编排 + 报告归档到 reports/YYYYMM.md
bash build/monthly_update.sh
```

### 查询 workspace（Skill / Webchat 都通过 CLI）
```bash
python3 skills/ascend-c/tools/cannex_doc.py {list, structure, pages, search} ...
python3 skills/ascend-c/tools/cannex_repo.py {list, card, list_samples, code, symbol, context} ...
```

### Phase 1 · 在 Claude Code 中加载 Skill
```bash
# 从仓库根目录执行；软链需绝对源路径，用 $(pwd) 由当前位置推导，不再硬编码
ln -sf "$(pwd)/skills/ascend-c" ~/.claude/skills/ascend-c
```

### Phase 2 · Webchat 本地启动
```bash
cd webchat/cannex-chat && source .venv/bin/activate
chainlit run app.py -w
# 浏览器 → http://localhost:8000
```

---

## 八、给未来会话的提示

1. **回答"项目当前进展"**：只读 `docs/superpowers/plans/` 下日期最新的 plan，不要重新扫代码
2. **检索 workspace**：用 `tools/cannex_doc.py` / `cannex_repo.py`，不要直接 Read 大 JSON
3. **PageIndex 补丁不能丢**：见 §六，升级时必查
4. **建树失败排查**：先看 `logs/build_*.log`；DeepSeek 服务端断连通常自愈重试可恢复
5. **架构演进历史**：原设计在 `docs/CannEx-PRD.md` / `docs/CannEx-SDD.md`；收敛后的决策见本文件 §五 + 各 plan 自审节
6. **Skill 改动**：软链方式下无需重链；复制方式需重新 cp 到 `~/.claude/skills/`

---

## 九、双知识源使用约束（文档侧 + 代码侧 并列）

CannEx 有两个独立的知识源，**各自的检索范式不同，必须分开约束，不能互相污染**。

### 9.1 文档侧约束（PageIndex - 不变）

**哲学**：PageIndex 是 *vectorless, reasoning-based RAG*——relevance 由 LLM 在 ToC tree 上推理产生，**工具层不做打分排序**。

**工具能力契约**（`lib/cannex_knowledge/retriever_doc.py` 只允许这四类 API）：

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

**工具能力契约**（`lib/cannex_knowledge/retriever_repo.py` 分四层）：

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

**禁止出现的语义**（代码侧）：
- ❌ lib 内 SQLite 直查（`sqlite3.connect` / `SELECT FROM nodes` / `FROM edges` / `nodes_fts MATCH`）
- ❌ lib 内相关性二次排序（`sorted(matches, key=lambda x: x['score'])`）
- ❌ lib 内阈值过滤（`if score > threshold: ...`）
- ❌ 教 LLM 写裸 SQL（旧 `codegraph-guide.md` 模式，已废弃）

**反模式（✅ 已废弃，Phase A 实施，2026-05-28）**：
- `retriever_repo.api_symbol` — `SELECT FROM nodes WHERE name=?` → **改为委托 `api_search_symbol`，保留向后兼容包装**
- `retriever_repo.api_context` — SQL `LIKE '%query%' LIMIT 5` → **彻底删除**（由 `api_explore_symbols` 替代）
- `samples.yaml` 字段 `recommendation_reason` → **删除**（语义重叠 `teaches`）

**燃料能力到位（✅ Phase A 新增，commits 9e3d629—738224f）**：
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

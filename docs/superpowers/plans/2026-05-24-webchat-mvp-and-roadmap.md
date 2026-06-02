# CannEx Webchat MVP & 全局进度路线图

> ⚠️ **本 plan 部分 Task 已被 `2026-05-24-webchat-redesign.md` 取代**（Webchat 架构全面重构）。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 CannEx 教学能力从「Claude Code 内 Skill」扩展到「独立 Web 应用」，并把跨阶段进度从 CLAUDE.md 迁移到本 plan 统一跟踪。

**Architecture:** Chainlit 前端 + Python agent 编排层（意图分类 → 多源检索 → litellm 流式调用 Claude）。Webchat 通过 subprocess 复用现有 `cannex_doc.py` / `cannex_repo.py` CLI，零侵入现有知识层。

**Tech Stack:** Chainlit ≥2.5、litellm ≥1.40、Claude Sonnet 4.6（经 bytego.team 代理）、Python 3.11、subprocess 解耦检索依赖。

**关联文档：**
- `docs/specs/2026-05-23-cannex-v2-design.md`（v2 架构）
- `docs/superpowers/plans/2026-05-23-cannex-v2-alpha.md`（v2-α 实施 plan，已完成）

---

## 全局约束与共享上下文

- **工作目录**：`/Users/justbin/Desktop/CannEx/`
- **Webchat 子工程**：`webchat/cannex-chat/`（独立 .venv，**不**复用 PageIndex venv）
- **检索 CLI 路径**：`skills/ascend-c/tools/{cannex_doc.py, cannex_repo.py}`（v2-α 已交付）
- **LLM**：教学侧 `claude-sonnet-4-6`（litellm），文档建树侧 `deepseek/deepseek-chat`（PageIndex venv，未变）
- **环境变量**：`ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL=https://www.bytego.team` / `CANNEX_ROOT` / `CANNEX_MODEL`
- **commits 节奏**：每个 Task 完成后一次 commit

---

## 文件结构现状（v2-α + Webchat MVP 完成后）

```
~/Desktop/CannEx/
├── CLAUDE.md                              # 项目身份 + 操作命令，不再承载进度
├── build/                                 # 离线管道（v2-α 已交付）
│   ├── sync_sources.py
│   ├── build_docs.py
│   ├── build_repos.py
│   ├── monthly_update.sh
│   ├── docs.yaml
│   └── repos.yaml
├── skills/ascend-c/
│   ├── SKILL.md                           # v2 双知识源路由
│   └── tools/
│       ├── cannex_doc.py                  # 文档检索 CLI
│       ├── cannex_repo.py                 # 代码仓检索 CLI
│       └── cannex.py                      # v1 遗留入口
├── workspace/                             # 静态检索产物
│   ├── _meta.json                         # v2 schema
│   ├── docs/<doc_id>.json                 # PageIndex 输出（2 份文档）
│   └── repos/ops-transformer/             # repo_card.yaml + samples.yaml + .codegraph/
├── webchat/cannex-chat/                   # NEW — 本 plan 主体
│   ├── app.py                             # Chainlit 入口
│   ├── agent/
│   │   ├── teacher.py                     # 意图分类 + prompt 拼装 + 流式
│   │   └── retriever.py                   # subprocess 包装 cannex_{doc,repo} CLI
│   ├── chainlit.md                        # Chainlit 欢迎页
│   ├── requirements.txt
│   └── .env / .env.example
├── reports/202605.md                      # monthly_update.sh 归档
└── docs/superpowers/plans/                # 本 plan 所在地
```

---

## 已完成里程碑（仅勾选项，无需再执行）

### Milestone A：Day-0 PoC（已完成 · 2026-05-22）
- [x] PageIndex 环境就绪（venv + DeepSeek key）
- [x] PageIndex 源码 5 处补丁应用（utils.py / page_index.py，见 CLAUDE.md §五）
- [x] 小文档 PoC：`CANN 9.0.0 软件安装 01.pdf`（108 页）建树成功
- [x] Skill v1（单一 ascend-c Skill + cannex.py）软链到 `~/.claude/skills/`

### Milestone B：v2-α 架构升级（已完成 · 2026-05-23，commit b57852d）
对应 plan：`docs/superpowers/plans/2026-05-23-cannex-v2-alpha.md`
- [x] 目录骨架 + .gitignore + git init（commit a111d65）
- [x] workspace v2 schema 迁移（`_meta.json` 升级，文档移入 `docs/` 子目录）
- [x] `cannex_doc.py` v2 schema 适配 + `source_type` 字段
- [x] `build/sync_sources.py` 拉取/更新原始素材
- [x] `build/docs.yaml` + `build/repos.yaml` 配置驱动
- [x] `build/build_docs.py` 配置驱动批量建文档树（替代旧 `build_index.py`）
- [x] `build/build_repos.py` CodeGraph 索引阶段 + `_meta.json.repos` 注册
- [x] ops-transformer `repo_card.yaml` + `samples.yaml` 手写 bootstrap
- [x] `cannex_repo.py` 代码仓查询 CLI（list/card/list_samples/code/symbol/context）
- [x] `build/monthly_update.sh` 编排管道 + `reports/YYYYMM.md` 归档
- [x] `SKILL.md` v2 重写（双知识源路由 + 来源标注规则）

### Milestone C：文档扩库（部分完成）
- [x] `软件安装` PDF 建树（108 页，doc_id `717ca9ab…`）
- [x] `Ascend C 算子开发指南 技术部分 01_trimmed` PDF 建树（712 页，doc_id `e8997a18…`）
- [x] ops-transformer 仓 CodeGraph 索引

### Milestone D：Webchat MVP（已完成 · 2026-05-24）
- [x] `webchat/cannex-chat/` 工程骨架（独立 .venv，不污染 PageIndex 环境）
- [x] `requirements.txt`：chainlit / litellm / python-dotenv / pyyaml
- [x] `.env` 配置（ANTHROPIC_API_KEY / BASE_URL / CANNEX_ROOT / CANNEX_MODEL）
- [x] `app.py`：Chainlit 会话生命周期 + 流式输出 + 历史截断（10 轮）
- [x] `agent/retriever.py`：subprocess 包装 8 个 CLI 调用（doc_list/structure/pages/search、repo_list/card/list_samples/code/symbol/context）
- [x] `agent/teacher.py`：6 类意图分类（concept/code_example/api_lookup/repo_navigate/debug/howto）+ 检索编排 + SYSTEM_PROMPT（落地 SKILL.md 教学原则）
- [x] litellm 配置（ANTHROPIC_BASE_URL 走 bytego 代理）+ Claude Sonnet 4.6 流式

---

## 待办：Phase 1b 后续任务

### Task 1：Webchat 端到端真实问题验证

**Files:**
- Test: `webchat/cannex-chat/tests/manual_qa.md`（新建，记录测试 case + 实际输出）

- [ ] **Step 1: 启动服务**

```bash
cd ~/Desktop/CannEx/webchat/cannex-chat
source .venv/bin/activate
chainlit run app.py -w
```
Expected: 浏览器开启 `http://localhost:8000`，看到欢迎语「我是 CannEx…」

- [ ] **Step 2: 跑 6 类意图各 1 个用例，记录质量**

测试用例（写入 `tests/manual_qa.md`）：

| 意图 | 问题 | 预期检索路径 | 预期 quality 关注点 |
|---|---|---|---|
| concept | TPipe 是什么？和 TQue 的关系？ | doc_search(算子开发指南) | 来源标注 §章节 |
| howto | 怎么在 Ubuntu 安装 CANN toolkit？ | doc_search(安装) | 步骤完整 + 标注 |
| code_example | 找一个 FlashAttention 的算子实现 | doc + repo_context | `[REPO] ops-transformer/...` |
| api_lookup | `DataCopy` 的函数签名是什么？ | doc + repo_symbol | 命中行号 |
| repo_navigate | ops-transformer 仓有哪些算子？ | repo_card | 整理性描述带 ⚠️ |
| debug | DataCopy 报错 EE9999 怎么办？ | doc_search + install_ctx | 不胡编 + 引导排查 |

- [ ] **Step 3: 验收标准**

每个 case 检查：(a) 是否触发对应检索（看上下文有无 [DOC]/[REPO]）；(b) 是否有来源标注；(c) 当检索为空时是否说"未找到"而不是幻觉。失败 case 用 ⚠️ 标记到 `manual_qa.md`。

- [ ] **Step 4: Commit**

```bash
git add webchat/cannex-chat/tests/manual_qa.md
git commit -m "test(webchat): manual QA 6 intents end-to-end"
```

---

### Task 2：Webchat 关键缺陷修复（按 Task 1 发现的问题）

**预期常见问题** —— 验证后按需启用对应步骤：

- [ ] **Step 1: subprocess 超时调优**

`agent/retriever.py:23` 当前硬编码 `timeout=30`，CodeGraph 查询可能超时。改为按工具分级：

```python
TIMEOUTS = {"doc": 30, "repo_context": 60, "default": 30}
def _run(args, kind="default"):
    result = subprocess.run([PYTHON] + args, capture_output=True, text=True, timeout=TIMEOUTS[kind])
    ...
```

- [ ] **Step 2: 检索结果过长截断**

若 `_run` 返回 > 8000 字符，前端流式会很慢。在 `retriever.py` 各 doc/repo 函数尾部加 `result[:8000]` 截断 + 末尾追加 `\n…[截断]`。

- [ ] **Step 3: 意图分类兜底**

`teacher.py:67` 默认回退到 `"concept"` 可能漏检 repo 关键词。补充：classify 后若 `needs_repo(question, intent)` 为真但 intent 不在 repo 分支，强制改 `intent="code_example"`。

- [ ] **Step 4: Run Task 1 回归 + commit**

```bash
git add webchat/cannex-chat/agent/
git commit -m "fix(webchat): timeout tiering + result truncation + intent fallback"
```

---

### Task 3：文档扩库 P0/P1

**Files:**
- Modify: `build/docs.yaml`（追加 P0/P1 条目）

- [ ] **Step 1: 列出待建文档清单**

在 `build/docs.yaml` 中追加（按 CANN 9.0.0 官方资料）：

```yaml
- category: performance_tuning
  audience: [A, F]
  priority: P0
  source: raw/docs/CANN社区版 9.0.0 性能调优工具使用指南.pdf
- category: precision_debug
  audience: [A]
  priority: P1
  source: raw/docs/CANN社区版 9.0.0 精度调试工具.pdf
- category: operator_toolchain
  audience: [A, F]
  priority: P1
  source: raw/docs/CANN社区版 9.0.0 算子开发工具.pdf
```

- [ ] **Step 2: 获取 PDF 放入 raw/docs/**

由用户提供 PDF 路径或下载链接。**不**在 plan 里假定来源。

- [ ] **Step 3: 跑增量建树**

```bash
cd ~/project/CANN/PageIndex && source .venv/bin/activate
python3 ~/Desktop/CannEx/build/build_docs.py --only performance_tuning
# 大文档预估 1-2 小时 + ~$1-3，跑完看 logs/build_*.log
```
Expected: `workspace/docs/<new-doc_id>.json` 生成，`_meta.json` 新增条目。

- [ ] **Step 4: 抽查准确率**

```bash
python3 skills/ascend-c/tools/cannex_doc.py structure "性能调优"
python3 skills/ascend-c/tools/cannex_doc.py pages "性能调优" "10-15"
```
肉眼对照 PDF 原文，错误率 < 10% 视为合格。

- [ ] **Step 5: Commit 每个文档单独 commit**

```bash
git add build/docs.yaml workspace/_meta.json workspace/docs/<new-doc_id>.json
git commit -m "feat(workspace): index 性能调优工具使用指南 (P0)"
```

---

### Task 4：Pitfall 库种子建设

**Files:**
- Create: `workspace/pitfalls/_index.yaml`
- Create: `workspace/pitfalls/<slug>.yaml`（每条 1 文件）

- [ ] **Step 1: 定义 pitfall schema**

```yaml
# workspace/pitfalls/dc-host-device-sync.yaml
id: dc-host-device-sync
title: DataCopy 后忘记同步 Host/Device
symptom: 输出全 0 或脏数据
root_cause: aclrtSynchronizeStream 未调用
fix: |
  在 DataCopy 之后、读取 Host 内存之前调用 aclrtSynchronizeStream(stream)
references:
  - doc: "Ascend C 算子开发指南 §6.3"
    pages: "112-115"
  - repo: "ops-transformer/transformer/flash_attention/op_kernel/*.cpp"
applicable_to: [A, F]
```

- [ ] **Step 2: 从已建文档抽 10 条**

人工 + LLM 辅助从 `Ascend C 算子开发指南` 抽取典型错误。每条对应一个 yaml 文件。

- [ ] **Step 3: 新增 `cannex_pitfall.py` CLI**

```bash
python3 skills/ascend-c/tools/cannex_pitfall.py list
python3 skills/ascend-c/tools/cannex_pitfall.py show dc-host-device-sync
python3 skills/ascend-c/tools/cannex_pitfall.py search "DataCopy"
```

- [ ] **Step 4: 在 `teacher.py` 接入 `pitfall_search` 用于 `debug` 意图**

`retriever.py` 新增 `pitfall_search(question)`；`teacher.py:retrieve_context` 的 `debug` 分支前置调用，命中则注入 `[PITFALL]` 块。

- [ ] **Step 5: Commit**

```bash
git add workspace/pitfalls/ skills/ascend-c/tools/cannex_pitfall.py webchat/cannex-chat/agent/
git commit -m "feat(pitfalls): 10 条种子条目 + cannex_pitfall CLI + webchat 接入"
```

---

### Task 5：CLAUDE.md 瘦身（迁移进度到 plan）

**Files:**
- Modify: `CLAUDE.md`

**实际执行**：与用户对齐"两阶段（Phase 1 Skill / Phase 2 Webchat）+ CLAUDE.md 作为速查通道"信息架构后，一次性整体重写 CLAUDE.md（而非分步增删）。Task 5 + Task 5b 已合并完成。

- [x] **Step 1: 整体重写 CLAUDE.md（约 150 行 → 120 行）** ✅ 2026-05-24
  - 新增「§一 两阶段路线」明示 Phase 1 / Phase 2
  - 新增「§二 进度速查」指向 plans/ 日期最新文件
  - §三 目录地图重写为 v2-α + Phase 2 现状（含 build/、webchat/、cannex_doc/repo.py）
  - §四 技术决策表补充 Claude Sonnet 4.6 / CodeGraph / Webchat 集成方式
  - §六 操作命令重写为 v2-α 管道（sync_sources / build_docs / build_repos / monthly_update / chainlit run）
  - 删除 §三 架构论证（属于 spec 范畴）+ §四 Phase 1a 范围（属于 plan 范畴）
  - §七 给未来会话提示首条改为「先读 plan 再回答进展」

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md docs/superpowers/plans/2026-05-24-webchat-mvp-and-roadmap.md
git commit -m "docs(claude): 重写为身份+稳定知识+plans 指针，进度全量迁出"
```

---

### ~~Task 5b：CLAUDE.md §二/§四/§六 同步到 v2-α 现状~~ ✅ 已并入 Task 5

Task 5 整体重写时一并完成。

---

### Task 6（可选）：Webchat 部署化

仅当 Phase 1b 验证通过、想给同事试用时启动。

- [ ] **Step 1: Dockerfile**（chainlit 官方 base image + 复制 cannex 仓 + workspace 只读挂载）
- [ ] **Step 2: 鉴权**（chainlit 的 password auth 或对接公司 SSO）
- [ ] **Step 3: 部署目标确认**（本地 docker / 内网 server / 云厂商）后再展开具体步骤——本任务暂留占位，启动时另起 plan。

---

## 自审

- ✅ **进度覆盖**：CLAUDE.md §八/§九 的所有条目都映射到本 plan：
  - §八 Day 0 完成项 → Milestone A
  - §八 当前 workspace 内容 → Milestone C
  - §九 候选 1（Day 3 验证）→ Task 1
  - §九 候选 2-3（扩库）→ Task 3
  - §九 候选 4（Pitfall）→ Task 4
- ✅ **Webchat 新增**：Milestone D 完整记录已交付内容；Task 1-2 覆盖验证 + 修复
- ✅ **占位扫描**：除 Task 6（可选部署）明确标注「另起 plan」外，无 TBD
- ✅ **类型一致**：CLI 名称（cannex_doc / cannex_repo / cannex_pitfall）跨 Task 一致；意图分类 6 类与 teacher.py:50-58 一致
- ✅ **TDD/commit 节奏**：每个 Task 末尾有明确 commit 步骤

无遗留问题。

# CannEx v2 设计文档

**日期**：2026-05-23
**版本**：v2.0（草案）
**状态**：待评审
**前置**：v1（已完成单 Skill + 2 份 PDF 建树基线）

---

## §1 整体定位

### 1.1 产品定位

**CannEx 是昇腾 CANN 开发者的知识助手**，根据用户角色与意图自适应切换"教学引导 / 直接答 / 导航 / 对照"四种应答模式，把分散在**官方文档 + 几十个开源代码仓**中的知识，以可信、可溯源、低幻觉的方式传递给开发者。

与 v1 定位（"让算子开发者学会 Ascend C"）的关键变化：

- "学会"不再是唯一目的——对应用开发类问题，直接给答案是更合理的帮助
- 知识源从"PDF 文档"扩展到"文档 + 代码仓"两条并行的索引
- "自适应"成为核心能力——由意图识别决定应答模式

### 1.2 目标用户与"实质性帮助"

| 角色 | 高频问题模式 | CannEx 提供的帮助 |
|---|---|---|
| **A 算子开发者** | "Pipeline 怎么用"、"UB 大小不够"、"Tiling 怎么算" | 教学引导 + 概念溯源（保留 v1 定位） |
| **B 应用开发者** | "怎么装环境"、"这个 API 怎么调"、"为什么报错" | 直接答案 + 文档来源 |
| **F 代码仓使用/贡献者** | "哪个仓有 vector→cube 样例"、"我要加算子改哪些文件" | 代码仓导航 + 样例推荐 + 贡献路径 |

### 1.3 边界（明确不做）

**做**：
- ✅ 性能调优技术文档全量纳入 PageIndex 检索树（传递知识/方法论/经验）

**不做**：
- ❌ 不集成公司内部性能分析/调优工具（已有专门团队负责）
- ❌ 不做 Web/IDE 形态（Phase 1 只 Claude Code Skill；Web 是后置阶段）
- ❌ 不做代码生成器（教学场景仍不替写代码；代码仓样例可引用）
- ❌ 不做横向竞品对比
- ❌ 不做模型迁移类知识（已移除 C 迁移工程师角色）

---

## §2 架构分层

### 2.1 核心原则

**Skill 是接入层之一，不是核心**。所有"知识"和"业务逻辑"必须落在可独立调用的层，使未来 Web 接入层能复用同一套数据和工具。

避免的反模式：
- ❌ 把意图路由、应答策略写死在 SKILL.md 的 prompt 里且无 Web 复用（v1 现状）
- ❌ workspace JSON 格式与 Claude Code 强耦合
- ❌ 在 LLM 已经胜任的环节（意图理解、应答合成）发明独立 Python 服务（避免过度设计）

### 2.2 三层架构

```
┌─────────────────────────────────────────────────────────┐
│ 【离线管道】（月度跑一次，或文档/代码更新时）            │
│   build/                                                │
│   ├── repos.yaml + docs.yaml      ← 源配置             │
│   ├── sync_sources.py             ← 自动拉取原始素材    │
│   ├── build_docs.py               ← PageIndex 建文档树  │
│   ├── build_repos.py              ← CodeGraph + bootstrap│
│   └── monthly_update.sh           ← 串起整条管线       │
└─────────────────────┬───────────────────────────────────┘
                      ▼ 产出静态产物
┌─────────────────────────────────────────────────────────┐
│ 【数据层】workspace/                                     │
│   ├── docs/<doc_id>.json          (PageIndex 文档树)   │
│   ├── repos/<repo>/                                     │
│   │   ├── .codegraph/codegraph.db (CodeGraph 索引)     │
│   │   ├── repo_card.yaml          (人工/半自动)         │
│   │   └── samples.yaml            (人工/半自动)         │
│   └── _meta.json                  (全局清单)            │
└─────────────────────┬───────────────────────────────────┘
                      ▼ 被运行时查询
┌─────────────────────────────────────────────────────────┐
│ 【查询工具】tools/                                       │
│   ├── cannex_doc.py    ← 查 PageIndex                  │
│   └── cannex_repo.py   ← 查 repo 元信息 + CodeGraph    │
│   （简单 CLI，无服务抽象）                              │
└─────────────────────┬───────────────────────────────────┘
                      ▼ 被接入层调用
┌─────────────────────────────────────────────────────────┐
│ 【接入层】                                              │
│   Phase 1 (当前):                                       │
│     Claude Code Skill                                    │
│     └── SKILL.md 教 LLM 用上面两个 CLI                 │
│                                                          │
│   Phase 2 (Web 化，后置):                               │
│     选定的开源 Web agent 框架                           │
│     ├── 把同样两个 CLI 注册为工具                       │
│     └── 把 SKILL.md 规则迁到 system prompt              │
└─────────────────────────────────────────────────────────┘
```

### 2.3 离线 vs 运行时边界

| 环节 | 时机 | 输出 |
|---|---|---|
| 拉取 PDF / git clone | 离线（月度或更新触发） | `raw/docs/`、`raw/repos/<repo>/` |
| PageIndex 建文档树 | 离线（增量） | `workspace/docs/<doc_id>.json` |
| CodeGraph 索引代码仓 | 离线（增量） | `workspace/repos/<repo>/.codegraph/` |
| Bootstrap 元信息生成（LLM 自动 + 人工 review） | 离线（增量 + 人工） | `workspace/repos/<repo>/{repo_card,samples}.yaml` |
| **运行时仅做静态产物 lookup** | 用户提问时 | agent 回答 |

**运行时绝不联网**。

### 2.4 Web 化迁移路径（v2-γ 阶段实施）

```
Phase 1 (当前)         →  Phase 2 (Web)
─────────────────────────────────────────
SKILL.md (规则文本)    →  复制到 Web agent system prompt
cannex_doc.py CLI      →  注册为 Web agent 的工具（同一脚本）
cannex_repo.py CLI     →  注册为 Web agent 的工具（同一脚本）
workspace/             →  Web agent 服务器读同一目录
```

迁移成本 ≈ 配置工作量，零核心代码改动。

**Web 化预留的全部内容**：SKILL.md 用普通 Markdown 写，不用 Claude Code 专属语法。零成本预留。

---

## §3 知识源结构

### 3.1 目录布局（原始素材 与 workspace 分离）

```
原始素材（与 workspace 分离，agent 不读取）
├── raw/docs/             ← 手动下载 / sync_sources 拉取的 CANN 官方 PDF
└── raw/repos/            ← git clone 的代码仓（完整 clone，非 --depth=1）

           │ 月度离线管道
           ▼

workspace/                ← agent 唯一读取的目录
├── _meta.json            ← 全局清单（轻量）
├── docs/<doc_id>.json    ← PageIndex 产物
└── repos/<repo>/
    ├── .codegraph/       ← CodeGraph 索引
    ├── repo_card.yaml    ← 仓库定位
    └── samples.yaml      ← 样例清单
```

**关键**：`raw/repos/` 用**完整 clone**，不用 `--depth=1`，避免丢失历史信息。

### 3.2 `_meta.json` 全局清单

```json
{
  "version": "v2.0",
  "cann_version": "9.0.0",
  "last_updated": "2026-05-23",
  "docs": [
    {
      "doc_id": "e8997a18-...",
      "doc_name": "Ascend C 算子开发指南",
      "category": "operator_dev",
      "audience": ["A", "F"],
      "pages": 712,
      "priority": "P0"
    }
  ],
  "repos": [
    {
      "repo_name": "samples",
      "repo_url": "https://gitee.com/ascend/samples",
      "category": "operator_samples",
      "audience": ["A", "F"],
      "indexed_at": "2026-05-23",
      "priority": "P0"
    }
  ]
}
```

agent 看完 `_meta.json` 就能知道有什么知识源、各自定位、覆盖哪类用户——所有路由决策的起点。

### 3.3 文档知识源

P0 文档清单（按角色排序）：

| category | 文档 | 服务角色 | 状态 |
|---|---|---|---|
| `install` | CANN 软件安装指南 | B | ✅ 已建 |
| `operator_dev` | Ascend C 算子开发指南 | A | ✅ 已建 |
| `app_dev` | CANN 应用开发指南 | B | 📋 待建 |
| `performance` | 性能调优指南 + 经验文档 | A 进阶 / B 进阶 | 📋 待建 |
| `troubleshooting` | 常见问题/错误码手册 | 全员 | 📋 待建 |

文档结构沿用 v1 PageIndex 产物（已验证，不改）。

### 3.4 代码仓知识源（v2 新增）

#### 3.4.1 `repo_card.yaml`

```yaml
repo_name: samples
repo_url: https://gitee.com/ascend/samples
audience: [A, F]
category: operator_samples

tagline: "Ascend C 官方算子样例集，覆盖 Vector/Cube/混合算子的入门到进阶实现"

scenarios:
  - 找参考实现学习算子开发
  - 验证 Tiling/Pipeline 设计模式
  - 贡献新算子样例

not_for:
  - 生产环境直接复用
  - 性能极致调优案例

key_paths:
  - path: operator/AddCustomSample
    desc: 最简单的 Vector 算子样例，入门首选
  - path: operator/MatmulCustomSample
    desc: Cube 算子样例
  - path: operator/MixVecCubeSample
    desc: Vector→Cube 混合算子样例

contribution:
  guide_path: CONTRIBUTING.md
  pr_template: .github/PULL_REQUEST_TEMPLATE.md

maintained_by: cannex_team
last_reviewed: 2026-05-23
```

#### 3.4.2 `samples.yaml`（核心增量价值）

```yaml
samples:
  - id: add_custom_basic
    name: AddCustom 基础版
    path: operator/AddCustomSample
    entry_files:
      - add_custom.cpp
      - add_custom_tiling.cpp

    # 业务语义标签（agent 检索关键）
    computation_pattern: vector  # vector / cube / vector_to_cube / cube_to_vector / fusion
    apis_used: [DataCopy, Add, TPipe]
    complexity: beginner          # beginner / intermediate / expert

    teaches:
      - Pipeline 三阶段基本结构
      - TPipe 内存分配

    recommendation_reason: "代码最短、结构最清晰，是理解 Ascend C 算子骨架的最佳起点"

    limitations:
      - 未使用 Double Buffer

    related_docs:
      - doc_id: e8997a18-...
        section: "第 3 章 算子开发流程"

  - id: mix_vec_cube_basic
    name: Vector→Cube 混合算子样例
    path: operator/MixVecCubeSample
    computation_pattern: vector_to_cube
    apis_used: [DataCopy, Add, Mmad, TPipe, TQue]
    complexity: intermediate
    teaches:
      - Vector 计算与 Cube 计算的衔接
      - UB → L0 数据流编排
    recommendation_reason: "官方推荐的 vec→cube 衔接范例，UB/L0 复用思路清晰"
```

**三个标签是检索关键**：`computation_pattern` × `complexity` × `apis_used` 让 agent 能精确响应业务问题（如"先 vector 再 cube 的好实现"）。

#### 3.4.3 P0 代码仓清单

| repo | category | 服务角色 | 优先级 | 阶段 |
|---|---|---|---|---|
| `samples` (官方算子样例) | operator_samples | A, F | P0 | v2-α PoC |
| `cann-ops-adv` (高级算子) | operator_advanced | A 进阶 | P0 | v2-β |
| 其他仓（用户指定本地路径） | TBD | TBD | TBD | v2-β |

### 3.5 跨源引用（文档 ↔ 代码仓）

- **代码 → 文档**：`samples.yaml` 的 `related_docs` 字段
- **文档 → 代码**：暂不主动反向链接（成本高，价值低）；agent 可在概念回答后追加"如想看代码实现，samples 仓有对应样例 `<id>`"

### 3.6 仓库/文档自动拉取脚本

#### `build/repos.yaml`

```yaml
repos:
  - name: samples
    url: https://gitee.com/ascend/samples.git
    ref: master                  # branch / tag / commit hash
    audience: [A, F]
    priority: P0
    enabled: true

  - name: cann-ops-adv
    url: https://gitee.com/ascend/cann-ops-adv.git
    ref: v9.0.0
    audience: [A]
    priority: P0
    enabled: false               # v2-α 阶段先关掉
```

#### `build/docs.yaml`

```yaml
docs:
  - name: ascend-c-dev-guide
    url: https://www.hiascend.com/document/...
    version: 9.0.0
    enabled: true
```

#### `build/sync_sources.py`

职责：
1. 读 repos.yaml + docs.yaml
2. 对每个 enabled=true 的项目：
   - repo：不存在 → git clone --branch <ref>；已存在 → git fetch + git checkout <ref>
   - doc：比对本地版本，url 给的版本更新则下载
3. 输出变更摘要 → 决定 build_docs.py / build_repos.py 哪些需要重跑

### 3.7 完整离线管道

```bash
build/
├── repos.yaml + docs.yaml       # 配置（人工维护）
├── sync_sources.py              # ① 拉取/更新原始素材
├── build_docs.py                # ② PageIndex 建树（增量）
├── build_repos.py               # ③ CodeGraph + bootstrap 元信息（增量）
└── monthly_update.sh            # 串起 ①②③

monthly_update.sh:
  python sync_sources.py        # 拉新
  python build_docs.py          # 增量建文档树
  python build_repos.py         # 增量建仓库索引
  echo "Review report at ./reports/$(date +%Y%m).md"
```

### 3.8 半自动 bootstrap 工作流（针对新代码仓）

```
build/build_repos.py <repo_name>
   │
   ├─ 1. 检查 raw/repos/<repo>/ 存在
   ├─ 2. codegraph init 生成 .codegraph/
   ├─ 3. 调 LLM 扫 README + 目录结构 → repo_card.yaml 初稿
   ├─ 4. 扫示例目录 → samples.yaml 初稿（自动打 computation_pattern 等标签）
   └─ 5. 输出报告：哪些字段 LLM 不确定，需要人工 review
```

人工 review 后 commit，即作为权威源。下次仓库更新时增量重跑（变化文件触发对应样例字段更新）。

---

## §4 意图路由设计

### 4.1 核心思想

**意图路由不是一段代码，而是 SKILL.md 里给 LLM 的判别表 + 决策树**。LLM 在每轮对话开始时跑一遍这套规则，决定：

```
意图路由输出 = (角色推断, 意图类型, 应答模式, 检索计划)
```

### 4.2 角色推断（信号驱动，不主动问）

| 用户语境信号 | 推断角色 |
|---|---|
| 提到 UB / GM / TPipe / Tiling / Cube / Vector / AI Core | A |
| 提到 ACL / aclrtMalloc / 推理流程 / 模型加载 | B |
| 提到 git / PR / 贡献 / 仓库 / sample / example / 参考实现 | F |
| 仅提到"算子是什么"、"CANN 是什么"等概念 | 默认 A |
| 多类信号混合 | 取最强信号；冲突时按 A>F>B 优先级 |

**绝不主动问"你是哪类开发者"**——根据问题判断，错了用户下一轮自然纠正。

### 4.3 意图类型

| 意图 | 触发信号 | 知识源偏好 |
|---|---|---|
| `concept` | "是什么"、"原理" | docs（概述节点） |
| `howto` | "怎么用"、"步骤"、"如何" | docs（示例节点） |
| `debug` | "报错"、"错误"、"不生效" | docs + 错误码手册 |
| `compare` | "区别"、"对比" | docs（多节点并行） |
| `code-example` 🆕 | "样例"、"参考实现"、"代码" | repos（samples.yaml + CodeGraph） |
| `api-lookup` 🆕 | "X 的参数"、"X 怎么调" | docs（接口节点） |
| `repo-navigate` 🆕 | "X 仓的结构"、"我要加算子改哪" | repos（repo_card + CodeGraph） |

### 4.4 应答模式决策表（核心）

| 角色 | 意图 | 应答模式 |
|---|---|---|
| A | concept | 教学引导 |
| A | howto | 教学引导 |
| A | debug | 教学引导 |
| A | code-example | 导航 + 教学 |
| A | api-lookup | 直接答 |
| B | concept | 直接答（简） |
| B | howto | 直接答 |
| B | debug | 直接答 |
| B | api-lookup | 直接答 |
| F | repo-navigate | 导航 |
| F | code-example | 导航 |
| F | concept | 教学引导 |
| 全员 | compare | 对照（并列呈现） |

**优先级冲突**：高置信度信号 > 默认。例如 B 类问 concept 问题但提到"我要提 PR 加这个算子"——立刻切到 F 类应答。

### 4.5 检索计划（决定调哪个工具）

| 意图 × 应答模式 | 检索计划 |
|---|---|
| concept/howto/debug | `cannex_doc.list → structure → pages` |
| code-example | `cannex_repo.list_samples --pattern X → cannex_repo.code` |
| api-lookup | `cannex_doc.search_api`（按 API 名直接定位） |
| repo-navigate | `cannex_repo.card + CodeGraph` |

### 4.6 内容来源标注规则（v2 新增）

#### 核心原则

**每个技术断言必须标明来源类型，区分确定性与潜在幻觉**：

```
【原文抽取】（确定性高，直接给用户）
- 文档原文段落（不改写）
- 代码片段（来自代码仓原文，不修改）
- API 签名、参数表、错误码
- 视觉：> 引用块格式 + [来源] 标注

【LLM 加工】（可能失真，需备注）
- 类比 / 比喻
- 跨章节合成
- 教学性梳理（用自己话重新组织）
- 推理性回答（"为什么这么设计"）
- 视觉：⚠️ 标记 + 备注话术
```

#### 标注话术

**原文抽取**：
```markdown
> [原文]
> "TPipe 是 Ascend C 提供的统一内存与流水管理框架..."
> [来源: CANN 9.0.0 算子开发指南 §2.3]
```

**LLM 加工**：
```markdown
⚠️ 以下为基于检索原文的综合理解，可能存在加工偏差，关键技术决策请核对原文。

打个比方：内存搬运像快递员送货，Vector 计算像工人加工...
```

#### 决策规则

| 内容性质 | 标注 |
|---|---|
| 文档原段落引用 | `> 原文` + `[来源]` |
| 代码仓原文件片段 | 代码块 + `[来源]` |
| samples.yaml 人工字段（推荐理由等） | 视为权威，`[来源: samples.yaml]` |
| LLM 自由组织语言重述 | `⚠️` + 备注 |
| 类比 / 比喻 | `⚠️` + 备注 |
| 跨章节合成 | `⚠️` + 备注 |
| 推理性回答 | `⚠️` + 备注（且更慎重） |

#### 工程含义

- SKILL.md 增加"内容来源标注规则"章节，强制 LLM 在合成回答时做来源分段
- `cannex_doc.py` / `cannex_repo.py` 返回结果时必须附带 `source_type: "original" | "metadata"`，让 LLM 一眼分辨
- 任何 LLM 自由生成的连接性表达 → 默认归为加工，必须标注

### 4.7 路由失败兜底

| 失败场景 | 处理 |
|---|---|
| 角色信号完全缺失 | 默认 A（保守教学，等用户纠正） |
| 意图模糊 | 取并集，先概念后操作 |
| 应答模式冲突 | 按角色定夺：A→教学，B→直接答 |
| 检索全部命中失败 | 沿用 v1 三级失败处理 |

### 4.8 SKILL.md 在 v2 的目标结构（瘦身后 ~100 行）

```
SKILL.md
├── 1. 触发 description
├── 2. 角色推断信号表（4.2）
├── 3. 意图类型表（4.3）
├── 4. 应答模式决策表（4.4 —— 核心）
├── 5. 检索计划表（4.5）
├── 6. 内容来源标注规则（4.6）
├── 7. 抗幻觉规则（保留 v1，下沉为通用约束）
└── 8. 边界处理（保留 v1）

教学风格细则（类比、结构、深度自适应）下沉到 references/answer-styles.md，
仅在应答模式=教学引导时按需 Read。
```

---

## §5 核心交互场景示例

### 场景 1：A × concept（教学引导，保留 v1 体验）

**提问**："Pipeline 到底是干什么的？为什么不能像普通 C++ 那样顺序写？"

**路由**：角色=A、意图=concept、模式=教学引导、检索=`cannex_doc → 算子开发指南 → "Pipeline" 概述节点`

**回答骨架**：
```markdown
> [原文]
> Pipeline 是 Ascend C 提供的并行编排框架，用于重叠数据搬运与计算执行。
> [来源: CANN 9.0.0 算子开发指南 §2.3]

⚠️ 以下为辅助理解的类比与展开（综合理解，可能加工偏差）：

打个比方：内存搬运像快递员送货，Vector 计算像工人加工...

> [原文：Pipeline 三阶段示例代码]
> ```cpp
> Process() { CopyIn(); Compute(); CopyOut(); }
> ```
> [来源: CANN 9.0.0 算子开发指南 §2.3 代码 2-1]

[下一步]
想继续了解 TPipe 内存管理，还是先看 Tiling 设计？
```

### 场景 2：B × howto（直接答，v2 新增）

**提问**："我装完 CANN 之后想跑个推理 demo，怎么写最简单的代码？"

**路由**：角色=B、意图=howto、模式=直接答、检索=`cannex_doc → 应用开发指南 → 推理流程章节`

**回答骨架**：
```markdown
[直接给步骤]
推理 demo 最小三步：

> [原文：示例代码]
> 1. 初始化 ACL 环境：aclInit, aclrtSetDevice
> 2. 加载离线模型：aclmdlLoadFromFile
> 3. 准备输入输出，执行推理：aclmdlExecute
> [来源: CANN 9.0.0 应用开发指南 §4.2]

完整可运行的示例见 samples 仓的 inference/AclResnet50Sample。
[来源: samples.yaml#acl_resnet50]
```

**关键差异（vs v1）**：直接给代码、不问"你想从哪开始"、末尾不强加"下一步建议"。

### 场景 3：F × code-example（导航 + 推荐，杀手锏）

**提问**："我想看一下 CANN 先计算 vector 再计算 cube 的比较好的实现用例。"

**路由**：角色=F、意图=code-example、模式=导航+推荐、检索=`cannex_repo list_samples --pattern vector_to_cube`

**回答骨架**：
```markdown
[一句话推荐]
在官方 samples 仓里有 2 个 vector→cube 混合算子样例，按入门难度推荐 mix_vec_cube_basic 起步。

[推荐 1：入门级]
> [来源: samples.yaml#mix_vec_cube_basic]
> 样例：MixVecCubeSample
> 路径：samples/operator/MixVecCubeSample/
> 推荐理由：UB→L0 数据流编排清晰，是理解 vec→cube 衔接的最佳骨架。
> 教学要点：Vector 计算结果先入 UB；通过 TQue 衔接到 Cube 输入

> [原文：核心 Pipeline 部分代码骨架]
> ```cpp
> // 5-10 行关键代码片段（DataCopy + Add + Mmad）
> ```
> [来源: samples/operator/MixVecCubeSample/mix_vec_cube.cpp]

[推荐 2：进阶级]
> [来源: samples.yaml#mix_vec_cube_with_dbuf]
> 在 #1 基础上加入 Double Buffer，演示带宽掩盖。

[关联文档]
配合阅读：CANN 算子开发指南 §6.3 混合算子设计模式

[导航建议]
想深入 #1 的某个文件细节，告诉我文件名我用 CodeGraph 帮你定位调用关系。
```

### 5.5 设计验证小结

| 场景 | 验证 | 通过？ |
|---|---|---|
| 1. A × concept | v1 教学模式 + 来源标注 | ✅ |
| 2. B × howto | v2 直接答 + 不绕弯 | ✅ |
| 3. F × code-example | v2 杀手锏：业务语义标签精确检索 | ✅ |

发现的设计补丁（不改架构）：
- 场景 2 末尾"完整示例见 X 仓"——意味着即使 B 类问题，samples 仓也是潜在引用源（不只 F 用）
- 场景 3 的"导航建议"格式化——CodeGraph 应提供 `--calling-graph` 命令按需取调用关系，不默认全取

---

## §6 演进路径

### 6.1 阶段总览

```
v1（已完成）       v2-α（架构升级）    v2-β（知识扩库）    v2-γ（Web 化）
─────────────  →  ──────────────  →  ──────────────  →  ──────────────
单 Skill          重构 + 单仓 PoC      代码仓优先扩库       接入开源框架
2 份文档          + 来源标注           + 文档次之           跨形态复用
                  ↑ 当前应该做这步
```

注：本文档不再标注估时。开发由 Claude Code 协作完成，节奏按实际进度评估。

### 6.2 Phase 1a：v1 基线（已完成）

**状态**：✅
- v1 SKILL.md（239 行）
- 2 份 PDF 已建树
- PageIndex 5 处补丁已应用
- `~/.claude/skills/` 软链已建

**遗留**：未做端到端 Skill 教学效果验证。

### 6.3 Phase 1b：v2-α 架构升级（核心阶段，立刻开工）

**目标**：把 v1 升级为 v2 架构（角色路由 + 双知识源 + 来源标注），跑通 `samples` 仓的端到端 PoC。

**强制前置：CodeGraph spike**

第一步先跑 `codegraph init` 对 `samples` 仓做真实索引，验证：
- 节点数、解析覆盖率
- 跨文件调用解析对 C++ 的实际效果
- SQLite 索引大小、MCP query 速度

spike 结论决定 §3.4 `samples.yaml` 的 `entry_files` 字段是否需要补"CodeGraph 节点 ID"作为强连接（解析够准 → 直接文件名引用；不准 → 节点 ID 兜底）。

**交付物**

1. 重构 SKILL.md（v1 239 行 → v2 ~100 行）
2. 离线管道脚手架：`build/{repos.yaml, docs.yaml, sync_sources.py, build_docs.py, build_repos.py, monthly_update.sh}`
3. 查询工具升级：`tools/cannex_doc.py`（沿用 v1）+ `tools/cannex_repo.py`（新）
4. 单代码仓 PoC：`samples`（含 repo_card + samples.yaml 至少 5 条样例 + CodeGraph 索引）
5. references 资源：`answer-styles.md`（教学风格下沉）+ 保留 `learning-paths.md` / `teaching-personas.md`

**Done criteria**

- [ ] 3 个示例场景（§5）人工对话验证全通过
- [ ] 每个回答都带正确的来源标注（原文 vs LLM 加工）
- [ ] 用户原始问题（vector→cube 用例）能精确路由到 samples 仓的样例
- [ ] B 类问题（"装完 CANN 怎么写推理 demo"）能给出直接答案 + 引用 samples 仓
- [ ] 月度增量管线在 `samples` 仓上至少跑通一次（模拟 git pull 后增量重建）

**关键风险**

- CodeGraph 对 CANN C++ 仓的实际效果未验证 → spike 阶段决定是否需要 fallback
- bootstrap LLM 自动打标签的质量 → 准备"人工 review 模板"，LLM 不确定字段单独标出

### 6.4 Phase 1c：v2-β 知识扩库

#### v1c-1：代码仓扩库（优先）

代码仓优先扩展（与 v1 设想的"文档优先"相反——因业务语义沉淀成本高，趁有精力先做厚）：

```
P0 仓库扩库顺序：
1. cann-ops-adv (高级算子)   ← 服务 A 进阶，与 samples 互补
2. 用户指定（本地路径，待定）
3. 用户指定（本地路径，待定）
```

每加一个新仓走相同流水线，并新增 1-2 个针对该仓的端到端验证场景（避免扩库过程中应答质量回退）。

#### v1c-2：文档扩库（次之）

代码仓铺到 3-4 个之后回头补文档：

```
1. 应用开发指南
2. 性能调优指南 + 经验文档
3. 常见问题/错误码手册
```

理由：文档扩库的边际成本低（流水线已验证），代码仓的人工 review 成本高。

### 6.5 Phase 2：v2-γ Web 化（远期，按需启动）

**触发条件**（满足任一启动）：
- v2-β 在 Claude Code 形态下被昇腾内部 50+ 开发者稳定使用
- 收到清晰的"非 Claude Code 用户也想用"反馈

**关键工作**：
1. 选定开源 Web agent 框架（候选：Dify / LobeChat / AnythingLLM 等，选定后不换）
2. 迁移：SKILL.md 规则 → system prompt；CLI 工具注册；workspace 挂载
3. Web 形态增强：流式输出（SSE）、来源标注可点击展开原文、代码块高亮 + 一键复制

### 6.6 不在演进路径里的东西（避免漂移）

- ❌ 多用户 / 权限 / SSO（即使 Web 化也先单租户）
- ❌ 跨语言（仅中文，英文版未来由社区贡献）
- ❌ 性能调优工具集成（仍只覆盖文档）
- ❌ 代码生成器（即使有 samples 仓，依然不替写完整算子）
- ❌ 模型迁移类知识（已移除 C 角色）

---

## 附录 A：v1 → v2 关键差异速查

| 维度 | v1 | v2 |
|---|---|---|
| 目标用户 | A 算子开发者 | A + B + F |
| 知识源 | 文档（PDF） | 文档 + 代码仓 |
| 应答模式 | 仅"教学引导" | 教学引导 / 直接答 / 导航 / 对照 |
| 意图路由 | 仅"信息分类"（concept/howto/...） | 信息 × 角色 × 应答模式 三维 |
| 内容来源标注 | 仅末尾 [来源] 章节 | 段落级区分原文 vs LLM 加工 |
| Skill 结构 | 单一 SKILL.md（239 行） | SKILL.md 瘦身 ~100 行 + references 下沉 |
| 离线管道 | 单脚本 build_index.py | 配置驱动的多阶段管线 |
| Web 化预留 | 无 | 三层架构 + Markdown 规则可移植 |

## 附录 B：CLAUDE.md 需要更新的内容

CannEx 项目根 CLAUDE.md 需在 v2-α 完成后更新：
- "目录地图"补 `build/`、`raw/`、`workspace/repos/`
- "操作命令"补离线管道入口
- "当前进度" 改为 v2-α 进度跟踪
- "下一步候选" 改为 v2-β 扩库列表

# CannEx — 技术方案设计文档（SDD）

> 基于 CannEx-PRD 和开发者需求分析的技术实现方案
> 更新：2026-04-29

---

## 一、设计决策总览

| 决策项        | 结论                                                              | 理由            |
| ---------- | --------------------------------------------------------------- | ------------- |
| Skill 架构   | Skill 家族（入口 + 3 个子 skill）                                       | 模块独立、可单独迭代    |
| 知识层架构      | 自包含 mini wiki（借鉴 vault wiki 范式）                                 | 可独立分发，不依赖外部系统 |
| 知识组织方式     | 类型化（entities/concepts/examples/repos/pitfalls）+ [[wikilink]] 互联 | 知识是图谱不是文件夹    |
| 数据来源管理     | CANN 文档按版本归档 + 代码仓全量覆盖（知识蒸馏）                                    | 全量索引但轻量存储     |
| 抗幻觉策略      | 事实素材库 + Prompt 约束 + 运行时降级                                       | 可信度优先于流畅度     |
| 层级策略       | 内隐自适应，不做显式诊断                                                    | 降低用户使用门槛      |
| Phase 1 交付 | CLI Skill Pack                                                  | 即时可用          |
| Phase 2 演进 | + RAG 向量库 + Web 服务                                              | 覆盖组合查询、扩大用户面  |

---

## 二、目录结构

```
CannEx/
│
├── skills/                              ← Layer 1: Skill Pack（教学逻辑）
│   ├── ascend-c.md                      ←   入口：意图识别 + 分发
│   ├── learn.md                         ←   概念教学 + 方法论
│   ├── examples.md                      ←   代码样例检索
│   ├── pitfalls.md                      ←   故障诊断 + 踩坑预警
│   └── shared/                          ←   子 skill 共享资源
│       ├── persona.md                   ←     人格设定 + 桥接策略
│       ├── question-bank.yaml           ←     教学问题集
│       └── learning-paths.yaml          ←     学习路径定义
│
├── knowledge/                           ← Layer 2: 领域知识图谱
│   ├── entities/                        ←   实体页
│   │   ├── ascend-c.md                  ←     Ascend C 语言
│   │   ├── cann.md                      ←     CANN 框架
│   │   ├── ai-core.md                   ←     AI Core 硬件架构
│   │   ├── tpipe.md                     ←     TPipe 框架
│   │   └── atlas-platforms.md           ←     各硬件平台差异
│   │
│   ├── concepts/                        ←   概念页
│   │   ├── operator-taxonomy.md         ←     算子四分类全景
│   │   ├── dev-workflow.md              ←     算子开发完整工作流
│   │   ├── pipeline.md                  ←     Pipeline 编程范式
│   │   ├── memory-hierarchy.md          ←     内存层级
│   │   ├── tiling-design.md             ←     Tiling 设计方法论
│   │   ├── double-buffer.md             ←     Double Buffer 机制
│   │   ├── simd.md                      ←     SIMD 编程模型
│   │   ├── simt.md                      ←     SIMT 编程模型
│   │   ├── precision-alignment.md       ←     精度对齐方法论
│   │   ├── perf-optimization.md         ←     性能优化决策树
│   │   └── profiling-tools.md           ←     Profiling 工具使用
│   │
│   ├── examples/                        ←   代码样例（原文保留，不加教学注释）
│   │   ├── vector-add.md                ←     纯 Vector：Add
│   │   ├── vector-relu.md               ←     纯 Vector：ReLU
│   │   ├── vector-fusion-layernorm.md   ←     Vector 融合：LayerNorm
│   │   ├── vector-fusion-gelu.md        ←     Vector 融合：GELU
│   │   ├── cube-matmul.md               ←     纯 Cube：MatMul
│   │   └── cube-vector-matmul-relu.md   ←     Cube+Vector 融合
│   │
│   ├── comparisons/                     ←   对比页
│   │   ├── ascend-c-vs-cuda.md
│   │   └── simd-vs-simt.md
│   │
│   ├── summaries/                       ←   原始文档摘要
│   │   ├── summary-ascend-c-dev-guide.md
│   │   ├── summary-ascend-c-api-ref.md
│   │   └── ...
│   │
│   ├── pitfalls/                        ←   踩坑/故障条目
│   │   ├── datacopy-alignment.md
│   │   ├── ub-size-cross-platform.md
│   │   ├── dtype-unsupported.md
│   │   └── ...
│   │
│   ├── repos/                           ←   算子仓知识层
│   │   ├── index.md                     ←     全览目录（按类型分类）
│   │   ├── samples.md                   ←     每个仓一个知识页
│   │   ├── cann-ops-adv.md
│   │   ├── cann-benchmark.md
│   │   └── ...（全量覆盖 CANN 组织下所有算子仓）
│   │
│   ├── index.md                         ←   知识层全局索引
│   └── SCHEMA.md                        ←   知识层组织规则
│
├── raw/                                 ← Layer 3: 原始权威数据源
│   ├── docs/                            ←   CANN 技术文档（按版本归档）
│   │   ├── current/                     ←     符号链接 → 最新版本
│   │   ├── v9.0.0-beta2/
│   │   │   ├── _meta.yaml              ←     同步元信息
│   │   │   ├── operator-dev-guide/
│   │   │   ├── api-reference/
│   │   │   └── ...
│   │   ├── v8.0.0/
│   │   │   └── ...
│   │   └── sync_log.yaml               ←     同步记录
│   ├── repos/                           ←   代码仓数据
│   │   ├── registry.yaml                ←     仓库注册表
│   │   ├── profiles/                    ←     结构画像（自动生成）
│   │   │   ├── samples.yaml
│   │   │   ├── cann-ops-adv.yaml
│   │   │   └── ...
│   │   └── extract_rules/               ←     提取规则（人工编写）
│   │       ├── samples.yaml
│   │       ├── cann-ops-adv.yaml
│   │       └── ...
│   └── sync/                            ←   同步脚本
│       ├── doc_syncer.py
│       ├── repo_syncer.py
│       ├── change_detector.py
│       └── sync_scheduler.sh
│
└── docs/                                ← 项目文档
    ├── CannEx-PRD.md
    ├── CannEx-SDD.md                    ←   本文档
    └── developer-needs.md               ←   开发者需求分析
```

---

## 三、Layer 1 — Skill Pack 设计

### 3.1 入口 Skill（ascend-c.md）

**职责**：意图识别 + 分发，不承载教学内容。

```yaml
---
name: ascend-c
description: |
  CannEx — CANN 开发者学习导师 Agent。
  面向 Ascend C 算子开发者提供概念教学、代码样例检索和故障诊断。
  触发词：ascend-c、CannEx、"学习算子开发"、"Ascend C"
type: skill
allowed-tools:
  - Read
  - Glob
  - Grep
  - Agent
  - WebFetch
---
```

**分发规则**：

```
用户输入                                 → 分发目标
──────────────────────────────────────────────────────
ascend-c（无参数）                        → 欢迎引导
ascend-c:learn pipeline                  → learn.md
ascend-c:examples add                    → examples.md
ascend-c:pitfalls datacopy               → pitfalls.md

语义匹配（自然语言输入）：
"Pipeline 是什么"                         → learn.md
"有没有 MatMul 的代码"                    → examples.md
"DataCopy 报错了" / "结果和 PyTorch 对不上" → pitfalls.md
```

**首次交互文案**：

```
我是 CannEx，你的 Ascend C 学习导师。

我可以帮你：
- 学习概念 — 硬件架构、Pipeline、Tiling、精度对齐、性能优化...
- 代码样例 — 按算子类型检索完整可运行代码
- 故障诊断 — 报错排查、精度排障、常见踩坑预警

直接告诉我你想了解什么，或者说出你遇到的问题。
```

### 3.2 概念教学（learn.md）

**职责**：覆盖六大教学能力，根据问题内容自适应深度。

```yaml
---
name: ascend-c:learn
description: |
  Ascend C 概念教学与方法论引导。
  覆盖：硬件架构、算子开发范式、精度对齐、性能优化、前置知识桥接。
type: skill
allowed-tools:
  - Read
  - Glob
  - Grep
---
```

**Prompt 核心指令**：

```markdown
# 角色
你是 CannEx 的概念教学模块。你的目标是把 Ascend C 的核心知识
从 700 页官方文档中提炼出来，用开发者能理解的方式讲清楚。

# 知识来源与抗幻觉
- 优先从 knowledge/ 目录检索结构化知识页面
- 知识页不足时，从 raw/ 目录读取官方 PDF 原文
- 回答时标注知识来源：[知识页: concepts/pipeline.md] 或 [原文: §3.2]
- 知识页存储的是事实素材（官方原文摘录），不是预写好的答案
- 基于事实素材组织回答，超出素材的推理/解读标注为"辅助理解"
- 知识库完全未覆盖时，坦诚告知并指路官方文档

# 自适应深度规则
- 根据用户问题本身判断认知水平，不做显式分级
- "算子是什么" → 从全景图讲起，不跳步骤
- "Double Buffer 没提速" → 直接讲流水瓶颈分析
- "L0A Bank 冲突" → 给微架构级回答

# 术语处理规则
- 首次出现的专业术语必须内联解释
- 格式：**术语**（解释）
- 示例："数据通过 **TPipe**（Ascend C 的流水线管理框架，
  负责协调数据在不同内存间的搬运和计算的执行顺序）进行编排"

# 前置知识桥接
- 根据用户的提问语境推断其背景（PyTorch 用户 / C++ 开发者 / CUDA 开发者）
- 用对应领域的类比解释新概念
- PyTorch 用户："torch.add() 背后就是一个算子"
- CUDA 开发者："TPosition 相当于 CUDA 的 shared memory 但更抽象"
- C++ 开发者："类似多线程中的生产者-消费者模式"

# 版本/硬件标注
- 涉及具体 API 或硬件特性时，标注适用范围
- 格式：[适用: Atlas A2 / CANN 9.0+]
- 如果不同硬件行为不同，必须明确说明差异

# 学习路径引导
- 回答完当前问题后，推荐自然的下一步
- "理解了 Pipeline 后，建议接下来了解 Tiling 设计"
- 推荐基于 learning-paths.yaml 中定义的概念依赖关系

# 回答结构
1. 先给结论（一句话回答核心问题）
2. 展开解释（原理 + 类比）
3. 关联知识（[[wikilink]] 指向相关页面）
4. 下一步建议（学习路径或动手实践）
```

**六大教学能力的路由**：

| 能力 | 典型触发问题 | 知识来源 |
|------|------------|---------|
| 硬件架构认知 | "AI Core 结构"、"数据怎么流动" | knowledge/entities/ai-core.md |
| 算子开发范式 | "怎么开发一个算子"、"完整流程" | knowledge/concepts/dev-workflow.md |
| 精度对齐方法论 | "精度对不上"、"误差多大算正常" | knowledge/concepts/precision-alignment.md |
| 性能优化方法论 | "算子太慢"、"怎么优化" | knowledge/concepts/perf-optimization.md |
| 前置知识桥接 | "算子是什么"、"为什么不用 PyTorch" | knowledge/concepts/operator-taxonomy.md |
| 版本/硬件适配 | "Atlas A2 和 300 区别" | knowledge/entities/atlas-platforms.md |

### 3.3 代码样例检索（examples.md）

**职责**：根据开发者需求，检索匹配的完整代码样例。

```yaml
---
name: ascend-c:examples
description: |
  Ascend C 代码样例检索。按算子类型、计算单元、难度匹配完整可运行代码。
  触发词："有没有 XX 的代码"、"XX 算子怎么写"、"给我一个例子"
type: skill
allowed-tools:
  - Read
  - Glob
  - Grep
---
```

**Prompt 核心指令**：

```markdown
# 角色
你是 CannEx 的代码样例检索模块。你的目标是帮开发者找到最匹配的
完整代码样例，并用教学方式讲解关键代码段。

# 检索逻辑
1. 解析用户需求：算子类型、计算单元（Vector/Cube/融合）、难度
2. 在 knowledge/examples/ 目录检索匹配的样例页
3. 如果精确匹配不到，推荐最相近的样例并说明差异

# 回答结构
1. 定位："这属于 [算子类型]，对应 [计算单元]"
2. 完整代码（从样例页原样读取，禁止修改）
3. 文字说明代码关键逻辑（用文字解释，不改代码）
4. 数据流说明："数据从 GM → UB → 计算 → UB → GM"
5. 适用范围：[适用: 硬件型号 / CANN 版本]
6. 进阶建议："在此基础上可以尝试 XX 变体"

# 样例质量要求
- 必须是完整可运行的代码，不是片段
- 代码保持原文，不添加教学注释、不做任何修改
- 用独立的文字段落解释代码逻辑，与代码分离
- 标注前置依赖（需要先理解哪些概念）
- 标注代码来源（仓库路径 + commit hash）
```

### 3.4 故障诊断 + 踩坑预警（pitfalls.md）

**职责**：双模式——事后排障 + 前置预警。

```yaml
---
name: ascend-c:pitfalls
description: |
  Ascend C 故障诊断与踩坑预警。
  诊断模式：报错码解读、精度排查、运行时错误分析。
  预警模式：常见约束提醒、平台差异警告、API 隐式限制。
  触发词："报错"、"结果不对"、"XX 要注意什么"
type: skill
allowed-tools:
  - Read
  - Glob
  - Grep
---
```

**Prompt 核心指令**：

```markdown
# 角色
你是 CannEx 的故障诊断模块。你帮开发者快速定位问题、解决报错、
避免已知陷阱。

# 双模式识别
- 诊断模式信号："报错"、"失败"、"结果不对"、"跑不通"、错误码
- 预警模式信号："要注意什么"、"有什么坑"、"第一次用 XX"

# 诊断模式回答结构
1. 问题识别（确认错误现象）
2. 可能原因（按可能性排序，最常见的在前）
3. 排查步骤（给具体命令或检查方法）
4. 解决方案
5. 来源标注

# 预警模式回答结构
1. 核心约束（最重要的注意事项）
2. 常见陷阱列表
3. 每条附来源标注

# 来源标注规范（必须遵守）
- 官方文档记载    → [来源: 官方开发指南 §章节号]
- 社区 Issues     → [来源: gitee.com/ascend/xxx/issues/编号]
- 内部实测        → [来源: 内部实测 日期]
- 文档推断        → [推断: 基于 XX 推导]

# 精度排障专项流程
当用户说"结果不对"或"精度对不上"时：
1. 确认对比基准（PyTorch CPU? GPU? 哪个版本？）
2. 确认数据类型（fp16/fp32/bf16）
3. 引导用户检查：输入数据是否一致 → 中间结果 dump → 逐层对比
4. 常见精度原因：fp16 累加溢出、cast 顺序、reduce 算法差异
5. 推荐工具：精度比对工具使用方法

# 版本/硬件关联
- 回答时标注该问题在哪些硬件/版本上出现
- 如果是特定版本的已知 bug，标注修复版本
```

### 3.5 共享资源（shared/）

#### persona.md — 人格设定

```markdown
# CannEx 人格设定

## 身份
你是 CannEx，面向 Ascend C 算子开发者的学习导师。

## 沟通风格
- 专业但不冰冷：用准确的技术语言，但配合类比和示例
- 鼓励但不敷衍：遇到基础问题不居高临下，遇到高级问题不回避复杂性
- 结论先行：先给答案，再给解释（Bottom-line up front）
- 中文回复，术语保留英文（如 Pipeline、Tiling、Double Buffer）

## 前置知识桥接策略
根据用户提问语境推断其技术背景，选择对应的类比体系：

| 背景信号 | 桥接策略 |
|---------|---------|
| 提到 PyTorch/TensorFlow | 用框架算子做类比 |
| 提到 CUDA/GPU 编程 | 用 CUDA 概念做对比映射 |
| 提到 C++/多线程 | 用生产者-消费者等模式做类比 |
| 没有技术背景信号 | 用生活化比喻（厨房搬运、流水线工厂） |

## 抗幻觉规则（所有 Skill 必须遵守）

1. **只说知识库里有的**
   - 回答必须基于 knowledge/ 中的具体页面内容
   - 无法在知识库中找到依据时，明确告知：
     "这个问题超出了我当前知识库的覆盖范围，建议查阅官方文档：[具体文档名 + 章节]"
   - 禁止用模型自身训练知识补充 CANN 技术细节

2. **代码零修改原则**
   - 展示代码样例时，必须原样引用 knowledge/ 中的代码
   - 不得对原始代码做任何修改、补全、或"优化"
   - 如需解释代码，用文字说明，不改代码本身

3. **溯源标注**
   - 每个技术断言必须标注来源：
     "根据《算子开发指南》3.2 节，..."
     "参见 samples 仓 operator/AddCustom/..."
   - 无法标注来源的断言不说

4. **版本锁定**
   - 回答前先确认开发者使用的 CANN 版本
   - 引用知识页时检查 applies_to 字段是否匹配
   - 版本不匹配时明确提醒，不强行回答

5. **不确定性表达**
   - 允许说"我不确定"、"知识库中没有覆盖这个场景"
   - 禁止模棱两可地猜测技术细节

## 其他禁止行为
- 不跳过前置概念直接讲高级话题（除非用户问题本身表明已掌握前置知识）
```

#### learning-paths.yaml — 学习路径定义

```yaml
# 概念依赖图：A depends_on B 表示学 A 之前建议先理解 B
dependencies:
  operator-taxonomy: []                    # 算子分类 — 无前置依赖，起点
  ai-core: []                             # AI Core 架构 — 无前置依赖，起点
  pipeline: [operator-taxonomy, ai-core]   # Pipeline 依赖算子分类 + 硬件认知
  memory-hierarchy: [ai-core]             # 内存层级依赖硬件认知
  tiling-design: [memory-hierarchy]       # Tiling 依赖内存层级
  double-buffer: [pipeline, tiling-design] # Double Buffer 依赖 Pipeline + Tiling
  simd: [pipeline]                        # SIMD 依赖 Pipeline
  simt: [pipeline]                        # SIMT 依赖 Pipeline
  dev-workflow: [pipeline, tiling-design]  # 开发工作流依赖 Pipeline + Tiling
  precision-alignment: [dev-workflow]      # 精度对齐依赖开发工作流
  perf-optimization: [double-buffer, tiling-design] # 性能优化依赖 DB + Tiling

# 推荐学习路径（按典型场景）
paths:
  first-operator:
    name: "第一个算子"
    sequence: [operator-taxonomy, ai-core, pipeline, memory-hierarchy, tiling-design, dev-workflow]
    description: "从零到跑通一个 Vector Add 算子"

  optimization:
    name: "性能优化"
    sequence: [memory-hierarchy, tiling-design, double-buffer, perf-optimization]
    description: "算子能跑但太慢，系统学习优化方法"
    prerequisite: "已完成 first-operator 路径或等效知识"

  precision:
    name: "精度对齐"
    sequence: [dev-workflow, precision-alignment]
    description: "结果不对时的系统排查方法"
    prerequisite: "已能独立编写算子"
```

#### question-bank.yaml — 教学问题集

```yaml
# 高频问题 → 知识页映射（用于 :learn 的知识检索优化）
questions:
  # 前置知识类
  - pattern: ["算子是什么", "为什么要写算子", "PyTorch 不够吗"]
    knowledge: [concepts/operator-taxonomy.md]
    bridge: pytorch

  - pattern: ["Ascend C 和 CUDA 什么关系", "要先学 CUDA 吗"]
    knowledge: [comparisons/ascend-c-vs-cuda.md]
    bridge: cuda

  # 硬件架构类
  - pattern: ["AI Core", "硬件架构", "计算单元"]
    knowledge: [entities/ai-core.md]

  - pattern: ["内存层级", "UB", "GM", "数据搬运"]
    knowledge: [concepts/memory-hierarchy.md]

  # 开发范式类
  - pattern: ["Pipeline", "TPipe", "TQue", "三阶段"]
    knowledge: [concepts/pipeline.md]

  - pattern: ["Tiling", "切块", "tile 大小"]
    knowledge: [concepts/tiling-design.md]

  - pattern: ["怎么开发算子", "完整流程", "从零开始"]
    knowledge: [concepts/dev-workflow.md]

  # 精度类
  - pattern: ["精度", "结果不对", "和 PyTorch 对不上", "误差"]
    knowledge: [concepts/precision-alignment.md]

  # 性能类
  - pattern: ["性能", "太慢", "优化", "Double Buffer"]
    knowledge: [concepts/perf-optimization.md, concepts/double-buffer.md]

  # 版本/硬件类
  - pattern: ["910A", "910B", "Atlas A2", "Atlas 300", "平台差异"]
    knowledge: [entities/atlas-platforms.md]
```

---

## 四、Layer 2 — 知识图谱设计

### 4.1 组织规范（SCHEMA.md）

知识图谱借鉴 vault wiki 架构，遵循以下规范：

**页面类型与模板**：

| 类型 | 目录 | 用途 | 必填字段 |
|------|------|------|---------|
| Entity | entities/ | 工具、硬件、框架 | title, tags, sources, created, updated |
| Concept | concepts/ | 方法论、模式、原理 | title, tags, sources, created, updated |
| Example | examples/ | 完整代码样例 | title, tags, operator_type, compute_unit, difficulty, applies_to, sources |
| Comparison | comparisons/ | A vs B 对比 | title, tags, sources |
| Summary | summaries/ | 原始文档摘要 | title, tags, sources |
| Repo | repos/ | 算子仓知识页 | title, tags, repo_url, category, applies_to, sources |
| Pitfall | pitfalls/ | 踩坑/故障条目 | title, tags, severity, affects, source_type, applies_to, sources |

**Entity 页模板**：

```yaml
---
title: AI Core 硬件架构
tags: [hardware, ai-core, architecture]
sources: [raw/ascend-c-dev-guide.pdf§2.1]
created: 2026-04-29
updated: 2026-04-29
---

## 概述
[一段话定义]

## 核心特性
[详细内容]

## 关联
- [[ascend-c]] — Ascend C 运行在 AI Core 上
- [[memory-hierarchy]] — AI Core 的内存层级

## 变更记录
- 2026-04-29: 初始创建
```

**Concept 页模板**：

```yaml
---
title: Pipeline 编程范式
tags: [programming-model, pipeline, tpipe]
sources: [raw/ascend-c-dev-guide.pdf§3.1]
created: 2026-04-29
updated: 2026-04-29
---

## 定义
[精确定义]

## 核心要点
[要点列表]

## 应用场景
[适用上下文]

## 关联
- 依赖 [[ai-core]] 硬件理解
- 前置于 [[tiling-design]]
- 与 [[double-buffer]] 配合使用

## 变更记录
- 2026-04-29: 初始创建
```

**Example 页模板**：

```yaml
---
title: Vector Add 算子
tags: [vector, add, beginner]
operator_type: element-wise
compute_unit: vector
difficulty: beginner
applies_to:
  hardware: [Atlas A2, Atlas 300I Pro]
  cann_version: ">=8.0"
sources: [raw/ascend-c-dev-guide.pdf§5.2]
created: 2026-04-29
updated: 2026-04-29
---

## 算子说明
[一句话：做什么、输入输出是什么]

## 前置知识
- [[pipeline]] — 理解三阶段流水
- [[memory-hierarchy]] — 理解 GM 和 UB 的关系

## 完整代码

### Host 端（Tiling）
[原始代码，保持原文不做任何修改]

### Device 端（Kernel）
[原始代码，保持原文不做任何修改]

## 数据流图
[文字描述或 ASCII 图：数据从哪到哪]

## 官方文档说明
[摘录官方文档中对该样例的说明，标注来源章节]

## 变体建议
- "在此基础上试试 Sub 算子（只改一行计算指令）"
- "进阶版本：加上 Double Buffer → [[vector-relu]]"

## 关联
- [[operator-taxonomy]] — 属于纯 Vector 算子
- [[dev-workflow]] — 按此工作流完成
```

**Pitfall 页模板**：

```yaml
---
title: DataCopy 32 字节对齐
tags: [datacopy, alignment, vector, cube]
severity: high
affects: [vector, cube]
source_type: official
applies_to:
  hardware: [all]
  cann_version: ">=8.0"
sources: [raw/ascend-c-dev-guide.pdf§4.3.2]
created: 2026-04-29
updated: 2026-04-29
---

## 现象
[开发者会看到什么错误/异常]

## 原因
[为什么会出现这个问题]

## 解决方案
[具体怎么修]

## 排查步骤
[如果遇到了，按什么步骤排查]

## 关联
- [[memory-hierarchy]] — 理解对齐要求的硬件背景
- [[datacopy-burst]] — 相关的 burst 长度限制
```

**Repo 页模板**：

```yaml
---
title: cann-ops-adv
tags: [repo, fusion-ops, high-performance]
repo_url: https://gitee.com/ascend/cann-ops-adv
category: 高性能融合算子
applies_to:
  hardware: [Ascend 910B, Ascend 310P]
  cann_version: ">=8.0"
sources: [raw/repos/registry.yaml]
created: 2026-04-29
updated: 2026-04-29
---

## 一句话定位
[这个仓是什么、解决什么问题]

## 解决什么问题
[开发者在什么场景下会用到这个仓]

## 核心能力
[仓内包含的主要算子/工具列表及简要说明]

## 代码结构导读
[目录结构 + 关键目录的用途说明]

## 与其他仓的关系
- [[samples]] — 基础版本对比
- [[cann-benchmark]] — 性能基准
- 基础概念见 [[concept-cube-vector-fusion]]

## 常见问题
[开发者对该仓最常见的疑问，摘自 Issue 或社区反馈]

## 变更记录
- 2026-04-29: 初始创建
```

**Repo 全览目录（repos/index.md）**：

```markdown
# CANN 算子仓全览

## 按类型分类

### 基础教学类
| 仓名 | 定位 | 算子数 | 难度 |
|---|---|---|---|
| [[samples]] | 官方入门样例集 | 30+ | ⭐ |

### 高性能实现类
| 仓名 | 定位 | 算子数 | 难度 |
|---|---|---|---|
| [[cann-ops-adv]] | 融合算子优化实现 | 15+ | ⭐⭐⭐ |

### 工具链类
| 仓名 | 定位 | 说明 |
|---|---|---|
| [[cann-benchmark]] | 性能基准测试 | ... |
| [[att]] | 精度比对工具 | ... |

### 框架适配类
| 仓名 | 定位 | 说明 |
|---|---|---|
| [[pytorch-adapter]] | PyTorch 适配层 | ... |
```

### 4.2 交叉引用网络

每个知识页至少链接 2 个其他页面，形成知识图谱：

```
                    [[operator-taxonomy]]
                     ↙        ↓        ↘
          [[ai-core]]    [[pipeline]]    [[ascend-c-vs-cuda]]
              ↓          ↙       ↘
    [[memory-hierarchy]]    [[tiling-design]]
         ↓        ↘              ↓
  [[double-buffer]]  [[precision-alignment]]
                          ↓
                  [[perf-optimization]]

  examples/ 链回对应的 concept：
  [[vector-add]] → [[pipeline]], [[memory-hierarchy]]
  [[cube-matmul]] → [[tiling-design]], [[memory-hierarchy]]

  pitfalls/ 链回对应的 concept + example：
  [[datacopy-alignment]] → [[memory-hierarchy]], [[vector-add]]
```

### 4.3 知识页数量规划（Phase 1）

| 类型 | 数量 | 说明 |
|------|------|------|
| entities/ | 5 | ascend-c, cann, ai-core, tpipe, atlas-platforms |
| concepts/ | 11 | 含精度对齐、性能优化、开发工作流等方法论 |
| examples/ | 6 | 覆盖四类算子（Vector×2, 融合×2, Cube×1, 混合×1） |
| repos/ | 50+ | 全量覆盖 CANN 组织下所有算子仓 |
| comparisons/ | 2 | ascend-c-vs-cuda, simd-vs-simt |
| summaries/ | 3+ | 每个 raw PDF 对应一个 |
| pitfalls/ | 20+ | 初始种子库，持续积累 |
| **合计** | **97+** | |

---

## 五、Layer 3 — 原始数据源管理

### 5.1 两类数据源

| 数据源 | 特点 | 管理方式 |
|--------|------|---------|
| CANN 技术文档 | 按版本发布，每版数百页 PDF，权威但晦涩 | 全量归档，按版本目录隔离 |
| 开源代码仓（50+） | 持续变化，代码+Issue+README，价值密度不均 | 全量覆盖，知识蒸馏提取 |

### 5.2 CANN 技术文档管理

#### 数据获取方式

**对接昇腾社区发布仓接口**（复用"昇腾社区搜索项目"在黄区的发布仓接口通路）：
- 该通路已被内部"CANN API 助手"项目验证可行
- 优势：URL 与官网 hiascend.com 路径完全一致，解决 URL 映射问题
- CannEx 复用同一套接口适配层（鉴权、调取逻辑），上层定义自己的取数范围

**取数规则**（CannEx 比 CANN API 助手范围更广）：

```yaml
filter_rules:
  # CANN API 助手只取 API 文档，CannEx 取教学相关全集
  include:
    - "CANN/算子开发/**"            # 算子开发指南、接口参考
    - "CANN/工具使用/**"            # 性能调优、精度调试工具
    - "CANN/故障处理/**"            # 故障排查文档
    - "CANN/环境部署/**"            # 安装、环境变量
    - "CANN/Release Notes/**"      # 版本变更说明
  exclude:
    - "CANN/推理应用/**"            # 不属于算子开发范畴
    - "CANN/模型训练/**"            # 不属于算子开发范畴
```

#### 按版本归档

```
raw/docs/
├── current/                          ← 符号链接，指向最新版本
├── v9.0.0-beta2/
│   ├── _meta.yaml                    ←   同步元信息
│   ├── operator-dev-guide/
│   │   ├── chapter-01.md
│   │   └── ...
│   └── api-reference/
│       └── ...
├── v8.0.0/
│   └── ...
└── sync_log.yaml                     ← 同步记录
```

```yaml
# raw/docs/v9.0.0-beta2/_meta.yaml
version: "9.0.0-beta2"
type: commercial                       # commercial | community
synced_at: 2026-04-29T10:00:00+08:00
source_url: https://hiascend.com/doc/...
changes_since_last:
  added: [perf-tuning/new-chapter.md]
  modified: [operator-dev-guide/chapter-03.md]
  deleted: []
```

#### 版本管理策略

**采用"标注制"而非"副本制"**：
- raw/ 按版本存全量文档
- knowledge/ 只存一份知识页，用 `applies_to` 标注适用版本范围
- 版本间差异用 `> [!warning] v9.0 变更` callout 标注
- 不为每个 CANN 版本维护一套 knowledge 副本

**版本保留策略**（CANN 每年约 4 个商发版本 + 12 个社区版本）：

```yaml
version_policy:
  display_default: latest              # 默认展示最新版
  user_switch: true                    # 用户可手动切版本
  retain:
    commercial: 2                      # 保留最近 2 个商发版本
    community: 1                       # 保留最近 1 个社区版本（仅最新）
    total_max: 3                       # 最多同时存在 3 个版本
  eviction:
    trigger: new_version_released
    action:
      - archive_oldest                 # 归档最旧版本
      - remove_from_vector_db          # 从向量库删除（Phase 2）
      - keep_knowledge_pages           # 知识页保留但标注 deprecated
```

保留 3 个版本的理由：商发版本更新周期约 3 个月，保留 2 个覆盖最近半年；社区版本更新频繁，只保留最新 1 个避免检索噪音；向量库不会线性膨胀。

**Phase 1 优先 Ingest 的文档**：

| 优先级 | 文档 | 用途 |
|--------|------|------|
| P0 | Ascend C 算子开发指南 | 核心教学知识来源 |
| P0 | Ascend C 算子开发接口参考 | :examples 代码 + :pitfalls API 约束 |
| P1 | 性能调优工具用户指南 | 性能优化方法论 |
| P1 | 精度调试工具用户指南 | 精度对齐方法论 |
| P1 | 算子开发工具用户指南 | 开发工作流 |
| P2 | 故障处理 | :pitfalls 故障案例 |
| P2 | 环境变量参考 | 配置类踩坑 |
| P2 | 软件安装指南 | 环境搭建参考 |

### 5.3 开源代码仓管理

#### 核心思路：全量覆盖，轻量拉取，知识蒸馏

不拉取全量源码，通过 GitCode API 按需获取目标信息，把每个仓"翻译"成开发者能直观理解的知识页。原始代码通过 `repo_url` + 路径引用回去。

**为什么用 GitCode API 而非 Git Submodule**：

| 维度 | GitCode API | Git Submodule |
|---|---|---|
| 拉取内容 | 按需取单个文件/目录树 | 拉取整个仓库全量代码 |
| 50 个仓数据量 | ~2MB | 可能 10-50GB |
| Issue/Star/元信息 | API 直接返回 | 拿不到 |
| URL 映射问题 | 不存在（GitCode URL 即规范 URL） | 不存在 |

**为什么代码仓不存在 URL 映射问题**：官方文档发布在 hiascend.com，从 GitCode 取数据会导致 URL 不一致，所以改用发布仓接口。代码仓的规范 URL 就是 GitCode 本身，API 返回的链接即用户可直接访问的地址。

#### 轻量化拉取策略

每个仓只通过 API 获取以下信息：

```
信息需求              获取方式                        数据量
─────────           ─────────                     ────────
仓描述/Star/语言      API: GET /repos/{repo}          ~1KB
目录结构              API: GET /repos/{repo}/          ~5KB
                         git/trees/main
README 内容          API: GET /repos/{repo}/          ~10KB
                         raw/README.md
算子列表             从目录树中解析，不需额外请求         0
Issue Top20          API: GET /repos/{repo}/          ~20KB
                         issues?sort=reactions
Release 信息         API: GET /repos/{repo}/releases   ~5KB

每个仓合计：~40KB，50 个仓 ≈ 2MB
```

**不拉取的**：全量源代码、测试文件、CI 配置、构建产物、git 历史。

#### 两阶段提取方案

50+ 个仓目录结构各不相同，无法用一套通用规则自动提取所有信息。采用"先探测结构，再配置化提取"的方案。

**阶段一：结构探测（全自动）**

对每个仓，通过 API 拉取目录树，用规则生成结构画像：

```yaml
# 自动生成：raw/repos/profiles/cann-ops-adv.yaml
repo: cann-ops-adv
tree_scanned_at: 2026-04-29

detected_layout:
  readme: README.md
  doc_dir: doc/                        # 探测到的实际路径
  example_dir: doc/samples/            # 样例目录（可能在 doc/ 下）
  operator_dir: src/                   # 算子代码目录
  has_changelog: false
  has_issues: true

files_of_interest:
  docs:
    - doc/API说明.md
    - doc/开发指南.md
  examples:
    - doc/samples/add_demo.py
    - doc/samples/matmul_demo.py
  operators:
    - src/flash_attention/
    - src/fused_layernorm/

status: pending_human_review
```

探测规则（覆盖常见目录名变体）：

```python
DOC_PATTERNS     = ["docs/", "doc/", "document/", "documentation/"]
EXAMPLE_PATTERNS = ["examples/", "samples/", "demo/",
                     "docs/samples/", "docs/examples/", "doc/samples/"]
OPERATOR_PATTERNS = ["ops/", "src/", "operator/", "kernels/",
                      "ascendc/", "op_host/", "op_kernel/"]
```

匹配不上的标记 `layout: unknown`，交给人工处理。

**阶段二：人工确认 + 配置化提取**

人工审阅结构画像后，为每个仓编写提取配置：

```yaml
# raw/repos/extract_rules/cann-ops-adv.yaml
# 人工编写，每个仓一份（一次性工作）

repo: cann-ops-adv

positioning:
  source: README.md
  method: first_paragraph              # 取 README 第一段原文

examples:
  - path: doc/samples/add_demo.py
    label: "Add 算子使用样例"
  - path: doc/samples/matmul_demo.py
    label: "MatMul 算子使用样例"

operators:
  scan_dir: src/
  depth: 1                             # 第一层子目录 = 算子名

docs:
  - path: doc/开发指南.md
    label: "开发指南"
  - path: doc/API说明.md
    label: "API 参考"

applies_to:
  source: README.md
  fallback: doc/开发指南.md
```

自动化脚本按此配置用 API 拉取指定文件，原样写入知识页。

**工作量评估**：

```
全自动部分（一次性开发）：
  - 结构探测脚本 + 规则化提取脚本：~12 小时

人工部分（每个仓）：
  - 审核结构画像：~5 分钟
  - 编写 extract_rules.yaml：~15 分钟
  - 确认知识页内容：~10 分钟
  合计：~30 分钟/仓 × 50 = ~25 小时 ≈ 1 人周

增量更新（每两周）：
  - 自动检测变更：零成本
  - 人工处理变更（通常 2-5 个仓有变化）：~2-4 小时
```

#### 仓库注册表

```yaml
# raw/repos/registry.yaml
repos:
  - name: samples
    url: https://gitee.com/ascend/samples
    canonical_url: https://gitcode.com/ascend/samples  # URL 稳定性校验用
    purpose: 官方算子开发样例集
    category: 基础教学
    extract_rules: raw/repos/extract_rules/samples.yaml
    knowledge_page: knowledge/repos/samples.md
    last_synced: 2026-04-29
    last_commit: abc1234

  - name: cann-ops-adv
    url: https://gitee.com/ascend/cann-ops-adv
    purpose: 高性能融合算子实现
    category: 高性能实现
    extract_rules: raw/repos/extract_rules/cann-ops-adv.yaml
    knowledge_page: knowledge/repos/cann-ops-adv.md
    last_synced: 2026-04-29
    last_commit: def5678

  # ... 全量登记 CANN 组织下所有算子仓
```

#### 知识页内容要求（忠于原文）

每个仓的知识页包含：
- 一句话定位（基于 README 原文摘录）
- 解决什么问题（基于 README 原文摘录）
- 核心能力列表（基于仓内目录和文档）
- 代码结构导读（目录树原样呈现）
- 关键代码片段（原样引用，标注 GitCode URL + commit hash，不做任何修改）
- 与其他仓的关系（[[wikilink]] 互联）
- 常见问题（摘自 Issue 或社区反馈，标注来源 URL）

**Repo 全览目录**提供按类型分类的检索入口，解决"开发者不知道有哪些仓、各仓能力是什么"的问题。

### 5.4 数据同步与 Ingest 流程

#### 总体流程

```
                     每两周触发一次
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
     doc_syncer.py              repo_syncer.py
     (发布仓接口)                (GitCode API)
              │                       │
              ▼                       ▼
     变更检测：                  变更检测：
     获取 2 周内变更清单          对比新旧 registry
              │                       │
              ▼                       ▼
     增量下载文档                 增量同步元信息
     存入 raw/docs/              更新 registry.yaml
              │                       │
              ▼                       ▼
     生成变更报告                 生成变更报告
              │                       │
              ▼                       ▼
     ┌────────┴────────┐      ┌───────┴────────┐
     │ Phase 1:         │      │ Phase 1:        │
     │ 人工触发 Ingest   │      │ 人工更新知识页   │
     │                  │      │                 │
     │ Phase 2:         │      │ Phase 2:        │
     │ 自动 Ingest      │      │ LLM 辅助更新    │
     │ + 向量库入库      │      │ + 人工审核       │
     └─────────────────┘      └─────────────────┘
```

#### CANN 文档同步

```
自动化部分（doc_syncer.py + cron，每两周执行）：
1. 调用发布仓接口，获取 2 周内变更清单
2. 增量下载变更文档，存入 raw/docs/[version]/
3. 写入 _meta.yaml 同步元信息
4. 生成变更报告（哪些文档变了、影响哪些知识页）
5. 追加 sync_log.yaml

人工部分（收到变更报告后执行）：
1. 审阅变更报告，确认需要更新的知识页
2. 读取变更文档，提取核心事实内容（官方原文摘录）
3. 更新 summaries/ 摘要页
4. 更新已有 knowledge/ 页面（补充新信息，更新 applies_to）
5. 创建新页面（如需要）
6. 提取踩坑条目 → pitfalls/
7. 提取代码样例 → examples/（代码保持原文）
8. 更新 index.md
```

#### 代码仓同步

```
自动化部分（repo_syncer.py + cron，每两周执行）：
1. 列出 CANN 组织下所有仓库，与 registry.yaml 对比
   - 新仓出现 → 自动触发结构探测，生成 profiles/
   - 已有仓 → 检查最后 commit 是否变化
2. 对有变更的仓，按 extract_rules 重新拉取目标文件
3. 生成变更报告
4. 校验 canonical_url 可达性（发现不可达时告警）
5. 追加 sync_log.yaml

人工部分：
1. 新仓：审阅结构画像 → 编写 extract_rules → 创建知识页
2. 已有仓变更：审阅变更报告 → 更新知识页
3. 更新 repos/index.md 全览目录
4. 更新 knowledge/index.md
```

#### 变更报告模板

每次同步后自动生成，供人工审阅：

```markdown
# CannEx 数据同步报告 — 2026-04-29

## 官方文档变更
- 新增：性能调优指南新增第 8 章（v9.0.0-beta2）
- 修改：算子开发指南 §3.2 Pipeline 章节（措辞调整）
- 影响知识页：concepts/pipeline.md, concepts/perf-optimization.md
- 待处理：需人工审阅 pipeline.md 是否需要同步更新

## 代码仓变更
- 新仓发现：ascend/cann-ops-contrib（社区贡献算子）
  - 结构画像已生成：raw/repos/profiles/cann-ops-contrib.yaml
  - 待处理：需编写 extract_rules + 创建知识页
- samples 仓新增样例：operator/SoftmaxCustom
  - 待处理：评估是否提取为 knowledge/examples/ 页面
- cann-ops-adv 仓 README 更新
  - 待处理：同步到 knowledge/repos/cann-ops-adv.md

## 版本淘汰
- v7.0.0 已超出保留范围，已归档
```

#### 同步服务技术选型

```yaml
# Phase 1：脚本化（轻量启动）
sync_service:
  runtime: Python 脚本 + cron
  components:
    - doc_syncer.py       # 对接发布仓接口，增量下载文档
    - repo_syncer.py      # 对接 GitCode API，同步仓库元信息
    - change_detector.py  # 变更检测 + diff 生成 + 报告输出
    - sync_scheduler.sh   # cron 调度（每两周触发）
  storage:
    docs: raw/docs/[version]/
    repos: raw/repos/（registry.yaml + profiles/ + extract_rules/）
    logs: raw/sync_log.yaml

# Phase 2：服务化（规模扩展时）
# 迁移到独立微服务，增加：
# - 消息队列（变更事件驱动 Ingest）
# - 向量库入库管道
# - 监控告警（同步失败/数据异常）
```

### 5.5 数据质量保障

```yaml
quality_checks:
  # 每次同步后自动执行
  post_sync:
    - url_consistency:
        desc: "知识页中引用的 URL 可访问"
        action: 校验 sources 字段中的 URL 可达性
    - version_consistency:
        desc: "知识页的 applies_to 与实际文档版本匹配"
        action: 交叉校验 knowledge/ 页面与 raw/docs/ 版本
    - orphan_detection:
        desc: "是否有知识页引用了已淘汰版本"
        action: 扫描 applies_to 中的版本是否在保留范围内

  # 每月人工执行
  monthly:
    - content_freshness:
        desc: "知识页内容是否与最新文档一致"
        action: 抽查 10% 知识页与原文对比
    - repo_coverage:
        desc: "是否有新仓未被 registry 覆盖"
        action: 对比 GitCode 组织仓库列表与 registry.yaml
```

---

## 六、Skill 运行时行为

### 6.1 知识检索流程与抗幻觉机制

Agent 在回答用户问题时的知识检索路径：

```
用户提问
  ↓
1. 匹配 question-bank.yaml 的 pattern
   → 命中：直接读取映射的知识页
   → 未命中：进入步骤 2
  ↓
2. 在 knowledge/ 目录中 Grep 关键词
   → 命中：读取匹配的知识页
   → 未命中：进入步骤 3
  ↓
3. 在 raw/ 目录中检索 PDF 原文
   → 命中：读取相关章节，回答并建议 Ingest 到知识层
   → 未命中：诚实说"当前知识库未覆盖此内容"
```

**抗幻觉：知识页的定位是"事实素材库"而非"预写答案"**

```
┌────────────────────────────────────────────────────┐
│           知识页（静态，Ingest 阶段写入）              │
│                                                    │
│  存：官方原文摘录、API 定义、代码原文、                │
│      版本适用范围、仓库元信息                         │
│  不存：解读、类比、教学叙述                           │
│                                                    │
│  作用：提供"地基事实"，约束模型回答的边界              │
└──────────────────┬─────────────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────────┐
│        Skill Prompt（运行时规则）                     │
│                                                    │
│  规则 1：回答必须基于知识页中的事实素材                 │
│  规则 2：超出素材的推理/解读，标注为辅助理解            │
│  规则 3：无相关素材时坦诚告知 + 指路官方文档            │
│  规则 4：代码原样引用，不修改                         │
│  规则 5：先确认版本再回答                             │
│                                                    │
│  作用：控制模型"怎么用"这些素材                       │
└──────────────────┬─────────────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────────┐
│           模型实时生成                                │
│                                                    │
│  做：基于素材组织针对性的回答、类比解释、               │
│      关联多个知识页综合回答                            │
│  不做：编造 API、修改代码、猜测技术细节                 │
└────────────────────────────────────────────────────┘
```

**为什么不预写答案**：开发者问题是开放的，无法穷举。知识页存储事实素材（官方文档摘录、代码原文、API 定义），模型的价值是实时将这些素材组织成开发者能理解的回答。Prompt 规则确保模型不越界编造。

### 6.2 层级自适应行为

不做显式分级，通过 Skill prompt 指令实现内隐自适应：

```
问题复杂度信号              → 应答策略
────────────              ─────────
概念本身就是入门级的          → 从前置知识讲起，用类比，控制信息量
 "算子是什么"
 "Pipeline 是什么"

问题暗示有一定基础            → 跳过基础铺垫，直接讲核心原理
 "Double Buffer 没提速"
 "Tiling 怎么算最优"

问题涉及微架构/极限优化       → 给精确技术回答，不啰嗦基础
 "L0A Bank 冲突判断"
 "静态 Tensor 什么场景值得"
```

---

## 七、部署方案

### 7.1 Phase 1：CLI Skill Pack

```
分发方式：
  git clone https://github.com/xxx/CannEx.git

安装：
  将 CannEx/skills/ 链接到 ~/.claude/skills/cannex/
  或在项目级 CLAUDE.md 中配置 skill 路径

使用：
  > ascend-c                          # 入口
  > ascend-c:learn pipeline           # 概念教学
  > ascend-c:examples matmul          # 代码样例
  > ascend-c:pitfalls "DataCopy 报错" # 故障诊断
```

### 7.2 Phase 2：Web 服务

```
架构：
  前端（Chat UI）→ 后端（Claude API + Tool Use）→ Claude 模型

核心复用：
  - skills/*.md → 后端读取为 system prompt（零修改）
  - knowledge/ → Tool Use 工具检索（search_knowledge / read_page）
  - raw/ → Tool Use 工具按需读取

需额外构建：
  - Chat UI 前端
  - Agent Loop 后端（Claude Agent SDK）
  - 上下文压缩（滑动窗口 + 摘要）
  - 会话持久化（Session Store）

可选快速验证：
  - 部署到 Dify / Coze 等 Agent 平台（零代码）
```

### 7.3 Phase 2：RAG 增强

**触发条件**：Phase 1 运行后，当以下场景频繁出现且知识页无法覆盖时启动。

| 场景 | RAG 解决什么 |
|------|-------------|
| API 参数组合查询 | 向量化存储 API 文档 |
| 错误码诊断 | 错误码全表索引 |
| 硬件 × 数据类型 × API 组合 | 兼容性矩阵检索 |
| CANN 版本差异 | 版本 diff 索引 |
| 社区长尾问题 | gitee issues 向量库 |
| 开源代码仓检索 | 代码级语义检索 |

---

## 八、Phase 1 交付物清单

| 交付物 | 数量/规模 | 状态 |
|--------|----------|------|
| Skill 文件 | 4 个（入口 + learn + examples + pitfalls） | 待开发 |
| 共享资源 | 3 个（persona + question-bank + learning-paths） | 待开发 |
| Entity 知识页 | 5 个 | 待 Ingest |
| Concept 知识页 | 11 个 | 待 Ingest |
| Example 代码样例 | 6 个 | 待编写 |
| Repo 算子仓知识页 | 50+ 个 | 待 Ingest |
| Repo 全览目录 | 1 个 | 待编写 |
| 仓库注册表 registry.yaml | 1 个 | 待编写 |
| 仓库提取规则 extract_rules/ | 50+ 个（每仓一份） | 待编写 |
| Comparison 对比页 | 2 个 | 待 Ingest |
| Pitfall 踩坑条目 | 20+ 个 | 待采集 |
| Summary 摘要页 | 3+ 个 | 部分已有 |
| SCHEMA.md | 1 个 | 待编写 |
| index.md | 1 个 | 待编写 |
| 同步脚本 | 4 个（doc_syncer + repo_syncer + change_detector + scheduler） | 待开发 |
| 项目文档 | 3 个（PRD + SDD + 需求分析） | PRD 已有 |

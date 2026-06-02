# CannEx Webchat 输出可视化整治 — 设计

> 日期：2026-05-31
> 状态：设计已批准，待写实施计划
> 范围：`webchat/cannex_chat/`（Phase 2 Chainlit 应用）

---

## 一、问题

Webchat 的回答里，凡是「流程 / 管线 / 调用链」类内容，LLM 当前都用 **ASCII 画框**（`┌─┐│└┘→` 拼图）放在 ` ``` ` 围栏代码块里输出。highlight.js 把它当纯文本等宽渲染，结果：

1. **丑**：等宽 ASCII 框在 Web 上排版粗糙、对齐易错位。
2. **太简化**：box-drawing 图物理上装不下多少信息，导致内容被迫压缩。

这是两个耦合的问题——视觉粗糙 + 内容密度低——根因同一个：**用错了表达载体**。

## 二、渲染基底（实测结论）

- `webchat/chainlit` fork 已不存在，现为 **stock Chainlit 2.11.1**（pip 安装，预构建前端）。CLAUDE.md 中「fork」记载已过时。
- Agent 经 `app.py` 的 `answer_msg.stream_token(ev["delta"])` **纯文本流式输出**，全程只写一个 `cl.Message`，从不 emit Chainlit element。
- `config.toml` 已启用 `custom_css = "/public/custom.css"`；`custom_js` 可用（当前注释）。
- 预构建前端**已捆绑**：KaTeX、highlight.js、Plotly element、Dataframe element、`public/elements/` 自定义 JSX 元素（`cl.CustomElement`）。
- **Mermaid 不在运行时 bundle 中**（仅出现在 source map 的依赖名引用里），` ```mermaid ` 围栏块当前不会自动渲染。

## 三、方案选择与取舍

整体走「**全面整治**」路线，但按架构实测收敛为三件套，并**砍掉** Plotly/Dataframe：

- **Mermaid 渲染机制**：选**客户端 `custom_js` 自动渲染**，而非后端 `cl.CustomElement` 逐图插入。
  - 理由：agent 是 token 流式输出。后端逐图插入需在流中检测完整 mermaid 块、暂停流、emit 元素、再续流——与流式架构冲突、边界难判、侵入 agent loop。客户端 Observer 方案 agent 侧零改动。
- **Plotly / Dataframe**：**去掉（YAGNI）**。
  - 理由：agent 是检索接地的文档/代码教师，手里没有跑 profiling 得到的数值序列可画图；CSV 形的表用 Markdown 表格已足够；且原生元素同样要打断纯文本流。

## 四、组件设计

### 组件 1 · `public/custom.js`（新文件）— 客户端 Mermaid 渲染器

- `config.toml`：启用 `custom_js = "/public/custom.js"`。
- 脚本内动态 `import("https://cdn.jsdelivr.net/npm/mermaid@11/+esm")`（经典 script + 动态 import，无需 type=module）。
- `mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: <跟随暗/亮> })`。
- **MutationObserver**（debounce ≈120ms，应对高频 token 流）监听消息容器，扫描 `pre code.language-mermaid`（highlight.js 不识别 `mermaid` 语言 → 保留 `language-mermaid` class，`textContent` 即原始源码）。
- **流式安全**：对每个块先 `mermaid.parse()` 校验；不完整则跳过、等下次稳定。以源码 hash 写 `data-mmd` 标记——已渲染或源码未变则不重绘，防闪烁。
- **渲染**：`mermaid.render()` 产出 SVG，插到 `pre` 之后并隐藏原 `pre`。
- **主题感知**：监听 `documentElement` 的 class 变化（Chainlit 暗/亮切换）→ 清标记重渲染。
- **优雅降级**：CDN 加载失败 / parse 失败 → 保留原始 ` ```mermaid ` 源码块（由 highlight.js 渲染），绝不白屏。

> **安全权衡**：`securityLevel: 'strict'` 会转义标签，因此 **mermaid 节点内禁用 `<br/>` 等 HTML**（LLM 输出是不可信渲染源，避免 XSS）。节点文本保持简短；确需分行时用 Mermaid 引号文本，不用裸 HTML。此约束写入 Prompt（组件 2）。

### 组件 2 · `prompts/system_prompt.md`（新增「输出可视化规范」节）

- **硬禁**：ASCII 画框 / box-drawing（`┌─┐│└┘` + `→` 拼图）。
- **决策规则**：

  | 内容形态 | 用什么 |
  |---|---|
  | 图结构：流程 / 管线 / **调用链** / **影响面** / CRTP 继承层级 / 状态机 | ` ```mermaid ` flowchart |
  | 维度对照：阶段→命令→产物、文件→用途、API 对比 | Markdown 表格 |
  | 顺序步骤 | 编号列表 + 加粗阶段名 |
  | 简单 A→B→C 线性关系 | 行内箭头 |

- **Mermaid 语法约束**：用 `flowchart LR` / `flowchart TD`；节点文本简短、无 HTML、无反引号（避免解析冲突）；边 label 简短。
- **2 个 few-shot 示例**：性能调优 pipeline、FlashAttention 调用链（贴合 CannEx 核心场景，因 mermaid 是 LLM 的新增能力，需示例锚定风格）。
- **不变量（沿用现有铁律，不得削弱）**：
  - 图后仍带 `[来源: …]` 标注。
  - grounding / 反幻觉铁律不变（§检索工作流 来源标注规则）。
  - 调用链 playbook 的 `coverage` 盲区节点，在 mermaid 中用专门 class 标注 `[cut?]`。

### 组件 3 · `public/custom.css`（增量）

- Mermaid SVG 容器：居中、`max-width`、圆角背景、留白。
- `[cut?]` 盲区节点样式（虚线边框 / 降透明度），与组件 2 的盲区标注呼应。
- 在现有排版基础上微调代码块 / 表格密度（多数已覆盖，仅做增量）。

## 五、数据流

```
agent（按 system_prompt 规范产出含 ```mermaid 的纯文本）
  → app.py: answer_msg.stream_token(delta) 流入单个 cl.Message
  → 消息 DOM
  → public/custom.js MutationObserver
  → CDN mermaid.parse() 校验 → mermaid.render() 出 SVG
  → 主题感知重绘
```

**agent loop / `teacher.py` / `worker/` 零改动。** 改动面仅限：`public/custom.js`（新）、`public/custom.css`（增量）、`prompts/system_prompt.md`（新增节）、`.chainlit/config.toml`（启用一行）。

## 六、错误处理与降级

| 失败点 | 行为 |
|---|---|
| CDN mermaid 加载失败（如离线环境） | 退回显示原始 ` ```mermaid ` 源码块；后续可改本地打包 |
| `mermaid.parse()` 失败（中文/特殊字符） | 跳过渲染，保留源码块；靠 Prompt 语法约束降低发生率 |
| 流式中途块不完整 | parse 校验失败 → 等待下次 Observer 触发 |

## 七、测试策略

无前端测试框架，以**手工 E2E 验收**为主：

1. 跑 `chainlit run app.py -w`，问 3 个代表问题：
   - 性能调优 pipeline（流程图）
   - FlashAttention 调用链（图结构 + `[cut?]` 盲区）
   - 内存层级有哪几种（表格/列表，验证非图结构内容不滥用 mermaid）
2. 核对：图渲染正确、暗/亮主题切换重绘、流式不闪烁、parse 失败优雅退回源码。
3. Prompt 侧：跑若干 query 确认不再产出 ASCII 画框，且按决策规则选对载体。

## 八、风险

1. **CDN 依赖**：离线/内网环境 mermaid 拉不到 → 已有源码块降级兜底；如成为常态，后续迭代改 `custom_build` 本地打包。
2. **Mermaid 解析鲁棒性**：中文 + 特殊字符偶发 parse 失败 → Prompt 语法约束（短文本、无 HTML、无反引号）+ 降级兜底双重缓解。
3. **安全**：LLM 输出为不可信渲染源 → `securityLevel:'strict'` + 禁用节点内 HTML。

## 九、非目标（YAGNI）

- 不引入 Plotly / Dataframe 等需打断纯文本流的后端元素。
- 不 patch / rebuild Chainlit 前端（避免与 pip 升级冲突）。
- 不预构建本地 mermaid 包（先 CDN，离线成为问题再说）。
- 不改动 agent loop / teacher.py / worker。

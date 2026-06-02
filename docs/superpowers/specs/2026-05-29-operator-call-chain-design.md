# 算子完整调用链 / 影响面分析设计

**Date:** 2026-05-29
**Status:** Approved（brainstorming 阶段完成，待 plan 实施）
**Owner:** justbin
**Related:**
- `docs/superpowers/specs/2026-05-28-codegraph-integration-redesign.md`（前置：CodeGraph L0-L4 集成）
- `docs/superpowers/plans/2026-05-28-followup-tasks.md`（早期记录"CodeGraph 价值未兑现"疑虑）
- `CLAUDE.md §二`（配套改写：把二开/魔改纳入场景 B，见本 spec §八）

---

## 一、背景与目标

### 客户与场景

CannEx 场景 B（官方算子仓）的目标客户**包含基于昇腾官方算子做魔改 / 二开的中高阶开发者**，不只是"读样例学习"的学习者。二开者的核心诉求：

- "这个算子的**完整调用链**是什么，我要看懂执行逻辑再动手"（向下 callees）
- "我改这个函数 / Tiling，**会波及哪些文件**，要回归哪些路径"（向上 impact 影响面）

### 为什么这是个真问题（而非 IDE / grep 能替代）

经三轮分析与实测确认的事实：

1. **CodeGraph 解析未预处理源码**，对 CANN 的两类主干结构**静默失明**：
   - 入口宏分发（`INVOKE_FA_*` / `REGIST_MATMUL_OBJ`）—— 宏不是图节点（实测 `REGIST_MATMUL_OBJ` "not found"）
   - CRTP 模板特化 —— 模板方法 callers 反查为空
2. **"读源码 ≠ grep"**：grep / CodeGraph 都是机械的，都展不开宏、解不了模板；LLM 读源码是**语义理解**，能展开宏、解析模板、跟随 `#ifdef`。这是突破盲区的唯一手段。
3. **但读源码不"完整"也不便宜**：只覆盖实际打开的文件，深度上容易半路停（实测 FA 调用链在 `Process()` 处停下），且烧 token。

**结论——互补失败模式：**

| | CodeGraph 图遍历 | LLM 读源码 | ripgrep 文本搜 |
|---|---|---|---|
| 速度 / token | 快、近零 token | 慢、烧 token | 快、零 LLM token |
| 广度 / 深度遍历 | 强（传递闭包） | 弱（受打开文件数限） | 弱（无结构） |
| 普通方法调用 | 可靠不漏 | 可能看漏 | 噪声多 |
| 宏 / 模板跳转 | **静默漏** | **能语义补全** | 能召回文本命中 |

**没有单一工具能可靠给出 CANN 算子的完整调用链 / 影响面。** 本设计的价值正是把三者焊在一起——这是裸 IDE / 裸 grep / 裸 CodeGraph 都给不了的差异化。

---

## 二、设计原则

1. **图谱主干 + 接缝补全（seam-patching）**：宏 / 模板只是少数"接缝"，CANN 算子里直路远多于接缝。图谱跑直路（便宜），LLM 只在接缝处读源码（受控），接上后控制权交回图谱。

2. **省 token 优先，但完整度可 escalate**：默认保守预算服务日常探索；二开者动手前可一键提高预算换完整度。两个姿态共存，互不绑架（见 §五）。

3. **确定性归 lib，语义归 agent**：图谱遍历、接缝正则预标、ripgrep 召回 —— 确定性、可单测、可量化 recall，放 lib，零 LLM token。宏 / 模板的语义展开、ripgrep 候选分类 —— 放 agent。

4. **影响面绝不假装完整**：对要动手的人，"不完整的影响分析"比"没有"更危险。所有结果带 **coverage 信号**，未展开节点响亮标 `[cut?]`，**不替用户做改动决策**（守住 §一定位底线）。

5. **复用 L0 策展做种子**：算子根符号优先取 `samples.yaml` 的 entry（人工策展，最准），退化才用 `search_code_symbol`。

---

## 三、向下：完整调用链（seam-patching 算法）

```
输入: 算子名 | 根符号, max_depth, read_budget
输出: 带来源标注的调用树 + coverage

① 取根符号
   samples.yaml entry（优先）→ search_code_symbol（退化）

② 图谱 BFS 遍历（lib，零 LLM token）
   从根 callees 逐层展开到 max_depth，建骨架树
   每节点: {symbol, file:line, provenance="graph"}

③ 接缝检测 / 打"失明风险"（lib，零 LLM token）
   a. 图侧信号: 名含 Process/Init/Compute/Launch、或 op_kernel 入口 .cpp，
      却 callees=0 / 异常少 → 可疑叶子
   b. 源侧信号（正则扫节点 body 区间）:
      - 全大写宏调用  MACRO(            → 宏接缝
      - 模板实例化   Foo<...>::Bar / std::conditional → 模板接缝
   lib 返回: 骨架树 + 接缝节点清单 + 每个接缝的源码区间(file:line)

④ 定向补全（agent，token 受控）
   - 只读接缝节点的"函数体区间"（用图给的 start_line→end_line），不读整文件
   - 宏接缝: 读宏定义体一次并缓存（同一宏全仓复用一份）
   - LLM 从展开结果抽出真实被调符号 → 插入树(provenance="read")
   - 新符号若是图节点（如 Process）→ 回灌 ② 继续图谱遍历（迭代）

⑤ 预算与停止
   - read_budget 触顶 / 超 max_depth 的可疑节点 → provenance="cut"（存疑）

⑥ 输出: 带来源标注调用树 + coverage
```

### 省 token 的四个机关

1. 图谱跑直路，大部分普通调用零源码 token
2. **读函数体区间而非整文件**（1500 行文件可能只读 80 行）
3. **宏定义缓存**（同一宏全仓只读一次）
4. **风险门控**：只在接缝读，低风险节点直接信图谱

---

## 四、向上：改动影响面（图谱 + ripgrep 召回网）

impact（改 X 会炸谁 = 向上反查所有依赖者）的盲区比向下更重：X 被宏间接调用时，图谱不记这条 caller 边；靠读源码向上补需扫全仓，token 爆炸。**ripgrep 恰好补这个洞，且几乎零 token。**

```
impact(X) 影响面 =
  图谱 callers(X) / impact(X)        ← 精确、带类型，漏宏/模板调用点
  ∪ ripgrep "X" 全仓文本引用          ← 便宜(零LLM token)，召回宏/模板/文本命中
  → LLM 只对"ripgrep 命中但图谱没有"的少量候选做分类
    （真调用 / 注释 / 字符串 / 同名无关）
  → 输出带 coverage 标注的影响面
```

**分工**：图谱负责精度，ripgrep 负责召回，LLM 只做少量边界分类。保守预算下也能把 recall 拉到可交付——这正是 grep 在 CannEx 的真正价值落点：**不替代图谱，作图谱向上反查的召回兜底网。**

---

## 五、coverage 信号 + escalate（保守预算下的安全阀）

token 优先意味着更早触顶、更多 `[cut?]`。对二开者这是致命的，故强制：

- 每次查询返回 **coverage 信号**：`图谱确认 N 处 + 读源码/ripgrep 补 M 处 + K 处未展开(存疑)`
- **绝不**把保守预算下的局部结果当完整呈现
- 提供一键 **escalate**：动手前要确认完整影响面 → 提高 `read_budget` 重跑
- 默认姿态：**token 优先、保守**（日常探索）；escalate 档：完整度优先（改动决策）

### 输出形态示例（带来源标注的调用树）

```
FlashAttentionScore (entry .cpp)
├─[read:宏 INVOKE_FA_GENERAL_OP_IMPL] REGIST_MATMUL_OBJ → bmm1/bmm2 注册
├─[read:宏展开] op.Init()
└─[read:宏展开] op.Process()                       ← 接缝补全
   ├─[graph] CopyCosSin()  attention/.../bf16.h:541   ← 回到图谱直路
   ├─[graph] ExpandNeg()   ...:508
   └─[cut?]  InnerCompute() ← 超预算/可疑模板，未展开，建议人工核查

coverage: 图谱 12 + 读源码补 4 + 存疑 1（cut）
盲区声明: 宏/模板接缝 4 处由读源码补全；1 处因预算未展开，
          二开改动前请重点核查 InnerCompute 分支。
```

---

## 六、lib 接口契约（混合方案，确定性可单测）

```python
# 向下：算子完整调用链
def api_call_chain(repo, root, max_depth=4, read_budget=8):
    """
    返回 envelope.data:
      {
        "tree": <调用树骨架，节点带 provenance=graph>,
        "seams": [ {symbol, file_path, span:[start,end],
                    kind: "macro"|"template"|"suspect_leaf"} ],
        "coverage": {"graph": N, "seam_total": M}
      }
    lib 只做：图谱 BFS + 正则接缝预标 + 给出源码区间。
    agent 负责：读 seams 的 span、展开宏/模板、回灌新符号。
    """

# 向上：改动影响面（v1 纳入）
def api_impact_surface(repo, symbol, read_budget=8):
    """
    返回 envelope.data:
      {
        "graph_callers": [ ... ],              # 图谱精确反查
        "ripgrep_refs":  [ {file_path, line, text} ],  # 全仓文本引用
        "to_classify":   [ ripgrep 命中但图谱缺的候选 ],
        "coverage": {"graph": N, "ripgrep_only": M}
      }
    lib 只做：图谱 callers/impact + ripgrep 召回 + 求差集。
    agent 负责：对 to_classify 分类（真调用/注释/字符串/同名无关）。
    """
```

- 统一沿用现有 `_envelope(source_type, evidence, data, error, fallback_hint)` 结构
- 两个 API 内部复用现有 `codegraph_client.call_cli` + `api_callees/api_callers/api_impact`
- ripgrep 通过 subprocess 调 `rg --json`（新增依赖，需确认环境已装 ripgrep）
- 接缝正则、suspect_leaf 阈值为具名常量（禁魔法数字）

---

## 七、测试策略（record-replay，沿用现有约定）

- **lib 层**：固定 fixtures（图谱骨架 JSON + 源码片段 + ripgrep 输出），monkeypatch subprocess
  - `api_call_chain`：正常调用链全 graph / 含宏接缝标 macro / 可疑叶子标 suspect_leaf / 预算触顶标 cut
  - `api_impact_surface`：graph∪ripgrep 求差集正确 / coverage 计数正确
- **可靠性 spike（先行验证，决定 C 能否交付）**：挑 3-5 个真实二开式问题，量化
  1. 裸 codegraph 遍历 recall（预期：普通调用高、宏/模板处掉）
  2. 图谱 + 接缝补全 / ripgrep 后 recall（验证融合能否补到可交付水平）
  - 不达标 → 退回"方案 B（仅 L1 符号定位）"

---

## 八、配套：CLAUDE.md §二 定位改写（必须同步）

现行 §二"**不做**…调用链反查（维护者需求）"与本设计直接冲突。改写为带边界版本：

> 做调用链反查与影响面分析，**仅服务二开/魔改场景**，且**必须标注图谱盲区与 coverage、不替用户做改动决策**（仍守"让开发者学会、不替他干活"底线）。

并在场景 B 描述里显式纳入"基于官方算子做魔改/二开的中高阶开发者"为目标客户。

---

## 九、范围边界（YAGNI）

- v1 含：向下 `api_call_chain` + 向上 `api_impact_surface`（用户选择 impact 纳入 v1）
- v1 不含：跨仓调用链、调用链 diff、可视化渲染
- 默认姿态 token 优先保守；完整度靠 escalate（非默认）
- 不预构建调用链缓存（在线动态，与"代码↔文档关联不预构建"一致）

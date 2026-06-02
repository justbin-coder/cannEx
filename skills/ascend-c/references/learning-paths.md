# 学习路径与概念依赖

来源：CannEx SDD §3.5 learning-paths.yaml + PRD 附录 A。

---

## 算子分类全景（任何分类问题的回答起点）

```
大模型算子分类（按计算单元）
│
├── 1. 纯 Vector 算子（元素级计算）
│   ├── 代表：Add, ReLU, Sigmoid, Abs, Cast, Exp, Log
│   ├── 特征：逐元素操作，无数据依赖
│   └── 学习顺序：★ 第一站（必经）
│
├── 2. Vector 融合算子
│   ├── 代表：LayerNorm, RMSNorm, SiLU×Mul, GELU, Softmax
│   ├── 特征：多步 Vector 串联，减少 GM 读写
│   └── 学习顺序：★★ 第二站
│
├── 3. 纯 Cube 算子
│   ├── 代表：MatMul, BatchMatMul, GEMM
│   ├── 特征：调用 Cube 硬件单元，L1→L0 两级缓存
│   └── 学习顺序：★★★ 第三站
│
└── 4. Cube + Vector 融合算子
    ├── 代表：MatMul+ReLU, MatMul+LeakyReLU, Attention(QKV)
    ├── 特征：CO2→VECIN 级联，不回 GM
    └── 学习顺序：★★★★ 第四站
```

---

## 概念依赖图（决定"下一步"推荐时参考）

```
operator-taxonomy（无前置）─┐
                            ├─→ pipeline ─┬─→ simd
ai-core（无前置）─┐         │             ├─→ simt
                  ├─→ ────┘             ├─→ dev-workflow ─→ precision-alignment
                  └─→ memory-hierarchy ─→ tiling-design ─┬─→ double-buffer
                                                          └─→ perf-optimization
```

**依赖关系解释**：
- 学 `pipeline` 前要先理解 `operator-taxonomy`（知道有哪些算子）+ `ai-core`（理解硬件）
- 学 `tiling-design` 前要先理解 `memory-hierarchy`
- 学 `double-buffer` 前要先理解 `pipeline` + `tiling-design`
- 学 `perf-optimization` 前要先理解 `double-buffer` + `tiling-design`

---

## 推荐路径（按典型场景）

### 路径 1：第一个算子（first-operator）
**目标**：从零到跑通一个 Vector Add 算子
```
operator-taxonomy → ai-core → pipeline → memory-hierarchy → tiling-design → dev-workflow
```

### 路径 2：性能优化（optimization）
**目标**：算子能跑但太慢，系统学习优化方法
**前置**：已完成 first-operator 路径
```
memory-hierarchy → tiling-design → double-buffer → perf-optimization
```

### 路径 3：精度对齐（precision）
**目标**：结果不对时的系统排查方法
**前置**：已能独立编写算子
```
dev-workflow → precision-alignment
```

---

## "下一步"推荐决策表

| 用户刚理解的概念 | 推荐下一步 | 推荐措辞 |
|---|---|---|
| operator-taxonomy | ai-core | "已经知道算子有哪几类。要不要了解一下 AI Core 这个硬件长什么样？" |
| ai-core | pipeline | "理解了硬件后，下一步是数据怎么在硬件里流动——这就是 Pipeline。继续？" |
| pipeline | tiling-design 或 memory-hierarchy | "下一步可以学 Tiling 设计——为什么要把数据切块。要看吗？" |
| memory-hierarchy | tiling-design | "理解了内存层级，自然要问：UB 这么小，数据怎么放进去？这就是 Tiling。" |
| tiling-design | double-buffer 或 dev-workflow | "Tiling 解决了空间问题，接下来 Double Buffer 解决时间问题——让搬运和计算并行。" |
| double-buffer | perf-optimization | "知道了 Double Buffer，下一步可以学系统的性能优化方法论。" |

---

## 反模式：什么时候**不要**推下一步

- 用户表现出疲惫或满足（"了解了，谢谢"）→ 不推
- 用户问的是事实查询不是学习 → 不推
- 用户连续追问 3 轮还在同一个概念 → 不推，给更详细展开
- 用户主动说"我想学 X" → 跳过推荐，直接进入 X

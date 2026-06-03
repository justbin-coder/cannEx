# API 参考文档零 LLM 构建方案设计

> 日期：2026-06-03
> 状态：设计确认，待实施
> 关联：`build/build_docs.py`、`lib/cannex_knowledge/retriever_doc.py`、`build/docs.yaml`

---

## 0. 一句话结论

operator_api_ref（3301 页 / 1696 TOC 条目）弃用 PageIndex 建树，改用 **PyMuPDF 零 LLM 直提**——利用 PDF 自带的完美 TOC 构建与 PageIndex 同 schema 的 JSON + API 名称倒排索引，构建成本从"数小时 + 数十刀 + 可能失败"降到"秒级 + $0 + 必成功"。

---

## 1. 问题陈述

### 1.1 PageIndex 对 API 参考文档的三重失配

| 维度 | 问题 |
|------|------|
| 构建成本 | ~1695 节点各需 LLM summary；TOC 转换因高度雷同 API 名导致 LLM 复读/幻觉（已打 6+ 补丁仍未建成）；单次尝试已刷爆网关配额 |
| 运行时成本 | `api_outline()` 返回 1695 节点 + summary → 巨量 token；LLM 要在大树上推理"读哪几页" |
| 运行时效果 | PageIndex 的 tree reasoning 为叙事文档设计；API 参考的主要用法是按名查找，ToC 推理是高射炮打蚊子 |

### 1.2 API 参考文档的本质特征

- **结构极度规整**：每个 API 独立条目（名称 → 参数 → 返回值 → 约束 → 示例）
- **PDF 自带完美 TOC**：1696 条目，4 层深度，level/title/page 齐全
- **标题即 API 名**：`2.2.1.8 GetSize`、`2.2.1.12 GetPhyAddr`——标题本身是最好的"summary"
- **用户查询模式偏精确**（~7:3）：多数时候已知 API 名，要查参数/约束/用法

### 1.3 对比：叙事文档仍适合 PageIndex

`operator_dev`（712 页）是叙事型，章节标题不足以描述内容（"编程指南 > 硬件实现 > 基本架构"不告诉你里面讲什么），LLM summary 真正有价值。**本方案不影响叙事文档的 PageIndex 建树路径。**

---

## 2. 方案概述

### 2.1 构建侧

新增 `build/build_api_ref.py`——零 LLM 的 API 参考文档构建器。

**输入**：`docs.yaml` 中 `build_mode: api_ref` 的 PDF

**处理流程**：

```
PDF → PyMuPDF
  ├─ get_toc() → 1696 条 (level, title, page)
  │   └─ 转换为 PageIndex 兼容的 structure 树（递归嵌套 nodes）
  ├─ 逐页 get_text() → pages 数组 [{page, content}]
  └─ 遍历叶子节点 → 构建 api_index（名称倒排索引）
```

**输出 JSON schema**（PageIndex 兼容 + 额外 `api_index`）：

```json
{
  "id": "<uuid>",
  "type": "pdf",
  "path": "<source PDF path>",
  "doc_name": "<PDF filename>",
  "doc_description": "<硬编码的文档描述>",
  "page_count": 3301,
  "structure": [
    {
      "title": "Ascend C API列表",
      "node_id": "0001",
      "start_index": 45,
      "end_index": 98,
      "summary": "",
      "nodes": []
    },
    {
      "title": "SIMD API",
      "node_id": "0002",
      "start_index": 99,
      "end_index": 3287,
      "summary": "",
      "nodes": [
        {
          "title": "通用说明和约束",
          "node_id": "0003",
          "start_index": 99,
          "end_index": 102,
          "summary": "",
          "nodes": []
        }
      ]
    }
  ],
  "pages": [
    {"page": 1, "content": "<PyMuPDF extracted text>"},
    {"page": 2, "content": "..."}
  ],
  "api_index": {
    "DataCopy": {
      "pages": [450, 455],
      "section": "SIMD API > 数据搬运接口 > DataCopy"
    },
    "MatmulApiStaticTiling": {
      "pages": [1200, 1205],
      "section": "Cube API > Matmul > MatmulApiStaticTiling"
    }
  }
}
```

### 2.2 `api_index` 构建规则

1. 遍历 TOC 叶子节点（level 3-4 的条目）
2. 从标题提取 API 名称：去除章节号前缀（`2.2.1.8 GetSize` → `GetSize`）
3. key = API 名称原文，value = `{pages: [start_page, end_page], section: 面包屑路径}`
4. `end_page` = 下一个同级或更高级 TOC 条目的 page - 1（即该 API 条目的页范围）
5. 同名 API（重载）合并为同一 key，pages 取并集

### 2.3 `structure` 转换规则

1. TOC 的 `level` 映射为嵌套深度：level 1 → 顶层 nodes，level 2 → 子 nodes，以此类推
2. `node_id`：按遍历顺序生成 4 位十六进制（`0000`, `0001`, ...），与 PageIndex 格式一致
3. `start_index` / `end_index`：直接取 TOC 的 page 值；`end_index` = 下一个同级条目的 start - 1
4. `summary`：空字符串（API 参考标题自描述，不需要 LLM summary）

### 2.4 `doc_description`

硬编码字符串，内容如：
> "CANN 9.1.0-beta.1 Ascend C 算子开发接口参考。涵盖 SIMD、Cube、Vector、AI CPU 四大类 API 的完整接口说明，包括函数签名、参数说明、使用约束和代码示例。共 3301 页。"

### 2.5 与 `build_docs.py` 的集成

`build_docs.py` 的 `build_one()` 检查 `docs.yaml` 条目的 `build_mode` 字段：
- `build_mode` 缺失或 `pageindex`（默认）→ 走现有 `PageIndexClient.index()` 路径
- `build_mode: api_ref` → 调用 `build_api_ref.build_one()` 代替

入口统一，无需手动选脚本。

---

## 3. 运行时变更

### 3.1 `retriever_doc.py` 新增 `api_lookup_api()`

```python
def api_lookup_api(name_or_id: str, query: str) -> dict:
    """按 API 名称查找，返回匹配条目 + 页码范围。

    匹配策略（按优先级）：
    1. 精确匹配（大小写不敏感）
    2. 前缀/子串匹配
    3. 无命中 → 返回空 + fallback_hint

    返回:
    {
      "doc_name": "...",
      "matches": [
        {"api_name": "DataCopy", "section": "SIMD API > ...", "pages": [450, 455]}
      ],
      "fallback_hint": null | "未找到精确匹配，建议用 api_outline 按分类浏览"
    }
    """
```

**设计约束**：
- 匹配在 Python 内存完成（api_index ~1696 条 key），无外部依赖
- 子串匹配结果按名称长度升序排列（越短越精确排前面），上限 10 条
- **不引入 score / rank / top_k 语义**——遵守 CLAUDE.md §九文档侧约束，这是确定性名称查找，不是相关性检索
- 文档 JSON 无 `api_index` 字段时（PageIndex 建的文档）返回 `{"matches": [], "fallback_hint": "该文档不支持 API 名称查找，请用 api_outline 浏览"}`

### 3.2 现有 API 不变

`api_list()` / `api_meta()` / `api_outline()` / `api_pages()` 全部不改。新构建的 JSON 符合同 schema，自动兼容。

`api_outline()` 返回的 structure 节点 `summary` 字段为空字符串，不影响序列化和现有调用方。

### 3.3 运行时查找路径

#### 路径 A：精确查找（主要，~70% 场景）

```
用户："DataCopy 的参数和约束是什么？"
  → Agent 调 api_lookup_api("operator_api_ref", "DataCopy")
  → 索引命中: {pages: [450, 455], section: "SIMD API > 数据搬运接口 > DataCopy"}
  → Agent 调 api_pages("operator_api_ref", "450-455")
  → 基于原文回答
```

2 次工具调用，零 outline 推理，token 消耗极低。

#### 路径 B：模糊探索（辅助，~30% 场景）

```
用户："有哪些数据搬运相关的 API？"
  → Agent 调 api_outline("operator_api_ref", max_depth=2)
  → 看到: SIMD API > 数据搬运接口 / Cube API > ...
  → LLM 推理选 "数据搬运接口" 章节
  → Agent 调 api_pages 读该章节页范围
  → 列出相关 API 并概述
```

与现有 PageIndex 文档的 outline 推理路径一致。标题自描述（"数据搬运接口"、"DataCopy"），无 summary 不影响导航。

---

## 4. 接通层变更

### 4.1 Phase 1 CLI：`skills/ascend-c/tools/cannex_doc.py`

新增子命令 `lookup`：

```bash
python3 cannex_doc.py lookup <doc> <api_name>
```

### 4.2 Phase 2 Webchat

**`worker/server.py`**：HANDLERS 加一条
```python
"lookup_doc_api": lambda p: retriever_doc.api_lookup_api(p["doc"], p["query"])
```

**`agent/tools.py`**：TOOLS 列表加一个 `lookup_doc_api` 工具定义，description 引导 agent 在用户问具体 API 时优先调用。

### 4.3 Prompt playbook

`system_prompt.md` / `SKILL.md` 加决策分支：
- 用户问题含具体 API 名 → **先** `lookup_doc_api` → 命中则 `read_doc_pages` → 回答
- 未命中或用户在探索 → 走现有 `get_doc_outline` → 推理 → `read_doc_pages`

---

## 5. 配置变更

### 5.1 `docs.yaml`

```yaml
- name: operator_api_ref
  file: "CANN社区版 9.1.0-beta.1 Ascend C算子开发接口参考 01.pdf"
  local_path: "raw/docs/CANN社区版 9.1.0-beta.1 Ascend C算子开发接口参考 01.pdf"
  version: 9.1.0-beta.1
  category: operator_api_ref
  build_mode: api_ref          # 走 build_api_ref 而非 PageIndex
  enabled: true
```

未来其他 API 参考类文档也可切换到 `build_mode: api_ref`。

---

## 6. 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `build/build_api_ref.py` | **新增** | 零 LLM 构建核心逻辑 |
| `build/build_docs.py` | 小改 | 按 `build_mode` 分发到 PageIndex 或 api_ref |
| `build/docs.yaml` | 小改 | operator_api_ref 加 `build_mode: api_ref` |
| `lib/cannex_knowledge/retriever_doc.py` | 小改 | 加 `api_lookup_api()` |
| `skills/ascend-c/tools/cannex_doc.py` | 小改 | 加 `lookup` 子命令 |
| `webchat/cannex_chat/worker/server.py` | 小改 | 加 handler |
| `webchat/cannex_chat/agent/tools.py` | 小改 | 加工具定义 |
| `webchat/cannex_chat/prompts/system_prompt.md` | 小改 | 加决策分支 |
| `skills/ascend-c/SKILL.md` | 小改 | 加决策分支 |

---

## 7. 不做的事

- **不改 PageIndex 源码**：本方案完全绕开 PageIndex，不新增补丁
- **不改叙事文档的构建路径**：`build_mode` 默认仍走 PageIndex
- **不引入向量/BM25/相关性检索**：名称索引是确定性查找，遵守 §九约束
- **不生成 LLM summary**：API 参考标题自描述，方案 A 纯零 LLM；如未来需要可渐进升级到方案 B（仅对 top 2 层加 summary）

---

## 8. 前置条件

- `raw/docs/` 下放置 operator_api_ref PDF 原文
- Python 环境有 `PyMuPDF`（`pip install pymupdf`）
- 现有 `workspace/docs/` 的 9 份 PageIndex JSON 不受影响

---

## 9. 成功标准

1. `python3 build/build_docs.py` 成功构建 operator_api_ref，秒级完成
2. `workspace/docs/<uuid>.json` 产物含完整 structure + pages + api_index
3. `api_lookup_api("operator_api_ref", "DataCopy")` 返回正确页码范围
4. `api_outline("operator_api_ref")` 返回可导航的 ToC 树
5. `api_pages("operator_api_ref", "<page_range>")` 返回正确原文
6. 现有 9 份 PageIndex 文档的所有 API 调用不受影响（回归测试全 PASS）

# Retriever 反模式废弃与燃料补全 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 CannEx 检索层与 `CLAUDE.md §八` PageIndex 使用约束对齐——废弃两个反模式 API（`api_search` / `api_context`），补全三处 LLM 推理燃料缺位（`doc_description` / node `summary` / `api_meta`），并把 Skill / Webchat 教学 prompt 中对废弃工具的引用做**等价替换**（不重新设计教学策略，只把死工具名换成对应的活工具序列），确保本计划完成后 LLM 端不会因 prompt 残留而 hard-fail。

**Architecture:** 三层自底向上 ——
1. **lib 层**：在 `lib/cannex_knowledge/` 补燃料（向后兼容），再废弃反模式 API（破坏性）
2. **接口层**：同步 CLI（`skills/ascend-c/tools/`）、worker handler（`webchat/cannex_chat/worker/`）、测试
3. **prompt 层**：等价替换 `skills/ascend-c/SKILL.md` 与 `webchat/cannex_chat/prompts/system_prompt.md` 中对 `query_documentation` / `query_code_repo` 的所有引用——工具定义段删除、路由表改写、反模式举例更换、CLI 映射表清理

TDD 风格：每个 lib/CLI 改动先写测试再实现，每个 Task 一个 commit。Prompt 层改动不写自动化测试，靠手工 smoke + grep 残留验证。

**Tech Stack:** Python 3.11 / pytest / Click 风格 argparse CLI / NDJSON-RPC worker

---

## 背景：必须一次性完成的理由

反模式 + 燃料缺位是**互相强化**的：
- 燃料缺位（`outline` 无 summary、`list` 无 doc_description）让 LLM 无法在 tree 上推理
- LLM 被迫退回到 `api_search` 这种"打包工具"抄近路
- 单独修一边都是半截路——只删 search 会让 LLM 失去 fallback 但仍推不动；只补燃料则反模式继续诱导新会话调用

因此本计划一次性覆盖两侧。

## 影响清单（grep 确认过的引用点）

**lib 改动**：
- `lib/cannex_knowledge/retriever_doc.py:65-77` (`api_list`) — 加 `doc_description`
- `lib/cannex_knowledge/retriever_doc.py:80-106` (`api_outline`) — 节点加 `summary`
- `lib/cannex_knowledge/retriever_doc.py` — 新增 `api_meta(name_or_id)`
- `lib/cannex_knowledge/retriever_doc.py:134-210` (`api_search`) — **整体删除**
- `lib/cannex_knowledge/retriever_repo.py:132-182` (`api_context`) — **整体删除**

**CLI 改动**：
- `skills/ascend-c/tools/cannex_doc.py:34-46` (`cmd_meta`) — 改用 `api_meta`
- `skills/ascend-c/tools/cannex_doc.py:12, 57-58, 70` (`cmd_search_api`) — **删除**
- `skills/ascend-c/tools/cannex_repo.py:64-65, 135` (`cmd_context`) — **删除**

**测试改动**：
- `lib/cannex_knowledge/tests/test_retriever_doc.py:21-24` — 删 search 测试，加 outline summary / list doc_description / api_meta 测试
- `tests/test_cannex_doc_api.py:23-34` — 删 search 测试
- `tests/test_cannex_repo_api.py:29-30` — 删 context 测试

**Webchat 改动**：
- `webchat/cannex_chat/worker/server.py:33-36` — 删除 `query_documentation` / `query_code_repo` 两个 handler

**Prompt 等价替换**（重头戏，独立 Task）：
- `skills/ascend-c/SKILL.md` — 删除 2 个废弃工具定义段、路由表 4 行改写、反模式举例替换、CLI 映射表 2 行清理、双链路心智模型改写、来源标注表 1 处改写、§一 CLI 命令清单 1 行删除（Task 7）
- `webchat/cannex_chat/prompts/system_prompt.md` — Task 7 的镜像版（不含附录 A 和 §一 CLI 命令清单）（Task 8）

**文档改动**：
- `skills/ascend-c/references/codegraph-guide.md:149, 170` — 移除 `api_context` 引用

**不动**：
- `docs/superpowers/plans/2026-05-2[34]-*.md`（历史 plan）— 保留作历史记录，不修改
- `docs/specs/2026-05-23-cannex-v2-design.md` — 保留作历史

---

## 前置检查

- [ ] **运行现有测试基线**

```bash
cd /Users/justbin/Desktop/CannEx
source ~/project/CANN/PageIndex/.venv/bin/activate
pytest lib/cannex_knowledge/tests/ tests/ -v 2>&1 | tee /tmp/baseline.log
```

Expected: 记录当前 PASS 的测试集合作为对照基线。完整通过即可，部分失败也无妨（只要不是 search/context 相关的）。

- [ ] **确认 doc_json 包含 doc_description 字段**

```bash
python3 -c "
from lib.cannex_knowledge import retriever_doc as d
docs = d.api_list()
for entry in docs:
    doc = d.load_doc_json(d.resolve_doc(d.load_meta(), entry['doc_id']))
    print(entry['doc_id'], '->', 'has doc_description:', 'doc_description' in doc)
"
```

Expected: 全部 `True`。如果有 `False`，说明该文档建树时未生成 doc_description，需要先重建（不在本计划范围）。

---

## Task 1: `api_list` 暴露 `doc_description`

**Files:**
- Modify: `lib/cannex_knowledge/retriever_doc.py:65-77`
- Modify: `lib/cannex_knowledge/tests/test_retriever_doc.py:4-9`

- [ ] **Step 1: 写失败测试**

修改 `lib/cannex_knowledge/tests/test_retriever_doc.py` 的 `test_api_list_returns_docs`：

```python
def test_api_list_returns_docs():
    docs = d.api_list()
    assert isinstance(docs, list)
    assert len(docs) >= 1
    assert "doc_name" in docs[0]
    assert "doc_id" in docs[0]
    # 新增断言：每个文档必须包含 doc_description（LLM 推理燃料）
    assert "doc_description" in docs[0]
    assert isinstance(docs[0]["doc_description"], str)
    assert len(docs[0]["doc_description"]) > 0
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest lib/cannex_knowledge/tests/test_retriever_doc.py::test_api_list_returns_docs -v
```

Expected: FAIL with `assert "doc_description" in docs[0]`

- [ ] **Step 3: 改实现**

修改 `lib/cannex_knowledge/retriever_doc.py` 的 `api_list`：

```python
def api_list() -> list:
    """返回文档清单，含 doc_description（来自 PageIndex 离线建树）作为 LLM 选文档的依据。"""
    meta = load_meta()
    out = []
    for d in meta.get("docs", []):
        entry = {
            "doc_id": d["doc_id"],
            "doc_name": d["doc_name"],
            "category": d.get("category", ""),
            "pages": d.get("pages", 0),
            "priority": d.get("priority", ""),
        }
        # 加载 doc_json 取 doc_description（LLM 推理燃料，不可省略）
        try:
            doc_json = load_doc_json(d)
            entry["doc_description"] = doc_json.get("doc_description", "")
        except Exception:
            entry["doc_description"] = ""
        out.append(entry)
    return out
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest lib/cannex_knowledge/tests/test_retriever_doc.py::test_api_list_returns_docs -v
```

Expected: PASS

- [ ] **Step 5: 跑全部 doc 测试确认无回归**

```bash
pytest lib/cannex_knowledge/tests/test_retriever_doc.py tests/test_cannex_doc_api.py -v
```

Expected: 除 `test_api_search_*` 还在通过外，其他全部 PASS

- [ ] **Step 6: 提交**

```bash
git add lib/cannex_knowledge/retriever_doc.py lib/cannex_knowledge/tests/test_retriever_doc.py
git commit -m "feat(retriever): api_list 暴露 doc_description 作为 LLM 推理燃料"
```

---

## Task 2: `api_outline` 节点暴露 `summary`

**Files:**
- Modify: `lib/cannex_knowledge/retriever_doc.py:80-106`
- Modify: `lib/cannex_knowledge/tests/test_retriever_doc.py:12-18`

- [ ] **Step 1: 写失败测试**

修改 `test_api_outline_returns_structure`：

```python
def test_api_outline_returns_structure():
    docs = d.api_list()
    name = docs[0]["doc_name"]
    res = d.api_outline(name, max_depth=2)
    assert "doc_name" in res
    assert "outline" in res
    assert isinstance(res["outline"], list)
    # 新增断言：节点必须包含 summary（LLM 在 tree 上推理的燃料）
    assert len(res["outline"]) > 0
    first_node = res["outline"][0]
    assert "summary" in first_node
    assert isinstance(first_node["summary"], str)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest lib/cannex_knowledge/tests/test_retriever_doc.py::test_api_outline_returns_structure -v
```

Expected: FAIL with `assert "summary" in first_node`

- [ ] **Step 3: 改实现**

修改 `lib/cannex_knowledge/retriever_doc.py:90-101` 的 `_trim` 内嵌函数：

```python
def _trim(node: dict, depth: int) -> dict:
    out = {
        "title": node.get("title", ""),
        "summary": node.get("summary", ""),  # LLM 推理燃料，不可省略
        "start_index": node.get("start_index"),
        "end_index": node.get("end_index"),
    }
    children = node.get("nodes", [])
    if children and depth < max_depth:
        out["nodes"] = [_trim(c, depth + 1) for c in children]
    elif children:
        out["truncated_children"] = len(children)
    return out
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest lib/cannex_knowledge/tests/test_retriever_doc.py::test_api_outline_returns_structure -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add lib/cannex_knowledge/retriever_doc.py lib/cannex_knowledge/tests/test_retriever_doc.py
git commit -m "feat(retriever): api_outline 节点暴露 summary 作为 tree-walk 燃料"
```

---

## Task 3: 新增 `api_meta(doc)` lib 函数

**Files:**
- Modify: `lib/cannex_knowledge/retriever_doc.py`（新增函数）
- Modify: `lib/cannex_knowledge/tests/test_retriever_doc.py`（新增测试）

- [ ] **Step 1: 写失败测试**

在 `test_retriever_doc.py` 末尾追加：

```python
def test_api_meta_returns_single_doc_metadata():
    docs = d.api_list()
    name = docs[0]["doc_name"]
    meta = d.api_meta(name)
    assert meta["doc_id"] == docs[0]["doc_id"]
    assert meta["doc_name"] == name
    assert "doc_description" in meta
    assert "pages" in meta
    assert "category" in meta
    # api_meta 是单文档版的 get_document，对应 PageIndex 官方 demo step 1
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest lib/cannex_knowledge/tests/test_retriever_doc.py::test_api_meta_returns_single_doc_metadata -v
```

Expected: FAIL with `AttributeError: module ... has no attribute 'api_meta'`

- [ ] **Step 3: 实现 `api_meta`**

在 `lib/cannex_knowledge/retriever_doc.py` 的 `api_pages` **之前** 插入：

```python
def api_meta(name_or_id: str) -> dict:
    """返回单文档元数据（含 doc_description）。
    对应 PageIndex 官方范式中的 get_document(doc_id) ——
    tree-walk 第一步：LLM 看 doc_description 决定要不要展开 outline。
    """
    meta = load_meta()
    entry = resolve_doc(meta, name_or_id)
    doc = load_doc_json(entry)
    return {
        "doc_id": entry["doc_id"],
        "doc_name": entry["doc_name"],
        "category": entry.get("category", ""),
        "audience": entry.get("audience", ""),
        "pages": entry.get("pages", 0),
        "priority": entry.get("priority", ""),
        "doc_description": doc.get("doc_description", ""),
    }
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest lib/cannex_knowledge/tests/test_retriever_doc.py::test_api_meta_returns_single_doc_metadata -v
```

Expected: PASS

- [ ] **Step 5: CLI `cmd_meta` 改为委托 `api_meta`**

修改 `skills/ascend-c/tools/cannex_doc.py:34-46`：

```python
def cmd_meta(key):
    _print(D.api_meta(key))
```

并把模块顶部的 docstring "Usage" 段保持不变（meta 子命令已存在）。

- [ ] **Step 6: 跑 CLI smoke test**

```bash
python3 skills/ascend-c/tools/cannex_doc.py meta "$(python3 skills/ascend-c/tools/cannex_doc.py list | python3 -c 'import json,sys; print(json.load(sys.stdin)["docs"][0]["doc_id"])')"
```

Expected: JSON 输出含 `doc_description` 字段，非空。

- [ ] **Step 7: 提交**

```bash
git add lib/cannex_knowledge/retriever_doc.py lib/cannex_knowledge/tests/test_retriever_doc.py skills/ascend-c/tools/cannex_doc.py
git commit -m "feat(retriever): 新增 api_meta(doc) 对齐 PageIndex 官方 get_document 范式"
```

---

## Task 4: 废弃 `api_search`（lib + CLI + 测试 + webchat handler）

**Files:**
- Modify: `lib/cannex_knowledge/retriever_doc.py:134-210`（删除 `api_search` 整段）
- Modify: `lib/cannex_knowledge/tests/test_retriever_doc.py:21-24`（删除 `test_api_search_returns_sections_shape`）
- Modify: `tests/test_cannex_doc_api.py:23-34`（删除 `test_api_search_*` 两个测试）
- Modify: `skills/ascend-c/tools/cannex_doc.py`（删 `cmd_search_api` + argparse 分支 + docstring）
- Modify: `webchat/cannex_chat/worker/server.py:33-34`（删 `query_documentation` handler）

- [ ] **Step 1: 删 lib 实现**

打开 `lib/cannex_knowledge/retriever_doc.py`，删除 `def api_search(query: str, scope: str = "all", top_k: int = 3) -> dict:` 整个函数（约 134-210 行）。

- [ ] **Step 2: 删 lib 测试**

打开 `lib/cannex_knowledge/tests/test_retriever_doc.py`，删除 `test_api_search_returns_sections_shape` 函数（21-24 行）。

- [ ] **Step 3: 删项目级集成测试**

打开 `tests/test_cannex_doc_api.py`，删除 `test_api_search_returns_sections`（23-32 行）和 `test_api_search_with_invalid_scope_returns_empty`（33-42 行附近，按实际内容）。

- [ ] **Step 4: 删 CLI 命令**

修改 `skills/ascend-c/tools/cannex_doc.py`：

a) 删除 docstring 中 `cannex_doc.py search_api <api_name>` 那一行（L12）
b) 删除 `cmd_search_api` 函数定义（L57-58）
c) 删除 `main()` 中 `elif cmd == "search_api" ...` 分支（L70）

- [ ] **Step 5: 删 webchat handler**

修改 `webchat/cannex_chat/worker/server.py:33-34`，删除：

```python
    "query_documentation": lambda p: doc_mod.api_search(
        query=p["query"], scope=p.get("scope", "all"), top_k=p.get("top_k", 3)),
```

- [ ] **Step 6: 验证残留**

```bash
grep -rn "api_search\|search_api\|cmd_search_api\|query_documentation" \
  lib/ skills/ tests/ webchat/ --include="*.py" --include="*.md" \
  | grep -v __pycache__
```

Expected: 仅 `CLAUDE.md` 中 §八 文档引用还有（这是规范本身，正确保留）；其余代码无残留。

- [ ] **Step 7: 跑全部测试**

```bash
pytest lib/cannex_knowledge/tests/ tests/ -v
```

Expected: 全部 PASS（包括 Task 1-3 新增/修改的测试，且不再有 `test_api_search_*`）

- [ ] **Step 8: webchat worker smoke test**

```bash
echo '{"id":1,"method":"query_documentation","params":{"query":"x"}}' | \
  python3 webchat/cannex_chat/worker/server.py
```

Expected: `{"id":1,"ok":false,"error":{"type":"UnknownMethod","message":"method 'query_documentation' not registered"}}`

- [ ] **Step 9: 提交**

```bash
git add lib/ tests/ skills/ webchat/
git commit -m "refactor(retriever): 废弃 api_search 反模式（keyword 打分代替 LLM 推理）

- 删除 lib/cannex_knowledge/retriever_doc.py 中 api_search 整段
- 删除对应单元测试与集成测试
- 删除 skills/ascend-c/tools/cannex_doc.py 的 search_api CLI 命令
- 删除 webchat worker 的 query_documentation handler
- 教学路由改由 LLM 在 list/meta/outline/pages 原子工具上 tree-walk 完成

依据：CLAUDE.md §八 PageIndex 使用约束"
```

---

## Task 5: 废弃 `api_context`（lib + CLI + 测试 + webchat handler）

**Files:**
- Modify: `lib/cannex_knowledge/retriever_repo.py:132-182`（删 `api_context` 整段）
- Modify: `tests/test_cannex_repo_api.py:29-30`（删 `test_api_context_returns_snippets` 及相关断言）
- Modify: `skills/ascend-c/tools/cannex_repo.py:64-65, 135`（删 `cmd_context` + argparse 分支）
- Modify: `webchat/cannex_chat/worker/server.py:35-36`（删 `query_code_repo` handler）

- [ ] **Step 1: 删 lib 实现**

打开 `lib/cannex_knowledge/retriever_repo.py`，删除 `def api_context(name: str, query: str) -> dict:` 整个函数（约 132-182 行）。

- [ ] **Step 2: 删项目级集成测试**

打开 `tests/test_cannex_repo_api.py`，删除 `test_api_context_returns_snippets` 函数及其依赖（约 29 行开始）。如果该测试是文件内唯一测试，**保留**文件骨架但移除该函数；若文件因此变空，**保留**文件（git 不喜欢空 .py 但保留也无害）。

- [ ] **Step 3: 删 CLI 命令**

修改 `skills/ascend-c/tools/cannex_repo.py`：

a) 删除 `cmd_context` 函数（L64-65）
b) 删除 argparse 中的 `context` 子命令定义（向上翻找含 `"context"` 字符串的 subparser 注册行）
c) 删除 `main()` 中 `elif args.cmd == "context": cmd_context(...)` 分支（L135）

如果文件顶部 docstring 提到 context 命令也一并删除。

- [ ] **Step 4: 删 webchat handler**

修改 `webchat/cannex_chat/worker/server.py:35-36`，删除：

```python
    "query_code_repo": lambda p: repo_mod.api_context(
        name=p.get("repo", "ops-transformer"), query=p["query"]),
```

- [ ] **Step 5: 验证残留**

```bash
grep -rn "api_context\|cmd_context\|query_code_repo" \
  lib/ skills/ tests/ webchat/ --include="*.py" --include="*.md" \
  | grep -v __pycache__
```

Expected: 仅 `CLAUDE.md §八` 与 `skills/ascend-c/references/codegraph-guide.md`（下一 Task 处理）；其余代码无残留。

- [ ] **Step 6: 跑全部测试**

```bash
pytest lib/cannex_knowledge/tests/ tests/ -v
```

Expected: 全部 PASS

- [ ] **Step 7: CLI smoke test**

```bash
python3 skills/ascend-c/tools/cannex_repo.py context ops-transformer FlashAttention 2>&1 || true
```

Expected: argparse 报错 "invalid choice: 'context'" 或类似——证明命令已下线。

- [ ] **Step 8: 提交**

```bash
git add lib/ tests/ skills/ webchat/
git commit -m "refactor(retriever): 废弃 api_context 反模式（SQL LIKE 模糊匹配代替 LLM 推理）

- 删除 lib/cannex_knowledge/retriever_repo.py 中 api_context 整段
- 删除对应集成测试
- 删除 skills/ascend-c/tools/cannex_repo.py 的 context CLI 命令
- 删除 webchat worker 的 query_code_repo handler
- 代码符号定位继续由 api_symbol（精确 lookup）承担

依据：CLAUDE.md §八 PageIndex 使用约束"
```

---

## Task 6: 清理 codegraph-guide.md 中的 api_context 引用

> SKILL.md / system_prompt.md 的等价替换由 Task 7 / Task 8 完成（量较大，独立成 Task）。本 Task 只处理 references/codegraph-guide.md。

**Files:**
- Modify: `skills/ascend-c/references/codegraph-guide.md:149, 170`

- [ ] **Step 1: 修 codegraph-guide.md**

读取 `skills/ascend-c/references/codegraph-guide.md` 全文，将原文：

> 以下 SQL 直接查询 `codegraph.db`。在 `cannex_repo.py` 中，`api_context()` 和 `api_symbol()` 已封装了常用模式。

改为：

> 以下 SQL 直接查询 `codegraph.db`。在 `cannex_repo.py` 中，`api_symbol()` 封装了精确符号 lookup；模糊匹配/关键词检索曾由 `api_context()` 提供，**已废弃**——参见 `CLAUDE.md §八`，跨文档 / 跨符号的检索由 LLM 在原子工具上 tree-walk 完成。

并删除原文中"LIKE 模糊匹配（当前 api_context 使用此模式）"的 SQL 示例段落（L170 周围），保留其它纯查询示例。

- [ ] **Step 2: 提交**

```bash
git add skills/ascend-c/references/codegraph-guide.md
git commit -m "docs(retriever): 清理 codegraph-guide 中 api_context 已废弃的引用"
```

---

## Task 7: SKILL.md 等价替换（删除废弃工具引用 + 替换为活工具序列）

**目标**：把 `skills/ascend-c/SKILL.md` 中所有对 `query_documentation` / `query_code_repo` / `cannex_repo.py context` 的引用替换为对应的活工具序列。**不重新设计教学策略**，只做等价替换。

**Files:**
- Modify: `skills/ascend-c/SKILL.md`

**预计修改点**（按行号从大到小逐项 Edit，避免行号偏移）：

| # | 位置 | 操作 |
|---|---|---|
| P1 | L249-256 来源标注表 | `code/symbol/context` → `code/symbol/read_file` |
| P2 | L214-215 CLI 映射表 | 删除 `query_documentation` 行 + `query_code_repo` 行 |
| P3 | L159 反模式三 | 替换"只走 grep 路径"段落 |
| P4 | L141-150 选择策略表 | 4 行涉及废弃工具改写 |
| P5 | L127-135 read_repo_file 何时用 | 删除 `query_code_repo 给了 excerpt` 行 |
| P6 | L90-99 query_code_repo 整节 | 整段删除 |
| P7 | L79-86 文档类 outline/pages 小节 | 删除"比 query_documentation 更便宜"和"通过 outline/search" |
| P8 | L74-77 query_documentation 整节 | 整段删除 |
| P9 | L52-58 双链路心智模型 | 改写"检索链路"行，删除 query_code_repo |
| P10 | L45 CLI 命令清单 | 删除 `cannex_repo.py context` 一行 |

- [ ] **Step 1: 应用 P1（来源标注表）**

```python
# Edit old_string (L249-256 区段)：
"代码原文（`code`/`symbol`/`context` 返回） | `[来源: ops-transformer/<路径>:<行号>]` | 直接引用"
# new_string:
"代码原文（`code`/`symbol`/`read_file` 返回） | `[来源: ops-transformer/<路径>:<行号>]` | 直接引用"
```

并在同段下方：

```python
# old_string:
"- `symbol` / `context` / `code` 返回代码原文 → 直接引用，无需加 ⚠️"
# new_string:
"- `symbol` / `code` / `read_file` 返回代码原文 → 直接引用，无需加 ⚠️"
```

- [ ] **Step 2: 应用 P2（CLI 映射表）**

删除附录 A 中两行表格：

```
| `query_documentation(query, scope)` | `python3 skills/ascend-c/tools/cannex_doc.py structure <doc-key>` 然后 `pages <doc-key> <range>` |
| `query_code_repo(query, repo)` | `python3 skills/ascend-c/tools/cannex_repo.py context <repo> "<query>"` |
```

- [ ] **Step 3: 应用 P3（反模式三：只走 grep 路径）**

```python
# old_string (L159 整行):
"❌ **\"只走 grep 路径\"**：直接 `query_code_repo(\"FlashAttention\")` 拿一堆 15 行零碎 excerpt 就回答——这种片段不够支撑深度解读，命中后必须用 `read_repo_file` 拉到完整上下文。"
# new_string:
"❌ **\"跳过结构直接读文件\"**：用户问\"FlashAttention 怎么实现\"时不先 `list_repo_samples(pattern=\"flash\")` 看精选样例、不先 `lookup_code_symbol(\"FlashAttentionScore\")` 探出 file_path，就盲猜路径调 `read_repo_file`——会读到无关文件或错过 arch35 新硬件实现。必须先在 samples / symbol 上推理定位，再 read_repo_file。"
```

- [ ] **Step 4: 应用 P4（选择策略表 4 行）**

```python
# old L141:
"| 概念解释（X 是什么 / 原理）| `query_documentation` | 想引用原文 → `read_document_pages` |"
# new:
"| 概念解释（X 是什么 / 原理）| `list_known_resources` 选文档 → `get_document_outline` 选章节 | 想引用原文 → `read_document_pages` |"
```

```python
# old L144:
"| \"X 在仓里有哪些调用模式\" | `query_code_repo` | 必要时 `read_repo_file` 读完整上下文 |"
# new:
"| \"X 在仓里有哪些调用模式\" | `lookup_code_symbol(\"X\")` 精确定位 + `list_repo_samples(pattern=\"X\")` 看教学样例 | 综合 file_path 后 `read_repo_file` 读完整上下文 |"
```

```python
# old L147:
"| 样例库未收录的算子 | `query_code_repo(pattern=X)` 探测路径 | 命中 → `read_repo_file` 读真实文件 |"
# new:
"| 样例库未收录的算子 | `list_repo_files` 扫目录 + `lookup_code_symbol` 探符号 | 综合后 `read_repo_file` 读真实文件 |"
```

```python
# old L150:
"| 报错/排查 | `query_documentation(scope=install)` | 再视情况查代码 |"
# new:
"| 报错/排查 | `list_known_resources` 选 install 类文档 → `get_document_outline` 看错误码章节 → `read_document_pages` | 再视情况查代码 |"
```

- [ ] **Step 5: 应用 P5（read_repo_file 段删除 query_code_repo 触发条件）**

```python
# old:
"  - `query_code_repo` 给了 excerpt 但你想看更大上下文\n"
# new: 空字符串（删除该行）
```

- [ ] **Step 6: 应用 P6（删除 query_code_repo 整节，L90-99）**

```python
# old_string: 整个 #### `query_code_repo(query, repo?)` 小节内容（从标题行到下一节标题前的所有行）
# new_string: 空字符串
```

具体边界：从 `#### `query_code_repo(query, repo?)`` 起，到 `#### `lookup_code_symbol(symbol, repo?, kind?)`` 前一空行止，全部删除。

- [ ] **Step 7: 应用 P7（query_documentation 段的下游引用清理）**

```python
# old (L82):
"- **比 query_documentation 更便宜**——先看 ToC 再决定要不要读原文"
# new:
"- **何时用**：用户问概念/原理/API 含义/安装步骤/调优思路时——先用 `list_known_resources` 选定文档，再用 outline 看章节，决定要读哪几页"
```

```python
# old (L86):
"- **何时用**：通过 outline / search 已经知道答案在哪些页，需要拿到逐字原文用于引用"
# new:
"- **何时用**：通过 outline 已经定位到目标章节的 page 范围，需要拿到逐字原文用于引用"
```

- [ ] **Step 8: 应用 P8（删除 query_documentation 整节，L74-77）**

```python
# old_string: 整个 #### `query_documentation(query, scope?)` 小节内容
# new_string: 空字符串
```

具体边界：从 `#### `query_documentation(query, scope?)`` 起，到 `#### `get_document_outline(doc_name, max_depth?)`` 前一空行止。

- [ ] **Step 9: 应用 P9（双链路心智模型改写，L52-58）**

```python
# old:
"你有 11 个语义化检索动作，分为「概览」「文档」「代码」三组。根据用户意图选择合适的动作（可多次调用、跨动作组合）。\n\n**代码检索的两条互补链路**（重要心智模型）：\n- **教学链路**（人工策划）：`list_repo_samples` → `read_sample_code` —— 走 samples.yaml 标注的精选入口文件，结构化、有教学要点，但只覆盖被人工标注的样例\n- **检索链路**（CodeGraph 全覆盖）：`query_code_repo` / `lookup_code_symbol` → `read_repo_file` —— 走 CodeGraph 索引，覆盖所有源文件，但需要模型自己拼装上下文\n\n**两条链路并行使用，不是替代关系**。教学链路命中时质量更高；未命中或要看 samples 没标的更深文件时，必须用检索链路兜底。"
# new:
"你有 9 个语义化检索动作，分为「概览」「文档」「代码」三组。根据用户意图选择合适的动作（可多次调用、跨动作组合）。\n\n**代码检索的两条互补链路**（重要心智模型）：\n- **教学链路**（人工策划）：`list_repo_samples` → `read_sample_code` —— 走 samples.yaml 标注的精选入口文件，结构化、有教学要点，但只覆盖被人工标注的样例\n- **精确链路**（CodeGraph 全覆盖）：`lookup_code_symbol` → `read_repo_file` —— 走 CodeGraph 精确符号定位 + 自由 Read，覆盖所有源文件，由模型在 file_path 上推理决定要读什么\n\n**两条链路并行使用，不是替代关系**。教学链路命中时质量更高；未命中或要看 samples 没标的更深文件时，必须用精确链路兜底。"
```

- [ ] **Step 10: 应用 P10（CLI 命令清单，L45）**

```python
# old:
"python3 skills/ascend-c/tools/cannex_repo.py context ops-transformer \"<英文查询>\"\n"
# new: 空字符串（删除该行）
```

- [ ] **Step 11: 验证残留**

```bash
grep -n "query_documentation\|query_code_repo\|cannex_repo.py context\|api_search\|api_context" \
  skills/ascend-c/SKILL.md
```

Expected: 0 行输出。

- [ ] **Step 12: 通读 smoke check**

```bash
wc -l skills/ascend-c/SKILL.md
```

Expected: 行数比修改前少 25-40 行（删除了 2 个工具定义段 + 路由表 4 行 + CLI 映射 2 行）。

打开文件目测：
- §一 CLI 命令清单（L29-46 附近）只剩活命令
- §检索工作流 开头说"9 个动作"
- 文档类只有 `get_document_outline` + `read_document_pages`
- 代码类只有 `lookup_code_symbol` / `list_repo_samples` / `read_sample_code` / `list_repo_files` / `read_repo_file`
- 选择策略表无废弃工具名

- [ ] **Step 13: 提交**

```bash
git add skills/ascend-c/SKILL.md
git commit -m "refactor(skill): SKILL.md 等价替换废弃工具引用为 tree-walk 序列

- 删除 query_documentation / query_code_repo 工具定义段
- 路由表 4 行改写为 list/outline/pages 与 symbol/samples/read_file 组合
- 反模式举例从'只走 grep 路径'替换为'跳过结构直接读文件'
- 附录 A CLI 映射表删除 2 行废弃命令
- 来源标注表 context → read_file
- 双链路心智模型：'检索链路'→'精确链路'，去掉 query_code_repo

依据：CLAUDE.md §八 PageIndex 使用约束"
```

---

## Task 8: webchat system_prompt.md 等价替换

**目标**：`webchat/cannex_chat/prompts/system_prompt.md` 与 SKILL.md 内容高度重叠（约 70% 相同段落），但**不含** §一 CLI 命令清单和附录 A CLI 映射表。本 Task 复用 Task 7 的等价替换规则。

**Files:**
- Modify: `webchat/cannex_chat/prompts/system_prompt.md`

**预计修改点**（按行号从大到小逐项 Edit）：

| # | 位置（system_prompt.md 行号）| 操作 | 对应 Task 7 |
|---|---|---|---|
| P1 | L128 反模式三 | 替换"只走 grep 路径"段落 | = Task 7 P3 |
| P2 | L110-119 选择策略表 | 4 行涉及废弃工具改写 | = Task 7 P4 |
| P3 | L96-104 read_repo_file 段 | 删除 `query_code_repo 给了 excerpt` 行 | = Task 7 P5 |
| P4 | L59-67 query_code_repo 整节 | 整段删除 | = Task 7 P6 |
| P5 | L48-55 outline/pages 下游引用 | 删除"比 query_documentation 更便宜"和"通过 outline/search" | = Task 7 P7 |
| P6 | L43-46 query_documentation 整节 | 整段删除 | = Task 7 P8 |
| P7 | L21-27 双链路心智模型 | 改写"检索链路"，删除 query_code_repo | = Task 7 P9 |

- [ ] **Step 1: 应用 P1（反模式三）**

替换 `webchat/cannex_chat/prompts/system_prompt.md:128` 整行——同 Task 7 Step 3 的 old/new 字符串。

- [ ] **Step 2: 应用 P2（选择策略表 4 行）**

替换 `webchat/cannex_chat/prompts/system_prompt.md:110/113/116/119`——同 Task 7 Step 4 的 4 组 old/new。

- [ ] **Step 3: 应用 P3（删除 query_code_repo 触发条件）**

删除 `webchat/cannex_chat/prompts/system_prompt.md:100` 的 `query_code_repo 给了 excerpt...` 行——同 Task 7 Step 5。

- [ ] **Step 4: 应用 P4（删除 query_code_repo 整节）**

从 `#### `query_code_repo(query, repo?)`` 起到 `#### `lookup_code_symbol(...)`` 前一空行止，全部删除——同 Task 7 Step 6。

- [ ] **Step 5: 应用 P5（query_documentation 下游清理）**

替换 L51 与 L55 两行——同 Task 7 Step 7 的 2 组 old/new。

- [ ] **Step 6: 应用 P6（删除 query_documentation 整节）**

从 `#### `query_documentation(query, scope?)`` 起到 `#### `get_document_outline(...)`` 前一空行止——同 Task 7 Step 8。

- [ ] **Step 7: 应用 P7（双链路心智模型）**

替换 L21-27 整段——同 Task 7 Step 9 的 old/new。注意 system_prompt.md 没有附录 A 和 §一 CLI 命令清单，所以 Task 7 的 P2 / P10 不适用。

- [ ] **Step 8: 验证残留**

```bash
grep -n "query_documentation\|query_code_repo" webchat/cannex_chat/prompts/system_prompt.md
```

Expected: 0 行输出。

- [ ] **Step 9: 通读 smoke check**

```bash
wc -l webchat/cannex_chat/prompts/system_prompt.md
```

Expected: 行数比修改前少 20-30 行。

- [ ] **Step 10: 提交**

```bash
git add webchat/cannex_chat/prompts/system_prompt.md
git commit -m "refactor(webchat): system_prompt.md 等价替换废弃工具引用为 tree-walk 序列

- 删除 query_documentation / query_code_repo 工具定义段
- 路由表 4 行改写为 list/outline/pages 与 symbol/samples/read_file 组合
- 反模式举例替换为'跳过结构直接读文件'
- 双链路心智模型 query_code_repo → lookup_code_symbol

依据：CLAUDE.md §八 PageIndex 使用约束（与 Task 7 SKILL.md 改动等价镜像）"
```

---

## Task 9: 端到端验证

- [ ] **Step 1: 全量测试**

```bash
pytest lib/cannex_knowledge/tests/ tests/ -v 2>&1 | tee /tmp/final.log
```

Expected: 全部 PASS，且：
- 包含新测试 `test_api_meta_returns_single_doc_metadata`
- `test_api_list_returns_docs` / `test_api_outline_returns_structure` 含新断言
- 已无 `test_api_search_*` / `test_api_context_*`

- [ ] **Step 2: doc CLI smoke test 链路**

```bash
DOC_ID=$(python3 skills/ascend-c/tools/cannex_doc.py list | python3 -c 'import json,sys; print(json.load(sys.stdin)["docs"][0]["doc_id"])')
python3 skills/ascend-c/tools/cannex_doc.py meta "$DOC_ID" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("doc_description"), "no doc_description"; print("OK meta")'
python3 skills/ascend-c/tools/cannex_doc.py structure "$DOC_ID" | python3 -c 'import json,sys; d=json.load(sys.stdin); n=d["outline"][0]; assert "summary" in n, "no summary in outline"; print("OK structure")'
python3 skills/ascend-c/tools/cannex_doc.py pages "$DOC_ID" "1-2" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("pages"), "no pages returned"; print("OK pages")'
```

Expected: 三行 OK 输出，无 traceback。

- [ ] **Step 3: repo CLI smoke test**

```bash
REPO=$(python3 skills/ascend-c/tools/cannex_repo.py list | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d[0]["name"] if isinstance(d, list) else d["repos"][0]["name"])')
python3 skills/ascend-c/tools/cannex_repo.py card "$REPO" >/dev/null && echo "OK card"
python3 skills/ascend-c/tools/cannex_repo.py context "$REPO" foo 2>&1 | grep -q "invalid choice\|unrecognized" && echo "OK context disabled" || echo "FAIL: context 命令未下线"
```

Expected: `OK card` + `OK context disabled`

- [ ] **Step 4: webchat worker smoke test**

```bash
python3 -c "
import json, subprocess
p = subprocess.Popen(['python3', 'webchat/cannex_chat/worker/server.py'],
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
out, _ = p.communicate('\n'.join([
    json.dumps({'id':1,'method':'query_documentation','params':{'query':'x'}}),
    json.dumps({'id':2,'method':'query_code_repo','params':{'query':'x'}}),
    json.dumps({'id':3,'method':'list_known_resources','params':{}}),
]))
for line in out.strip().split('\n'):
    print(line)
"
```

Expected:
- id=1: `ok:false`, `UnknownMethod`
- id=2: `ok:false`, `UnknownMethod`
- id=3: `ok:true`, `docs` 列表（且每个文档含 `doc_description`）

- [ ] **Step 5: 终极 grep（活代码 + 活 prompt 残留扫描）**

```bash
grep -rn "api_search\|api_context\|search_api\|query_documentation\|query_code_repo\|cmd_context\|cmd_search_api" \
  /Users/justbin/Desktop/CannEx \
  --include="*.py" --include="*.md" --include="*.yaml" \
  | grep -v __pycache__ | grep -v ".venv" \
  | grep -v "docs/superpowers/plans/" \
  | grep -v "docs/specs/2026-05-23" \
  | grep -v "CLAUDE.md"
```

Expected: 0 行输出。**所有活代码、活 prompt 都不再引用废弃工具/API**。仅历史 plan / spec / CLAUDE.md §八 的引用被排除。

- [ ] **Step 6: webchat 教学路径 smoke test（手工）**

```bash
cd webchat/cannex-chat && source .venv/bin/activate
chainlit run app.py -w &
CHAINLIT_PID=$!
sleep 5
# 浏览器手工测：
# 1) 打开 http://localhost:8000
# 2) 问："Ascend C 算子开发的内存层级有几种？"
# 3) 观察 worker 日志（tail -f logs/...）：
#    - 期望 LLM 调用顺序：list_known_resources → get_document_outline → read_document_pages
#    - 不应出现 query_documentation / query_code_repo（这些 method 已下线）
#    - 不应出现 UnknownMethod 错误（说明 LLM 没在 prompt 引导下尝试调用死工具）
# 4) 验证完成 kill $CHAINLIT_PID
```

Expected: LLM 自主走 list → outline → pages 的 tree-walk 路径，无废弃工具调用尝试，回答 grounded 在原文。**这是验证 prompt 等价替换是否成功的核心检验**。

- [ ] **Step 7: Skill 教学路径 smoke test（手工，需在 Claude Code 内）**

在 Claude Code 中重启会话或 `/clear`，确保 ascend-c skill 加载新版 SKILL.md。

测试 prompt："`/ascend-c` Ascend C 算子开发的内存层级有几种？"

观察 Bash 工具调用：
- 期望：`cannex_doc.py list` → `cannex_doc.py structure ...` → `cannex_doc.py pages ...`
- 不应出现：`cannex_doc.py search_api` / `cannex_repo.py context`

Expected: 同 Step 6，Skill 侧也走纯 tree-walk。

- [ ] **Step 8: plan 完成总结**

不需要额外 commit（plan 文件本身已在 git 中，所有 Task 已分别 commit）。可顺手做的清理：把 `CLAUDE.md §八` 的"已知反模式"和"已知燃料缺位"两节标注为 `✅ 已修复 (本计划 Task 1-8)` 或直接删除。**不在本计划必做范围**，下次顺手做即可。

---

## 完成后的项目状态

**lib/cannex_knowledge/retriever_doc.py 暴露**：`api_list` / `api_meta` / `api_outline` / `api_pages`（4 个原子能力，对齐 PageIndex 官方 demo 范式）

**lib/cannex_knowledge/retriever_repo.py 暴露**：`api_list` / `api_card` / `api_overview` / `api_outline`(N/A) / `api_symbol`（精确）/ `api_list_samples` / `api_list_files` / `api_read_file` / `api_read_sample`（8 个原子能力，无任何排序/打分）

**Webchat worker 暴露**：10 个原子 tool（删除 query_documentation / query_code_repo 后剩余），全部为 list / meta / outline / lookup / read 类型，无 search 类。

**CLAUDE.md §八 与代码完全一致**：表里的"已知反模式"与"已知燃料缺位"两节，本计划完成后应被清空（届时把 §八 的这两节标注"✅ 已修复 (commit hash)"或直接删除）——这是本计划之外的小尾巴，建议下次顺手做。

---

## 非任务说明：webchat 教学 prompt 的二次效应

`worker/server.py` 删除两个 handler 后，**LLM 端**可能仍在 system prompt 里被告知"你有 query_documentation 工具"——Task 6 Step 3 已处理这部分，但 prompt 重写本身**不在本计划深度优化范围**。本计划只确保 prompt 不再宣传废弃工具；优化"教 LLM 走 tree-walk"的 prompt 工程是独立工作，需要单独 brainstorm。

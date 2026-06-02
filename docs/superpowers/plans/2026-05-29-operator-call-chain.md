# 算子完整调用链 / 影响面分析 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 在 lib 层实现"图谱主干 + 接缝补全 + ripgrep 召回网"的算子完整调用链(`api_call_chain`)与改动影响面(`api_impact_surface`)分析，并接通 webchat / Phase 1 CLI。

**Architecture:** lib 做确定性工作(图谱 BFS、正则接缝预标、ripgrep 召回、coverage 计数)，零 LLM token；agent 做语义工作(读接缝 span 展开宏/模板、对 ripgrep 候选分类)。默认 token 优先保守，靠 read_budget 参数 escalate 换完整度。

**Tech Stack:** Python 3.11，pytest(`asyncio_mode=auto`)，CodeGraph CLI(经 `codegraph_client`)，ripgrep(`rg --json`)。

**Spec:** `docs/superpowers/specs/2026-05-29-operator-call-chain-design.md`

**依赖契约(实施前已校准)：**
- `_envelope(source_type, data, evidence=None, error=None, fallback_hint=None)` → `{source_type, evidence, data, error, fallback_hint}`
- `api_search_symbol` → `data={"matches":[{...,"file_path","start_line","end_line"?,"name","score"}]}`
- `api_callees` → `data={"symbol":..,"callees":[{"name","kind","file_path","start_line"}]}`
- `api_callers` → `data={"symbol":..,"callers":[同上]}`
- `api_read_file` → `{"content","total_lines","start_line","end_line","truncated",...}` 或 `{"error"}`
- `codegraph_client._get_repo_path(repo)` → 绝对 `Path` 或 `None`

---

### Task 1: 可靠性 spike（决策闸门，先行）

**Files:**
- Create: `scripts/call_chain_recall_spike.py`
- Create: `reports/call-chain-spike-2026-05-29.md`（人工填测量结果）

**目的：** 在写任何生产代码前，量化裸 codegraph 传递遍历的 recall 缺口，决定方案 C 能否交付。**不达标（裸图谱已 ≥90% 且接缝补全无法显著提升）→ 停，退回方案 B（仅 L1）。**

- [x] **Step 1: 写 spike 脚本**

```python
# scripts/call_chain_recall_spike.py
"""裸 codegraph 传递 callees recall 测量。对 3 个算子，从 samples.yaml entry 根符号出发，
图谱 BFS 到 depth=4，打印调用树 + 每层 callees 为空的"可疑叶子"，供人工对照源码评估漏了多少。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from cannex_knowledge import retriever_repo as r

OPERATORS = [
    ("ops-transformer", "FlashAttentionScore"),
    ("ops-transformer", "FlashAttentionScoreKernelTrain"),
    ("ops-transformer", "Process"),
]

def walk(repo, sym, depth, seen, maxd=4):
    if depth > maxd or sym in seen:
        return
    seen.add(sym)
    res = r.api_callees(repo, sym, limit=30)
    callees = (res.get("data") or {}).get("callees", [])
    flag = "  <-- 可疑叶子(图谱空)" if not callees and any(
        k in sym for k in ("Process", "Init", "Compute", "Launch")) else ""
    print("  " * depth + f"{sym} (callees={len(callees)}){flag}")
    for c in callees:
        walk(repo, c.get("name", "?"), depth + 1, seen, maxd)

if __name__ == "__main__":
    for repo, root in OPERATORS:
        print(f"\n===== {repo} :: {root} =====")
        walk(repo, root, 0, set())
```

- [x] **Step 2: 运行并人工评估**

Run: `python3 scripts/call_chain_recall_spike.py`
Expected: 打印 3 棵调用树，标出"可疑叶子"。人工对照源码估算：每棵树漏掉的真实调用占比、漏掉的是否集中在宏/模板处。

- [x] **Step 3: 记录结论到报告，做闸门决策**

把测量写入 `reports/call-chain-spike-2026-05-29.md`：裸图谱 recall 估值、漏点是否宏/模板主导、接缝补全的预期收益。**结论=继续 → 进 Task 2；结论=不值得 → 停止并通知 owner。**

- [x] **Step 4: Commit**

```bash
git add scripts/call_chain_recall_spike.py reports/call-chain-spike-2026-05-29.md
git commit -m "chore(spike): 算子调用链裸 codegraph recall 测量 + 闸门结论"
```

---

### Task 2: seam.py — 接缝正则检测（纯函数）

**Files:**
- Create: `lib/cannex_knowledge/seam.py`
- Test: `lib/cannex_knowledge/tests/test_seam.py`

- [x] **Step 1: 写失败测试**

```python
# lib/cannex_knowledge/tests/test_seam.py
from cannex_knowledge import seam


def test_detects_macro_call():
    src = "INVOKE_FA_GENERAL_OP_IMPL(op, tiling);\nREGIST_MATMUL_OBJ(&pipe, ws);"
    out = seam.detect_seams(src)
    tokens = {(s["kind"], s["token"]) for s in out}
    assert ("macro", "INVOKE_FA_GENERAL_OP_IMPL") in tokens
    assert ("macro", "REGIST_MATMUL_OBJ") in tokens


def test_detects_template_call():
    src = "FlashAttentionScoreKernelTrain<CubeBlockType, VecBlockType>::Process();"
    out = seam.detect_seams(src)
    assert any(s["kind"] == "template" for s in out)


def test_detects_std_conditional():
    src = "using T = typename std::conditional<g_coreType == AIC, A, B>::type;"
    out = seam.detect_seams(src)
    assert any(s["token"] == "std::conditional" for s in out)


def test_excludes_false_positive_allcaps():
    src = "if (ptr == NULL) return TRUE;"
    assert seam.detect_seams(src) == []


def test_dedups_repeated_macro():
    src = "FOO_BAR(a);\nFOO_BAR(b);\nFOO_BAR(c);"
    out = [s for s in seam.detect_seams(src) if s["kind"] == "macro"]
    assert len(out) == 1


def test_empty_source():
    assert seam.detect_seams("") == []
```

- [x] **Step 2: 运行验证失败**

Run: `python3 -m pytest lib/cannex_knowledge/tests/test_seam.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cannex_knowledge.seam'`

- [x] **Step 3: 实现 seam.py**

```python
# lib/cannex_knowledge/seam.py
"""源码接缝(seam)正则检测：识别图谱会失明的宏调用 / 模板实例化点。

纯函数、零依赖。供 retriever_repo.api_call_chain 在 lib 层零 LLM token 预标接缝。
检测 = 语法启发式，不保证零误报；agent 读 span 时做语义确认。
"""
import re

# 全大写标识符(>=3字符) 紧跟 ( ：CANN 宏调用的强信号
_MACRO_CALL = re.compile(r"\b([A-Z][A-Z0-9_]{2,})\s*\(")
# 模板实例化调用：Foo<...>::Bar
_TEMPLATE_CALL = re.compile(r"\b([A-Za-z_]\w*\s*<[^;{}\n]*>\s*::\s*\w+)")
# 模板分发关键字（CANN arch35 双核分离常用）
_TEMPLATE_KEYWORDS = ("std::conditional", "std::enable_if")
# 全大写但非宏的常见误报
_MACRO_FALSE_POSITIVES = frozenset({"NULL", "TRUE", "FALSE", "AIC", "AIV"})


def detect_seams(source: str) -> list[dict]:
    """扫描源码片段，返回去重后的接缝列表 [{kind, token}]。kind ∈ {macro, template}。"""
    seams: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def _add(kind: str, token: str):
        key = (kind, token)
        if key not in seen:
            seen.add(key)
            seams.append({"kind": kind, "token": token})

    for m in _MACRO_CALL.finditer(source):
        name = m.group(1)
        if name not in _MACRO_FALSE_POSITIVES:
            _add("macro", name)
    for m in _TEMPLATE_CALL.finditer(source):
        _add("template", re.sub(r"\s+", "", m.group(1)))
    for kw in _TEMPLATE_KEYWORDS:
        if kw in source:
            _add("template", kw)
    return seams
```

- [x] **Step 4: 运行验证通过**

Run: `python3 -m pytest lib/cannex_knowledge/tests/test_seam.py -v`
Expected: PASS（6 passed）

- [x] **Step 5: Commit**

```bash
git add lib/cannex_knowledge/seam.py lib/cannex_knowledge/tests/test_seam.py
git commit -m "feat(lib): seam.py 接缝正则检测（宏/模板，图谱盲区预标）"
```

---

### Task 3: ripgrep_client.py — 文本引用召回

**Files:**
- Create: `lib/cannex_knowledge/ripgrep_client.py`
- Test: `lib/cannex_knowledge/tests/test_ripgrep_client.py`

- [x] **Step 1: 写失败测试**

```python
# lib/cannex_knowledge/tests/test_ripgrep_client.py
import subprocess
from cannex_knowledge import ripgrep_client as rgc


def _fake_rg_output():
    import json
    lines = [
        {"type": "match", "data": {"path": {"text": "/repo/a.cpp"},
         "lines": {"text": "REGIST_MATMUL_OBJ(x);\n"}, "line_number": 12}},
        {"type": "begin", "data": {"path": {"text": "/repo/a.cpp"}}},
        {"type": "match", "data": {"path": {"text": "/repo/b.h"},
         "lines": {"text": "  foo(Bar);\n"}, "line_number": 88}},
    ]
    return "\n".join(json.dumps(x) for x in lines)


def test_find_refs_parses_matches(monkeypatch):
    def fake_run(cmd, **kw):
        class R:
            returncode = 0
            stdout = _fake_rg_output()
            stderr = ""
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run)
    out = rgc.find_refs("/repo", "REGIST_MATMUL_OBJ")
    assert out["error"] is None
    assert len(out["refs"]) == 2
    assert out["refs"][0] == {"file_path": "/repo/a.cpp", "line": 12,
                              "text": "REGIST_MATMUL_OBJ(x);"}


def test_find_refs_rg_missing(monkeypatch):
    def fake_run(cmd, **kw):
        raise FileNotFoundError("rg")
    monkeypatch.setattr(subprocess, "run", fake_run)
    out = rgc.find_refs("/repo", "X")
    assert out["refs"] == []
    assert "not found" in out["error"]


def test_find_refs_no_match_is_not_error(monkeypatch):
    def fake_run(cmd, **kw):
        class R:
            returncode = 1  # rg 无命中时退出码 1，非错误
            stdout = ""
            stderr = ""
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run)
    out = rgc.find_refs("/repo", "X")
    assert out == {"refs": [], "error": None}
```

- [x] **Step 2: 运行验证失败**

Run: `python3 -m pytest lib/cannex_knowledge/tests/test_ripgrep_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [x] **Step 3: 实现 ripgrep_client.py**

```python
# lib/cannex_knowledge/ripgrep_client.py
"""ripgrep 包装层：全仓文本引用召回，作图谱向上反查(impact)的召回兜底网。

零 LLM token。rg 无命中时退出码为 1，不视为错误。
"""
import json
import shutil
import subprocess


def _resolve_rg() -> str:
    return shutil.which("rg") or "rg"


def find_refs(repo_path: str, symbol: str, timeout: int = 10) -> dict:
    """rg -w <symbol> <repo_path>，返回 {refs:[{file_path,line,text}], error}。"""
    try:
        r = subprocess.run(
            [_resolve_rg(), "--json", "-w", "--", symbol, str(repo_path)],
            capture_output=True, timeout=timeout, text=True,
        )
    except FileNotFoundError:
        return {"refs": [], "error": "ripgrep (rg) not found in PATH"}
    except subprocess.TimeoutExpired:
        return {"refs": [], "error": f"ripgrep timeout after {timeout}s"}

    refs = []
    for line in r.stdout.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "match":
            continue
        d = obj["data"]
        refs.append({
            "file_path": d["path"].get("text", ""),
            "line": d.get("line_number"),
            "text": d["lines"].get("text", "").rstrip("\n"),
        })
    return {"refs": refs, "error": None}
```

- [x] **Step 4: 运行验证通过**

Run: `python3 -m pytest lib/cannex_knowledge/tests/test_ripgrep_client.py -v`
Expected: PASS（3 passed）

- [x] **Step 5: Commit**

```bash
git add lib/cannex_knowledge/ripgrep_client.py lib/cannex_knowledge/tests/test_ripgrep_client.py
git commit -m "feat(lib): ripgrep_client 文本引用召回（impact 召回兜底网）"
```

---

### Task 4: api_call_chain — 向下调用链（图谱 BFS + 入口接缝优先 + 根消歧）

> **spike 修正（2026-05-29，见 `reports/call-chain-spike-2026-05-29.md`）：**
> 实测裸图谱"入口致命失明、内部极丰富"——`FlashAttentionScore`(算子名)→3 节点即死、`Process`→181 节点深树。故本 Task 重心调整：
> 1. **入口接缝优先**：root 永远扫源码补缝（priority="entry"）；内部可疑叶子降为次要（仅占 6.6%，priority="interior"），预算优先给入口。
> 2. **根符号消歧**：`Process` 等泛名对应多节点，输出 `root_candidates` + `root_ambiguous`，透明化遍历的是哪个节点。
> 3. **算子名→kernel 入口的桥接不在本函数**：算子自然名解析到 host 死链，该桥接由 agent 经 samples.yaml 完成（见 Task 8 playbook）。本函数只对"传入的符号"做图谱遍历 + 接缝预标。

**Files:**
- Modify: `lib/cannex_knowledge/retriever_repo.py`（在 `api_explore_symbols` 后追加）
- Test: `lib/cannex_knowledge/tests/test_retriever_repo.py`（追加）

- [x] **Step 1: 写失败测试**

```python
# 追加到 lib/cannex_knowledge/tests/test_retriever_repo.py
def _stub_search_single(monkeypatch, file_path="root.cpp", start=1, end=40):
    monkeypatch.setattr(repo_mod, "api_search_symbol",
        lambda name, sym, kind=None, limit=10: {"data": {"matches": [
            {"name": sym, "file_path": file_path, "start_line": start, "end_line": end,
             "score": 100}]}, "error": None})


def test_api_call_chain_graph_only(monkeypatch):
    """全是普通方法调用：树全 graph，零接缝（root 读源码但无宏/模板）。"""
    graph = {"A": ["B", "C"], "B": [], "C": []}
    monkeypatch.setattr(repo_mod, "api_callees",
        lambda name, sym, limit=20: {"data": {"callees": [
            {"name": n, "file_path": f"{n}.h", "start_line": 1} for n in graph.get(sym, [])]},
            "error": None})
    _stub_search_single(monkeypatch)
    monkeypatch.setattr(repo_mod, "api_read_file",
        lambda *a, **k: {"content": "return b + c;", "error": None})

    res = repo_mod.api_call_chain("ops-transformer", "A", max_depth=3, read_budget=8)
    tree = res["data"]["tree"]
    assert tree["symbol"] == "A"
    assert {c["symbol"] for c in tree["children"]} == {"B", "C"}
    assert res["data"]["coverage"]["seams_entry"] == 0
    assert res["data"]["coverage"]["seams_interior"] == 0


def test_api_call_chain_entry_seam_priority(monkeypatch):
    """root 是死入口（callees 空）+ 源码含宏 → 标 entry_seam，priority=entry。"""
    monkeypatch.setattr(repo_mod, "api_callees",
        lambda name, sym, limit=20: {"data": {"callees": []}, "error": None})
    _stub_search_single(monkeypatch, file_path="entry.cpp", start=10, end=30)
    monkeypatch.setattr(repo_mod, "api_read_file",
        lambda *a, **k: {"content": "INVOKE_FA_GENERAL_OP_IMPL(op, tiling);", "error": None})

    res = repo_mod.api_call_chain("ops-transformer", "FlashAttentionScore", max_depth=2, read_budget=8)
    seams = res["data"]["seams"]
    assert any(s["token"] == "INVOKE_FA_GENERAL_OP_IMPL" and s["priority"] == "entry" for s in seams)
    assert res["data"]["tree"]["provenance"] == "entry_seam"
    assert res["data"]["coverage"]["seams_entry"] == 1
    assert res["fallback_hint"]


def test_api_call_chain_surfaces_root_ambiguity(monkeypatch):
    """root 泛名解析到多个不同文件 → root_ambiguous=True + root_candidates 列出。"""
    monkeypatch.setattr(repo_mod, "api_callees",
        lambda name, sym, limit=20: {"data": {"callees": []}, "error": None})
    monkeypatch.setattr(repo_mod, "api_search_symbol",
        lambda name, sym, kind=None, limit=10: {"data": {"matches": [
            {"name": "Process", "file_path": "a.h", "start_line": 1, "score": 113},
            {"name": "Process", "file_path": "b.h", "start_line": 9, "score": 113}]}, "error": None})
    monkeypatch.setattr(repo_mod, "api_read_file",
        lambda *a, **k: {"content": "x();", "error": None})

    res = repo_mod.api_call_chain("ops-transformer", "Process", max_depth=1, read_budget=4)
    assert res["data"]["coverage"]["root_ambiguous"] is True
    assert len(res["data"]["root_candidates"]) == 2


def test_api_call_chain_respects_read_budget(monkeypatch):
    """read_budget=0：不读源码、不产生 seam（连入口都不扫）。"""
    monkeypatch.setattr(repo_mod, "api_callees",
        lambda n, s, limit=20: {"data": {"callees": []}, "error": None})
    _stub_search_single(monkeypatch)
    called = {"reads": 0}
    def fake_read(*a, **k):
        called["reads"] += 1
        return {"content": "FOO_BAR(x);", "error": None}
    monkeypatch.setattr(repo_mod, "api_read_file", fake_read)

    res = repo_mod.api_call_chain("ops-transformer", "Init", max_depth=1, read_budget=0)
    assert called["reads"] == 0
    assert res["data"]["coverage"]["reads_used"] == 0
```

- [x] **Step 2: 运行验证失败**

Run: `python3 -m pytest lib/cannex_knowledge/tests/test_retriever_repo.py -k call_chain -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'api_call_chain'`

- [x] **Step 3: 实现 api_call_chain**

在 `retriever_repo.py` 顶部 import 区加 `from . import seam as _seam` 和 `import re as _re`；在文件末尾追加：

```python
# ── 完整调用链：图谱主干 + 入口接缝优先 + 根消歧（向下 callees）──────────────────
_WORK_DOER_RE = _re.compile(r"(Process|Init|Compute|Launch|Execute|Run|Kernel|Entry)", _re.IGNORECASE)
_CALL_CHAIN_CALLEE_LIMIT = 30
_SEAM_SCAN_SPAN = 120  # 读源码体的默认行窗


def _scan_for_seams(name: str, symbol: str, budget: dict, priority: str) -> list:
    """读 symbol 源码体区间做接缝正则扫描；预算耗尽则跳过。修改 budget['used']。"""
    if budget["used"] >= budget["budget"]:
        return []
    matches = (api_search_symbol(name, symbol, limit=1).get("data") or {}).get("matches", [])
    if not matches:
        return []
    m = matches[0]
    fp, s = m.get("file_path"), m.get("start_line")
    if not fp or not s:
        return []
    e = m.get("end_line") or (s + _SEAM_SCAN_SPAN - 1)
    src = api_read_file(name, fp, start_line=s, end_line=e)
    budget["used"] += 1
    if src.get("error"):
        return []
    return [{**sm, "at_symbol": symbol, "file_path": fp, "span": [s, e], "priority": priority}
            for sm in _seam.detect_seams(src.get("content", ""))]


def api_call_chain(name: str, root: str, max_depth: int = 4,
                   read_budget: int = 8) -> dict:
    """算子完整调用链：图谱 BFS 主干 + 入口接缝优先补全 + 根符号消歧。

    spike 实证：图谱"入口致命失明、内部极丰富"。故 root 永远优先扫接缝(priority=entry)，
    内部可疑叶子次之(priority=interior)。算子名→kernel 入口的桥接由 agent 经 samples.yaml 完成。

    lib 产出"骨架树 + seams + 各 seam 源码区间 + coverage + root_candidates"；
    agent 负责读 seam span、展开宏/模板、回灌本函数（迭代）。
    """
    # 根符号消歧：surface 解析到哪些节点、是否歧义（不强行替 codegraph 按名遍历做范围限定）
    root_matches = (api_search_symbol(name, root, limit=5).get("data") or {}).get("matches", [])
    root_candidates = [{"name": m.get("name"), "file_path": m.get("file_path"),
                        "start_line": m.get("start_line"), "score": m.get("score")}
                       for m in root_matches]
    root_ambiguous = len({c["file_path"] for c in root_candidates if c.get("file_path")}) > 1

    visited: set = set()
    seams: list = []
    budget = {"used": 0, "budget": read_budget}

    def build(symbol: str, depth: int, is_root: bool = False) -> dict:
        if symbol in visited:
            return {"symbol": symbol, "provenance": "graph", "revisit": True, "children": []}
        if depth > max_depth:
            return {"symbol": symbol, "provenance": "cut", "children": []}
        visited.add(symbol)
        callees = (api_callees(name, symbol, limit=_CALL_CHAIN_CALLEE_LIMIT)
                   .get("data") or {}).get("callees", [])
        node = {"symbol": symbol, "provenance": "graph", "children": []}
        is_suspect = not callees and bool(_WORK_DOER_RE.search(symbol))
        if is_root or is_suspect:
            found = _scan_for_seams(name, symbol, budget,
                                    "entry" if is_root else "interior")
            if found:
                seams.extend(found)
                node["provenance"] = "entry_seam" if is_root else "suspect_leaf"
                node["seam_tokens"] = [s["token"] for s in found]
        for c in callees:
            node["children"].append(build(c.get("name", "?"), depth + 1))
        return node

    tree = build(root, 0, is_root=True)
    coverage = {
        "graph_nodes": len(visited),
        "seams_entry": sum(1 for s in seams if s.get("priority") == "entry"),
        "seams_interior": sum(1 for s in seams if s.get("priority") == "interior"),
        "reads_used": budget["used"],
        "budget_exhausted": budget["used"] >= read_budget,
        "root_ambiguous": root_ambiguous,
    }
    hint = None
    if seams:
        hint = ("seams 是图谱失明的接缝（entry 优先）：用 api_read_file 读其 file_path+span，"
                "展开宏/模板定义，把恢复的被调符号回灌 api_call_chain 继续遍历。")
    if root_ambiguous:
        hint = (hint or "") + " root 名歧义：见 root_candidates，必要时换更精确的根符号重跑。"
    return _envelope(
        "original",
        {"tree": tree, "seams": seams, "coverage": coverage,
         "root_candidates": root_candidates},
        fallback_hint=hint,
    )
```

- [x] **Step 4: 运行验证通过**

Run: `python3 -m pytest lib/cannex_knowledge/tests/test_retriever_repo.py -k call_chain -v`
Expected: PASS（4 passed）

- [x] **Step 5: Commit**

```bash
git add lib/cannex_knowledge/retriever_repo.py lib/cannex_knowledge/tests/test_retriever_repo.py
git commit -m "feat(lib): api_call_chain 图谱主干 + 入口接缝优先 + 根消歧"
```

---

### Task 5: api_impact_surface — 向上影响面（图谱 callers ∪ ripgrep）

**Files:**
- Modify: `lib/cannex_knowledge/retriever_repo.py`
- Test: `lib/cannex_knowledge/tests/test_retriever_repo.py`

- [x] **Step 1: 写失败测试**

```python
# 追加到 test_retriever_repo.py
def test_api_impact_surface_diffs_ripgrep_against_graph(monkeypatch):
    """ripgrep 命中但图谱 callers 没覆盖的文件 → 进 to_classify。"""
    monkeypatch.setattr(repo_mod, "api_callers",
        lambda n, s, limit=20: {"data": {"callers": [
            {"name": "X", "file_path": "graph_seen.cpp", "start_line": 5}]}, "error": None})
    monkeypatch.setattr(repo_mod._cgc, "_get_repo_path", lambda repo: __import__("pathlib").Path("/repo"))
    monkeypatch.setattr(repo_mod._rg, "find_refs",
        lambda rp, sym, timeout=10: {"refs": [
            {"file_path": "/repo/graph_seen.cpp", "line": 5, "text": "call"},
            {"file_path": "/repo/macro_hidden.h", "line": 9, "text": "MACRO(sym)"}],
            "error": None})

    res = repo_mod.api_impact_surface("ops-transformer", "sym", read_budget=8)
    paths = {c["file_path"] for c in res["data"]["to_classify"]}
    assert "/repo/macro_hidden.h" in paths
    assert "/repo/graph_seen.cpp" not in paths
    assert res["data"]["coverage"]["ripgrep_only"] == 1
    assert res["fallback_hint"]


def test_api_impact_surface_no_index(monkeypatch):
    monkeypatch.setattr(repo_mod, "api_callers", lambda n, s, limit=20: {"data": {"callers": []}, "error": None})
    monkeypatch.setattr(repo_mod._cgc, "_get_repo_path", lambda repo: None)
    res = repo_mod.api_impact_surface("ops-transformer", "sym")
    assert res["error"]
```

- [x] **Step 2: 运行验证失败**

Run: `python3 -m pytest lib/cannex_knowledge/tests/test_retriever_repo.py -k impact_surface -v`
Expected: FAIL — `AttributeError: api_impact_surface`

- [x] **Step 3: 实现 api_impact_surface**

在 import 区加 `import os as _os` 和 `from . import ripgrep_client as _rg`；追加：

```python
# ── 改动影响面：图谱 callers ∪ ripgrep 召回（向上）─────────────────────────────
def _rel_path(p: str, root: str) -> str:
    try:
        return _os.path.relpath(p, root)
    except ValueError:
        return p


def api_impact_surface(name: str, symbol: str, read_budget: int = 8) -> dict:
    """改动影响面：图谱 callers（精度）∪ ripgrep 文本引用（召回兜底）。

    lib 产出"图谱 callers + ripgrep refs + to_classify(图谱漏的候选) + coverage"；
    agent 负责对 to_classify 分类（真调用/注释/字符串/同名无关）。
    coverage 必须呈现，绝不把保守预算下的局部结果当完整影响面。
    """
    graph_callers = (api_callers(name, symbol, limit=50).get("data") or {}).get("callers", [])
    graph_paths = {c.get("file_path") for c in graph_callers if c.get("file_path")}

    repo_path = _cgc._get_repo_path(name)
    if repo_path is None:
        return _envelope(
            "original",
            {"graph_callers": graph_callers, "ripgrep_refs": [], "to_classify": []},
            error=f"repo '{name}' has no codegraph index",
            fallback_hint="用 api_list_files 浏览目录结构",
        )

    rg = _rg.find_refs(str(repo_path), symbol)
    refs = rg.get("refs", [])
    to_classify = [r for r in refs
                   if _rel_path(r["file_path"], str(repo_path)) not in graph_paths]

    coverage = {
        "graph_callers": len(graph_callers),
        "ripgrep_refs": len(refs),
        "ripgrep_only": len(to_classify),
        "rg_error": rg.get("error"),
    }
    return _envelope(
        "original",
        {"graph_callers": graph_callers, "ripgrep_refs": refs,
         "to_classify": to_classify, "coverage": coverage},
        evidence=_evidence_from_matches(graph_callers),
        fallback_hint=(
            "to_classify 是 ripgrep 命中但图谱漏掉的候选（可能宏/模板调用点）："
            "逐个判定真调用/注释/字符串/同名无关，真调用计入影响面。"
            "改动决策前若 coverage 偏低，提高 read_budget 重跑。"
            if to_classify else None
        ),
    )
```

> 注：测试中引用 `repo_mod._cgc` / `repo_mod._rg`，确认 retriever_repo 已 `from . import codegraph_client as _cgc` 与 `from . import ripgrep_client as _rg`。

- [x] **Step 4: 运行验证通过**

Run: `python3 -m pytest lib/cannex_knowledge/tests/test_retriever_repo.py -k impact_surface -v`
Expected: PASS（2 passed）

- [x] **Step 5: Commit**

```bash
git add lib/cannex_knowledge/retriever_repo.py lib/cannex_knowledge/tests/test_retriever_repo.py
git commit -m "feat(lib): api_impact_surface 图谱+ripgrep 召回网的改动影响面"
```

---

### Task 6: worker RPC handlers

**Files:**
- Modify: `webchat/cannex_chat/worker/server.py`（HANDLERS 字典）
- Test: `webchat/cannex_chat/tests/test_worker_server.py`

- [x] **Step 1: 写失败测试**（沿用现有 `_make_worker()`/`_send()` 模式）

```python
# 追加到 webchat/cannex_chat/tests/test_worker_server.py
def test_rpc_get_call_chain(monkeypatch):
    w = _make_worker()
    resp = _send(w, "get_operator_call_chain",
                 {"repo": "ops-transformer", "root": "FlashAttentionScore"})
    assert resp["ok"]
    assert "tree" in resp["result"]["data"]
    assert "coverage" in resp["result"]["data"]


def test_rpc_get_impact_surface(monkeypatch):
    w = _make_worker()
    resp = _send(w, "get_change_impact_surface",
                 {"repo": "ops-transformer", "symbol": "DataCopy"})
    assert resp["ok"]
    assert "coverage" in resp["result"]["data"]
```

- [x] **Step 2: 运行验证失败**

Run: `python3 -m pytest webchat/cannex_chat/tests/test_worker_server.py -k "call_chain or impact_surface" -v`
Expected: FAIL — UnknownMethod

- [x] **Step 3: 实现 — 在 HANDLERS 字典追加两条**

```python
    # ── 完整调用链 / 影响面（2026-05-29 新增）──────────────────────────────
    "get_operator_call_chain": lambda p: repo_mod.api_call_chain(
        p["repo"], p["root"],
        max_depth=p.get("max_depth", 4), read_budget=p.get("read_budget", 8)),
    "get_change_impact_surface": lambda p: repo_mod.api_impact_surface(
        p["repo"], p["symbol"], read_budget=p.get("read_budget", 8)),
```

- [x] **Step 4: 运行验证通过**

Run: `python3 -m pytest webchat/cannex_chat/tests/test_worker_server.py -k "call_chain or impact_surface" -v`
Expected: PASS（2 passed）

- [x] **Step 5: Commit**

```bash
git add webchat/cannex_chat/worker/server.py webchat/cannex_chat/tests/test_worker_server.py
git commit -m "feat(webchat): worker RPC 接通 call_chain / impact_surface"
```

---

### Task 7: agent 工具定义

**Files:**
- Modify: `webchat/cannex_chat/agent/tools.py`（TOOLS 列表内追加 2 个）
- Test: `webchat/cannex_chat/tests/test_tools.py`

- [x] **Step 1: 改测试计数与断言**

```python
# 改 test_tools_count
def test_tools_count():
    assert len(TOOLS) == 17  # 15 + 2 新增
```
并在 `test_tool_names` 追加：
```python
    assert "get_operator_call_chain" in TOOL_NAMES
    assert "get_change_impact_surface" in TOOL_NAMES
```

- [x] **Step 2: 运行验证失败**

Run: `python3 -m pytest webchat/cannex_chat/tests/test_tools.py -v`
Expected: FAIL — count 15 != 17

- [x] **Step 3: 实现 — TOOLS 列表 `]` 之前追加**

```python
    {
        "name": "get_operator_call_chain",
        "description": (
            "★ Build an operator's COMPLETE call chain: graph traversal as the backbone, "
            "with macro/template 'seams' flagged for you to expand. Use for 'show me the full "
            "call chain of FlashAttention' or 'I want to understand this operator's execution "
            "logic before modifying it'. Returns {tree, seams, coverage}. The seams list = graph "
            "blindspots: read each seam's file_path+span with read_repo_file, expand the macro/"
            "template, then call this again on recovered symbols. ⚠️ Heavy — call at most ONCE "
            "per answer; raise read_budget only when completeness matters."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "root": {"type": "string", "description": "Root symbol or operator entry name"},
                "max_depth": {"type": "integer", "description": "Graph BFS depth, default 4"},
                "read_budget": {"type": "integer",
                                "description": "Max source-body reads for seam scan, default 8 (raise to escalate completeness)"},
            },
            "required": ["repo", "root"],
        },
    },
    {
        "name": "get_change_impact_surface",
        "description": (
            "★ Analyze the change impact surface of a symbol for SECONDARY DEVELOPMENT: graph "
            "callers (precise) UNION ripgrep references (recall net for macro/template call sites "
            "the graph misses). Use for 'if I modify Tiling, what's affected'. Returns "
            "{graph_callers, ripgrep_refs, to_classify, coverage}. to_classify = ripgrep hits the "
            "graph missed — classify each (real call / comment / string / unrelated). NEVER present "
            "a low-coverage result as complete; tell the user to raise read_budget before acting. "
            "⚠️ Heavy — call at most ONCE per answer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "symbol": {"type": "string"},
                "read_budget": {"type": "integer", "description": "default 8"},
            },
            "required": ["repo", "symbol"],
        },
    },
```

- [x] **Step 4: 运行验证通过**

Run: `python3 -m pytest webchat/cannex_chat/tests/test_tools.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add webchat/cannex_chat/agent/tools.py webchat/cannex_chat/tests/test_tools.py
git commit -m "feat(webchat): 新增 call_chain / impact_surface 两个 agent 工具"
```

---

### Task 8: prompt playbook + Phase 1 CLI 对齐（文档/对齐，无新逻辑）

**Files:**
- Modify: `webchat/cannex_chat/prompts/system_prompt.md`
- Modify: `skills/ascend-c/SKILL.md`
- Modify: `skills/ascend-c/tools/cannex_repo.py`（加 `call_chain` / `impact_surface` 子命令，委托同名 api_*）

- [x] **Step 1: system_prompt.md 加"接缝补全 playbook"段**

写明：用户问"完整调用链/执行逻辑"或"二开影响面"时 →
1. **先桥接入口**（spike 关键教训）：算子自然名（如 FlashAttentionScore）在图谱里解析到 host 死链，**不要**直接拿它当 call_chain 的 root。先 `list_repo_samples` 拿该算子 kernel 的 `entry_files` → `read_repo_file` 读 kernel 入口 .cpp 的宏分发 → 找到真正的 kernel 方法符号（如 `op.Process()` 中 op 的类型方法）。
2. 用上一步定位到的 **kernel 方法符号** 调 `get_operator_call_chain`(向下) / `get_change_impact_surface`(向上)。
3. 读返回的 `seams`(entry 优先) / `to_classify`：用 `read_repo_file` 读 span，展开宏/模板、分类 ripgrep 候选。
4. 把恢复的符号回灌 call_chain（迭代）。若 `root_ambiguous`，按 `root_candidates` 选对的节点重跑。
5. **必须**呈现 coverage，标注 `[cut?]` 盲区，**不替用户做改动决策**；coverage 低时提示提高 read_budget。
预算：call_chain / impact_surface 每答最多各 1 次（重型工具预算节）。

- [x] **Step 2: SKILL.md 同步**：决策树加 2 分支 + Appendix CLI 表加 2 行（`call_chain` / `impact_surface`）。

- [x] **Step 3: cannex_repo.py 加 CLI 子命令**

```python
def cmd_call_chain(args):
    _print(api_call_chain(args.repo, args.root,
                          max_depth=args.max_depth, read_budget=args.read_budget))

def cmd_impact_surface(args):
    _print(api_impact_surface(args.repo, args.symbol, read_budget=args.read_budget))
```
并在 argparse 注册 `call_chain`(repo, root, --max-depth=4, --read-budget=8)、`impact_surface`(repo, symbol, --read-budget=8) 两个 subparser 与 dispatch。

- [x] **Step 4: 冒烟验证 CLI**

Run: `python3 skills/ascend-c/tools/cannex_repo.py call_chain ops-transformer FlashAttentionScore --max-depth 2`
Expected: 输出含 tree / seams / coverage 的 JSON，无异常。

- [x] **Step 5: 全量回归**

Run: `python3 -m pytest lib/cannex_knowledge/tests/ webchat/cannex_chat/tests/ -q`
Expected: 全 PASS。

- [x] **Step 6: Commit**

```bash
git add webchat/cannex_chat/prompts/system_prompt.md skills/ascend-c/SKILL.md skills/ascend-c/tools/cannex_repo.py
git commit -m "docs/feat: 接缝补全 playbook + Phase1 CLI 对齐 call_chain/impact_surface"
```

---

## 自审（writing-plans self-review）

- **Spec 覆盖**：§三调用链→Task 4；§四 impact+ripgrep→Task 3/5；§五 coverage/escalate→Task 4/5 的 coverage 字段 + read_budget 参数 + prompt(Task 8)；§六 lib 契约→Task 4/5；§七 record-replay 测试→各 Task TDD + spike→Task 1；§八 CLAUDE.md 改写→已在前序对话落地（本计划不重复）。
- **类型一致**：`api_callees().data.callees[].name`、`api_search_symbol().data.matches[].{file_path,start_line,end_line}`、`api_read_file().content`、`_get_repo_path()→Path|None`、`find_refs()→{refs,error}` 全程一致。
- **无占位符**：每个改码步骤含完整代码与确切命令。
- **闸门**：Task 1 spike 是硬前置——不达标则停，不进 Task 2。

"""CannEx 代码仓数据访问层（纯查询，无 prompt/无策略）。

source_type 规则：
  - "original" : 代码原文或 CodeGraph 索引（直接给用户）
  - "metadata" : repo_card.yaml / samples.yaml（LLM 加工过，需标注）
"""
import json
import os as _os
import re
from pathlib import Path

import yaml

from .paths import CANNEX_ROOT as ROOT, META_FILE, REPOS_DIR
from . import codegraph_client as _cgc
from . import ripgrep_client as _rg
from . import seam as _seam


# ── 模块常量 ──────────────────────────────────────────────────────────────────

_DEFAULT_MAX_FILE_LINES = 800   # 单文件硬上限，防止把巨型生成代码塞进 context
_DEFAULT_MAX_DIR_ENTRIES = 20
_READ_FILE_DEFAULT_LINES = 300  # read_repo_file 默认窗口，模型可显式指定行范围
_MAX_LIST_ENTRIES = 80  # 单次 list 返回上限，防爆 context

_ARCH_DIR_RE = re.compile(r"(?:^|/)(arch\d+)(?=/)")


# ── 基础工具 ──────────────────────────────────────────────────────────────────

def load_meta() -> dict:
    return json.loads(META_FILE.read_text(encoding="utf-8"))


def get_repo_meta(name: str) -> dict:
    meta = load_meta()
    entry = next((r for r in meta.get("repos", []) if r["name"] == name), None)
    if not entry:
        avail = ", ".join(r["name"] for r in meta.get("repos", []))
        raise SystemExit(f"未找到代码仓 '{name}'。已注册仓: {avail or '(无)'}")
    return entry


def list_repos() -> list:
    if not REPOS_DIR.exists():
        return []
    return sorted(p.name for p in REPOS_DIR.iterdir() if p.is_dir())


def load_card(name: str) -> dict:
    f = REPOS_DIR / name / "repo_card.yaml"
    if not f.exists():
        raise SystemExit(f"repo_card 不存在: {f}")
    return yaml.safe_load(f.read_text(encoding="utf-8"))


def load_samples(name: str) -> list:
    f = REPOS_DIR / name / "samples.yaml"
    if not f.exists():
        return []
    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    return data.get("samples", [])



def _detect_sibling_archs(repo_root_abs: Path, entry_files: list,
                          sample_rel_path: str) -> tuple[set, set]:
    """扫描 entry_files 检测涉及到的 archXX/ 目录，并列出实际文件系统里同级有哪些 archYY/。
    返回 (covered_archs, missing_archs)：
      covered_archs: entry_files 已经覆盖的 archXX
      missing_archs: 文件系统里存在但 entry_files 未覆盖的 archYY
    """
    covered: set = set()
    parents_to_scan: set = set()
    for f in entry_files:
        m = _ARCH_DIR_RE.search(f)
        if not m:
            continue
        covered.add(m.group(1))
        # 找出该 archXX 所在的父目录（相对仓库根）
        full_rel = f"{sample_rel_path}/{f}" if sample_rel_path else f
        idx = full_rel.find(m.group(0).lstrip("/"))
        if idx >= 0:
            parents_to_scan.add(full_rel[:idx].rstrip("/"))

    missing: set = set()
    for parent_rel in parents_to_scan:
        parent_abs = (repo_root_abs / parent_rel).resolve() if parent_rel else repo_root_abs
        if not parent_abs.exists() or not parent_abs.is_dir():
            continue
        try:
            for child in parent_abs.iterdir():
                if child.is_dir():
                    m = re.fullmatch(r"arch\d+", child.name)
                    if m and child.name not in covered:
                        missing.add(child.name)
        except OSError:
            continue
    return covered, missing


# ── Module API（供 worker 进程 import 使用，不打印到 stdout）────────────────

def api_list() -> list:
    """返回代码仓清单，从 _meta.json 的 repos 数组读取（含 category、priority）。"""
    meta = load_meta()
    return [
        {
            "name": r["name"],
            "category": r.get("category", ""),
            "priority": r.get("priority", ""),
        }
        for r in meta.get("repos", [])
    ]


def api_card(name: str) -> dict:
    """返回指定仓的 repo_card.yaml 内容（dict）。"""
    return load_card(name)


def api_symbol(name: str, symbol: str, kind: str = "any") -> dict:
    """[DEPRECATED] 向后兼容包装：委托给 api_search_symbol。

    旧 schema: {matches: [...], source_type}
    新 schema: 通过 api_search_symbol 的 envelope

    Phase B 中 worker handler 切到 api_search_symbol 后此函数可彻底删除。
    """
    k = None if kind == "any" else kind
    res = api_search_symbol(name, symbol, kind=k, limit=10)
    if res.get("error"):
        return {"matches": [], "error": res["error"]}
    return {
        "matches": res["data"].get("matches", []),
        "source_type": "original",
    }


def api_overview(name: str) -> dict:
    """返回仓库卡片（repo_card.yaml 内容），含技术栈、入口指引、教学要点等。
    这是模型理解一个新仓库的最佳入口。
    """
    try:
        card = load_card(name)
    except SystemExit as e:
        return {"error": str(e)}
    return {"repo": name, "card": card, "source_type": "metadata"}


def api_list_samples(name: str, pattern: str | None = None,
                     complexity: str | None = None,
                     computation_pattern: str | None = None) -> dict:
    """列出仓库的精选样例（samples.yaml）。

    过滤参数：
      pattern: 模糊匹配 name/id/computation_pattern（向后兼容字段）
      complexity: 严格匹配（beginner/intermediate/expert）
      computation_pattern: 严格匹配（vector/cube/vector_to_cube/cube_to_vector/fusion）
    """
    samples = load_samples(name)
    if pattern:
        p = pattern.lower()
        samples = [s for s in samples
                   if p in s.get("name", "").lower()
                   or p in s.get("id", "").lower()
                   or p in s.get("computation_pattern", "").lower()]
    if complexity:
        samples = [s for s in samples if s.get("complexity") == complexity]
    if computation_pattern:
        samples = [s for s in samples if s.get("computation_pattern") == computation_pattern]
    return {
        "repo": name,
        "count": len(samples),
        "samples": [
            {
                "id": s.get("id"),
                "name": s.get("name"),
                "path": s.get("path"),
                "entry_files": s.get("entry_files", []),
                "computation_pattern": s.get("computation_pattern"),
                "complexity": s.get("complexity"),
                "apis_used": s.get("apis_used", []),
                "teaches": s.get("teaches", []),
                # 注意：recommendation_reason 已永久删除，不再 expose
            }
            for s in samples
        ],
        "source_type": "metadata",
    }


def api_list_files(name: str, dir_path: str = "", max_depth: int = 2) -> dict:
    """列出仓库内某目录的文件树（受 max_depth 限制，递归子目录）。
    用途：让模型发现 samples.yaml 未标注的文件（如 arch35/ 新硬件实现、子模块等）。

    参数：
      dir_path:  相对仓库根（"" = 仓库根；如 "attention/common/op_kernel"）
      max_depth: 递归深度，默认 2

    返回 {repo, dir_path, entries: [{name, type, children?}], truncated}
    """
    try:
        repo_meta = get_repo_meta(name)
    except SystemExit as e:
        return {"error": str(e)}

    repo_root = (ROOT / repo_meta["local_path"]).resolve()
    if not repo_root.exists():
        return {"error": f"仓库本地路径不存在: {repo_root}"}

    try:
        target = (repo_root / dir_path).resolve()
        target.relative_to(repo_root)
    except (ValueError, OSError):
        return {"error": f"非法路径（疑似越界）: {dir_path}"}

    if not target.exists():
        return {"error": f"目录不存在: {dir_path}"}
    if not target.is_dir():
        return {"error": f"不是目录: {dir_path}"}

    truncated = False

    def _walk(d: Path, depth: int) -> list:
        nonlocal truncated
        out = []
        try:
            children = sorted(d.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        except PermissionError:
            return out
        for i, p in enumerate(children):
            if i >= _MAX_LIST_ENTRIES:
                truncated = True
                break
            if p.name.startswith(".") and p.name not in (".codegraph",):
                continue
            if p.is_dir():
                entry = {"name": p.name + "/", "type": "dir"}
                if depth < max_depth:
                    entry["children"] = _walk(p, depth + 1)
                out.append(entry)
            else:
                out.append({"name": p.name, "type": "file"})
        return out

    return {
        "repo": name,
        "dir_path": dir_path or "/",
        "entries": _walk(target, 1),
        "truncated": truncated,
        "source_type": "metadata",
    }


def api_read_file(name: str, file_path: str,
                  start_line: int = 1, end_line: int | None = None) -> dict:
    """按相对路径读取仓库内任意源文件（自由 Read 能力，但限制在仓库根目录下）。
    用途：当 lookup_code_symbol 返回 file_path 后，
         模型可以用这个工具读取该文件的指定行范围。

    安全：用 resolve() + is_relative_to() 防 path traversal（不能逃出仓库根）。

    参数：
      name:       仓库名
      file_path:  相对仓库根的路径（如 "op_kernel/arch35/flash_attention_score_kernel_base.h"）
      start_line: 起始行（1-indexed），默认 1
      end_line:   结束行（含），默认 start_line + 300

    返回 {repo, file_path, total_lines, start_line, end_line, content, truncated}
    """
    try:
        repo_meta = get_repo_meta(name)
    except SystemExit as e:
        return {"error": str(e)}

    repo_root = (ROOT / repo_meta["local_path"]).resolve()
    if not repo_root.exists():
        return {"error": f"仓库本地路径不存在: {repo_root}"}

    # 防 path traversal：resolve 后必须仍在 repo_root 内
    try:
        full = (repo_root / file_path).resolve()
        full.relative_to(repo_root)
    except (ValueError, OSError):
        return {"error": f"非法路径（疑似越界）: {file_path}"}

    if not full.exists():
        return {"error": f"文件不存在: {file_path}"}
    if not full.is_file():
        return {"error": f"不是文件: {file_path}"}

    try:
        text = full.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": f"读取失败: {e}"}

    lines = text.splitlines()
    total = len(lines)
    s = max(1, start_line)
    e = end_line if end_line is not None else s + _READ_FILE_DEFAULT_LINES - 1
    e = min(e, total)

    if s > total:
        return {
            "repo": name, "file_path": file_path, "total_lines": total,
            "start_line": s, "end_line": s, "content": "",
            "error": f"start_line({s}) 超过文件总行数({total})",
        }

    # 1-indexed 切片
    snippet = "\n".join(lines[s - 1:e])
    truncated = e < total

    return {
        "repo": name,
        "file_path": file_path,
        "total_lines": total,
        "start_line": s,
        "end_line": e,
        "content": snippet,
        "truncated": truncated,
        "source_type": "original",
    }


def api_read_sample(name: str, sample_id: str, skeleton: bool = False,
                    max_lines_per_file: int = _DEFAULT_MAX_FILE_LINES) -> dict:
    """按 sample id 读取 entry_files 全文（教学场景的最高价值能力）。
    skeleton=True 时只返回每个文件前 60 行（用于先看结构）。
    自动检测 sibling arch 目录，发现 entry_files 未覆盖的 archXX/ 时附加 hint，
    引导模型主动用 read_repo_file 读取其他架构版本。
    """
    samples = load_samples(name)
    sample = next((s for s in samples if s.get("id") == sample_id), None)
    if not sample:
        available = [s.get("id") for s in samples]
        return {
            "error": f"未找到 sample id='{sample_id}'",
            "available_sample_ids": available,
        }

    try:
        repo_meta = get_repo_meta(name)
    except SystemExit as e:
        return {"error": str(e)}

    repo_root_abs = (ROOT / repo_meta["local_path"]).resolve()
    sample_rel_path = sample.get("path", "")
    sample_path = repo_root_abs / sample_rel_path
    entry_files = sample.get("entry_files", [])

    files_out = []
    for fname in entry_files:
        fpath = sample_path / fname
        if fpath.is_dir():
            sub = sorted(p.name for p in fpath.iterdir() if p.is_file())[:_DEFAULT_MAX_DIR_ENTRIES]
            files_out.append({"file": fname, "type": "directory", "contents": sub})
            continue
        if not fpath.exists():
            files_out.append({"file": fname, "error": "not_found"})
            continue
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            files_out.append({"file": fname, "error": f"read_failed: {e}"})
            continue

        lines = content.splitlines()
        line_limit = 60 if skeleton else max_lines_per_file
        truncated = len(lines) > line_limit
        if truncated:
            content = "\n".join(lines[:line_limit])

        files_out.append({
            "file": fname,
            "path_in_repo": str(fpath.relative_to(repo_root_abs)),
            "total_lines": len(lines),
            "truncated": truncated,
            "content": content,
        })

    result = {
        "repo": name,
        "sample_id": sample_id,
        "sample_name": sample.get("name"),
        "files": files_out,
        "source_type": "original",
    }

    # ★ 关键：sibling arch 检测，硬塞 hint 给模型
    covered_archs, missing_archs = _detect_sibling_archs(
        repo_root_abs, entry_files, sample_rel_path)
    if missing_archs:
        result["sibling_archs_covered"] = sorted(covered_archs)
        result["sibling_archs_missing"] = sorted(missing_archs)
        result["next_action_required"] = (
            f"★ 本仓库还有未读取的硬件架构目录：{sorted(missing_archs)}（你只读了 {sorted(covered_archs)}）。"
            f"CANN 仓库中 archXX 数字越大通常是越新的硬件（如 arch35 是 910B/C/D，arch38 更新）。"
            f"必须立刻调用 read_repo_file 读取这些 arch 目录下的对应实现，"
            f"回答中要明确覆盖所有架构版本，否则解读不完整。"
            f"建议先用 list_repo_files 列出 {sample_rel_path}/op_kernel 看目录结构。"
        )

    return result


# ── envelope helper ────────────────────────────────────────────────────────────

def _envelope(
    source_type: str,
    data: dict,
    evidence: list = None,
    error: str | None = None,
    fallback_hint: str | None = None,
) -> dict:
    """统一返回 schema：{source_type, evidence, data, error, fallback_hint}。"""
    return {
        "source_type": source_type,
        "evidence": evidence or [],
        "data": data,
        "error": error,
        "fallback_hint": fallback_hint,
    }


def _evidence_from_matches(matches: list) -> list:
    """从 normalize 后的 matches 抽出 evidence 列表。"""
    out = []
    for m in matches:
        if "file_path" in m and "start_line" in m:
            out.append({
                "file_path": m["file_path"],
                "start_line": m["start_line"],
                "end_line": m.get("end_line", m["start_line"]),
            })
    return out


# ── L1 符号定位（CodeGraph CLI 接入）─────────────────────────────────────────

def api_search_symbol(
    name: str,
    query: str,
    kind: str | None = None,
    limit: int = 10,
) -> dict:
    """FTS5 + ranking 符号搜索，包装 `codegraph query`。

    返回 envelope，data = {matches: [...]}，每个 match 含 score（CodeGraph 内部 ranking）。
    """
    flags = ["-l", str(limit)]
    if kind:
        flags.extend(["-k", kind])
    raw = _cgc.call_cli(name, "query", query, flags=flags)

    if isinstance(raw, dict) and raw.get("error"):
        return _envelope("original", {}, error=raw["error"],
                         fallback_hint=raw.get("fallback_hint"))

    # codegraph query 返回 list: [{node: {...}, score: float}, ...]
    matches = []
    for item in _cgc._normalize_keys(raw):
        n = item.get("node", {}) if isinstance(item, dict) else {}
        if not n:
            continue
        matches.append({**n, "score": item.get("score")})

    return _envelope(
        "original",
        {"matches": matches},
        evidence=_evidence_from_matches(matches),
    )


def api_node(name: str, symbol: str, kind: str | None = None) -> dict:
    """精确查单个符号（拿第一条 query 结果的完整 node info）。

    CodeGraph CLI 不暴露独立 `node` 子命令；用 `query --limit 1` 等价。
    """
    flags = ["-l", "1"]
    if kind:
        flags.extend(["-k", kind])
    raw = _cgc.call_cli(name, "query", symbol, flags=flags)

    if isinstance(raw, dict) and raw.get("error"):
        return _envelope("original", {}, error=raw["error"],
                         fallback_hint=raw.get("fallback_hint"))

    items = _cgc._normalize_keys(raw)
    if not items:
        return _envelope(
            "original", {},
            error=f"未找到符号 '{symbol}'（repo={name}）",
            fallback_hint=(
                f"用 api_search_symbol('{name}', '{symbol}') 模糊查找，"
                f"或用 api_list_files 探索目录"
            ),
        )

    first = items[0]
    node = first.get("node", {}) if isinstance(first, dict) else {}
    if "score" in first:
        node["score"] = first["score"]

    return _envelope(
        "original",
        {"node": node},
        evidence=_evidence_from_matches([node]) if node else [],
    )


# ── L2 图关系反查（CodeGraph CLI v0.9.4+）────────────────────────────────────

def _call_graph_query(name: str, subcommand: str, symbol: str, limit: int) -> dict:
    """callers / callees 共享实现，差异只在 subcommand。"""
    flags = ["-l", str(limit)]
    raw = _cgc.call_cli(name, subcommand, symbol, flags=flags)
    if isinstance(raw, dict) and raw.get("error"):
        return _envelope("original", {}, error=raw["error"],
                         fallback_hint=raw.get("fallback_hint"))

    data = _cgc._normalize_keys(raw)
    items_key = "callers" if subcommand == "callers" else "callees"
    items = data.get(items_key, [])

    fallback = None
    if not items:
        fallback = (
            f"未找到 '{symbol}' 的 {items_key}。"
            f"CodeGraph 无法穿透宏展开/模板特化，"
            f"建议 api_read_file 直读源码定位调用点。"
        )

    return _envelope(
        "original",
        data,
        evidence=_evidence_from_matches(items),
        fallback_hint=fallback,
    )


def api_callers(name: str, symbol: str, limit: int = 20) -> dict:
    """反查谁调用了 symbol，包装 `codegraph callers`。"""
    return _call_graph_query(name, "callers", symbol, limit)


def api_callees(name: str, symbol: str, limit: int = 20) -> dict:
    """反查 symbol 调用了谁，包装 `codegraph callees`。"""
    return _call_graph_query(name, "callees", symbol, limit)


def api_impact(name: str, symbol: str, depth: int = 2) -> dict:
    """分析修改 symbol 会波及哪些代码，包装 `codegraph impact`。

    timeout=20s（impact 比 search 重）。
    """
    flags = ["-d", str(depth)]
    raw = _cgc.call_cli(name, "impact", symbol, flags=flags, timeout=20)
    if isinstance(raw, dict) and raw.get("error"):
        return _envelope("original", {}, error=raw["error"],
                         fallback_hint=raw.get("fallback_hint"))

    data = _cgc._normalize_keys(raw)
    return _envelope(
        "original",
        data,
        evidence=_evidence_from_matches(data.get("affected", [])),
    )


# ── L4 阙割版探索（context + --no-code）──────────────────────────────────────

def api_explore_symbols(name: str, query: str, max_symbols: int = 30) -> dict:
    """任务相关的符号清单（CodeGraph context 输出，源码已剥除）。

    用 `codegraph context "<task>" -n <max> --no-code -f json`：
    - CodeGraph 内置 --no-code 不返回 code blocks
    - context 命令 JSON flag 是 `-f json`，不是 `--json`
    """
    flags = ["-n", str(max_symbols), "--no-code"]
    raw = _cgc.call_cli(
        name, "context", query,
        flags=flags,
        json_flag=["-f", "json"],
        timeout=20,
    )
    if isinstance(raw, dict) and raw.get("error"):
        return _envelope("original", {}, error=raw["error"],
                         fallback_hint=raw.get("fallback_hint"))

    data = _cgc._normalize_keys(raw)

    # 防御性：即使 CodeGraph 升级后回归带源码字段，lib 主动剥
    def _strip_code(items):
        for it in items or []:
            for k in ("source_code", "code", "content", "body"):
                it.pop(k, None)
        return items

    data["symbols"] = _strip_code(data.get("nodes") or data.get("symbols") or [])
    if "nodes" in data:
        del data["nodes"]
    data["entry_points"] = _strip_code(data.get("entry_points", []))

    # evidence: entry_points + symbols 去重（file_path+start_line 作 key）
    seen = set()
    evidence = []
    for item in (data["entry_points"] + data["symbols"]):
        key = (item.get("file_path"), item.get("start_line"))
        if key[0] and key not in seen:
            seen.add(key)
            evidence.append({
                "file_path": item["file_path"],
                "start_line": item["start_line"],
                "end_line": item.get("end_line", item["start_line"]),
            })

    return _envelope("original", data, evidence=evidence)


# ── 完整调用链：图谱主干 + 入口接缝优先 + 根消歧（向下 callees）──────────────────
_WORK_DOER_RE = re.compile(r"(Process|Init|Compute|Launch|Execute|Run|Kernel|Entry)", re.IGNORECASE)
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
    # 根符号消歧：surface 解析到哪些节点、是否歧义
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
                node["seam_tokens"] = [sm["token"] for sm in found]
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

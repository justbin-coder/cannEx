"""裸 codegraph 传递 callees recall 测量（spike，非生产代码）。

对若干算子，从根符号出发图谱 BFS 到指定深度，打印调用树，
标出 callees 为空的"可疑叶子"（名字像在干活但图谱说没下层调用 → 极可能宏/模板藏了调用）。
供人工对照源码评估：裸图谱漏了多少、漏点是否集中在宏/模板。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from cannex_knowledge import retriever_repo as r  # noqa: E402

OPERATORS = [
    ("ops-transformer", "FlashAttentionScore"),
    ("ops-transformer", "FlashAttentionScoreKernelTrain"),
    ("ops-transformer", "Process"),
]
WORK_DOER = ("Process", "Init", "Compute", "Launch", "Execute", "Run", "Kernel", "Entry")

stats = {"nodes": 0, "suspect_leaves": 0, "empty_leaves": 0}


def walk(repo, sym, depth, seen, maxd=4):
    if depth > maxd or sym in seen:
        return
    seen.add(sym)
    stats["nodes"] += 1
    res = r.api_callees(repo, sym, limit=30)
    err = res.get("error")
    callees = (res.get("data") or {}).get("callees", [])
    flag = ""
    if not callees:
        stats["empty_leaves"] += 1
        if any(k in sym for k in WORK_DOER):
            stats["suspect_leaves"] += 1
            flag = "   <== 可疑叶子(干活名但图谱空, 疑宏/模板藏调用)"
    errtag = f" [ERR:{err}]" if err else ""
    print("  " * depth + f"- {sym} (callees={len(callees)}){flag}{errtag}")
    for c in callees:
        walk(repo, c.get("name", "?"), depth + 1, seen, maxd)


if __name__ == "__main__":
    for repo, root in OPERATORS:
        print(f"\n===== {repo} :: {root} (depth<=4) =====")
        walk(repo, root, 0, set())
    print("\n===== 汇总 =====")
    print(f"总节点: {stats['nodes']}")
    print(f"空叶子(callees=0): {stats['empty_leaves']}")
    print(f"其中可疑叶子(干活名却空): {stats['suspect_leaves']}")
    if stats["nodes"]:
        ratio = stats["suspect_leaves"] / stats["nodes"] * 100
        print(f"可疑叶子占比: {ratio:.1f}%  (越高=裸图谱越不可信, 越需接缝补全)")

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
        d = obj.get("data") or {}
        # Skip malformed records missing critical fields
        if not d.get("path") or not d.get("lines"):
            continue
        file_path = d.get("path", {}).get("text", "")
        text = d.get("lines", {}).get("text", "").rstrip("\n")
        refs.append({
            "file_path": file_path,
            "line": d.get("line_number"),
            "text": text,
        })

    # Log warning on unexpected exit codes (2+)
    if r.returncode not in (0, 1) and r.stderr:
        import sys
        print(f"[ripgrep_client] rg exit {r.returncode}: {r.stderr[:200]}", file=sys.stderr)

    return {"refs": refs, "error": None}

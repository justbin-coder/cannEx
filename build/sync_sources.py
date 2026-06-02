#!/usr/bin/env python3
"""
拉取/更新 CannEx 原始素材

读取 build/repos.yaml + build/docs.yaml，对每个 enabled=true 项目：
  - repo: local_path 已存在 → git fetch + checkout ref；不存在 → git clone
  - doc:  检查 local_path 是否存在；不存在则报告（不自动下载，需用户手动放置）

输出：变更摘要，供后续 build_docs / build_repos 决定增量。
"""
import argparse
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REPOS_YAML = ROOT / "build/repos.yaml"
DOCS_YAML = ROOT / "build/docs.yaml"


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_path(p: str) -> Path:
    """支持绝对路径和相对于 ROOT 的路径"""
    candidate = Path(p)
    if candidate.is_absolute():
        return candidate
    return ROOT / p


def sync_one_repo(repo: dict, dry: bool) -> str:
    name = repo["name"]
    local = resolve_path(repo["local_path"])
    url = repo.get("url", "")
    ref = repo.get("ref", "master")

    if dry:
        return f"[DRY] repo {name}: ref={ref} → {local} (exists={local.exists()})"

    if not local.exists():
        if not url:
            return f"[SKIP] repo {name}: local_path 不存在且无 url，请手动放置"
        local.parent.mkdir(parents=True, exist_ok=True)
        print(f"[clone] {name} from {url}")
        subprocess.check_call(["git", "clone", "--branch", ref, url, str(local)])
        return f"[CLONED] {name}@{ref}"
    else:
        print(f"[fetch] {name}")
        try:
            subprocess.check_call(["git", "-C", str(local), "fetch", "--all", "--tags"])
            subprocess.check_call(["git", "-C", str(local), "checkout", ref])
            head = subprocess.check_output(
                ["git", "-C", str(local), "rev-parse", "HEAD"], text=True
            ).strip()
            return f"[UPDATED] {name}@{ref} ({head[:8]})"
        except subprocess.CalledProcessError as e:
            return f"[ERROR] {name}: {e}"


def sync_one_doc(doc: dict, dry: bool) -> str:
    name = doc["name"]
    local = resolve_path(doc["local_path"])
    if dry:
        return f"[DRY] doc {name}: expect at {local} (exists={local.exists()})"
    if not local.exists():
        return f"[MISSING] doc {name}: 请手动放置 PDF 到 {local}"
    return f"[OK] doc {name}: {local}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--repos-only", action="store_true")
    p.add_argument("--docs-only", action="store_true")
    args = p.parse_args()

    summary = []

    if not args.docs_only:
        repos = load_yaml(REPOS_YAML).get("repos", [])
        for r in repos:
            if not r.get("enabled"):
                continue
            try:
                summary.append(sync_one_repo(r, args.dry_run))
            except subprocess.CalledProcessError as e:
                summary.append(f"[ERROR] repo {r['name']}: {e}")

    if not args.repos_only:
        docs = load_yaml(DOCS_YAML).get("docs", [])
        for d in docs:
            if not d.get("enabled"):
                continue
            summary.append(sync_one_doc(d, args.dry_run))

    print("\n=== sync_sources summary ===")
    for line in summary:
        print(line)


if __name__ == "__main__":
    main()

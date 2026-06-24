#!/usr/bin/env python3
"""
build_repos.py — 对 enabled=true 的代码仓建索引 + 生成元信息

阶段 1（本 Task）：codegraph init/index
阶段 2（Task 8）：bootstrap repo_card.yaml + samples.yaml
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "workspace"
REPOS_DIR = WORKSPACE / "repos"
META_FILE = WORKSPACE / "_meta.json"
REPOS_YAML = ROOT / "build/repos.yaml"


def resolve_path(p: str) -> Path:
    candidate = Path(p)
    if candidate.is_absolute():
        return candidate
    return ROOT / p


def load_meta() -> dict:
    if META_FILE.exists():
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    return {"version": "v2.0", "cann_version": "9.0.0", "docs": [], "repos": []}


def save_meta(meta: dict):
    META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def codegraph_ensure(repo_local: Path) -> Path:
    """确保 codegraph 索引存在；已有则跳过，无则 init + index"""
    cg_dir = repo_local / ".codegraph"
    if cg_dir.exists():
        print(f"[skip codegraph] 已有索引: {cg_dir}")
    else:
        print(f"[codegraph init] {repo_local}")
        subprocess.check_call(["codegraph", "init", "--yes"], cwd=str(repo_local))
        print(f"[codegraph index] {repo_local}（可能需要几分钟）")
        subprocess.check_call(["codegraph", "index"], cwd=str(repo_local))
    return cg_dir


def sync_codegraph_to_workspace(repo_name: str, cg_src: Path):
    """把原始仓的 .codegraph/ 复制到 workspace/repos/<name>/.codegraph/"""
    dst = REPOS_DIR / repo_name / ".codegraph"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(cg_src, dst)
    print(f"[synced] {dst} ({dst.stat().st_size // 1024 // 1024} MB approx)")


# ── LLM bootstrap（Task 8 代码，放在同一文件） ────────────────────────────────

def _load_dotenv():
    try:
        from dotenv import load_dotenv
        from _paths import pageindex_dir
        load_dotenv(pageindex_dir() / ".env")
    except ImportError:
        pass


def call_llm(prompt: str) -> str:
    import litellm
    _load_dotenv()
    resp = litellm.completion(
        model="deepseek/deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
        max_tokens=8192,
        timeout=180,
    )
    return resp.choices[0].message.content


def extract_yaml_block(text: str) -> str:
    # 优先匹配完整 ```yaml ... ``` 块
    m = re.search(r"```yaml\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1)
    # 降级：剥掉开头的 ```yaml 行（LLM 有时不输出结尾 ```）
    text = re.sub(r"^```yaml\s*\n?", "", text.strip())
    text = re.sub(r"\n?```\s*$", "", text)
    return text


def render_template(template_path: Path, **kwargs) -> str:
    text = template_path.read_text(encoding="utf-8")
    for k, v in kwargs.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def bootstrap_repo_card(repo: dict, local: Path) -> Path:
    out = REPOS_DIR / repo["name"] / "repo_card.yaml"
    if out.exists():
        print(f"[skip card] {out} 已存在，不覆盖")
        return out

    readme = ""
    for cand in ["README.md", "README.zh.md", "README"]:
        f = local / cand
        if f.exists():
            readme = f.read_text(encoding="utf-8", errors="ignore")[:4000]
            break

    top_dirs = "\n".join(
        f"  - {p.name}/"
        for p in sorted(local.iterdir())
        if p.is_dir() and not p.name.startswith(".")
    )

    prompt = render_template(
        ROOT / "build/prompts/bootstrap_repo_card.md",
        repo_name=repo["name"],
        repo_url=repo.get("url", "N/A"),
        ref=repo.get("ref", "master"),
        readme_excerpt=readme or "(无 README)",
        top_dirs=top_dirs,
        today=date.today().isoformat(),
    )

    print(f"[LLM bootstrap repo_card for {repo['name']}]")
    raw = call_llm(prompt)
    yaml_text = extract_yaml_block(raw)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml_text, encoding="utf-8")
    print(f"[written] {out}  (请人工 review TBD 字段)")
    return out


def collect_operator_dirs(local: Path, max_count: int = 15) -> list:
    """
    ops-transformer 结构：顶层是算子类别目录（attention/ffn/moe/gmm/mc2...），
    每个类别下是具体算子目录。收集二级算子目录作为候选条目。
    忽略 common/3rd/cmake/docs/tests/scripts/torch_extension 等非算子目录。
    """
    skip = {"common", "3rd", "cmake", "docs", "tests", "scripts",
            "torch_extension", "experimental", ".codegraph"}
    candidates = []
    for category in sorted(local.iterdir()):
        if not category.is_dir() or category.name.startswith(".") or category.name in skip:
            continue
        # 二级：具体算子
        ops = [p for p in sorted(category.iterdir()) if p.is_dir() and not p.name.startswith(".")]
        if ops:
            for op in ops:
                candidates.append(op)
        else:
            candidates.append(category)
        if len(candidates) >= max_count:
            break
    return candidates[:max_count]


def bootstrap_samples(repo: dict, local: Path) -> Path:
    out = REPOS_DIR / repo["name"] / "samples.yaml"
    if out.exists():
        print(f"[skip samples] {out} 已存在，不覆盖")
        return out

    sample_dirs = collect_operator_dirs(local)
    if not sample_dirs:
        print(f"[skip samples] 未发现算子目录")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("samples: []\n", encoding="utf-8")
        return out

    dirs_text = "\n".join(f"  - {p.relative_to(local)}" for p in sample_dirs)
    files_text = ""
    for d in sample_dirs:
        files = [f.name for f in d.rglob("*") if f.is_file()][:8]
        files_text += f"\n### {d.relative_to(local)}\n" + "\n".join(f"  - {f}" for f in files)

    prompt = render_template(
        ROOT / "build/prompts/bootstrap_samples.md",
        repo_name=repo["name"],
        sample_dirs=dirs_text,
        sample_files_per_dir=files_text,
    )

    print(f"[LLM bootstrap samples for {repo['name']}]")
    raw = call_llm(prompt)
    yaml_text = extract_yaml_block(raw)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml_text, encoding="utf-8")
    print(f"[written] {out}  (请人工 review TBD 字段)")
    return out


def update_meta_repos(repo: dict, local: Path, meta: dict):
    """在 _meta.json 的 repos[] 中记录或更新该仓条目"""
    repos = meta.setdefault("repos", [])
    existing = next((r for r in repos if r["name"] == repo["name"]), None)
    entry = {
        "name": repo["name"],
        "category": repo.get("category"),
        "audience": repo.get("audience", []),
        "priority": repo.get("priority"),
        "local_path": os.path.relpath(local, ROOT),
        "codegraph_db": os.path.join(os.path.relpath(local, ROOT), ".codegraph", "codegraph.db"),
        "workspace_path": f"repos/{repo['name']}",
        "last_indexed": date.today().isoformat(),
    }
    if existing:
        existing.update(entry)
    else:
        repos.append(entry)


def process_repo(repo: dict, only_codegraph: bool):
    name = repo["name"]
    local = resolve_path(repo["local_path"])
    if not local.exists():
        print(f"[skip] {name}: local_path 不存在 {local}（先跑 sync_sources.py）")
        return

    cg_dir = codegraph_ensure(local)
    sync_codegraph_to_workspace(name, cg_dir)

    meta = load_meta()
    update_meta_repos(repo, local, meta)
    save_meta(meta)

    if only_codegraph:
        return
    # bootstrap 需显式传 --bootstrap 才触发，默认不调用 LLM



def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", help="只处理指定仓（按 name）")
    p.add_argument("--only-codegraph", action="store_true",
                   help="只跑 codegraph 索引，不做 bootstrap")
    p.add_argument("--bootstrap", action="store_true",
                   help="调用 LLM 生成 repo_card.yaml + samples.yaml 初稿（需配置 DEEPSEEK_API_KEY）")
    args = p.parse_args()

    cfg = yaml.safe_load(REPOS_YAML.read_text(encoding="utf-8"))
    repos = [r for r in cfg.get("repos", []) if r.get("enabled")]
    if args.repo:
        repos = [r for r in repos if r["name"] == args.repo]
        if not repos:
            sys.exit(f"未找到 enabled 仓: {args.repo}")

    for r in repos:
        process_repo(r, args.only_codegraph or not args.bootstrap)


if __name__ == "__main__":
    main()

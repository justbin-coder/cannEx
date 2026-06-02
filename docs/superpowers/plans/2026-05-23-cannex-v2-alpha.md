# CannEx v2-α Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor CannEx v1（单 Skill + 文档检索）升级到 v2-α 架构：角色路由 + 双知识源（文档 + 代码仓） + 内容来源标注，并以官方 `samples` 仓为 PoC 跑通端到端。

**Architecture:** 三层结构——离线管道（sync_sources / build_docs / build_repos）产出静态产物到 workspace/，运行时只通过查询 CLI（cannex_doc / cannex_repo）做 lookup；Claude Code Skill 作为接入层调度。

**Tech Stack:** Python 3.11（PageIndex 同环境）、PageIndex（文档建树）、CodeGraph（代码仓索引）、YAML 配置、Bash 编排。

**关联文档：** `docs/specs/2026-05-23-cannex-v2-design.md`

---

## 全局约束与共享上下文

- **工作目录**：`/Users/justbin/Desktop/CannEx/`
- **PageIndex 环境**：`~/project/CANN/PageIndex/.venv`（含 DEEPSEEK_API_KEY）—— 所有 Python 脚本统一用此环境
- **CodeGraph 安装**：参考 `~/project/CANN/codeIndex/codegraph/README.md`，使用 `npm i -g @colbymchenry/codegraph` 或一键脚本
- **样本仓本地路径**：执行 Task 4 时由用户提供，先记到 `build/repos.yaml`
- **激活环境**：每个 Python 步骤前 `cd ~/project/CANN/PageIndex && source .venv/bin/activate`
- **commits**：项目根目前**不是 git 仓**，Task 1 会 init；之后每个 Task 完成做一次 commit

---

## 文件结构（v2-α 完成后）

```
/Users/justbin/Desktop/CannEx/
├── .gitignore                              # NEW
├── CLAUDE.md                               # MODIFY (Task 14)
├── build/                                  # NEW (whole dir)
│   ├── repos.yaml
│   ├── docs.yaml
│   ├── sync_sources.py
│   ├── build_docs.py                       # ex build_index.py 扩展版
│   ├── build_repos.py
│   └── monthly_update.sh
├── raw/                                    # NEW (gitignored, 本地素材)
│   ├── docs/                               # PDF 落盘
│   └── repos/                              # git clone 目标
├── workspace/
│   ├── _meta.json                          # MODIFY (schema 扩展)
│   ├── docs/                               # NEW（迁移现有 JSON 进来）
│   │   ├── 717ca9ab-...json                # MOVE
│   │   └── e8997a18-...json                # MOVE
│   └── repos/                              # NEW
│       └── samples/
│           ├── .codegraph/                 # CodeGraph 自动产物
│           ├── repo_card.yaml
│           └── samples.yaml
├── skills/ascend-c/
│   ├── SKILL.md                            # REPLACE (Task 12, ~100 行)
│   ├── references/
│   │   ├── answer-styles.md                # NEW (Task 11)
│   │   ├── teaching-personas.md            # KEEP
│   │   └── learning-paths.md               # KEEP
│   └── tools/
│       ├── cannex_doc.py                   # NEW（替换 cannex.py）
│       └── cannex_repo.py                  # NEW
├── tests/                                  # NEW
│   ├── test_cannex_doc.py
│   ├── test_cannex_repo.py
│   └── test_pipeline.py
├── build_index.py                          # DELETE (Task 5 完成后)
└── docs/                                   # 已有
```

---

## Task 0：CodeGraph spike（强制前置，可能否决后续方案）

**目的**：验证 CodeGraph 对 CANN C++ 代码仓的解析效果。若结果不可用，停下来重审 §3.4 设计。

**Files:**
- Create: `docs/specs/2026-05-23-codegraph-spike-report.md`

- [ ] **Step 1: 安装 CodeGraph**

```bash
curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | sh
codegraph --version
```

Expected: 输出版本号且无错误。

- [ ] **Step 2: 确认 samples 仓本地路径**

向用户索要 samples 仓本地路径（如 `~/project/CANN/raw/repos/samples`）。
若仓未本地存在，执行 `git clone https://gitee.com/ascend/samples.git ~/project/CANN/raw/repos/samples`。

- [ ] **Step 3: 对 samples 仓建索引**

```bash
cd ~/project/CANN/raw/repos/samples
codegraph init
```

Expected: 在 `.codegraph/codegraph.db` 生成 SQLite 文件，输出索引统计（节点数、文件数）。

- [ ] **Step 4: 评估 5 个关键能力**

记录到 `docs/specs/2026-05-23-codegraph-spike-report.md`，模板：

```markdown
# CodeGraph spike on Ascend samples 仓

## 输入
- 仓库：samples (commit hash: <fill>)
- 文件数：<fill>
- 主要语言：C++ / Python / CMake

## 索引产物
- .codegraph/codegraph.db 大小：<fill> MB
- 总节点数：<fill>
- 总边数：<fill>
- 索引用时：<fill>

## 5 个关键能力评估

| 能力 | 测试方法 | 结果 | 评分 |
|---|---|---|---|
| 1. C++ 函数/类提取 | 数 operator/ 下任一样例的函数节点 | <fill> | ✅/⚠️/❌ |
| 2. 跨文件 include 解析 | 选一个 .cpp 看是否能跳到对应 .h | <fill> | ✅/⚠️/❌ |
| 3. 类继承关系 | KernelLauncher 类继承链能否查到 | <fill> | ✅/⚠️/❌ |
| 4. 函数调用图 | DataCopy 在样例中的调用点 | <fill> | ✅/⚠️/❌ |
| 5. MCP query 速度 | 启用 MCP 后查询响应时间 | <fill> ms | ✅/⚠️/❌ |

## 结论
- [ ] 通过（≥3 项 ✅）→ 继续 v2-α
- [ ] 部分可用 → 在 samples.yaml 用 entry_files 文件名引用，不依赖 CodeGraph 节点 ID
- [ ] 不可用 → 暂停后续 Task，与用户重审 §3.4
```

- [ ] **Step 5: 走查结论与用户确认**

把报告链接发给用户，得到"继续 v2-α"明确确认后才进 Task 1。

---

## Task 1：项目初始化（git + 目录骨架）

**Files:**
- Create: `/Users/justbin/Desktop/CannEx/.gitignore`
- Create: `/Users/justbin/Desktop/CannEx/build/`、`raw/docs/`、`raw/repos/`、`workspace/repos/`、`workspace/docs/`、`tests/`

- [ ] **Step 1: git init**

```bash
cd /Users/justbin/Desktop/CannEx
git init
git config user.name "$(git -C ~/project/CANN/PageIndex config user.name || echo cannex)"
git config user.email "$(git -C ~/project/CANN/PageIndex config user.email || echo cannex@local)"
```

- [ ] **Step 2: 创建 .gitignore**

```gitignore
# Raw 素材（本地落盘，体积大不入库）
raw/

# Python
__pycache__/
*.pyc
.venv/
*.egg-info/

# 日志和临时
logs/
*.log
*.pid

# CodeGraph 单仓索引产物（巨大，按需重建）
**/.codegraph/

# 系统
.DS_Store
```

- [ ] **Step 3: 创建目录骨架**

```bash
mkdir -p build raw/docs raw/repos workspace/docs workspace/repos tests
touch workspace/docs/.gitkeep workspace/repos/.gitkeep raw/docs/.gitkeep raw/repos/.gitkeep
```

- [ ] **Step 4: 初次提交**

```bash
git add .gitignore CLAUDE.md docs/ skills/ workspace/_meta.json workspace/*.json build_index.py trim_pdf.py
git status   # 确认 raw/ 和 .codegraph/ 不在列表
git commit -m "chore: v2-alpha 项目初始化与目录骨架"
```

Expected: 干净 commit，raw/ 与 .codegraph/ 被忽略。

---

## Task 2：迁移 workspace 布局，扩展 _meta.json schema

**Files:**
- Move: `workspace/717ca9ab-...json` → `workspace/docs/717ca9ab-...json`
- Move: `workspace/e8997a18-...json` → `workspace/docs/e8997a18-...json`
- Modify: `workspace/_meta.json`

- [ ] **Step 1: 移动现有 JSON 到 workspace/docs/**

```bash
cd /Users/justbin/Desktop/CannEx/workspace
mv 717ca9ab-c7bc-4cbb-8026-6e7089c0e4de.json docs/
mv e8997a18-9ac1-49ad-98ee-84483f43ffce.json docs/
ls docs/    # 验证两份在内
```

- [ ] **Step 2: 重写 _meta.json 为 v2 schema**

```json
{
  "version": "v2.0",
  "cann_version": "9.0.0",
  "last_updated": "2026-05-23",
  "docs": [
    {
      "doc_id": "717ca9ab-c7bc-4cbb-8026-6e7089c0e4de",
      "doc_name": "CANN社区版 9.0.0 软件安装 01.pdf",
      "category": "install",
      "audience": ["B"],
      "pages": 108,
      "priority": "P0",
      "path": "docs/717ca9ab-c7bc-4cbb-8026-6e7089c0e4de.json"
    },
    {
      "doc_id": "e8997a18-9ac1-49ad-98ee-84483f43ffce",
      "doc_name": "CANN社区版 9.0.0 Ascend C算子开发指南 技术部分 01_trimmed.pdf",
      "category": "operator_dev",
      "audience": ["A", "F"],
      "pages": 712,
      "priority": "P0",
      "path": "docs/e8997a18-9ac1-49ad-98ee-84483f43ffce.json"
    }
  ],
  "repos": []
}
```

注意：v1 的 `_meta.json` 是以 doc_id 为顶层 key 的字典；v2 改为 `docs[]` 数组，键名平铺到对象字段。

- [ ] **Step 3: 提交**

```bash
git add workspace/_meta.json workspace/docs/
git commit -m "refactor(workspace): 迁移文档 JSON 到 docs/ 子目录，_meta.json 升级到 v2 schema"
```

---

## Task 3：重写 cannex_doc.py（替换 cannex.py，加 source_type 字段）

**Files:**
- Create: `skills/ascend-c/tools/cannex_doc.py`
- Delete: `skills/ascend-c/tools/cannex.py`（Task 12 完成 SKILL 重写后再删）
- Create: `tests/test_cannex_doc.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_cannex_doc.py
import json
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).parent.parent / "skills/ascend-c/tools/cannex_doc.py"

def run(*args):
    r = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True)
    assert r.returncode == 0, f"CLI failed:\nSTDOUT={r.stdout}\nSTDERR={r.stderr}"
    return r.stdout

def test_list_outputs_audience_and_category():
    out = run("list")
    assert "operator_dev" in out, "list 必须显示 category"
    assert "[A" in out or "A," in out, "list 必须显示 audience"

def test_meta_returns_source_type_original():
    out = run("meta", "算子开发指南")
    payload = json.loads(out)
    assert payload["source_type"] == "original", "meta 必须标 source_type=original"

def test_pages_returns_source_type_original():
    out = run("pages", "软件安装", "5-6")
    payload = json.loads(out)
    assert isinstance(payload, list)
    for p in payload:
        assert p["source_type"] == "original"

def test_unknown_doc_helpful_error():
    r = subprocess.run([sys.executable, str(CLI), "meta", "不存在的文档名"], capture_output=True, text=True)
    assert r.returncode != 0
    assert "可用文档" in r.stderr or "可用文档" in r.stdout
```

- [ ] **Step 2: 验证测试失败**

```bash
cd /Users/justbin/Desktop/CannEx
~/project/CANN/PageIndex/.venv/bin/python -m pytest tests/test_cannex_doc.py -v
```

Expected: 4 个测试全部失败（cannex_doc.py 还不存在）。

- [ ] **Step 3: 实现 cannex_doc.py**

```python
#!/usr/bin/env python3
"""
CannEx 文档检索 CLI（v2）

供 Skill 使用。所有返回都附带 source_type 字段：
  - "original" : 原文抽取（直接给用户）
  - "metadata" : 元信息（来自 _meta.json，非原文）

Usage:
  cannex_doc.py list
  cannex_doc.py meta <name_or_id>
  cannex_doc.py structure <name_or_id>
  cannex_doc.py pages <name_or_id> <range>          # range: 5-7 | 3,8 | 12
  cannex_doc.py search_api <api_name>               # 占位：按 API 名定位（v2-β 实现）
"""
import json
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[3] / "workspace"
META_FILE = WORKSPACE / "_meta.json"


def load_meta() -> dict:
    if not META_FILE.exists():
        raise SystemExit(f"_meta.json 不存在: {META_FILE}")
    with open(META_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_doc(meta: dict, key: str) -> dict:
    docs = meta.get("docs", [])
    for d in docs:
        if d["doc_id"] == key:
            return d
    matches = [d for d in docs if key in d.get("doc_name", "")]
    if not matches:
        avail = "\n".join(f"  - {d['doc_name']}" for d in docs)
        raise SystemExit(f"未找到文档 '{key}'\n可用文档:\n{avail}")
    if len(matches) > 1:
        names = "\n".join(f"  - {d['doc_name']}" for d in matches)
        raise SystemExit(f"'{key}' 匹配多个文档:\n{names}")
    return matches[0]


def load_doc_json(doc_entry: dict) -> dict:
    path = WORKSPACE / doc_entry["path"]
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_pages(spec: str) -> set[int]:
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return out


def cmd_list():
    meta = load_meta()
    docs = meta.get("docs", [])
    print(f"workspace : {WORKSPACE}")
    print(f"cann_ver  : {meta.get('cann_version')}")
    print(f"docs      : {len(docs)}")
    print()
    print(f"{'doc_name':<60}  {'category':<15}  {'audience':<10}  {'pages':>6}")
    print("-" * 100)
    for d in docs:
        audience = ",".join(d.get("audience", [])) or "-"
        print(f"{d['doc_name'][:60]:<60}  {d.get('category','-'):<15}  [{audience:<8}]  {d.get('pages','?'):>6}")


def cmd_meta(key: str):
    meta = load_meta()
    d = resolve_doc(meta, key)
    doc = load_doc_json(d)
    print(json.dumps({
        "source_type": "original",
        "doc_id": d["doc_id"],
        "doc_name": d["doc_name"],
        "category": d.get("category"),
        "audience": d.get("audience"),
        "pages": d.get("pages"),
        "doc_description": doc.get("doc_description"),
    }, ensure_ascii=False, indent=2))


def cmd_structure(key: str):
    meta = load_meta()
    d = resolve_doc(meta, key)
    doc = load_doc_json(d)
    print(json.dumps({
        "source_type": "metadata",   # 结构是元信息，不是原文段落
        "doc_id": d["doc_id"],
        "doc_name": d["doc_name"],
        "structure": doc.get("structure", []),
    }, ensure_ascii=False, indent=2))


def cmd_pages(key: str, range_spec: str):
    meta = load_meta()
    d = resolve_doc(meta, key)
    doc = load_doc_json(d)
    pages = doc.get("pages") or []
    if not pages:
        raise SystemExit("该文档无可用页面正文")
    wanted = parse_pages(range_spec)
    out = []
    for p in pages:
        if p.get("page") in wanted:
            out.append({**p, "source_type": "original"})
    if not out:
        raise SystemExit(f"指定范围内无页面: {range_spec}")
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_search_api(api_name: str):
    # v2-α 占位：先按文档结构里的标题做朴素 contains 匹配
    meta = load_meta()
    results = []
    for d in meta.get("docs", []):
        doc = load_doc_json(d)
        for node in doc.get("structure", []):
            if api_name.lower() in node.get("title", "").lower():
                results.append({
                    "source_type": "metadata",
                    "doc_name": d["doc_name"],
                    "doc_id": d["doc_id"],
                    "node_title": node.get("title"),
                    "start_index": node.get("start_index"),
                    "end_index": node.get("end_index"),
                })
    print(json.dumps(results, ensure_ascii=False, indent=2))


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    cmd, args = sys.argv[1], sys.argv[2:]
    if   cmd == "list":                          cmd_list()
    elif cmd == "meta"       and len(args) == 1: cmd_meta(args[0])
    elif cmd == "structure"  and len(args) == 1: cmd_structure(args[0])
    elif cmd == "pages"      and len(args) == 2: cmd_pages(args[0], args[1])
    elif cmd == "search_api" and len(args) == 1: cmd_search_api(args[0])
    else:
        print(__doc__); sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 验证测试通过**

```bash
~/project/CANN/PageIndex/.venv/bin/python -m pytest tests/test_cannex_doc.py -v
```

Expected: 4 passed。

- [ ] **Step 5: 提交**

```bash
git add skills/ascend-c/tools/cannex_doc.py tests/test_cannex_doc.py
git commit -m "feat(cannex_doc): v2 schema 适配 + source_type 字段标注"
```

注意：`cannex.py` 暂保留，等 Task 12 SKILL 完成迁移后再删。

---

## Task 4：写 build/repos.yaml + build/docs.yaml 配置

**Files:**
- Create: `build/repos.yaml`
- Create: `build/docs.yaml`

- [ ] **Step 1: 写 repos.yaml**

```yaml
# CannEx 代码仓配置（agent 不读，仅离线管道读）
repos:
  - name: samples
    url: https://gitee.com/ascend/samples.git
    ref: master
    audience: [A, F]
    category: operator_samples
    priority: P0
    enabled: true
    # 本地落点（绝对路径或相对工作目录）；与 raw/repos/<name>/ 对齐
    local_path: raw/repos/samples

  - name: cann-ops-adv
    url: https://gitee.com/ascend/cann-ops-adv.git
    ref: v9.0.0
    audience: [A]
    category: operator_advanced
    priority: P0
    enabled: false       # v2-α 不开，v2-β 启用
    local_path: raw/repos/cann-ops-adv
```

- [ ] **Step 2: 写 docs.yaml**

```yaml
# CannEx 文档配置
docs:
  - name: install
    file: "CANN社区版 9.0.0 软件安装 01.pdf"
    local_path: raw/docs/CANN社区版 9.0.0 软件安装 01.pdf
    version: 9.0.0
    category: install
    audience: [B]
    priority: P0
    enabled: true

  - name: operator_dev
    file: "CANN社区版 9.0.0 Ascend C算子开发指南 技术部分 01_trimmed.pdf"
    local_path: raw/docs/CANN社区版 9.0.0 Ascend C算子开发指南 技术部分 01_trimmed.pdf
    version: 9.0.0
    category: operator_dev
    audience: [A, F]
    priority: P0
    enabled: true
```

注意：v2-α 阶段文档**不**做自动下载（CANN 文档需登录），仅记录"应放在哪里"，由用户手动落到 raw/docs/。

- [ ] **Step 3: 提交**

```bash
git add build/repos.yaml build/docs.yaml
git commit -m "feat(build): 代码仓与文档源配置"
```

---

## Task 5：实现 build/sync_sources.py

**Files:**
- Create: `build/sync_sources.py`
- Create: `tests/test_sync_sources.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_sync_sources.py
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "build/sync_sources.py"

def test_dry_run_lists_enabled_repos_and_docs(tmp_path, monkeypatch):
    """--dry-run 只打印不执行；列出 enabled=true 的项目"""
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert r.returncode == 0, r.stderr
    assert "samples" in r.stdout
    assert "cann-ops-adv" not in r.stdout, "enabled=false 的仓不应出现"
    assert "install" in r.stdout
    assert "operator_dev" in r.stdout

def test_reports_missing_docs_clearly():
    """docs 文件不存在时报告清楚（不报错退出，提示用户手动放置）"""
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--docs-only", "--dry-run"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert r.returncode == 0
    # 至少打印每份文档的 enabled 状态
    assert "install" in r.stdout
```

- [ ] **Step 2: 验证测试失败**

```bash
~/project/CANN/PageIndex/.venv/bin/python -m pytest tests/test_sync_sources.py -v
```

Expected: 失败（脚本不存在）。

- [ ] **Step 3: 实现 sync_sources.py**

```python
#!/usr/bin/env python3
"""
拉取/更新 CannEx 原始素材

读取 build/repos.yaml + build/docs.yaml，对每个 enabled=true 项目：
  - repo: 不存在 → git clone --branch <ref>；已存在 → git fetch + git checkout <ref>
  - doc:  检查 raw/docs/<file> 是否存在；不存在则报告（不自动下载，需用户手动放置）

输出：变更摘要（哪些仓更新了、哪些文档缺失），供后续 build_docs / build_repos 决定增量。
"""
import argparse
import subprocess
import sys
from pathlib import Path

import yaml  # PyYAML，PageIndex venv 中通常已有；若没有 pip install pyyaml

ROOT = Path(__file__).resolve().parent.parent
REPOS_YAML = ROOT / "build/repos.yaml"
DOCS_YAML = ROOT / "build/docs.yaml"


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def sync_one_repo(repo: dict, dry: bool) -> str:
    name = repo["name"]
    local = ROOT / repo["local_path"]
    url = repo["url"]
    ref = repo.get("ref", "master")

    if dry:
        return f"[DRY] repo {name}: ref={ref} → {local}"

    if not local.exists():
        local.parent.mkdir(parents=True, exist_ok=True)
        print(f"[clone] {name} from {url}")
        subprocess.check_call(["git", "clone", "--branch", ref, url, str(local)])
        return f"[CLONED] {name}@{ref}"
    else:
        print(f"[fetch] {name}")
        subprocess.check_call(["git", "-C", str(local), "fetch", "--all", "--tags"])
        subprocess.check_call(["git", "-C", str(local), "checkout", ref])
        head = subprocess.check_output(
            ["git", "-C", str(local), "rev-parse", "HEAD"], text=True
        ).strip()
        return f"[UPDATED] {name}@{ref} ({head[:8]})"


def sync_one_doc(doc: dict, dry: bool) -> str:
    name = doc["name"]
    local = ROOT / doc["local_path"]
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
```

- [ ] **Step 4: 安装 pyyaml（若 venv 缺）并跑测试**

```bash
~/project/CANN/PageIndex/.venv/bin/python -c "import yaml" 2>&1 || \
  ~/project/CANN/PageIndex/.venv/bin/pip install pyyaml

~/project/CANN/PageIndex/.venv/bin/python -m pytest tests/test_sync_sources.py -v
```

Expected: 2 passed。

- [ ] **Step 5: 实跑一次 dry-run 验证**

```bash
~/project/CANN/PageIndex/.venv/bin/python build/sync_sources.py --dry-run
```

Expected: 打印 samples（enabled）+ 两份文档，不出现 cann-ops-adv。

- [ ] **Step 6: 提交**

```bash
git add build/sync_sources.py tests/test_sync_sources.py
git commit -m "feat(build): sync_sources.py 拉取/更新原始素材"
```

---

## Task 6：把 build_index.py 改写为 build/build_docs.py（配置驱动）

**Files:**
- Create: `build/build_docs.py`
- Delete: `build_index.py`（保留到 Task 完结时删，先 git mv 演进）
- Modify: `workspace/_meta.json`（脚本自动更新）

- [ ] **Step 1: 实现 build/build_docs.py**

```python
#!/usr/bin/env python3
"""
build_docs.py — 按 docs.yaml 配置批量建文档树（增量）

行为：
  - 读 build/docs.yaml 中 enabled=true 的文档
  - 对每个文档：若 _meta.json 中已存在同 doc_name 则跳过（PageIndex 自带去重）
  - 否则调用 PageIndex 建树到 workspace/docs/<doc_id>.json
  - 完成后更新 workspace/_meta.json 的 docs[]

复用 v1 的 build_index.py 思路。
"""
import json
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
PAGEINDEX_DIR = Path.home() / "project" / "CANN" / "PageIndex"
load_dotenv(PAGEINDEX_DIR / ".env")
sys.path.insert(0, str(PAGEINDEX_DIR))
from pageindex import PageIndexClient  # noqa: E402

WORKSPACE = ROOT / "workspace"
DOCS_DIR = WORKSPACE / "docs"
META_FILE = WORKSPACE / "_meta.json"
DOCS_YAML = ROOT / "build/docs.yaml"


def load_meta() -> dict:
    if META_FILE.exists():
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    return {"version": "v2.0", "cann_version": "9.0.0", "docs": [], "repos": []}


def save_meta(meta: dict):
    META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def existing_doc_id(meta: dict, doc_name: str) -> str | None:
    for d in meta.get("docs", []):
        if d.get("doc_name") == doc_name:
            return d["doc_id"]
    return None


def move_built_json_to_docs_subdir(doc_id: str):
    """PageIndex 默认输出到 workspace/<doc_id>.json；我们要 docs/<doc_id>.json"""
    src = WORKSPACE / f"{doc_id}.json"
    dst = DOCS_DIR / f"{doc_id}.json"
    if src.exists() and not dst.exists():
        src.rename(dst)


def build_one(doc_cfg: dict, meta: dict) -> dict | None:
    pdf_path = ROOT / doc_cfg["local_path"]
    if not pdf_path.exists():
        print(f"[skip] PDF 不存在: {pdf_path}")
        return None

    doc_name = pdf_path.name
    eid = existing_doc_id(meta, doc_name)
    if eid:
        print(f"[skip] 已存在 doc_name='{doc_name}' (doc_id={eid})")
        return None

    print(f"[build] {doc_name}")
    client = PageIndexClient(workspace=str(WORKSPACE))
    t0 = time.time()
    doc_id = client.index(str(pdf_path))
    print(f"[done] {doc_name} → {doc_id}  用时 {(time.time()-t0)/60:.1f} 分钟")

    move_built_json_to_docs_subdir(doc_id)

    entry = {
        "doc_id": doc_id,
        "doc_name": doc_name,
        "category": doc_cfg.get("category"),
        "audience": doc_cfg.get("audience", []),
        "pages": None,  # 由 PageIndex 自带的 page_count 填入
        "priority": doc_cfg.get("priority"),
        "path": f"docs/{doc_id}.json",
    }
    # 补 page_count
    json_data = json.loads((DOCS_DIR / f"{doc_id}.json").read_text(encoding="utf-8"))
    entry["pages"] = json_data.get("page_count")
    return entry


def main():
    cfg = yaml.safe_load(DOCS_YAML.read_text(encoding="utf-8"))
    meta = load_meta()
    added = 0
    for d in cfg.get("docs", []):
        if not d.get("enabled"):
            continue
        entry = build_one(d, meta)
        if entry:
            meta["docs"].append(entry)
            added += 1
    if added:
        save_meta(meta)
        print(f"\n[summary] 新增 {added} 份文档")
    else:
        print("\n[summary] 无新增")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑一次（应该全跳过，因为现有 2 份文档已经在 _meta.json 里）**

```bash
~/project/CANN/PageIndex/.venv/bin/python build/build_docs.py
```

Expected: 输出"[skip] 已存在 doc_name=..." x2，summary: 无新增。

- [ ] **Step 3: 把 build_index.py 删掉**

```bash
git rm build_index.py
```

- [ ] **Step 4: 提交**

```bash
git add build/build_docs.py
git commit -m "refactor(build): build_docs.py 配置驱动批量建文档树，删除旧 build_index.py"
```

---

## Task 7：实现 build/build_repos.py — CodeGraph 集成部分

**Files:**
- Create: `build/build_repos.py`（先只放 CodeGraph 部分，Task 8 加 bootstrap）

- [ ] **Step 1: 实现 CodeGraph 索引步骤**

```python
#!/usr/bin/env python3
"""
build_repos.py — 对 enabled=true 的代码仓建索引 + 生成元信息

阶段 1（本 Task）：codegraph init
阶段 2（Task 8）：bootstrap repo_card.yaml + samples.yaml
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "workspace"
REPOS_DIR = WORKSPACE / "repos"
REPOS_YAML = ROOT / "build/repos.yaml"


def codegraph_init(repo_local: Path) -> dict:
    """在 repo_local 跑 codegraph init，返回索引产物路径"""
    cg_src = repo_local / ".codegraph"
    if cg_src.exists():
        print(f"[skip] 已有索引: {cg_src}")
    else:
        print(f"[codegraph init] {repo_local}")
        # codegraph init 默认在当前目录建 .codegraph/
        subprocess.check_call(["codegraph", "init", "--yes"], cwd=str(repo_local))

    return {"db": cg_src / "codegraph.db", "src": cg_src}


def sync_codegraph_to_workspace(repo_name: str, cg_src: Path):
    """把 raw/repos/<name>/.codegraph/ 复制到 workspace/repos/<name>/.codegraph/"""
    dst = REPOS_DIR / repo_name / ".codegraph"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(cg_src, dst)
    print(f"[synced] {dst}")


def process_repo(repo: dict, only_codegraph: bool):
    name = repo["name"]
    local = ROOT / repo["local_path"]
    if not local.exists():
        print(f"[skip] {name}: local_path 不存在 {local}（先跑 sync_sources.py）")
        return

    cg = codegraph_init(local)
    sync_codegraph_to_workspace(name, cg["src"])

    if only_codegraph:
        return
    # Task 8 会加 bootstrap


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", help="只处理指定仓（按 name）")
    p.add_argument("--only-codegraph", action="store_true",
                   help="只跑 codegraph init，不做 bootstrap")
    args = p.parse_args()

    cfg = yaml.safe_load(REPOS_YAML.read_text(encoding="utf-8"))
    repos = [r for r in cfg.get("repos", []) if r.get("enabled")]
    if args.repo:
        repos = [r for r in repos if r["name"] == args.repo]
        if not repos:
            sys.exit(f"未找到 enabled 仓: {args.repo}")

    for r in repos:
        process_repo(r, args.only_codegraph)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 在 samples 仓跑通**

```bash
# 前提：sync_sources.py 已经把 samples clone 到 raw/repos/samples
~/project/CANN/PageIndex/.venv/bin/python build/build_repos.py --repo samples --only-codegraph
ls workspace/repos/samples/.codegraph/
```

Expected: 看到 `codegraph.db` 之类文件。

- [ ] **Step 3: 提交**

```bash
git add build/build_repos.py
git commit -m "feat(build): build_repos.py CodeGraph 索引阶段"
```

---

## Task 8：扩展 build_repos.py — LLM bootstrap repo_card + samples.yaml

**Files:**
- Modify: `build/build_repos.py`（追加 bootstrap 逻辑）
- Create: `build/prompts/bootstrap_repo_card.md`
- Create: `build/prompts/bootstrap_samples.md`

- [ ] **Step 1: 创建提示词模板**

`build/prompts/bootstrap_repo_card.md`:

```markdown
你是 CANN 技术专家，请基于下列素材生成代码仓的"定位卡片"。

## 仓库信息
- 仓库名：{repo_name}
- URL：{repo_url}
- 默认分支/版本：{ref}

## 素材
### README 前 4000 字符
{readme_excerpt}

### 一级目录列表
{top_dirs}

## 输出要求
严格按以下 YAML schema 输出（用 ```yaml 包裹），所有字段必须填，不确定的写 "TBD: <你的猜测>"。

```yaml
repo_name: {repo_name}
repo_url: {repo_url}
audience: []         # 从 [A, B, F] 中选 1-3 个
category: ""
tagline: ""          # 一句话定位（≤30 字）
scenarios:           # 3-5 条
  - ""
not_for:             # 2-3 条
  - ""
key_paths:           # 3-6 条
  - path: ""
    desc: ""
contribution:
  guide_path: ""
  pr_template: ""
maintained_by: cannex_team
last_reviewed: "{today}"
```

不要解释，只输出 YAML。
```

`build/prompts/bootstrap_samples.md`:

```markdown
你是 CANN 算子开发专家。请扫描下列样例目录，为每个独立样例生成一条 samples.yaml 条目。

## 仓库
{repo_name}

## 样例目录列表（候选样例）
{sample_dirs}

## 每个样例可读到的文件名
{sample_files_per_dir}

## 输出要求
严格按以下 YAML schema 输出 samples: 列表，包裹在 ```yaml 中。

每条字段都必须填；不确定的填 "TBD: <你的猜测>"，便于人工 review。

```yaml
samples:
  - id: <kebab-case 唯一 ID>
    name: <可读名>
    path: <相对仓根路径>
    entry_files: [<.cpp/.py 文件名>]
    computation_pattern: <vector | cube | vector_to_cube | cube_to_vector | fusion | TBD>
    apis_used: [<API 名清单>]
    complexity: <beginner | intermediate | expert | TBD>
    teaches:
      - <要点>
    recommendation_reason: "<一句话，为什么推这个>"
    limitations:
      - <已知局限或 "TBD">
    related_docs: []     # 关联文档章节，初稿留空，人工补
```

不要解释，只输出 YAML。
```

- [ ] **Step 2: 在 build_repos.py 追加 bootstrap 部分**

在 `build_repos.py` 顶部追加 import：

```python
import json
import os
from datetime import date

import litellm  # 复用 PageIndex venv 中的 litellm
```

追加函数：

```python
def call_llm(prompt: str) -> str:
    """调 DeepSeek（与 PageIndex 同模型）生成内容"""
    resp = litellm.completion(
        model="deepseek/deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
        max_tokens=4096,
        timeout=120,
    )
    return resp.choices[0].message.content


def extract_yaml_block(text: str) -> str:
    """从 LLM 输出中抠出 ```yaml ... ``` 块；找不到就返回原文"""
    import re
    m = re.search(r"```yaml\s*\n(.*?)```", text, re.DOTALL)
    return m.group(1) if m else text


def render_template(template_path: Path, **kwargs) -> str:
    text = template_path.read_text(encoding="utf-8")
    for k, v in kwargs.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def bootstrap_repo_card(repo: dict, local: Path) -> Path:
    """生成 repo_card.yaml 初稿；若已存在则不覆盖"""
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
        f"  - {p.name}/" for p in local.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )

    prompt = render_template(
        ROOT / "build/prompts/bootstrap_repo_card.md",
        repo_name=repo["name"],
        repo_url=repo["url"],
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


def collect_sample_dirs(local: Path, max_count: int = 20) -> list[Path]:
    """启发式找候选样例目录：operator/* | samples/* | examples/*"""
    candidates = []
    for top in ["operator", "operators", "samples", "examples"]:
        d = local / top
        if d.exists():
            candidates.extend(p for p in d.iterdir() if p.is_dir())
    return candidates[:max_count]


def bootstrap_samples(repo: dict, local: Path) -> Path:
    out = REPOS_DIR / repo["name"] / "samples.yaml"
    if out.exists():
        print(f"[skip samples] {out} 已存在，不覆盖")
        return out

    sample_dirs = collect_sample_dirs(local)
    if not sample_dirs:
        print(f"[skip samples] 未在常见目录下发现样例")
        out.write_text("samples: []\n", encoding="utf-8")
        return out

    dirs_text = "\n".join(f"  - {p.relative_to(local)}" for p in sample_dirs)
    files_text = ""
    for d in sample_dirs:
        files = [f.name for f in d.rglob("*") if f.is_file()][:10]
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
    out.write_text(yaml_text, encoding="utf-8")
    print(f"[written] {out}  (请人工 review TBD 字段)")
    return out
```

修改 `process_repo` 中 `if only_codegraph: return` 之后：

```python
    bootstrap_repo_card(repo, local)
    bootstrap_samples(repo, local)
```

- [ ] **Step 3: 跑 samples 仓的完整 bootstrap**

```bash
~/project/CANN/PageIndex/.venv/bin/python build/build_repos.py --repo samples
```

Expected: 生成 `workspace/repos/samples/repo_card.yaml` + `samples.yaml`（均为 LLM 初稿，含 TBD）。

- [ ] **Step 4: 人工 review 两份 YAML**

⏸️ **暂停点**：把两份 yaml 打开过一遍，针对 TBD 字段补正确值。重点：
- `repo_card.yaml`：audience、category、tagline 准确性
- `samples.yaml`：每条样例的 `computation_pattern`、`complexity`、`recommendation_reason`

至少 5 条样例的字段必须完整无 TBD。

- [ ] **Step 5: 提交**

```bash
git add build/build_repos.py build/prompts/ workspace/repos/samples/
git commit -m "feat(build): build_repos bootstrap repo_card + samples.yaml 半自动生成"
```

---

## Task 9：实现 tools/cannex_repo.py

**Files:**
- Create: `skills/ascend-c/tools/cannex_repo.py`
- Create: `tests/test_cannex_repo.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_cannex_repo.py
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "skills/ascend-c/tools/cannex_repo.py"

def run(*args):
    r = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True)
    assert r.returncode == 0, f"CLI failed:\nSTDOUT={r.stdout}\nSTDERR={r.stderr}"
    return r.stdout

def test_list_shows_samples_repo():
    out = run("list")
    assert "samples" in out

def test_card_returns_yaml_content_as_metadata():
    out = run("card", "samples")
    data = json.loads(out)
    assert data["source_type"] == "metadata"
    assert data["repo_name"] == "samples"
    assert "tagline" in data

def test_list_samples_filter_by_pattern():
    """按 computation_pattern 筛"""
    out = run("list_samples", "samples", "--pattern", "vector")
    data = json.loads(out)
    assert data["source_type"] == "metadata"
    # 至少一个样例 pattern 含 vector
    assert len(data["samples"]) >= 1
    for s in data["samples"]:
        assert "vector" in s["computation_pattern"]

def test_code_returns_file_content_as_original():
    """取代码片段：source_type=original"""
    # 假设 samples.yaml 中至少一个 sample id 存在
    list_out = json.loads(run("list_samples", "samples"))
    sample_id = list_out["samples"][0]["id"]
    out = run("code", "samples", sample_id)
    data = json.loads(out)
    assert data["source_type"] == "original"
    assert "files" in data
    assert len(data["files"]) >= 1
    assert "content" in data["files"][0]
```

- [ ] **Step 2: 验证失败**

```bash
~/project/CANN/PageIndex/.venv/bin/python -m pytest tests/test_cannex_repo.py -v
```

Expected: 4 个失败。

- [ ] **Step 3: 实现 cannex_repo.py**

```python
#!/usr/bin/env python3
"""
CannEx 代码仓查询 CLI（v2）

Usage:
  cannex_repo.py list
  cannex_repo.py card <repo_name>
  cannex_repo.py list_samples <repo_name> [--pattern X] [--complexity Y]
  cannex_repo.py code <repo_name> <sample_id> [--skeleton]
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKSPACE = ROOT / "workspace"
META_FILE = WORKSPACE / "_meta.json"
REPOS_DIR = WORKSPACE / "repos"
RAW_REPOS_DIR = ROOT / "raw/repos"   # 取代码原文用


def load_meta() -> dict:
    return json.loads(META_FILE.read_text(encoding="utf-8"))


def list_repos() -> list[str]:
    if not REPOS_DIR.exists():
        return []
    return sorted(p.name for p in REPOS_DIR.iterdir() if p.is_dir())


def load_card(name: str) -> dict:
    f = REPOS_DIR / name / "repo_card.yaml"
    if not f.exists():
        raise SystemExit(f"repo_card 不存在: {f}")
    return yaml.safe_load(f.read_text(encoding="utf-8"))


def load_samples(name: str) -> list[dict]:
    f = REPOS_DIR / name / "samples.yaml"
    if not f.exists():
        return []
    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    return data.get("samples", [])


def cmd_list():
    repos = list_repos()
    print(f"workspace: {REPOS_DIR}\n")
    if not repos:
        print("无已索引代码仓。先跑 build/build_repos.py。")
        return
    print(f"{'repo_name':<25}  has_card  has_samples  has_codegraph")
    print("-" * 75)
    for n in repos:
        c = (REPOS_DIR / n / "repo_card.yaml").exists()
        s = (REPOS_DIR / n / "samples.yaml").exists()
        g = (REPOS_DIR / n / ".codegraph").exists()
        print(f"{n:<25}  {'✓' if c else '✗':<8}  {'✓' if s else '✗':<11}  {'✓' if g else '✗'}")


def cmd_card(name: str):
    card = load_card(name)
    print(json.dumps({"source_type": "metadata", **card}, ensure_ascii=False, indent=2))


def cmd_list_samples(name: str, pattern: str | None, complexity: str | None):
    samples = load_samples(name)
    filtered = []
    for s in samples:
        if pattern and pattern not in s.get("computation_pattern", ""):
            continue
        if complexity and s.get("complexity") != complexity:
            continue
        filtered.append(s)
    print(json.dumps({
        "source_type": "metadata",
        "repo": name,
        "filter": {"pattern": pattern, "complexity": complexity},
        "count": len(filtered),
        "samples": filtered,
    }, ensure_ascii=False, indent=2))


def cmd_code(name: str, sample_id: str, skeleton: bool):
    samples = load_samples(name)
    sample = next((s for s in samples if s.get("id") == sample_id), None)
    if not sample:
        raise SystemExit(f"未找到 sample id={sample_id} 在 repo={name}")

    repo_root = RAW_REPOS_DIR / name
    if not repo_root.exists():
        raise SystemExit(f"raw 代码不存在: {repo_root}（先跑 sync_sources.py）")

    sample_path = repo_root / sample["path"]
    entry_files = sample.get("entry_files", [])

    files_out = []
    for fname in entry_files:
        fpath = sample_path / fname
        if not fpath.exists():
            files_out.append({"file": fname, "error": "not_found"})
            continue
        content = fpath.read_text(encoding="utf-8", errors="ignore")
        if skeleton:
            # 简易骨架：保留前 50 行，便于上下文受控
            lines = content.splitlines()
            content = "\n".join(lines[:50]) + ("\n... (truncated)" if len(lines) > 50 else "")
        files_out.append({
            "file": fname,
            "path_in_repo": str((sample_path / fname).relative_to(repo_root)),
            "content": content,
        })

    print(json.dumps({
        "source_type": "original",
        "repo": name,
        "sample_id": sample_id,
        "sample_meta_source": "samples.yaml",
        "files": files_out,
    }, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    s = sub.add_parser("card"); s.add_argument("repo")
    s = sub.add_parser("list_samples"); s.add_argument("repo"); s.add_argument("--pattern"); s.add_argument("--complexity")
    s = sub.add_parser("code"); s.add_argument("repo"); s.add_argument("sample_id"); s.add_argument("--skeleton", action="store_true")
    args = p.parse_args()

    if   args.cmd == "list":         cmd_list()
    elif args.cmd == "card":         cmd_card(args.repo)
    elif args.cmd == "list_samples": cmd_list_samples(args.repo, args.pattern, args.complexity)
    elif args.cmd == "code":         cmd_code(args.repo, args.sample_id, args.skeleton)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 验证测试通过**

```bash
~/project/CANN/PageIndex/.venv/bin/python -m pytest tests/test_cannex_repo.py -v
```

Expected: 4 passed。如失败，检查 samples.yaml 中是否有 vector 模式样例 / entry_files 是否真实存在。

- [ ] **Step 5: 提交**

```bash
git add skills/ascend-c/tools/cannex_repo.py tests/test_cannex_repo.py
git commit -m "feat(cannex_repo): 代码仓查询 CLI（list/card/list_samples/code）"
```

---

## Task 10：写 monthly_update.sh 编排

**Files:**
- Create: `build/monthly_update.sh`
- Create: `reports/.gitkeep`

- [ ] **Step 1: 写脚本**

```bash
#!/usr/bin/env bash
# CannEx 月度更新管线
#
# 用法：bash build/monthly_update.sh [--dry-run]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$HOME/project/CANN/PageIndex/.venv/bin/python"
REPORT_DIR="$ROOT/reports"
REPORT="$REPORT_DIR/$(date +%Y%m).md"

DRY=""
if [[ "${1:-}" == "--dry-run" ]]; then DRY="--dry-run"; fi

mkdir -p "$REPORT_DIR"

{
  echo "# CannEx 月度更新报告"
  echo
  echo "- 日期：$(date +%Y-%m-%d)"
  echo "- 工作目录：$ROOT"
  echo
  echo "## 1. sync_sources"
  echo '```'
  $VENV_PY "$ROOT/build/sync_sources.py" $DRY 2>&1
  echo '```'
  echo
  echo "## 2. build_docs"
  echo '```'
  $VENV_PY "$ROOT/build/build_docs.py" 2>&1
  echo '```'
  echo
  echo "## 3. build_repos"
  echo '```'
  $VENV_PY "$ROOT/build/build_repos.py" 2>&1
  echo '```'
  echo
  echo "## 4. 后续人工动作"
  echo "- 检查 workspace/repos/*/{repo_card,samples}.yaml 是否有 TBD 字段"
  echo "- review 并提交 workspace/ 与 reports/ 下变更"
} | tee "$REPORT"

echo
echo "[done] 报告：$REPORT"
```

- [ ] **Step 2: 加可执行 + 跑一次 dry-run**

```bash
chmod +x build/monthly_update.sh
bash build/monthly_update.sh --dry-run
```

Expected: 生成 `reports/YYYYMM.md`，里面包含 sync_sources dry-run、build_docs 与 build_repos 的输出（这两个不支持 --dry-run，会实际执行但因素材未变会都跳过）。

- [ ] **Step 3: 提交**

```bash
mkdir -p reports && touch reports/.gitkeep
git add build/monthly_update.sh reports/.gitkeep reports/*.md
git commit -m "feat(build): monthly_update.sh 编排离线管道 + 报告归档"
```

---

## Task 11：写 references/answer-styles.md（教学风格下沉）

**Files:**
- Create: `skills/ascend-c/references/answer-styles.md`

- [ ] **Step 1: 写文件**

```markdown
# CannEx 教学风格细则（answer-styles）

> 本文件由 SKILL.md 在"应答模式 = 教学引导"时按需 Read。
> 直接答 / 导航 模式可忽略。

---

## 一、沟通基调

- **结论先行**：第一句给核心答案，再展开
- **中文回复**，技术术语保留英文：`Pipeline`、`Tiling`、`Double Buffer`、`TPipe`
- 专业但不冰冷：准确技术语言 + 类比 + 示例
- 避免无意义开场白（"当然"、"好的好的"）

## 二、类比桥接（按用户背景信号自动选）

| 用户语境信号 | 桥接策略 |
|---|---|
| 提到 PyTorch / TensorFlow | 用框架算子做类比："torch.add() 背后就是一个 Add 算子" |
| 提到 CUDA / GPU 编程 | 用 CUDA 概念做对比映射："TPosition 类似 shared memory 但更抽象" |
| 提到 C++ / 多线程 | 用生产者-消费者等模式类比 |
| 无明显背景信号 | 用生活化比喻：内存层级 = "冰箱→案板→炒锅→盘子" |

## 三、术语首次出现时内联解释

格式：**术语**（一句话解释）

例：
> 数据通过 **TPipe**（Ascend C 的流水线管理框架，负责协调数据搬运和计算的执行顺序）进行编排。

## 四、回答结构

```
1. 一句话结论（原文抽取，引用）
2. ⚠️ 综合理解展开（类比、推理、梳理）
3. 原文片段引用（代码/段落）
4. 来源标注
5. （可选）下一步建议
```

## 五、内隐自适应深度（不显式分级）

| 问题信号 | 用户隐含层级 | 应答策略 |
|---|---|---|
| "算子是什么"、"Pipeline 是什么"、"为什么不能用 PyTorch" | Beginner | 从全景图讲起，用类比，控制信息量到 1 个新概念/回合 |
| "Double Buffer 没提速"、"Tiling 怎么算"、"UB 不够用" | Intermediate | 跳过基础铺垫，直接讲性能模型/内存规划 |
| "L0A Bank 冲突"、"CO2→VECIN 衔接"、"静态 Tensor 收益" | Expert | 给精确技术回答，不啰嗦基础 |

**绝不**主动问"你是初级还是高级"——根据问题判断即可。

## 六、什么时候给"下一步建议"

| 情境 | 是否给下一步 |
|---|---|
| 用户问的是事实查询（"DataCopy 的参数有哪些"） | 否 |
| 用户表现出困惑或希望深入（"我还是没明白"） | 是（更详细展开，不是新方向） |
| 用户问的是踩坑（"为什么报错"） | 否（给解决方案即可） |
| 用户问的是概念入门（"Pipeline 是什么"） | 是（建议下一站，如 Tiling） |

下一步格式：
> "想继续了解 XX 吗？还是你这边还有别的问题？"
```

- [ ] **Step 2: 提交**

```bash
git add skills/ascend-c/references/answer-styles.md
git commit -m "feat(skill): 教学风格细则下沉到 references/answer-styles.md"
```

---

## Task 12：重写 SKILL.md 到 v2（~100 行）

**Files:**
- Modify (rewrite): `skills/ascend-c/SKILL.md`
- Delete: `skills/ascend-c/tools/cannex.py`

- [ ] **Step 1: 重写 SKILL.md**

完整新版内容：

```markdown
---
name: ascend-c
description: |
  CannEx — 昇腾 CANN 开发者知识助手。覆盖 Ascend C 算子开发、CANN 应用开发、
  代码仓导航三类场景。典型触发：算子原理/Pipeline/Tiling/UB 等技术问题；
  CANN 环境安装/推理 demo/API 调用；查 CANN 开源仓的实现样例与贡献入口。
---

# CannEx — 昇腾 CANN 开发者知识助手

你是 **CannEx**，按用户角色与意图自适应切换应答模式的 CANN 知识助手。

---

## 一、知识源

- 文档：`workspace/docs/<doc_id>.json`（PageIndex 树）
- 代码仓：`workspace/repos/<repo>/{repo_card.yaml, samples.yaml, .codegraph/}`
- 全局清单：`workspace/_meta.json`

**禁止**：直接 Read 任何 `<doc_id>.json` 或 `.codegraph/codegraph.db`（体积大，会爆上下文）。统一通过下面两个 CLI 查询。

```bash
# 文档查询
python3 ~/Desktop/CannEx/skills/ascend-c/tools/cannex_doc.py list
python3 ~/Desktop/CannEx/skills/ascend-c/tools/cannex_doc.py meta "<name>"
python3 ~/Desktop/CannEx/skills/ascend-c/tools/cannex_doc.py structure "<name>"
python3 ~/Desktop/CannEx/skills/ascend-c/tools/cannex_doc.py pages "<name>" "5-7"
python3 ~/Desktop/CannEx/skills/ascend-c/tools/cannex_doc.py search_api "<api>"

# 代码仓查询
python3 ~/Desktop/CannEx/skills/ascend-c/tools/cannex_repo.py list
python3 ~/Desktop/CannEx/skills/ascend-c/tools/cannex_repo.py card "<repo>"
python3 ~/Desktop/CannEx/skills/ascend-c/tools/cannex_repo.py list_samples "<repo>" --pattern <p>
python3 ~/Desktop/CannEx/skills/ascend-c/tools/cannex_repo.py code "<repo>" "<sample_id>" [--skeleton]
```

---

## 二、意图路由（每轮对话开始时执行）

### 2.1 角色推断信号（不主动问用户）

| 信号 | 角色 |
|---|---|
| UB / GM / TPipe / Tiling / Cube / Vector / AI Core | A 算子开发 |
| ACL / aclrtMalloc / 推理流程 / 模型加载 / 装环境 | B 应用开发 |
| git / PR / 贡献 / 仓库 / sample / 参考实现 | F 代码仓使用/贡献 |
| 仅概念性提问无具体信号 | 默认 A |
| 多类混合 | 取最强信号；冲突按 A > F > B 优先 |

### 2.2 意图类型

| 意图 | 触发信号 | 知识源 |
|---|---|---|
| `concept` | "是什么"、"原理" | docs |
| `howto` | "怎么用"、"步骤" | docs |
| `debug` | "报错"、"错误" | docs |
| `compare` | "区别"、"对比" | docs（多节点） |
| `code-example` | "样例"、"参考实现"、"代码" | repos |
| `api-lookup` | "X 的参数"、"怎么调" | docs |
| `repo-navigate` | "X 仓结构"、"贡献" | repos |

### 2.3 应答模式决策表

| 角色 | 意图 | 应答模式 |
|---|---|---|
| A | concept/howto/debug | 教学引导（读 references/answer-styles.md） |
| A | code-example | 导航 + 教学 |
| A | api-lookup | 直接答 |
| B | concept | 直接答（简）|
| B | howto/debug/api-lookup | 直接答 |
| F | repo-navigate/code-example | 导航 |
| F | concept | 教学引导 |
| 全员 | compare | 对照（并列呈现，不裁决） |

### 2.4 检索计划

| 模式 | 调用顺序 |
|---|---|
| 文档型（concept/howto/debug/compare） | `cannex_doc list → structure → pages` |
| code-example | `cannex_repo list_samples --pattern X → code <id> --skeleton` |
| api-lookup | `cannex_doc search_api <name> → pages` |
| repo-navigate | `cannex_repo card → list_samples` |

---

## 三、内容来源标注规则（不可妥协）

**每个技术断言必须区分原文 vs LLM 加工**：

### 原文抽取（确定性高，> 引用块）

```markdown
> [原文]
> "TPipe 是 Ascend C 提供的统一内存与流水管理框架..."
> [来源: CANN 9.0.0 算子开发指南 §2.3]
```

- 文档原段落、代码片段、API 签名、samples.yaml 字段（视为权威）
- 查询工具返回 `source_type: "original"` 的内容
- **禁止改写原文**

### LLM 加工（可能失真，⚠️ 标注）

```markdown
⚠️ 以下为基于检索原文的综合理解，可能存在加工偏差，关键技术决策请核对原文。

打个比方：内存搬运像快递员送货...
```

适用：类比、跨章节合成、教学性梳理、推理性回答。

### 决策表

| 内容性质 | 标注 |
|---|---|
| 文档原段落引用 | `> [原文]` + `[来源]` |
| 代码仓原文件片段（code 命令返回） | 代码块 + `[来源]` |
| samples.yaml 推荐理由等字段 | 视为权威，`[来源: samples.yaml#<id>]` |
| LLM 自由组织语言 | `⚠️` + 备注 |
| 类比 / 比喻 | `⚠️` + 备注 |

---

## 四、抗幻觉规则

1. **回答必须基于检索结果**：每个技术断言对应原文 / metadata 字段。
2. **代码零修改**：文档/代码仓中的代码原样引用。
3. **溯源标注必须有**：格式 `[来源: <文档名 §章节> | samples.yaml#<id> | <repo>/<path>]`。
4. **三级失败兜底**：
   - L1 无相关文档/仓 → "暂无覆盖，建议查 CANN 文档中心"
   - L2 有但无匹配节点 → "未找到对应章节，建议直接搜官方文档"
   - L3 有页面/样例但内容答不了 → 引用原文摘录 + 说明不足，禁止用预训练知识补全
5. **版本边界**：当前知识库 CANN 9.0.0，涉及版本敏感时说明。

---

## 五、边界场景处理

| 场景 | 应答 |
|---|---|
| 要求直接给完整算子代码（A 类教学边界） | "我的角色是帮你学会。可以带你分析设计思路、讲解 API 用法——代码由你写，这样才能掌握。" |
| 要求竞品对比（"Ascend vs CUDA 哪个好"） | "知识库只含 CANN 官方资料，无法做横向评价。可告诉你 Ascend C 的技术特性，由你判断。" |
| 学术不诚信（作业/考试） | "可以帮你理解概念和文档，答案需要你自己推导。" |
| 完全超出 CANN 范畴 | "超出 Ascend C/CANN 开发范畴，暂帮不上忙。" |

---

## 六、按需 Read 的参考文件

| 文件 | 何时读 |
|---|---|
| `references/answer-styles.md` | 应答模式 = 教学引导时 |
| `references/learning-paths.md` | 给"下一步建议"时 |
| `references/teaching-personas.md` | 拿不准用户层级时 |

不要默认全部加载。
```

- [ ] **Step 2: 删除 cannex.py（已被 cannex_doc.py 完全替代）**

```bash
git rm skills/ascend-c/tools/cannex.py
```

- [ ] **Step 3: 提交**

```bash
git add skills/ascend-c/SKILL.md
git commit -m "feat(skill): SKILL.md 重写到 v2（意图路由 + 来源标注 + 双知识源）"
```

---

## Task 13：端到端验证 — 3 个核心场景

**Files:**
- Create: `docs/specs/2026-05-23-v2-alpha-validation-report.md`

注：本 Task 是手动验证，需要在 Claude Code 里实际启动 Skill 跟 LLM 对话。

- [ ] **Step 1: 确保 Skill 已被加载**

```bash
ls -la ~/.claude/skills/ascend-c
# Expected: 软链指向 /Users/justbin/Desktop/CannEx/skills/ascend-c
```

如未建立，执行 `ln -sf /Users/justbin/Desktop/CannEx/skills/ascend-c ~/.claude/skills/ascend-c`。

- [ ] **Step 2: 启动 Claude Code，跑场景 1（A × concept）**

提问：
> "Pipeline 到底是干什么的？为什么不能像普通 C++ 那样顺序写？"

验证：
- [ ] 回答中至少一段是 `> [原文]` + `[来源: ... 算子开发指南 §...]`
- [ ] 至少一段类比内容带有 `⚠️` 标注
- [ ] 末尾有"下一步建议"（教学引导模式应给）

- [ ] **Step 3: 跑场景 2（B × howto）**

提问：
> "我装完 CANN 之后想跑个推理 demo，怎么写最简单的代码？"

验证：
- [ ] 直接给代码步骤，**不**走教学引导
- [ ] 引用到 `cannex_doc.py pages` 取到的原文
- [ ] 末尾**不**强加"下一步建议"
- [ ] 若 samples 仓有对应推理样例，应被引用（`[来源: samples.yaml#<id>]`）

- [ ] **Step 4: 跑场景 3（F × code-example 杀手锏）**

提问（原始触发需求）：
> "我想看一下 CANN 先计算 vector 再计算 cube 的比较好的实现用例。"

验证：
- [ ] 调用 `cannex_repo list_samples samples --pattern vector_to_cube` 或等价
- [ ] 推荐至少 1 个样例（如 samples.yaml 中只有 1 个 vector_to_cube 样例）
- [ ] 给出 `recommendation_reason`（来自 samples.yaml）
- [ ] 给出代码骨架（调 `cannex_repo code ... --skeleton`），标注 `source_type=original`
- [ ] 不给完整可运行代码

- [ ] **Step 5: 写验证报告**

`docs/specs/2026-05-23-v2-alpha-validation-report.md`:

```markdown
# CannEx v2-α 端到端验证报告

**日期：** 2026-05-23
**验证人：** <fill>

## 场景 1：A × concept
- 提问：[fill 实际提问]
- LLM 实际回答摘录：[fill]
- 验证结果：
  - [ ] 含 `> [原文]` 块
  - [ ] 含 `⚠️` 标注
  - [ ] 含"下一步建议"
- 备注：[fill 发现的问题]

## 场景 2：B × howto
[同上结构]

## 场景 3：F × code-example
[同上结构]

## 总体结论
- [ ] v2-α 验收通过
- [ ] 部分通过，待修补：[list]
- [ ] 不通过，需返工：[list]
```

- [ ] **Step 6: 提交**

```bash
git add docs/specs/2026-05-23-v2-alpha-validation-report.md
git commit -m "test(v2-alpha): 端到端验证报告"
```

---

## Task 14：更新 CLAUDE.md 反映 v2 现状

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: 替换 §二 目录地图**

旧版列出 v1 结构，新版补充：

```markdown
~/Desktop/CannEx/                          ← 工作目录
├── CLAUDE.md
├── docs/
│   ├── CannEx-PRD.md
│   ├── CannEx-SDD.md
│   ├── developer-needs.md
│   └── specs/                             ← 设计/验证报告
│       ├── 2026-05-22-skill-robustness.md
│       ├── 2026-05-23-cannex-v2-design.md   ← v2 设计
│       ├── 2026-05-23-codegraph-spike-report.md
│       └── 2026-05-23-v2-alpha-validation-report.md
├── build/                                 ← 离线管道
│   ├── repos.yaml / docs.yaml
│   ├── sync_sources.py
│   ├── build_docs.py
│   ├── build_repos.py
│   └── monthly_update.sh
├── raw/                                   ← 原始素材（gitignored）
│   ├── docs/  (手动放 PDF)
│   └── repos/ (sync_sources clone)
├── skills/ascend-c/                       ← v2 Skill
│   ├── SKILL.md                           ← ~100 行
│   ├── references/answer-styles.md        ← 教学风格
│   └── tools/
│       ├── cannex_doc.py
│       └── cannex_repo.py
├── workspace/                             ← agent 唯一读取目录
│   ├── _meta.json
│   ├── docs/<doc_id>.json
│   └── repos/<repo>/
│       ├── .codegraph/
│       ├── repo_card.yaml
│       └── samples.yaml
└── tests/                                 ← pytest
```

- [ ] **Step 2: 替换 §六 操作命令**

```markdown
### 离线管道（月度或更新时）
~/project/CANN/PageIndex/.venv/bin/python build/sync_sources.py     # 拉新
~/project/CANN/PageIndex/.venv/bin/python build/build_docs.py        # 建文档树
~/project/CANN/PageIndex/.venv/bin/python build/build_repos.py       # 建代码仓索引
bash build/monthly_update.sh                                          # 一键串

### Skill 查询 CLI（agent 自动调用，调试用）
python3 skills/ascend-c/tools/cannex_doc.py list
python3 skills/ascend-c/tools/cannex_repo.py list

### Skill 软链
ln -sf ~/Desktop/CannEx/skills/ascend-c ~/.claude/skills/ascend-c
```

- [ ] **Step 3: 替换 §八 当前进度**

```markdown
## 八、当前进度

✅ Phase 1a v1 基线（2 份 PDF 文档树）
✅ Phase 1b v2-α 架构升级（本次）：
   - 三层架构（离线管道 / workspace / Skill）
   - 角色路由 + 4 应答模式（教学 / 直接答 / 导航 / 对照）
   - 内容来源标注（原文 vs LLM 加工）
   - samples 代码仓 PoC（repo_card + samples.yaml + CodeGraph）
   - cannex_doc.py / cannex_repo.py 查询 CLI
   - monthly_update.sh 增量管线
```

- [ ] **Step 4: 替换 §九 下一步候选**

```markdown
## 九、下一步候选（v2-β 知识扩库）

按优先级：
1. **代码仓扩库（优先）**
   - cann-ops-adv（高级算子，已在 repos.yaml 中 enabled:false，启用即可）
   - 其他仓（用户指定本地路径）
2. **文档扩库**
   - 应用开发指南
   - 性能调优指南 + 经验文档
   - 常见问题/错误码手册

每次扩库后跑 monthly_update.sh + 在 SKILL 验证新场景。
```

- [ ] **Step 5: 提交**

```bash
git add CLAUDE.md
git commit -m "docs(claude): 更新 CLAUDE.md 反映 v2-α 现状"
```

---

## v2-α 完工 checklist

执行完上述 Task 后核对：

- [ ] **Task 0** CodeGraph spike 报告产出且结论为"继续"
- [ ] **Task 1** git 已 init、.gitignore 生效
- [ ] **Task 2** workspace/docs/ 含 2 份 JSON；_meta.json v2 schema
- [ ] **Task 3** cannex_doc.py 测试 4/4 通过
- [ ] **Task 4** repos.yaml + docs.yaml 存在
- [ ] **Task 5** sync_sources.py 可 dry-run + 实跑 samples
- [ ] **Task 6** build_docs.py 跑 2 份文档时全跳过
- [ ] **Task 7** build_repos.py --only-codegraph 在 samples 成功产出 .codegraph
- [ ] **Task 8** samples 仓的 repo_card.yaml + samples.yaml 至少 5 条样例完整无 TBD
- [ ] **Task 9** cannex_repo.py 测试 4/4 通过；vector_to_cube 过滤能拿到结果
- [ ] **Task 10** monthly_update.sh 可执行，reports/YYYYMM.md 产出
- [ ] **Task 11** answer-styles.md 已建
- [ ] **Task 12** SKILL.md 重写，~100 行，cannex.py 已删
- [ ] **Task 13** 3 个验证场景报告通过
- [ ] **Task 14** CLAUDE.md 更新

全勾 → v2-α 验收完成；可考虑启动 v2-β 扩库。

---

## 自审

本 plan 已自审：

- ✅ **Spec 覆盖**：
  - §1 定位与受众 → Task 12 SKILL 头部 + Task 14 CLAUDE.md
  - §2 三层架构 → Task 1（目录）+ Task 5-7（管道）+ Task 3/9（查询）
  - §3.1-3.5 知识源结构 → Task 2（迁移）+ Task 4（配置）+ Task 8（bootstrap）
  - §3.6 自动拉取 → Task 5
  - §3.7-3.8 完整管道 → Task 10
  - §4 意图路由 → Task 12 SKILL §2
  - §4.6 内容来源标注 → Task 3/9（CLI source_type 字段）+ Task 12 SKILL §3
  - §5 三个场景 → Task 13 验证
  - §6.3 v2-α Done criteria → 完工 checklist
- ✅ **占位扫描**：无 TBD（除 Task 0 spike 报告本身的填空模板，那是预期）
- ✅ **类型一致**：所有 CLI 调用、yaml 字段名在跨 Task 引用时保持一致（如 `computation_pattern` / `recommendation_reason` / `source_type`）

无遗留问题。

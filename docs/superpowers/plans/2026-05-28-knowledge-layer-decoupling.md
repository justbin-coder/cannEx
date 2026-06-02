# 知识检索层解耦（lib/cannex_knowledge）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 CannEx 的知识检索逻辑（`api_*` 数据访问函数）从 Phase 1 Skill 目录中抽取为独立 Python 库 `lib/cannex_knowledge/`，消除 webchat 通过 `skills/ascend_c`（symlink hack）对 `skills/` 的硬依赖，使 Phase 1（CC Skill）与 Phase 2（webchat）各自拥有独立的 prompt 与工具绑定，仅共享纯数据访问层。

**Architecture:**
- **共享层**：`lib/cannex_knowledge/`——只放客观数据访问（`api_*` + 路径解析 + helper），无 prompt、无策略、无工具协议。
- **Phase 1（自治）**：`skills/ascend-c/SKILL.md` 内容不变；`tools/cannex_*.py` 退化为薄 CLI wrapper，`cmd_*` 全部委托给 `lib` 的 `api_*`（顺带修复 `symbol`/`context` 依赖缺失的外部 `codegraph` 二进制的潜在 bug）。
- **Phase 2（自治）**：新建 `webchat/cannex_chat/prompts/system_prompt.md` 作为 Phase 2 唯一 prompt 来源；`worker/server.py` 改为 `import cannex_knowledge`；删除 `skill_loader.py` 的正则裁剪逻辑，改为读自己的 prompt 文件，**不再读 `SKILL.md`**。

**Tech Stack:** Python 3.11, pytest（`asyncio_mode=auto`），SQLite（CodeGraph），litellm/Anthropic tool_use（仅 webchat 侧）。

**关键约束（与对话确认）：**
- ✅ Phase 1 CLI 保留为薄 wrapper（向后兼容，CLI 命令零行为变化，`symbol`/`context` 反而被修复）
- ✅ Prompt 不抽 `shared_rules.md`——SKILL.md 与 system_prompt.md **完全独立**，短期内容相似但允许自然漂移（Rule of Three）
- ✅ webchat 可独立部署但不拆仓——`lib/` 留在 monorepo，通过 `sys.path` 注入，不发 pypi 包

**关键事实（实施前必读）：**
- `skills/ascend_c`（下划线）是指向 `skills/ascend-c`（连字符）的 symlink，是 webchat import 的 hack。本计划完成后该 symlink 不再被任何代码引用（Task 10 可选清理）。
- 测试从 `~/Desktop/CannEx` 根目录跑：`conftest.py` 把根目录加入 `sys.path`；`pytest.ini` 设 `asyncio_mode=auto`；`CANNEX_ROOT` 由各测试按需注入。
- `cmd_symbol`/`cmd_context`（`cannex_repo.py`）当前调用外部 `codegraph` 二进制（不在 PATH，已失效）；`api_symbol`/`api_context` 用 sqlite 直查。本计划让 CLI 委托 `api_*`，顺带修复。

---

## File Structure

**新建：**
- `lib/cannex_knowledge/__init__.py` — 包入口，re-export 关键 api
- `lib/cannex_knowledge/paths.py` — 集中路径解析（`CANNEX_ROOT`/`WORKSPACE`/`META_FILE`/`REPOS_DIR`）
- `lib/cannex_knowledge/retriever_repo.py` — 代码仓数据访问（从 `cannex_repo.py` 移入 `api_*` + helper）
- `lib/cannex_knowledge/retriever_doc.py` — 文档数据访问（从 `cannex_doc.py` 移入 `api_*` + helper）
- `lib/cannex_knowledge/tests/__init__.py`
- `lib/cannex_knowledge/tests/test_paths.py`
- `lib/cannex_knowledge/tests/test_retriever_repo.py`
- `lib/cannex_knowledge/tests/test_retriever_doc.py`
- `webchat/cannex_chat/prompts/__init__.py`
- `webchat/cannex_chat/prompts/system_prompt.md` — Phase 2 唯一 prompt 来源
- `webchat/cannex_chat/agent/prompt_loader.py` — 替代 `skill_loader.py`

**修改：**
- `skills/ascend-c/tools/cannex_repo.py` — `api_*`/helper 改为从 `lib` re-import；`cmd_*` 委托 `api_*`
- `skills/ascend-c/tools/cannex_doc.py` — 同上
- `webchat/cannex_chat/worker/server.py` — import 路径改为 `cannex_knowledge`
- `webchat/cannex_chat/agent/loop.py` — import `prompt_loader` 替代 `skill_loader`
- `webchat/cannex_chat/tests/test_worker_server.py` — 不变（黑盒 RPC，仅验证仍通过）
- `conftest.py` — `sys.path` 增加 `<root>/lib`

**删除（Task 8）：**
- `webchat/cannex_chat/agent/skill_loader.py`
- `webchat/cannex_chat/tests/test_skill_loader.py`（由 `test_prompt_loader.py` 取代）

---

## Task 1: lib 包骨架 + 集中路径解析

**Files:**
- Create: `lib/cannex_knowledge/__init__.py`
- Create: `lib/cannex_knowledge/paths.py`
- Create: `lib/cannex_knowledge/tests/__init__.py`
- Create: `lib/cannex_knowledge/tests/test_paths.py`
- Modify: `conftest.py:1-5`

- [ ] **Step 1: 把 lib 加入测试 sys.path**

修改 `conftest.py` 为：

```python
import sys
from pathlib import Path

_root = Path(__file__).parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "lib"))
```

- [ ] **Step 2: 写 paths.py 的失败测试**

创建 `lib/cannex_knowledge/tests/__init__.py`（空文件）。

创建 `lib/cannex_knowledge/tests/test_paths.py`：

```python
import os
from pathlib import Path


def test_root_falls_back_to_repo_root_when_env_unset(monkeypatch):
    monkeypatch.delenv("CANNEX_ROOT", raising=False)
    import importlib
    from cannex_knowledge import paths
    importlib.reload(paths)
    # paths.py 在 lib/cannex_knowledge/ 下，parents[2] = CannEx 根
    assert paths.CANNEX_ROOT.name == "CannEx"
    assert paths.WORKSPACE == paths.CANNEX_ROOT / "workspace"
    assert paths.META_FILE == paths.WORKSPACE / "_meta.json"
    assert paths.REPOS_DIR == paths.WORKSPACE / "repos"


def test_root_honors_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CANNEX_ROOT", str(tmp_path))
    import importlib
    from cannex_knowledge import paths
    importlib.reload(paths)
    assert paths.CANNEX_ROOT == tmp_path
    assert paths.WORKSPACE == tmp_path / "workspace"
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/test_paths.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'cannex_knowledge'`）

- [ ] **Step 4: 写 paths.py**

创建 `lib/cannex_knowledge/__init__.py`（暂时空文件，Task 2/3 后补 re-export）。

创建 `lib/cannex_knowledge/paths.py`：

```python
"""集中路径解析。优先 CANNEX_ROOT 环境变量，否则回退到仓库根（lib 的上两层）。"""
import os
from pathlib import Path


def _resolve_root() -> Path:
    env = os.environ.get("CANNEX_ROOT")
    if env:
        return Path(env)
    # paths.py: lib/cannex_knowledge/paths.py → parents[2] = CannEx 根
    return Path(__file__).resolve().parents[2]


CANNEX_ROOT = _resolve_root()
WORKSPACE = CANNEX_ROOT / "workspace"
META_FILE = WORKSPACE / "_meta.json"
REPOS_DIR = WORKSPACE / "repos"
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/test_paths.py -v`
Expected: PASS（2 passed）

- [ ] **Step 6: 提交**

```bash
cd ~/Desktop/CannEx
git add lib/cannex_knowledge/__init__.py lib/cannex_knowledge/paths.py lib/cannex_knowledge/tests/ conftest.py
git commit -m "$(cat <<'EOF'
feat(lib): 新建 cannex_knowledge 包骨架 + 集中路径解析

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 抽取代码仓数据访问层 retriever_repo.py

**说明：** 把 `skills/ascend-c/tools/cannex_repo.py` 中的 `api_*` 函数与其专属 helper **原样移动**到 `lib/cannex_knowledge/retriever_repo.py`，路径常量改为从 `paths.py` 导入。CLI（`cmd_*`/`main`）暂时留在原文件不动（Task 4 再改）。

**要移动的符号（来自当前 `cannex_repo.py`，原样保留函数体）：**
- 模块常量：`_DEFAULT_MAX_FILE_LINES`、`_DEFAULT_MAX_DIR_ENTRIES`、`_READ_FILE_DEFAULT_LINES`、`_MAX_LIST_ENTRIES`、`_ARCH_DIR_RE`
- helper：`load_meta`、`get_repo_meta`、`list_repos`、`load_card`、`load_samples`、`_get_codegraph_db`、`_detect_sibling_archs`
- api：`api_list`、`api_card`、`api_context`、`api_symbol`、`api_overview`、`api_list_samples`、`api_list_files`、`api_read_file`、`api_read_sample`

**Files:**
- Create: `lib/cannex_knowledge/retriever_repo.py`
- Create: `lib/cannex_knowledge/tests/test_retriever_repo.py`
- Modify: `lib/cannex_knowledge/__init__.py`

- [ ] **Step 1: 写 retriever_repo 的失败测试（基于真实 workspace 数据）**

创建 `lib/cannex_knowledge/tests/test_retriever_repo.py`：

```python
from cannex_knowledge import retriever_repo as r


def test_api_list_returns_ops_transformer():
    repos = r.api_list()
    names = [x["name"] for x in repos]
    assert "ops-transformer" in names


def test_api_list_files_root_shows_attention_dir():
    res = r.api_list_files("ops-transformer", "", max_depth=1)
    names = [e["name"] for e in res["entries"]]
    assert "attention/" in names
    assert res["source_type"] == "metadata"


def test_api_read_file_reads_header():
    res = r.api_read_file(
        "ops-transformer",
        "attention/flash_attention_score/op_kernel/flash_attention_score.cpp",
        start_line=1, end_line=10,
    )
    assert res["source_type"] == "original"
    assert "Huawei" in res["content"]
    assert res["total_lines"] > 100


def test_api_symbol_finds_kernel_base_via_sqlite():
    res = r.api_symbol("ops-transformer", "FlashAttentionScoreKernelBase", kind="class")
    assert res["source_type"] == "original"
    assert len(res["matches"]) >= 1
    assert any("arch" in m["file_path"] for m in res["matches"])


def test_api_list_samples_returns_metadata():
    res = r.api_list_samples("ops-transformer")
    assert res["source_type"] == "metadata"
    assert res["count"] >= 1


def test_api_read_file_rejects_path_traversal():
    res = r.api_read_file("ops-transformer", "../../../etc/passwd")
    assert "error" in res
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/test_retriever_repo.py -v`
Expected: FAIL（`ImportError: cannot import name 'retriever_repo'`）

- [ ] **Step 3: 创建 retriever_repo.py，从 cannex_repo.py 移入符号**

创建 `lib/cannex_knowledge/retriever_repo.py`，文件头为：

```python
"""CannEx 代码仓数据访问层（纯查询，无 prompt/无策略）。

source_type 规则：
  - "original" : 代码原文或 CodeGraph 索引（直接给用户）
  - "metadata" : repo_card.yaml / samples.yaml（LLM 加工过，需标注）
"""
import json
import re
import sqlite3
from pathlib import Path

import yaml

from .paths import CANNEX_ROOT as ROOT, META_FILE, REPOS_DIR
```

然后从当前 `skills/ascend-c/tools/cannex_repo.py` **原样复制**以下函数体（不改逻辑，仅确保它们引用上面 import 的 `ROOT`/`META_FILE`/`REPOS_DIR`）：

1. helper：`load_meta()`、`get_repo_meta(name)`、`list_repos()`、`load_card(name)`、`load_samples(name)`、`_get_codegraph_db(name)`、`_detect_sibling_archs(...)`
2. 模块常量：`_DEFAULT_MAX_FILE_LINES = 800`、`_DEFAULT_MAX_DIR_ENTRIES = 20`、`_READ_FILE_DEFAULT_LINES = 300`、`_MAX_LIST_ENTRIES = 80`、`_ARCH_DIR_RE = re.compile(r"(?:^|/)(arch\d+)(?=/)")`
3. api：`api_list()`、`api_card(name)`、`api_context(name, query)`、`api_symbol(name, symbol, kind="any")`、`api_overview(name)`、`api_list_samples(name, pattern=None, complexity=None)`、`api_list_files(name, dir_path="", max_depth=2)`、`api_read_file(name, file_path, start_line=1, end_line=None)`、`api_read_sample(name, sample_id, skeleton=False, max_lines_per_file=_DEFAULT_MAX_FILE_LINES)`

> 注意：`_get_codegraph_db` 当前实现用 `ROOT / db_rel`，移动后 `ROOT` 来自 `paths.CANNEX_ROOT`，语义不变。`api_context`/`api_symbol` 内部 `import sqlite3` 可保留或提到文件顶部（已在 header import）。

- [ ] **Step 4: 更新 __init__.py re-export**

把 `lib/cannex_knowledge/__init__.py` 写为：

```python
from . import paths, retriever_repo

__all__ = ["paths", "retriever_repo"]
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/test_retriever_repo.py -v`
Expected: PASS（6 passed）

- [ ] **Step 6: 提交**

```bash
cd ~/Desktop/CannEx
git add lib/cannex_knowledge/retriever_repo.py lib/cannex_knowledge/__init__.py lib/cannex_knowledge/tests/test_retriever_repo.py
git commit -m "$(cat <<'EOF'
feat(lib): 抽取代码仓数据访问层 retriever_repo（api_* + sqlite 检索）

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 抽取文档数据访问层 retriever_doc.py

**说明：** 同 Task 2 的模式处理 `cannex_doc.py`。实施前先 `Read skills/ascend-c/tools/cannex_doc.py` 全文，确认 helper 完整清单。

**要移动的符号（来自 `cannex_doc.py`）：**
- helper：`_normalize_doc_name`、`load_meta`、`resolve_doc`、`load_doc_json`、`parse_pages`（以文件实际为准，凡 `api_*` 调用到的 helper 都要移）
- api：`api_list`、`api_outline`、`api_pages`、`api_search`

**Files:**
- Create: `lib/cannex_knowledge/retriever_doc.py`
- Create: `lib/cannex_knowledge/tests/test_retriever_doc.py`
- Modify: `lib/cannex_knowledge/__init__.py`

- [ ] **Step 1: 写 retriever_doc 的失败测试**

创建 `lib/cannex_knowledge/tests/test_retriever_doc.py`：

```python
from cannex_knowledge import retriever_doc as d


def test_api_list_returns_docs():
    docs = d.api_list()
    assert isinstance(docs, list)
    assert len(docs) >= 1
    assert "doc_name" in docs[0]
    assert "doc_id" in docs[0]


def test_api_outline_returns_structure():
    docs = d.api_list()
    name = docs[0]["doc_name"]
    res = d.api_outline(name, max_depth=2)
    assert "doc_name" in res
    assert "outline" in res
    assert isinstance(res["outline"], list)


def test_api_search_returns_sections_shape():
    res = d.api_search("算子", scope="all", top_k=2)
    assert "sections" in res
    assert isinstance(res["sections"], list)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/test_retriever_doc.py -v`
Expected: FAIL（`ImportError: cannot import name 'retriever_doc'`）

- [ ] **Step 3: 创建 retriever_doc.py，从 cannex_doc.py 移入符号**

创建 `lib/cannex_knowledge/retriever_doc.py`，文件头为：

```python
"""CannEx 文档数据访问层（纯查询，无 prompt/无策略）。

source_type 规则：
  - "original" : 原文抽取（直接给用户）
  - "metadata" : 元信息（来自 _meta.json，非原文）
"""
import json
import re
from pathlib import Path

from .paths import WORKSPACE, META_FILE
```

然后从 `cannex_doc.py` **原样复制** `_normalize_doc_name`、`load_meta`、`resolve_doc`、`load_doc_json`、`parse_pages` 以及 `api_list`、`api_outline`、`api_pages`、`api_search`。确保它们引用上面 import 的 `WORKSPACE`/`META_FILE`（原文件用 `WORKSPACE = Path(__file__).resolve().parents[3] / "workspace"`，移动后改为 import）。

- [ ] **Step 4: 更新 __init__.py**

```python
from . import paths, retriever_doc, retriever_repo

__all__ = ["paths", "retriever_doc", "retriever_repo"]
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd ~/Desktop/CannEx && python3 -m pytest lib/cannex_knowledge/tests/test_retriever_doc.py -v`
Expected: PASS（3 passed）

- [ ] **Step 6: 提交**

```bash
cd ~/Desktop/CannEx
git add lib/cannex_knowledge/retriever_doc.py lib/cannex_knowledge/__init__.py lib/cannex_knowledge/tests/test_retriever_doc.py
git commit -m "$(cat <<'EOF'
feat(lib): 抽取文档数据访问层 retriever_doc（api_* 文档检索）

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: cannex_repo.py 退化为薄 CLI wrapper（并修复 symbol/context）

**说明：** `cannex_repo.py` 删除自身的 `api_*` 实现与重复 helper，改为从 `lib` re-import。`cmd_symbol`/`cmd_context` 当前调用外部 `codegraph` 二进制（已失效），改为委托 `api_symbol`/`api_context`（sqlite），顺带修复。`cmd_list_files`/`cmd_read_file` 已委托 `api_*`，保持。

**Files:**
- Modify: `skills/ascend-c/tools/cannex_repo.py`（大幅精简）

- [ ] **Step 1: 重写 cannex_repo.py 顶部为薄 wrapper**

把 `skills/ascend-c/tools/cannex_repo.py` 顶部的 import + 常量 + helper + 所有 `api_*` 定义，替换为对 lib 的引用。新文件结构：

```python
#!/usr/bin/env python3
"""CannEx 代码仓查询 CLI（薄 wrapper）。

实现已迁移到 lib/cannex_knowledge/retriever_repo.py。
本文件只负责 argparse → 调用 lib api_* → 打印 JSON。

Usage:
  cannex_repo.py list
  cannex_repo.py card <repo_name>
  cannex_repo.py list_samples <repo_name> [--pattern X] [--complexity Y]
  cannex_repo.py code <repo_name> <sample_id> [--skeleton]
  cannex_repo.py symbol <repo_name> <symbol_name> [--kind function|class|struct]
  cannex_repo.py context <repo_name> <query_text>
  cannex_repo.py list_files <repo_name> [dir_path] [--max_depth N]
  cannex_repo.py read_file <repo_name> <file_path> [--start_line N] [--end_line N]
"""
import argparse
import json
import os
import sys
from pathlib import Path

# 把 <root>/lib 加入 sys.path，使 cannex_knowledge 可 import
_ROOT = Path(os.environ.get("CANNEX_ROOT") or Path(__file__).resolve().parents[3])
sys.path.insert(0, str(_ROOT / "lib"))

from cannex_knowledge import retriever_repo as R  # noqa: E402


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))
```

- [ ] **Step 2: 重写所有 cmd_* 委托 lib（symbol/context 改用 sqlite api）**

`cannex_repo.py` 中所有 `cmd_*` 替换为：

```python
def cmd_list():
    repos = R.api_list()
    _print({"source_type": "metadata", "repos": repos})


def cmd_card(name):
    _print({"source_type": "metadata", **R.api_card(name)})


def cmd_list_samples(name, pattern, complexity):
    _print(R.api_list_samples(name, pattern=pattern, complexity=complexity))


def cmd_code(name, sample_id, skeleton):
    _print(R.api_read_sample(name, sample_id, skeleton=skeleton))


def cmd_symbol(name, symbol, kind):
    _print(R.api_symbol(name, symbol, kind=kind or "any"))


def cmd_context(name, query):
    _print(R.api_context(name, query))


def cmd_list_files(name, dir_path, max_depth):
    _print(R.api_list_files(name, dir_path, max_depth))


def cmd_read_file(name, file_path, start_line, end_line):
    _print(R.api_read_file(name, file_path, start_line, end_line))
```

> 注意：`cmd_code` 原来用 sample 的 `code` 输出格式，现统一走 `api_read_sample`（webchat 同款），输出含 `sibling_archs` hint，是增强不是回退。

`main()` 的 argparse 定义（子命令 + 参数）保持不变（含 Task 之前已加的 `list_files`/`read_file`），dispatch 调用上面的 `cmd_*`。

- [ ] **Step 3: 验证 CLI 全部子命令可用（含被修复的 symbol/context）**

```bash
cd ~/Desktop/CannEx
echo "--- list ---";        python3 skills/ascend-c/tools/cannex_repo.py list
echo "--- symbol (修复) ---"; python3 skills/ascend-c/tools/cannex_repo.py symbol ops-transformer FlashAttentionScoreKernelBase --kind class
echo "--- context (修复) ---"; python3 skills/ascend-c/tools/cannex_repo.py context ops-transformer DataCopy
echo "--- list_files ---";   python3 skills/ascend-c/tools/cannex_repo.py list_files ops-transformer "" --max_depth 1
echo "--- read_file ---";    python3 skills/ascend-c/tools/cannex_repo.py read_file ops-transformer "attention/flash_attention_score/op_kernel/flash_attention_score.cpp" --start_line 1 --end_line 5
```

Expected：
- `symbol` 返回 `"matches"` 含至少 1 条（arch35/arch38），不再因缺 `codegraph` 二进制报错
- `context` 返回 `"snippets"`
- 其余子命令返回 JSON，无 traceback

- [ ] **Step 4: 提交**

```bash
cd ~/Desktop/CannEx
git add skills/ascend-c/tools/cannex_repo.py
git commit -m "$(cat <<'EOF'
refactor(skill): cannex_repo CLI 退化为薄 wrapper，复用 lib；修复 symbol/context 依赖缺失 codegraph 二进制的 bug

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: cannex_doc.py 退化为薄 CLI wrapper

**说明：** 同 Task 4 模式。实施前 `Read skills/ascend-c/tools/cannex_doc.py` 全文，确认现有子命令（`list`/`meta`/`structure`/`pages` 等）与 `api_*` 的映射。

**Files:**
- Modify: `skills/ascend-c/tools/cannex_doc.py`

- [ ] **Step 1: 重写 cannex_doc.py 顶部为薄 wrapper**

替换文件头 + 常量 + helper + `api_*` 为：

```python
#!/usr/bin/env python3
"""CannEx 文档查询 CLI（薄 wrapper）。

实现已迁移到 lib/cannex_knowledge/retriever_doc.py。
"""
import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(os.environ.get("CANNEX_ROOT") or Path(__file__).resolve().parents[3])
sys.path.insert(0, str(_ROOT / "lib"))

from cannex_knowledge import retriever_doc as D  # noqa: E402


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))
```

- [ ] **Step 2: cmd_* 委托 lib**

把各 `cmd_*` 改为调用 `D.api_list()` / `D.api_outline(...)` / `D.api_pages(...)` / `D.api_search(...)` 并 `_print`。保留 `main()` 的 argparse 子命令定义不变。

> 若原 CLI 有 `structure` 子命令映射到 `api_outline`、`pages` 映射到 `api_pages`，保持这些子命令名不变（向后兼容 SKILL.md 附录 A 的命令）。

- [ ] **Step 3: 验证 CLI**

```bash
cd ~/Desktop/CannEx
echo "--- list ---";      python3 skills/ascend-c/tools/cannex_doc.py list
echo "--- structure ---"; python3 skills/ascend-c/tools/cannex_doc.py structure "算子开发指南"
```

Expected：返回 JSON（文档清单 / ToC），无 traceback。

- [ ] **Step 4: 提交**

```bash
cd ~/Desktop/CannEx
git add skills/ascend-c/tools/cannex_doc.py
git commit -m "$(cat <<'EOF'
refactor(skill): cannex_doc CLI 退化为薄 wrapper，复用 lib

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: webchat worker 改 import lib，断开 skills 依赖

**说明：** `worker/server.py` 当前 `sys.path.insert(0, root)` + `from skills.ascend_c.tools import cannex_doc, cannex_repo`（走 symlink hack）。改为加入 `<root>/lib` 并 `from cannex_knowledge import retriever_doc, retriever_repo`。HANDLERS 的函数引用相应更新。

**Files:**
- Modify: `webchat/cannex_chat/worker/server.py:13-59`

- [ ] **Step 1: 改 _setup_path 与 import**

把 `worker/server.py` 的 `_setup_path()` 与 import 段改为：

```python
def _setup_path():
    """把 <CANNEX_ROOT>/lib 加入 sys.path，使 cannex_knowledge 可 import。"""
    root = os.environ.get("CANNEX_ROOT")
    if not root:
        sys.stderr.write("ERROR: CANNEX_ROOT env var not set\n")
        sys.exit(1)
    sys.path.insert(0, str(Path(root) / "lib"))
    if not (Path(root) / "workspace" / "_meta.json").exists():
        sys.stderr.write(f"ERROR: workspace/_meta.json not found under {root}\n")
        sys.exit(1)


_setup_path()

from cannex_knowledge import retriever_doc as doc_mod  # noqa: E402
from cannex_knowledge import retriever_repo as repo_mod  # noqa: E402
```

- [ ] **Step 2: HANDLERS 引用更新**

`HANDLERS` 字典中所有 `doc_mod.api_*` / `repo_mod.api_*` 调用保持不变（函数名一致），只是 `doc_mod`/`repo_mod` 现在指向 lib 模块。逐项核对方法名仍存在：`api_search`、`api_list`、`api_context`、`api_symbol`、`api_outline`、`api_pages`、`api_overview`、`api_list_samples`、`api_read_sample`、`api_read_file`、`api_list_files`、`api_card`。

- [ ] **Step 3: 跑 worker 黑盒测试确认仍通过**

Run: `cd ~/Desktop/CannEx && python3 -m pytest webchat/cannex_chat/tests/test_worker_server.py -v`
Expected: PASS（4 passed — ping / list_known_resources / unknown_method / handler_exception）

- [ ] **Step 4: 手动验证 worker 经 lib 检索**

```bash
cd ~/Desktop/CannEx
CANNEX_ROOT=$(pwd) python3 -c '
import json, subprocess, sys, os
env = dict(os.environ, CANNEX_ROOT=os.getcwd())
p = subprocess.Popen([sys.executable, "webchat/cannex_chat/worker/server.py"],
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
req = {"id":"1","method":"list_repo_files","params":{"repo":"ops-transformer","dir_path":"","max_depth":1}}
out,_ = p.communicate((json.dumps(req)+"\n").encode(), timeout=30)
print(out.decode()[:300])
'
```

Expected：输出含 `"attention/"`，证明 worker 通过 lib 成功检索。

- [ ] **Step 5: 提交**

```bash
cd ~/Desktop/CannEx
git add webchat/cannex_chat/worker/server.py
git commit -m "$(cat <<'EOF'
refactor(webchat): worker 改 import cannex_knowledge，断开对 skills/ 的 symlink 依赖

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: 创建 Phase 2 独立 prompt 文件 system_prompt.md

**说明：** webchat 不再读 SKILL.md。新建 `prompts/system_prompt.md` 作为 Phase 2 唯一 prompt 来源。初始内容 = 当前 `skill_loader` 运行时实际产出的 prompt（即 SKILL.md 去掉「## 一、知识源与检索工具」CLI 操作节 + 「附录 A」后，加上 RUNTIME_CONSTRAINTS）。本任务把这份内容固化为一个独立文件，从此 Phase 2 自行维护。

**Files:**
- Create: `webchat/cannex_chat/prompts/__init__.py`
- Create: `webchat/cannex_chat/prompts/system_prompt.md`

- [ ] **Step 1: 生成当前 webchat 实际 prompt 作为初始内容**

```bash
cd ~/Desktop/CannEx
CANNEX_ROOT=$(pwd) python3 -c '
import sys; sys.path.insert(0, ".")
from webchat.cannex_chat.agent.skill_loader import load_system_prompt
open("webchat/cannex_chat/prompts/system_prompt.md","w",encoding="utf-8").write(load_system_prompt())
print("written", len(load_system_prompt()), "chars")
'
```

Expected：写出文件，字符数 > 2000。

- [ ] **Step 2: 人工审阅 system_prompt.md**

`Read webchat/cannex_chat/prompts/system_prompt.md`，确认：
- 含「检索工作流」「list_repo_files」「list_repo_samples」等工具策略正文
- 含「运行时约束（Webchat 环境）」节
- **不含** `cannex_doc.py` / `cannex_repo.py` / 「附录 A」等 Phase 1 CLI 细节

如有残留 Phase 1 CLI 文本，手动删除（这是从此独立维护的文件，可自由编辑）。

- [ ] **Step 3: 创建 prompts 包标记**

创建 `webchat/cannex_chat/prompts/__init__.py`（空文件）。

- [ ] **Step 4: 提交**

```bash
cd ~/Desktop/CannEx
git add webchat/cannex_chat/prompts/
git commit -m "$(cat <<'EOF'
feat(webchat): 新建 Phase 2 独立 system_prompt.md，从此自治不再寄生 SKILL.md

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: 用 prompt_loader 替换 skill_loader（删除正则裁剪）

**说明：** 新建 `prompt_loader.py` 直接读 `prompts/system_prompt.md`，无正则、无 SKILL.md 依赖。更新 `loop.py` import。删除 `skill_loader.py` 与 `test_skill_loader.py`，新增 `test_prompt_loader.py`。

**Files:**
- Create: `webchat/cannex_chat/agent/prompt_loader.py`
- Create: `webchat/cannex_chat/tests/test_prompt_loader.py`
- Modify: `webchat/cannex_chat/agent/loop.py:12`
- Delete: `webchat/cannex_chat/agent/skill_loader.py`
- Delete: `webchat/cannex_chat/tests/test_skill_loader.py`

- [ ] **Step 1: 写 prompt_loader 的失败测试**

创建 `webchat/cannex_chat/tests/test_prompt_loader.py`：

```python
from webchat.cannex_chat.agent.prompt_loader import load_system_prompt


def test_prompt_loads_and_is_substantial():
    p = load_system_prompt()
    assert isinstance(p, str)
    assert len(p) > 2000


def test_prompt_has_tool_workflow_and_runtime():
    p = load_system_prompt()
    assert "检索工作流" in p
    assert "list_repo_files" in p
    assert "运行时约束" in p or "Webchat" in p


def test_prompt_has_no_phase1_cli_details():
    p = load_system_prompt()
    assert "cannex_doc.py" not in p
    assert "cannex_repo.py" not in p
    assert "附录 A" not in p


def test_prompt_loader_does_not_read_skill_md():
    """防回归：prompt_loader 必须读自己的 system_prompt.md，不依赖 SKILL.md。"""
    import inspect
    from webchat.cannex_chat.agent import prompt_loader
    src = inspect.getsource(prompt_loader)
    assert "SKILL.md" not in src
    assert "system_prompt.md" in src


def test_load_idempotent():
    assert load_system_prompt() == load_system_prompt()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd ~/Desktop/CannEx && python3 -m pytest webchat/cannex_chat/tests/test_prompt_loader.py -v`
Expected: FAIL（`ModuleNotFoundError: ...prompt_loader`）

- [ ] **Step 3: 写 prompt_loader.py**

创建 `webchat/cannex_chat/agent/prompt_loader.py`：

```python
"""读取 Phase 2 自己的 system prompt（prompts/system_prompt.md）。

与 Phase 1 的 SKILL.md 完全解耦：webchat 不再读 SKILL.md，也不做正则裁剪。
"""
import os
from functools import lru_cache
from pathlib import Path


def _prompt_path() -> Path:
    override = os.environ.get("CANNEX_SYSTEM_PROMPT_PATH")
    if override:
        return Path(override)
    # prompt_loader.py: webchat/cannex_chat/agent/ → parents[1] = cannex_chat
    return Path(__file__).resolve().parents[1] / "prompts" / "system_prompt.md"


@lru_cache(maxsize=1)
def load_system_prompt() -> str:
    path = _prompt_path()
    if not path.exists():
        raise FileNotFoundError(f"system_prompt.md not found at {path}")
    return path.read_text(encoding="utf-8")
```

- [ ] **Step 4: 更新 loop.py import**

修改 `webchat/cannex_chat/agent/loop.py` 第 12 行：

```python
from .prompt_loader import load_system_prompt
```

（替换原 `from .skill_loader import load_system_prompt`）

- [ ] **Step 5: 删除旧文件**

```bash
cd ~/Desktop/CannEx
git rm webchat/cannex_chat/agent/skill_loader.py webchat/cannex_chat/tests/test_skill_loader.py
```

- [ ] **Step 6: 跑测试确认通过**

Run: `cd ~/Desktop/CannEx && python3 -m pytest webchat/cannex_chat/tests/test_prompt_loader.py webchat/cannex_chat/tests/test_loop.py -v`
Expected: PASS（prompt_loader 5 passed；test_loop 仍 PASS）

- [ ] **Step 7: 提交**

```bash
cd ~/Desktop/CannEx
git add webchat/cannex_chat/agent/prompt_loader.py webchat/cannex_chat/agent/loop.py webchat/cannex_chat/tests/test_prompt_loader.py
git commit -m "$(cat <<'EOF'
refactor(webchat): prompt_loader 取代 skill_loader，删除正则裁剪与 SKILL.md 依赖

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: 全量回归 + webchat E2E 冒烟 + Phase 1 Skill 冒烟

**说明：** 验证两个 Phase 都正常，且彼此解耦。

**Files:** 无（仅验证）

- [ ] **Step 1: 全量测试套件**

Run: `cd ~/Desktop/CannEx && python3 -m pytest -v`
Expected: 全部 PASS（含 lib/、webchat/ 下所有测试）。若有 import 残留错误，定位修复后重跑。

- [ ] **Step 2: 确认无代码再引用 skills.ascend_c**

```bash
cd ~/Desktop/CannEx
grep -rn "skills.ascend_c\|from skills" --include="*.py" webchat/ lib/ | grep -v test_ || echo "CLEAN: 无 webchat/lib 代码引用 skills 包"
```

Expected：输出 `CLEAN`（webchat/lib 不再 import skills 包）。

- [ ] **Step 3: Phase 1 Skill CLI 冒烟（模拟 CC 内 Bash 调用）**

```bash
cd ~/Desktop/CannEx
python3 skills/ascend-c/tools/cannex_repo.py list_files ops-transformer "attention/flash_attention_score/op_kernel" --max_depth 2 | head -20
python3 skills/ascend-c/tools/cannex_doc.py list
```

Expected：返回正确 JSON（含 arch32/arch35 目录树 + 文档清单），证明 Phase 1 经 lib 仍工作。

- [ ] **Step 4: Phase 2 webchat E2E 冒烟（需 API key）**

```bash
cd ~/Desktop/CannEx/webchat/cannex_chat && source .venv/bin/activate 2>/dev/null
CANNEX_ROOT=~/Desktop/CannEx chainlit run app.py -w
```

浏览器打开 http://localhost:8000，提问「ops-transformer 仓有哪些算子？」，确认：
- agent 调用 `list_repo_files` 工具（经 lib worker）
- 返回完整算子目录
- 无 import / prompt 加载错误

> 若当前环境无 API key，跳过本步，在交付说明中标注「Task 9 Step 4 webchat E2E 待人工验收」。

- [ ] **Step 5: 提交（若 Step 1-3 暴露并修复了问题）**

```bash
cd ~/Desktop/CannEx
git add -A
git commit -m "$(cat <<'EOF'
test: 知识层解耦全量回归 + 两 Phase 冒烟验证

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10:（可选）清理 symlink hack 与 v1 遗留

**说明：** 确认 `skills/ascend_c` symlink 与 `skills/__init__.py` 不再被任何代码引用后清理。**谨慎**：若 CC Skill 运行时机制或 `cannex.py`（v1 遗留）仍依赖，则保留。

**Files:**
- 可能删除：`skills/ascend_c`（symlink）、`skills/__init__.py`、`skills/ascend-c/__init__.py`、`skills/ascend-c/tools/__init__.py`

- [ ] **Step 1: 确认无引用**

```bash
cd ~/Desktop/CannEx
grep -rn "skills.ascend_c\|skills\.ascend" --include="*.py" . | grep -v ".venv" | grep -v "skills/ascend-c/tools/cannex" || echo "无外部引用"
```

Expected：除 `cannex.py`（v1 遗留）外无引用。若 `cannex.py` 引用，先确认它是否仍在用（SKILL.md 标注为遗留）。

- [ ] **Step 2: 删除 symlink 与多余 __init__.py（确认安全后）**

```bash
cd ~/Desktop/CannEx
git rm skills/ascend_c skills/__init__.py
# 注：保留 skills/ascend-c/ 本体及其 SKILL.md。__init__.py 删除前确认 CLI 仍能独立运行。
```

- [ ] **Step 3: 重跑 Phase 1 CLI 冒烟确认不依赖包结构**

```bash
cd ~/Desktop/CannEx
python3 skills/ascend-c/tools/cannex_repo.py list
```

Expected：仍正常（CLI 通过 `sys.path` 注入 lib，不依赖 `skills` 作为 Python 包）。

- [ ] **Step 4: 提交**

```bash
cd ~/Desktop/CannEx
git add -A
git commit -m "$(cat <<'EOF'
chore(skill): 清理 ascend_c symlink hack，知识层解耦后不再需要

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage：**
- ✅ 抽取 lib（Task 1-3）
- ✅ Phase 1 CLI 薄 wrapper + 修复 symbol/context（Task 4-5）
- ✅ webchat 断开 skills 依赖（Task 6）
- ✅ Phase 2 独立 prompt（Task 7-8）
- ✅ 两 Phase 解耦验证（Task 9）
- ✅ symlink 清理（Task 10）

**类型/命名一致性：**
- lib 模块名 `retriever_repo` / `retriever_doc` 在 Task 2/3/4/5/6 引用一致
- `api_*` 函数名在 lib、CLI wrapper、worker HANDLERS 三处一致（沿用现有名）
- prompt 文件名 `system_prompt.md` 在 Task 7/8 一致

**已知风险点（执行时注意）：**
1. `cmd_code` 输出格式从旧 `code` 改为 `api_read_sample` 格式——若 SKILL.md 附录 A 示例依赖旧字段，需同步更新附录（Task 4 Step 2 已说明，属增强）。
2. `cannex_doc.py` 未全文读过，Task 5 要求执行前先 Read 确认 helper 清单与子命令映射。
3. Task 10 删 symlink 有风险，标记为可选，需确认 CC Skill 运行机制不依赖 `skills` 包结构。

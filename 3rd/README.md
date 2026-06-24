# 3rd/ — 第三方依赖打包

CannEx 的离线构建管线依赖两个外部开源工具。它们**性质完全不同**，因此打包方式也不同。本目录把"重建这两个依赖所需的最小文件"集中收纳，让任何人 `git clone` 本仓后能**一键复原**整套构建环境。

| 依赖 | 形态 | 是否魔改 | 何时需要 | 打包方式 |
|---|---|---|---|---|
| **PageIndex** | Python 源码 | ✅ 7 处补丁 | 仅建文档树时 | 上游 commit pin + 补丁文件 |
| **CodeGraph** | npm 全局工具 | ❌ 原版 | 建图谱 + 运行时查询 | 版本锁定 + 安装脚本 |

> **为什么不直接把源码拷进仓？**
> - PageIndex 是我们改过的源码：直接拷会带进上游的 `.git`/`.venv`/`.env 凭据`、有 license 署名问题、且将来无法区分"上游的"和"我们改的"。**补丁文件**把"我们的改动"隔离成一个可审计的 diff，升级上游时一眼能复审——这正是业界对待"魔改开源依赖"的主流做法（pin 上游 + 打补丁）。
> - CodeGraph 是原封不动的第三方工具：vendor 它没有意义，锁版本 + 一行 `npm i -g` 即可。

---

## 目录结构

```
3rd/
├── README.md                  ← 本文件
├── pageindex/
│   ├── cannex.patch           ← 我们对上游 PageIndex 的全部改动（+537/-121，3 文件）
│   ├── .env.example           ← LLM 凭据 + 调优旋钮模板（真 .env 不入库）
│   └── setup.sh               ← 一键重建：clone 上游@pin → 打补丁 → 建 venv → 装依赖
└── codegraph/
    └── setup.sh               ← 一键安装锁定版 codegraph
```

> 注：`setup.sh` 会把 PageIndex clone 到 `3rd/pageindex/PageIndex/`，该子目录已被 `.gitignore` 排除，**不会**进仓。

---

## 快速开始（新开发者 clone 本仓后）

```bash
# ── 1. 重建 PageIndex（魔改版）──────────────────────────────
bash 3rd/pageindex/setup.sh
# 然后编辑凭据：
#   3rd/pageindex/PageIndex/.env   ← 填你自己的 LLM key

# ── 2. 安装 CodeGraph 工具 ─────────────────────────────────
bash 3rd/codegraph/setup.sh

# ── 3.（可选）显式指定 PageIndex 位置 ──────────────────────
# 构建脚本自动按序解析：CANNEX_PAGEINDEX_DIR → 3rd/pageindex/PageIndex → ~/project/CANN/PageIndex。
# 用上面 setup.sh 的默认位置时此步可跳过；装在别处才需要：
# export CANNEX_PAGEINDEX_DIR="/你的/PageIndex"

# ── 4. 拉原始素材 + 建库（在 CannEx 根目录）────────────────
python3 build/sync_sources.py     # 拉 PDF + clone 4 个算子仓 → raw/
python3 build/build_docs.py       # 建文档树 → workspace/docs/
python3 build/build_repos.py      # 建代码图谱 → workspace/repos/*/.codegraph/
```

跑完，文档树和代码图谱都在本地，webchat / skill 即可查询。

> **两个前提（任何方案都绕不开）**
> 1. 你需要 LLM API 凭据（建文档树要调 DeepSeek / Anthropic 网关）。
> 2. 你需要能访问原始素材（PDF 与算子仓 git 地址，已写在 `build/docs.yaml` / `build/repos.yaml`）。

---

## PageIndex 详解

### 补丁里有什么

`cannex.patch` 是对上游 `VectifyAI/PageIndex @ 7592163` 的 diff，涉及 3 个文件：

- `pageindex/config.yaml` — 模型选型（`anthropic/qwen3-max-2026-01-23`）等
- `pageindex/utils.py` — LLM 调用层（流式兼容、token 计数、并发限流、异常分类、熔断器…）
- `pageindex/page_index.py` — 建树主流程（TOC 分批转换、防重复幻影节点、空响应兜底…）

每处补丁的**成因与症状**记录在 CannEx 项目根 `CLAUDE.md` 的「§六 PageIndex 源码补丁」表里——升级上游时**必须逐条复审**。

### 升级上游 PageIndex 的标准流程

```bash
cd 3rd/pageindex/PageIndex
git fetch origin
git checkout <新的上游 commit>
git apply --3way ../cannex.patch     # 三方合并，冲突手工解
# 解完冲突、验证建树正常后，重新导出补丁覆盖旧的：
git diff <新commit> -- pageindex/ > ../cannex.patch
# 同步更新 setup.sh 里的 UPSTREAM_COMMIT 和本 README 的 pin
```

---

## CodeGraph 详解

- 包名：`@colbymchenry/codegraph`
- 锁定版本：**0.9.6**（自此版本起 `codegraph init` 默认非交互，移除了旧 `--yes` flag）
- 最低要求：**0.9.4**（`callers`/`callees`/`impact` 子命令引入版本）
- 安装：`bash 3rd/codegraph/setup.sh`（内部 `npm i -g @colbymchenry/codegraph@0.9.6`）

运行时若 worker / 非登录 shell 找不到二进制，用环境变量显式指定：

```bash
export CANNEX_CODEGRAPH_BIN="$(command -v codegraph)"
```

---

## 关于重产物（不入库，按需重建）

以下派生物体积巨大，**不进 git**（业界主流：只提交"配方"，不提交生成物，类比 `node_modules` / `.venv`），由上面第 4 步的管线确定性重建：

| 产物 | 体积 | 来源 |
|---|---|---|
| `raw/`（PDF + 算子仓源码） | ~1.7 GB | `build/sync_sources.py` |
| `workspace/repos/*/.codegraph/`（代码图谱） | ~1.1 GB | `build/build_repos.py` |

例外：`workspace/docs/`（文档树，仅 ~6 MB）体积小且重建要烧 LLM token，作为"开箱即用样例数据"入库。

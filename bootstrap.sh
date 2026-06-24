#!/usr/bin/env bash
#
# CannEx 一键环境构建脚本 —— 拉仓后跑这一个即可起本地/裸机环境。
#
# 用法：
#   bash bootstrap.sh             # 建 venv + 装依赖 + 生成 deploy/.env(含随机密钥) + 自检
#   bash bootstrap.sh --recreate  # 删掉旧 venv 重建（依赖装坏时用）
#
# 做的事（全部幂等，可反复跑）：
#   1. 锁定 Python 3.11 解释器
#   2. 在 webchat/cannex_chat/.venv 建虚拟环境并装 requirements.txt
#   3. 若无 deploy/.env，从模板生成并写入随机 CHAINLIT_AUTH_SECRET / CANNEX_CONFIG_SECRET
#   4. 自检 codegraph CLI（代码侧检索用）与 workspace 知识产物
# 不做：装 ANTHROPIC_API_KEY（需你手填）、装 node/codegraph（需 npm，按提示自行装）
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
APP_DIR="$PROJECT_ROOT/webchat/cannex_chat"
VENV="$APP_DIR/.venv"
REQ="$APP_DIR/requirements.txt"
SECRETS="$PROJECT_ROOT/deploy/.env"
SECRETS_EXAMPLE="$PROJECT_ROOT/deploy/.env.example"

RECREATE=0
[[ "${1:-}" == "--recreate" ]] && RECREATE=1

say()  { printf '\033[1;36m▶ %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# ── 1. 选 Python 3.11（项目钉死 3.11，不接受更新/更旧版本随意降级）──
pick_python() {
  if command -v python3.11 >/dev/null 2>&1; then echo python3.11; return; fi
  if command -v python3 >/dev/null 2>&1; then
    local ver minor
    ver="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
    minor="${ver#*.}"
    if [[ "${ver%.*}" == "3" && "$minor" -ge 11 ]]; then
      warn "未找到 python3.11，回退用 python3 ($ver)；如装依赖报错请装 3.11"
      echo python3; return
    fi
  fi
  die "未找到 Python 3.11。请先安装：macOS \`brew install python@3.11\` / Debian \`apt install python3.11 python3.11-venv\`"
}
PY="$(pick_python)"
say "使用 Python: $PY ($($PY --version 2>&1))"

# ── 2. 建 venv + 装依赖 ──
if [[ $RECREATE == 1 && -d "$VENV" ]]; then say "删除旧 venv"; rm -rf "$VENV"; fi
if [[ ! -d "$VENV" ]]; then
  say "创建 venv → $VENV"
  "$PY" -m venv "$VENV"
else
  ok "venv 已存在，复用（如需重建用 --recreate）"
fi
say "安装依赖: ${REQ}"
"$VENV/bin/python" -m pip install --upgrade pip --quiet
"$VENV/bin/python" -m pip install -r "$REQ"
ok "依赖安装完成"

# ── 3. 生成 deploy/.env + 随机密钥 ──
gen_secret() {
  if command -v openssl >/dev/null 2>&1; then openssl rand -hex 32
  else "$PY" -c 'import secrets;print(secrets.token_hex(32))'; fi
}
if [[ -f "$SECRETS" ]]; then
  ok "deploy/.env 已存在，跳过（如需重置密钥请手动编辑）"
else
  [[ -f "$SECRETS_EXAMPLE" ]] || die "缺 ${SECRETS_EXAMPLE} ，无法生成 .env"
  say "生成 deploy/.env 并写入随机密钥"
  "$PY" - "$SECRETS_EXAMPLE" "$SECRETS" "$(gen_secret)" "$(gen_secret)" <<'PY'
import sys
src, dst, auth, cfg = sys.argv[1:5]
seen = set()
out = []
for ln in open(src).read().splitlines():
    if ln.startswith("CHAINLIT_AUTH_SECRET="):
        out.append(f"CHAINLIT_AUTH_SECRET={auth}"); seen.add("a")
    elif ln.startswith("CANNEX_CONFIG_SECRET="):
        out.append(f"CANNEX_CONFIG_SECRET={cfg}"); seen.add("c")
    else:
        out.append(ln)
if "a" not in seen: out.append(f"CHAINLIT_AUTH_SECRET={auth}")
if "c" not in seen: out.append(f"CANNEX_CONFIG_SECRET={cfg}")
open(dst, "w").write("\n".join(out) + "\n")
PY
  ok "已生成 deploy/.env（密钥随机，ANTHROPIC_API_KEY 仍需手填）"
fi

# ── 4. 自检（不阻断）──
say "环境自检"
if command -v codegraph >/dev/null 2>&1; then
  ok "codegraph CLI: $(codegraph --version 2>&1 | head -1)（代码侧 L1-L4 可用）"
else
  warn "未装 codegraph CLI → 代码侧调用链/影响面检索不可用（文档侧不受影响）"
  warn "  需要时装：npm i -g @colbymchenry/codegraph@latest"
fi
if [[ -f "$PROJECT_ROOT/workspace/_meta.json" ]]; then
  ok "workspace 知识产物就位（文档侧可用）"
else
  warn "缺 workspace/_meta.json → 检索会失败，确认 clone 完整"
fi

cat <<EOF

$(printf '\033[1;32m环境就绪。\033[0m')下一步：
  1. 编辑 deploy/.env，填 ANTHROPIC_API_KEY（及 ANTHROPIC_BASE_URL，用代理时）
  2. 启动：  bash deploy/run_local.sh          # 默认 0.0.0.0:8080
     或开发：source $VENV/bin/activate && cd $APP_DIR && chainlit run app.py -w
  3. 建账号：见 deploy/README.md 的 seed_users 用法
EOF

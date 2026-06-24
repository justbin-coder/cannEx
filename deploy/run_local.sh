#!/usr/bin/env bash
#
# CannEx webchat 本地直跑启动脚本（非 Docker 部署）。
#
# 用法：
#   bash deploy/run_local.sh          # 停掉旧进程并重启（更新后端后用这个）
#
# 设计说明：
# - 这里 export 的环境变量会【优先于】.env —— app.py 用 load_dotenv(override=False)，
#   故无需修改 .env 即可纠正其中残留的 macOS CANNEX_ROOT 路径。
# - 敏感密钥（CHAINLIT_AUTH_SECRET / CANNEX_CONFIG_SECRET）不写在本脚本里，
#   而是从 deploy/.env（已 gitignore）读取；首次部署见 deploy/README.md。
# - ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL / CANNEX_MODEL 仍由 webchat 的 .env 提供。
#
set -euo pipefail

# 由脚本自身位置推导项目根（deploy/ 的上一级），不再硬编码绝对路径。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="$PROJECT_ROOT/webchat/cannex_chat"
LOG_FILE="$PROJECT_ROOT/logs/webchat.log"
SECRETS_FILE="$SCRIPT_DIR/.env"

# —— 加载部署密钥（deploy/.env，不入库）——
if [[ -f "$SECRETS_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$SECRETS_FILE"; set +a
fi

# —— 运行所需环境量（路径 + 用户库）——
export CANNEX_ROOT="$PROJECT_ROOT"
export CANNEX_USERS_DB="${CANNEX_USERS_DB:-$PROJECT_ROOT/deploy/cannex.db}"

# auth secret 必填：会话 JWT 签名密钥。换掉它会注销所有在线用户。
if [[ -z "${CHAINLIT_AUTH_SECRET:-}" ]]; then
  echo "ERROR: CHAINLIT_AUTH_SECRET 未设置。" >&2
  echo "  在 $SECRETS_FILE 写入（首次可这样生成）：" >&2
  echo "    echo \"CHAINLIT_AUTH_SECRET=\$(openssl rand -hex 32)\" >> \"$SECRETS_FILE\"" >&2
  echo "    echo \"CANNEX_CONFIG_SECRET=\$(openssl rand -hex 32)\" >> \"$SECRETS_FILE\"" >&2
  exit 1
fi
export CHAINLIT_AUTH_SECRET
# LLM 配置加密密钥；不设则代码回落 CHAINLIT_AUTH_SECRET。
export CANNEX_CONFIG_SECRET="${CANNEX_CONFIG_SECRET:-}"

# —— 幂等停旧进程 ——
if pkill -f "chainlit run app.py" 2>/dev/null; then
  echo "stopped existing chainlit process(es), waiting 1s ..."
  sleep 1
fi

cd "$APP_DIR"
if [[ ! -f ".venv/bin/activate" ]]; then
  echo "ERROR: 未找到 venv ($APP_DIR/.venv)。首次部署请先创建：" >&2
  echo "    python3.11 -m venv \"$APP_DIR/.venv\"" >&2
  echo "    \"$APP_DIR/.venv/bin/pip\" install -r \"$APP_DIR/requirements.txt\"" >&2
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

PORT="${CANNEX_PORT:-8080}"
echo "starting chainlit on 0.0.0.0:$PORT  (log: $LOG_FILE)"
nohup chainlit run app.py --host 0.0.0.0 --port "$PORT" --headless \
  > "$LOG_FILE" 2>&1 &
echo "started, pid $!"
echo "tail -f $LOG_FILE  # 查看启动日志"

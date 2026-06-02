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
# - ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL / CANNEX_MODEL 仍由 .env 提供。
#
set -euo pipefail

# 由脚本自身位置推导项目根（deploy/ 的上一级），不再硬编码绝对路径。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="$PROJECT_ROOT/webchat/cannex_chat"
LOG_FILE="$PROJECT_ROOT/logs/webchat.log"

# —— 运行所需环境量（路径 + 用户库 + auth secret）——
export CANNEX_ROOT="$PROJECT_ROOT"
export CANNEX_USERS_DB="$PROJECT_ROOT/deploy/cannex.db"
# 固定 auth secret：重启后已登录会话不失效；换掉它会注销所有在线用户。
export CHAINLIT_AUTH_SECRET=db07e9611a634ca8f8dc330c8c00889c2097811d4a93c4da3beb6d2c6c3ed133

# LLM 配置加密密钥；不设则回落 CHAINLIT_AUTH_SECRET。
export CANNEX_CONFIG_SECRET=db07e9611a634ca8f8dc330c8c00889c2097811d4a93c4da3beb6d2c6c3ed133

# —— 幂等停旧进程 ——
if pkill -f "chainlit run app.py" 2>/dev/null; then
  echo "stopped existing chainlit process(es), waiting 1s ..."
  sleep 1
fi

cd "$APP_DIR"
# shellcheck disable=SC1091
source .venv/bin/activate

echo "starting chainlit on 0.0.0.0:8000  (log: $LOG_FILE)"
nohup chainlit run app.py --host 0.0.0.0 --port 8000 --headless \
  > "$LOG_FILE" 2>&1 &
echo "started, pid $!"
echo "tail -f $LOG_FILE  # 查看启动日志"

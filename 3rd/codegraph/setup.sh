#!/usr/bin/env bash
# ============================================================================
# CodeGraph 依赖安装脚本
# ----------------------------------------------------------------------------
# CodeGraph 是未魔改的第三方 npm 工具，无需 vendor，全局安装锁定版本即可。
# 建库（build_repos.py）和运行时（webchat/skill 查 callers/impact）都依赖它。
# ============================================================================
set -euo pipefail

PKG="@colbymchenry/codegraph"
PIN="0.9.6"          # 锁定版本：0.9.6 起 init 默认非交互（移除了 --yes）
MIN="0.9.4"          # CannEx 代码要求的最低版本（callers/callees/impact 引入版本）

echo "==> CodeGraph 安装：$PKG@$PIN"

command -v npm >/dev/null 2>&1 || {
  echo "ERROR: 缺少 npm。请先装 Node.js（推荐 nvm）：https://github.com/nvm-sh/nvm"
  exit 1
}

# 已装且版本达标则跳过
if command -v codegraph >/dev/null 2>&1; then
  CUR="$(codegraph --version 2>/dev/null | head -1 | grep -oE '^[0-9]+\.[0-9]+\.[0-9]+' || true)"
  if [ "$CUR" = "$PIN" ]; then
    echo "    ✅ 已安装 codegraph $CUR，跳过"
    exit 0
  fi
  echo "    当前 codegraph 版本 = ${CUR:-未知}，将安装锁定版 $PIN"
fi

npm i -g "$PKG@$PIN"

echo ""
echo "==> 校验..."
codegraph --version
echo "    ✅ CodeGraph 就绪（最低要求 $MIN，已装 $PIN）"
echo ""
echo "提示：若 worker/非登录 shell 找不到 codegraph，可显式指定二进制路径："
echo "      export CANNEX_CODEGRAPH_BIN=\"\$(command -v codegraph)\""

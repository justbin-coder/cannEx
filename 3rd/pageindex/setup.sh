#!/usr/bin/env bash
# ============================================================================
# PageIndex 依赖一键重建脚本（魔改版）
# ----------------------------------------------------------------------------
# 做什么：clone 上游 PageIndex@锁定commit → 应用 CannEx 补丁 → 建 venv → 装依赖
# 产物：3rd/pageindex/PageIndex/（已被 .gitignore 排除，不入库）
# 幂等：PageIndex/ 已存在则跳过 clone+apply，仅确保依赖装好
# ============================================================================
set -euo pipefail

# ── 锁定参数 ────────────────────────────────────────────────────────────────
UPSTREAM_REPO="https://github.com/VectifyAI/PageIndex.git"
UPSTREAM_COMMIT="7592163e2a376b3917181fff9ac1858dc5daa2c6"  # Update README (#271)

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$HERE/PageIndex"
PATCH="$HERE/cannex.patch"

echo "==> PageIndex 重建开始"
echo "    上游: $UPSTREAM_REPO"
echo "    commit: $UPSTREAM_COMMIT"
echo "    目标: $TARGET"

# ── 前置检查 ────────────────────────────────────────────────────────────────
for bin in git python3; do
  command -v "$bin" >/dev/null 2>&1 || { echo "ERROR: 缺少 $bin，请先安装"; exit 1; }
done
[ -f "$PATCH" ] || { echo "ERROR: 找不到补丁 $PATCH"; exit 1; }

# ── clone + checkout pin + apply 补丁 ───────────────────────────────────────
if [ -d "$TARGET/.git" ]; then
  echo "==> PageIndex 已存在，跳过 clone（如需重建请先删除 $TARGET）"
else
  echo "==> clone 上游..."
  git clone "$UPSTREAM_REPO" "$TARGET"
  git -C "$TARGET" checkout "$UPSTREAM_COMMIT"

  echo "==> 应用 CannEx 补丁..."
  # 先 dry-run 校验，再正式应用，失败即报错退出（不留半残状态）
  git -C "$TARGET" apply --check "$PATCH"
  git -C "$TARGET" apply "$PATCH"
  echo "    ✅ 补丁应用成功"
fi

# ── Python venv + 依赖 ──────────────────────────────────────────────────────
if [ ! -d "$TARGET/.venv" ]; then
  echo "==> 创建 venv（Python 3.11 推荐）..."
  python3 -m venv "$TARGET/.venv"
fi
echo "==> 安装依赖..."
"$TARGET/.venv/bin/pip" install -q --upgrade pip
"$TARGET/.venv/bin/pip" install -q -r "$TARGET/requirements.txt"
echo "    ✅ 依赖安装完成"

# ── 凭据提示 ────────────────────────────────────────────────────────────────
if [ ! -f "$TARGET/.env" ]; then
  cp "$HERE/.env.example" "$TARGET/.env"
  echo ""
  echo "⚠️  已生成 $TARGET/.env（模板），请填入你自己的 LLM 凭据后再建树！"
fi

cat <<EOF

==> 完成 ✅

后续步骤：
  1. 编辑凭据：  $TARGET/.env
  2. 告诉 CannEx 构建脚本 PageIndex 在哪（二选一）：
       export CANNEX_PAGEINDEX_DIR="$TARGET"
     或把该 export 写进你的 shell 配置 / CannEx 的 .env
  3. 回到 CannEx 根目录建文档树：
       python3 build/build_docs.py
EOF

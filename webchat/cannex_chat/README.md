# CannEx Webchat

CannEx 的 Web 形态（Phase 2）——基于 Chainlit + Anthropic tool_use 的 Agentic RAG 应用。

## 架构

- **前端**：Chainlit，BYOK（用户自带 Anthropic API key）
- **后端**：Agent Loop（最多 3 轮 tool_use）+ 持久 Worker 进程
- **知识层**：复用 Phase 1 的 `workspace/`（PageIndex 文档树 + CodeGraph 代码索引）
- **教学原则**：单一来源 `skills/ascend-c/SKILL.md`

详见 `docs/specs/2026-05-24-webchat-architecture-design.md`。

## 快速上手（推荐）

拉仓后跑一键脚本：建 venv（Python 3.11）、装依赖、生成 `deploy/.env`（含随机密钥）、自检。

```bash
cd <项目根>
bash bootstrap.sh                  # 依赖装坏时用 bash bootstrap.sh --recreate
bash deploy/run_local.sh          # 直接启动；LLM key 由用户在 UI 里 BYOK，无需在 .env 填
```

## 本地开发（手动等价步骤）

```bash
# 1. 进入项目根目录
cd <项目根>

# 2. 创建 venv（首次）
python3.11 -m venv webchat/cannex_chat/.venv

# 3. 激活 venv 并安装依赖
source webchat/cannex_chat/.venv/bin/activate
pip install -r webchat/cannex_chat/requirements.txt

# 4. 配置环境变量
cp webchat/cannex_chat/.env.example webchat/cannex_chat/.env
# 编辑 .env，填写 ANTHROPIC_API_KEY（或依赖 BYOK）
# CANNEX_ROOT 无需设置，代码会自动推导

# 5. 启动 Chainlit（开发模式，-w 自动重载）
cd webchat/cannex_chat
chainlit run app.py -w
```

打开 http://localhost:8000，按 UI 提示配置 Anthropic API key。

## 团队部署（Mac / Linux 裸跑）

```bash
# 一键启动（自动推导路径、停旧进程、绑 0.0.0.0:8000）
bash deploy/run_local.sh
```

团队成员通过 `http://<本机IP>:8000` 访问。

用户管理：
```bash
# 添加用户
CANNEX_USERS_DB=$PWD/deploy/cannex.db \
  PYTHONPATH=$PWD \
  webchat/cannex_chat/.venv/bin/python3 deploy/seed_users.py <username> <password>

# 列出用户
# 同上，参数改为 --list

# 删除用户
# 同上，参数改为 --delete <username>
```

详见 `deploy/README.md`。

## 生产部署（Docker Compose + HTTPS）

详见 `deploy/README.md`（Docker Compose + Caddy 反代 + 自动 HTTPS）。

## BYOK 隐私承诺

你的 API key:
- 仅存于浏览器当前会话内存
- 不写入服务端日志
- 不持久化到数据库或文件
- 不转发任何第三方
- 关闭浏览器 / 刷新页面即删除

## 跑测试

```bash
cd <项目根>
python3 -m pytest webchat/cannex_chat/tests/ -v
```

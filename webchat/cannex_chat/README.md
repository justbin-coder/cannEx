# CannEx Webchat

CannEx 的 Web 形态（Phase 2）——基于 Chainlit + Anthropic tool_use 的 Agentic RAG 应用。

## 架构

- **前端**：Chainlit，BYOK（用户自带 Anthropic API key）
- **后端**：Agent Loop（最多 3 轮 tool_use）+ 持久 Worker 进程
- **知识层**：复用 Phase 1 的 `workspace/`（PageIndex 文档树 + CodeGraph 代码索引）
- **教学原则**：单一来源 `skills/ascend-c/SKILL.md`

详见 `docs/specs/2026-05-24-webchat-architecture-design.md`。

## 本地运行

```bash
# 1. 进入项目根，激活 webchat venv
cd /Users/justbin/Desktop/CannEx
source webchat/cannex_chat/.venv/bin/activate

# 2. 安装依赖（首次）
pip install -r webchat/cannex_chat/requirements.txt

# 3. 配置环境变量
cp webchat/cannex_chat/.env.example webchat/cannex_chat/.env
# 编辑 .env，确认 CANNEX_ROOT 指向项目根

# 4. 启动 Chainlit（从项目根运行）
cd /Users/justbin/Desktop/CannEx
chainlit run webchat/cannex_chat/app.py -w
```

打开 http://localhost:8000，按 UI 提示配置自己的 Anthropic API key（[去 Anthropic Console 申请](https://console.anthropic.com/)）。

## BYOK 隐私承诺

你的 API key:
- 仅存于浏览器当前会话内存
- 不写入服务端日志
- 不持久化到数据库或文件
- 不转发任何第三方
- 关闭浏览器 / 刷新页面即删除

## 跑测试

```bash
cd /Users/justbin/Desktop/CannEx
python3 -m pytest webchat/cannex_chat/tests/ -v
```

## 部署

部署形态（Dockerfile / nginx / HTTPS / 域名）作为独立后续 plan，本工程目前仅支持本地运行。

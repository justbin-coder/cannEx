# CannEx Beta 部署指南

> 适用：单机 Docker Compose 部署，5-20 人内部 beta，自建机房 + 公网 IP。

---

## ⚠️ 本机实际部署现状（2026-05-30，先读这节）

> 本文档其余章节描述的是 **Docker Compose 设想方案**。但当前服务器（项目根目录，下文记作 `<repo-root>`，
> 即本 README 所在 `deploy/` 的上一级）实际**不是用 Docker 跑的**，而是直接 `chainlit run` 裸跑。
> README 里所有 `docker compose exec ...` 命令在本机**不适用**，请改用本节命令。本节命令均假设已 `cd` 到 `<repo-root>`。

**实际运行形态**
- 进程：`chainlit run app.py --host 0.0.0.0 --port 8000 --headless`（无 Caddy / 无容器 / 无 systemd）
- 访问：`http://<本机IP>:8000`（无 HTTPS 反代）
- 不带 `-w`，**改代码不会自动重载，必须手动重启**
- 用户库：`deploy/cannex.db`（由 env `CANNEX_USERS_DB` 指定）

**必备环境量**
- `CANNEX_ROOT`（由 `run_local.sh` 按脚本位置自动推导为 `<repo-root>`，覆盖 `.env` 里残留的 macOS 路径）
- `CANNEX_USERS_DB=<repo-root>/deploy/cannex.db`（可在 `deploy/.env` 覆盖）
- `CHAINLIT_AUTH_SECRET`（**必填**，会话 JWT 签名密钥；换掉会注销所有在线用户）
- `CANNEX_CONFIG_SECRET`（可选，LLM 配置加密密钥；缺省回落 `CHAINLIT_AUTH_SECRET`；轮换会使所有用户 key 失效）
- `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL` / `CANNEX_MODEL` 由 `webchat/cannex_chat/.env` 提供

> 🔐 **密钥不再硬编码在脚本里**。`run_local.sh` 启动时从 `deploy/.env`（已 gitignore）读取
> `CHAINLIT_AUTH_SECRET` / `CANNEX_CONFIG_SECRET`，缺失会直接报错。首次部署：
> ```bash
> cd <repo-root>/deploy && cp .env.example .env
> echo "CHAINLIT_AUTH_SECRET=$(openssl rand -hex 32)" >> .env
> echo "CANNEX_CONFIG_SECRET=$(openssl rand -hex 32)" >> .env
> ```

**更新后端 / 重启**
```bash
bash deploy/run_local.sh   # 幂等停旧进程 + 重启 + 落日志到 logs/webchat.log
```

**用户增删改查**（本机版，注意 env + venv + PYTHONPATH，勿用 README 后文的 docker 写法）
```bash
cd <repo-root>            # 本 README 在 deploy/ 下，其上一级即项目根
PFX="CANNEX_USERS_DB=$PWD/deploy/cannex.db PYTHONPATH=$PWD \
  webchat/cannex_chat/.venv/bin/python3 deploy/seed_users.py"

eval "$PFX alice MySecretPw123"   # 新增 / 重置密码（同名 upsert）
eval "$PFX --list"                # 列出
eval "$PFX --delete alice"        # 删除
```
> 增删用户**无需重启**——auth 每次登录现查 SQLite，立即生效。

**账号管理**
> ⚠️ 不要把明文密码写进本文件（会随 git 入库泄露）。账号一律用上面的 `seed_users.py`
> 命令创建/重置，密码私下传递。fresh 部署没有任何预置账号，需先 seed。

---

## 拓扑

```
浏览器
  │  HTTPS (443) ── nip.io 域名
  ▼
Caddy 容器 (cannex-caddy)
  │  HTTP (内部网络 8000)
  ▼
Chainlit 容器 (cannex-web)
  ├─ /app/workspace (ro)  ← 从本地 rsync 上来
  ├─ /data (rw)           ← SQLite 用户库（卷）
  └─ /app/logs (rw)       ← 应用日志（卷）
```

## 服务器先决条件

- **OS**: openEuler 24.03 LTS-SP3（已确认）
- Docker 24+ 和 Docker Compose v2（`docker compose version` 应 ≥ 2.20）
- 公网 IP `179.147.19.2`（其他 IP 请改 `Caddyfile` 和下文 nip.io 域名）
- **入站 80 + 443 端口可达**（Let's Encrypt HTTP-01 challenge 必需）
  - 检查方法见下文「端口检查」节
- 至少 4GB 内存、20GB 磁盘空闲

### Docker 安装（openEuler 没自带）

```bash
# openEuler 官方源里有 docker-ce 兼容包，但版本可能旧。推荐用 Docker 上游源：
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
# openEuler 24.03 兼容 EL9，把 repo 里的 $releasever 改成 9：
sudo sed -i 's|$releasever|9|g' /etc/yum.repos.d/docker-ce.repo

sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker

# 当前用户加入 docker 组，免 sudo
sudo usermod -aG docker $USER
newgrp docker

# 验证
docker version
docker compose version
```

如果 Docker 官方源在国内拉取慢，可以用 openEuler 自带的 `moby-engine`（功能略简但够 beta 用）：

```bash
sudo dnf install -y moby-engine moby-cli
sudo systemctl enable --now docker
# moby-engine 不含 compose plugin，单独装：
sudo dnf install -y docker-compose-plugin || pip install docker-compose
```

---

## 一次性部署流程

### 1. 上传代码到服务器

本机上：

```bash
# 从项目根目录执行（不上传 workspace、raw、.venv 等）
rsync -avz --exclude='workspace/' --exclude='raw/' --exclude='.venv/' \
      --exclude='.git/' --exclude='__pycache__/' --exclude='reports/' \
      --exclude='webchat/chainlit/' \
      ./ jiazhibin@179.147.19.2:~/cannex/
```

### 2. 上传知识库（workspace/）

```bash
# workspace ~425MB，单独同步，按需重传
rsync -avz --delete workspace/ jiazhibin@179.147.19.2:~/cannex/workspace/
```

### 3. 端口检查与放行（openEuler 用 firewalld）

```bash
# 看 80/443 有没有被占
sudo ss -tlnp | grep -E ':(80|443)\s'

# 看 firewalld 状态和当前放行规则
sudo systemctl status firewalld --no-pager
sudo firewall-cmd --list-all

# 放行 80/443
sudo firewall-cmd --permanent --add-port=80/tcp
sudo firewall-cmd --permanent --add-port=443/tcp
sudo firewall-cmd --reload
sudo firewall-cmd --list-ports     # 验证 80/tcp 443/tcp 都在
```

**SELinux**（openEuler 默认 enforcing）：Docker 反代场景下一般无需特别配置，但如果 Caddy 容器日志报 `permission denied` 访问外部 socket，可能要放行：

```bash
getenforce                                  # 看当前模式
sudo setsebool -P httpd_can_network_connect 1   # 一次性允许 httpd 类容器出站
```

从**外部网络**（手机热点 / 别的云服务器）验证：

```bash
nc -zv 179.147.19.2 80
nc -zv 179.147.19.2 443
```

22 通但 80/443 不通 → ISP 封了入站 80/443（自建机房少见但有）或机房边界设备拦了。两种情况都得切 Cloudflare Tunnel 方案，见末尾「后续可选项」。

### 4. 配置环境变量

服务器上：

```bash
cd ~/cannex/deploy
cp .env.example .env

# 生成 Chainlit 签名密钥
echo "CHAINLIT_AUTH_SECRET=$(openssl rand -hex 32)" >> .env

# 编辑填入 Anthropic key 和 bytego 代理地址
vim .env
```

`.env` 关键字段：

```
CHAINLIT_AUTH_SECRET=<openssl rand -hex 32 的输出>
ANTHROPIC_API_KEY=sk-ant-...                # 共享兜底 key
ANTHROPIC_BASE_URL=https://api.bytego.xxx   # bytego 代理
```

### 5. 构建并启动

```bash
cd ~/cannex/deploy
docker compose up -d --build
docker compose logs -f web
```

首次启动 Caddy 会自动向 Let's Encrypt 申请证书，可能需要 30-60 秒。看到 `certificate obtained successfully` 类日志即成功。

### 6. 初始化用户账号

```bash
# 添加第一个用户
docker compose exec web python /app/deploy/seed_users.py alice MySecretPw123

# 批量添加（推荐）
cat <<EOF | docker compose exec -T web python /app/deploy/seed_users.py --stdin
alice pw_for_alice
bob   pw_for_bob
carol pw_for_carol
EOF

# 列出现有用户
docker compose exec web python /app/deploy/seed_users.py --list

# 删除用户
docker compose exec web python /app/deploy/seed_users.py --delete alice
```

### 7. 访问验证

浏览器打开：

```
https://179-147-19-2.nip.io
```

应该看到 Chainlit 登录页。用上一步创建的账号登录即可。

---

## 日常运维

### 看日志

```bash
docker compose logs -f web              # 应用日志
docker compose logs -f caddy            # 反代/证书日志
docker compose exec web ls /app/logs    # 持久化日志卷
```

### 更新代码

```bash
# 本机推新代码
rsync -avz --exclude='workspace/' --exclude='.venv/' --exclude='.git/' \
      --exclude='__pycache__/' --exclude='webchat/chainlit/' \
      ./ jiazhibin@179.147.19.2:~/cannex/

# 服务器上重建
cd ~/cannex/deploy
docker compose up -d --build
```

### 更新 workspace（月度跑完管道之后）

```bash
# 本机 rsync workspace
rsync -avz --delete workspace/ jiazhibin@179.147.19.2:~/cannex/workspace/

# 容器无需重启 — workspace 是只读卷，重新挂载即生效
# 但如果担心缓存，可以重启 web：
docker compose restart web
```

### 备份用户库

```bash
# SQLite DB 在命名卷 cannex-data 里
docker compose exec web cat /data/cannex.db > backup-$(date +%F).db
```

### 停止/卸载

```bash
docker compose down              # 停服务，保留卷
docker compose down -v           # 停服务并删除所有数据卷（危险）
```

---

## 故障排查

| 症状 | 排查 |
|---|---|
| `https://...nip.io` 浏览器红警告 / 拒绝连接 | Caddy 证书没签下来。`docker compose logs caddy` 看 acme 报错。最常见原因：80 端口外部不可达。 |
| 登录页能开但密码不对 | `docker compose exec web ls -la /data/cannex.db`。如果没有该文件，回到第 6 步先建用户。 |
| 登录成功但发问后报 `401 invalid_api_key` | `.env` 里 `ANTHROPIC_API_KEY` 没填或 `ANTHROPIC_BASE_URL` 错。重启 `docker compose restart web`。 |
| 代码侧检索报错 `codegraph CLI not found` | 镜像里 codegraph 应该已装。`docker compose exec web codegraph --version` 验证。 |
| 工具调用全部失败，提到 `workspace/_meta.json` | workspace 没 rsync 上来，或挂载路径错。`docker compose exec web ls /app/workspace/` 验证。 |
| WebSocket 连不上、消息发不出 | Caddy 默认支持 ws，但如果前面还有别的代理（公司负载均衡），需放行 `Upgrade` header。 |

---

## 后续可选项

1. **线程持久化**：Chainlit 自带 `SQLAlchemyDataLayer` 但 schema 是 Postgres 风格，SQLite 需要适配。当 beta 用户反馈想保留历史记录时再上。届时换 Postgres 容器更省心。
2. **可观测性**：现在依赖 `/app/logs/*.log`。需要的话加 Loki + Grafana。
3. **限流升级**：当前 30/min/session 是进程内 dict，重启清零。多实例时换 Redis。
4. **HTTPS 备用方案**：如果 80/443 始终打不开 → 切 Cloudflare Tunnel，Caddy 容器替换为 cloudflared，路由 `web:8000`，零端口暴露。

---

## 关键文件清单（这次新增/修改的）

```
deploy/
├── Dockerfile             ← 镜像构建
├── docker-compose.yaml    ← 两服务编排（web + caddy）
├── Caddyfile              ← 反代 + 自动 HTTPS（nip.io）
├── .env.example           ← 部署侧 secrets 模板
├── seed_users.py          ← 用户增删改查 CLI
└── README.md              ← 本文件

webchat/cannex_chat/
├── auth.py                ← 新增：bcrypt + SQLite 鉴权回调
├── app.py                 ← 加一行 import auth 触发回调注册
└── requirements.txt       ← 新增 bcrypt 依赖

.dockerignore              ← 镜像构建忽略清单
```

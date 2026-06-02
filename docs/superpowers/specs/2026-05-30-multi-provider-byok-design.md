# 多供应商 LLM 配置（BYOK v2）设计

> 让 webchat 用户在登录后自选 LLM 供应商（DeepSeek / OpenAI 兼容端点）、自填
> base_url / model / api_key，取消服务端兜底，配置按用户加密持久化。

**日期**：2026-05-30
**状态**：已评审通过，待写实施计划
**关联代码**：`webchat/cannex_chat/`（agent / ui / app.py / deploy）

---

## 1. 背景与问题

当前 webchat 的 LLM 配置三个参数中只有 `api_key` 是 per-user 的（BYOK，存 `user_session`），
`model` 与 `base_url` 是**全局写死**的：

- `model` = `CANNEX_MODEL` env，模块级常量（`agent/loop.py:16`），默认 `claude-sonnet-4-6`
- `base_url` = `ANTHROPIC_BASE_URL` env，client `__init__` 读取（`agent/anthropic_client.py:16`），固定指向 bytego 代理
- `api_key` = `user_session` 的 BYOK，回落 `.env` 的 `ANTHROPIC_API_KEY`（`app.py:121-123`）

后果：用户即便填了 DeepSeek 的 key，model 仍是 claude、base_url 仍指 bytego，请求必败。
用户**无法切换供应商**。

**关键利好**：客户端底层是 **litellm**（`agent/anthropic_client.py:7`），本身供应商无关，
chunk 解析已是 OpenAI 归一化格式。故 agent 交互逻辑（流式 / 工具调用）**无需 per-provider 适配**，
改动集中在「把 model/base_url 从全局变为 per-session 透传 + 配置持久化 + UI」。

---

## 2. 目标与非目标

**目标**
- 用户登录后可选供应商（v1：DeepSeek、OpenAI 兼容自定义端点），自填 base_url / model / api_key
- 取消服务端兜底：BYOK 强制，未配置不能对话
- 配置（含 key，加密）按用户持久化到 `cannex.db`，重登沿用

**非目标（YAGNI）**
- 不做 Anthropic 专档、不保留服务端默认 key 兜底
- 不做策展模型下拉（model 名交给用户自由填）
- 不做每用户多套命名 profile（每用户一份当前配置）
- 不做模型能力探测（是否支持工具调用由用户自负，仅 UI 提示）

---

## 3. 行为与交互

### 3.1 BYOK 设置面板（Chainlit `ChatSettings`，四控件）

| 控件 | id | 说明 |
|---|---|---|
| `Select` 供应商 | `provider` | 选项：`DeepSeek` / `OpenAI 兼容(自定义端点)` |
| `TextInput` base_url | `base_url` | DeepSeek 可留空（自动用官方）；OpenAI 兼容档**必填** |
| `TextInput` model | `model` | 自由填；placeholder 提示「须支持工具调用（如 deepseek-chat），否则检索会失效」 |
| `TextInput` api_key | `api_key` | placeholder「已保存则留空沿用，填写则更新」 |

### 3.2 生命周期

- **登录 / on_chat_start**：从 `cannex_llm_config` 载回该用户配置 → 写入 `user_session`；
  面板 initial 值预填 provider / base_url / model；api_key **不回显**（留空，占位提示已保存）。
- **保存设置**：`provider/base_url/model` 落库；`api_key` 非空则加密落库并更新会话，为空则沿用旧值。
- **无配置**：显示引导 banner（扩展现有 `NO_KEY_PROMPT`），不进入对话。

### 3.3 校验

- 选 `OpenAI 兼容` 但 `base_url` 为空 → 报错提示，不保存。
- `model` 为空 → 报错提示。
- `api_key` 为空且库中也无既存 key → 视为未配置。

---

## 4. 数据模型与加密

### 4.1 新表 `cannex_llm_config`（与认证表 `cannex_users` 分离）

```sql
CREATE TABLE IF NOT EXISTS cannex_llm_config (
    username     TEXT PRIMARY KEY,          -- 关联 cannex_users.username
    provider     TEXT NOT NULL,             -- 'deepseek' | 'openai_compat'
    base_url     TEXT,                       -- openai_compat 必填；deepseek 可空
    model        TEXT NOT NULL,
    api_key_enc  TEXT NOT NULL,             -- Fernet 加密后的密文
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
```

每用户一行（upsert，`ON CONFLICT(username) DO UPDATE`）。

### 4.2 key 加密

- 用 `cryptography` 的 **Fernet** 对称加密。
- 加密密钥派生：从 env `CANNEX_CONFIG_SECRET` 取；缺失则回落 `CHAINLIT_AUTH_SECRET`。
  Fernet 需 32 字节 urlsafe-base64 key → `base64.urlsafe_b64encode(sha256(secret.encode()).digest())`。
- **接受的安全后果（设计决策）**：
  1. 服务端 DB 存有用户供应商 key（已加密，但持有 `CANNEX_CONFIG_SECRET` 即可解密）。
  2. 轮换 `CANNEX_CONFIG_SECRET` 会使所有已存 key 无法解密，用户需重填（行为：解密失败按「无 key」处理并提示重配）。

### 4.3 迁移

- `requirements.txt` 增 `cryptography`。
- 给现有 `deploy/cannex.db` 建新表：沿用 `seed_users.py` 同款幂等 `CREATE TABLE IF NOT EXISTS`
  （在 `llm_config` 模块首次连接时自动建表，无需独立迁移脚本）。

---

## 5. 组件与代码改动

> 原则：agent loop 的流式 / 工具逻辑**零改**（litellm 已归一化）。改动集中在配置透传 + 持久化 + UI。

### 5.1 新增 `agent/providers.py` — 供应商注册表（纯函数）

```
PROVIDERS: dict[provider_id -> {label, litellm_prefix, default_base_url, base_url_required}]
  deepseek      -> {prefix="deepseek",  default_base_url="https://api.deepseek.com", base_url_required=False}
  openai_compat -> {prefix="openai",    default_base_url="",                          base_url_required=True}

resolve(provider, model, base_url) -> (litellm_model, api_base)
  deepseek      -> (f"deepseek/{model}", base_url or default_base_url)
  openai_compat -> (f"openai/{model}",   base_url)   # base_url 必填，缺则 raise
```

- 单一职责：把「用户面概念（provider/model/base_url）」翻译成「litellm 调用参数」。
- 无 IO、无依赖，纯函数，独立可测。

### 5.2 新增 `agent/llm_config.py` — 持久化 + 加解密

- `load_config(username) -> dict | None`：读 DB → 解密 key → 返回 `{provider, base_url, model, api_key}`；
  解密失败返回 None（按未配置处理）。
- `save_config(username, provider, base_url, model, api_key)`：加密 key → upsert。
- `_fernet()`：从 env 派生 Fernet 实例（见 §4.2）。
- 首次连接自动建表（§4.3）。

### 5.3 改 `agent/anthropic_client.py`

- `create_stream(..., base_url: str | None = None)`：新增 per-call `base_url` 入参，覆盖全局；
  传入则 `kwargs["api_base"] = base_url`。
- 类名 `AnthropicStreamClient` → **`LLMStreamClient`**（正在动它，理顺误导命名；同步改 `app.py` import）。

### 5.4 改 `agent/loop.py`

- 删模块级常量 `MODEL`。
- `run(...)` / `_stream_turn(...)` 增 `model` + `base_url` 参数，透传给 `create_stream`。

### 5.5 改 `app.py`

- on_chat_start：`llm_config.load_config(user)` → 写 `user_session`（provider/base_url/model/api_key）。
- 发消息：从会话取 model/base_url/api_key，传入 `loop.run`。
- 无配置（无 key 或 resolve 失败）：显示引导 banner，不调 LLM。
- 加固错误处理：工具调用失败 / 401 / 403 给更明确提示。

### 5.6 重写 `ui/byok.py`

- `make_byok_settings(current: dict | None)`：四控件，initial 预填 current（key 除外）。
- `save_llm_config(settings, username)`：校验（§3.3）→ `llm_config.save_config` → 写会话；
  key 空则沿用旧值。

### 5.7 部署

- `deploy/run_local.sh`、`deploy/.env.example`、`deploy/README.md`：补 `CANNEX_CONFIG_SECRET` 说明
  （可选，缺省回落 `CHAINLIT_AUTH_SECRET`）。

---

## 6. 测试（全程 TDD）

| 单元 | 用例 |
|---|---|
| `providers.resolve` | deepseek→`deepseek/<model>`+默认 url；openai_compat→`openai/<model>`+用户 url；openai_compat 缺 base_url→raise |
| `llm_config` | 加解密往返；DB upsert + load；解密失败→None；首次建表 |
| `byok` | save 校验（缺 base_url / 缺 model 报错）；key 空沿用旧值；load 预填 |
| `loop` | monkeypatch client，断言 `create_stream` 收到正确的 model + base_url |
| `app` | 无配置→引导 banner，不调 LLM |

---

## 7. 自审清单

- 无占位符 / TBD。
- 一致性：§3 行为、§4 数据模型、§5 代码改动相互对应（provider/base_url/model/key 四参贯穿）。
- 范围：单一实施计划可覆盖；无跨子系统拆分需求。
- 歧义消解：base_url 在 DeepSeek 可空、OpenAI 兼容必填（§3.1/§3.3/§5.1 一致）；
  key 空=沿用旧值（§3.2/§5.6 一致）；无兜底=BYOK 强制（§2/§3.2 一致）。

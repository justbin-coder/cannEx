# CannEx Webchat 架构设计（Phase 2 · 社区 Demo 形态）

> 设计契约文档。描述 What & Why，进度跟踪与执行步骤见 `docs/superpowers/plans/`。

---

## 0. 元信息

- **作者**：CannEx 项目（with Claude Opus 4.7）
- **日期**：2026-05-24
- **状态**：设计中
- **关联文档**：
  - `docs/CannEx-PRD.md`、`docs/CannEx-SDD.md`（原始设计）
  - `docs/specs/2026-05-23-cannex-v2-design.md`（v2-α 知识层设计）
  - `docs/superpowers/plans/2026-05-24-webchat-mvp-and-roadmap.md`（进度跟踪）
- **范围**：Phase 2 webchat 形态的**代码层架构**。部署形态（Dockerfile、nginx、域名、HTTPS）作为后续独立 plan，本 spec 不展开。

---

## 1. 背景与目标

### 1.1 项目两阶段定位

- **Phase 1 · Skill 形态**（已封板）：开发者在 Claude Code 内通过 `ascend-c` Skill 获得 CANN 教学引导。Claude 作为 agent，SKILL.md 作为系统指令，`cannex_doc.py` / `cannex_repo.py` 作为检索 CLI，Bash 作为工具协议。
- **Phase 2 · Webchat 形态**（本 spec）：把 Phase 1 的教学能力衍生到独立 Web 应用，**面向 Ascend C 社区开发者**，部署为公网社区 demo。

### 1.2 Phase 2 核心目标

| 目标 | 衡量 |
|---|---|
| 教学质量与 Phase 1 一致 | 同样的 SKILL.md，同样的检索路径，同样的 Claude 模型 |
| 业界标准 Agentic RAG 架构 | structured tool_use（非 raw bash 透传）+ 多轮 loop + system prompt 注入领域规则 |
| 公网部署就绪 | 无硬编码路径、worker 进程化、BYOK、限流、日志 |
| 社区 demo 合规 | 来源标注、版权免责、隐私声明 |

### 1.3 非目标

- **不**追求 Phase 1 的"字面 1:1 复刻"（如暴露 raw bash / 10 个 CLI subcommand 作为 10 个 tool）——这种做法不符合业界 agentic RAG web 应用范式，会损失 tool 调用准确度与 UX 可观测性。
- **不**实现多模型支持（DeepSeek / Qwen / GPT-4o 等）。本期仅 Claude。多模型留作后续 plan。
- **不**包含部署形态。Dockerfile / docker-compose / nginx / 域名 / HTTPS 作为独立后续 plan。
- **不**实现 Pitfall 库接入。Pitfall 库作为知识层扩展独立推进，本 spec 的 4 工具设计已预留扩展空间（query_documentation 的 scope 参数）。

---

## 2. 业界范式定位

Phase 2 形态对应业界 **Agentic RAG with custom tools** 范式：

```
LLM (Claude Sonnet 4.6) 作为 agent
  ├─ system_prompt：SKILL.md（教学规则 + 工具使用说明）
  ├─ tools：4 个 structured 工具（语义化检索动作）
  ├─ tool_use loop：最多 3 轮 think → call → observe
  └─ 知识层：workspace/（PageIndex 文档树 + CodeGraph 代码索引）
```

代表对标：Anthropic Customer Support Agent demo、Sourcegraph Cody、Cursor、LangGraph Agentic RAG。

---

## 3. 架构总览

```
┌──────────────── Browser ────────────────┐
│ Chainlit UI                              │
│ ├─ 首次访问：BYOK 配置弹窗（填 API key） │
│ ├─ 对话区：流式输出 + cl.Step 可视化     │
│ ├─ 来源 chip：[来源: ...] 可点击展开    │
│ └─ Banner：免责声明 + 来源声明           │
└────────────────────┬─────────────────────┘
                     │ WebSocket / SSE
┌────────────────────▼─────────────────────┐
│ Webchat Backend（Python + Chainlit）     │
│ ├─ Session：per-tab 历史 + BYOK key      │
│ ├─ Rate Limiter：IP 级 30 req/min        │
│ ├─ Agent Loop：tool_use 多轮编排（max 3）│
│ ├─ Anthropic API（litellm）+ 用户 key    │
│ ├─ Tool Dispatcher：4 个语义工具         │
│ │  → Worker RPC（JSON Lines stdin/stdout）│
│ └─ Logger（INFO 级，按日 logs/）         │
└────────────────────┬─────────────────────┘
                     │ JSON Lines IPC
┌────────────────────▼─────────────────────┐
│ Knowledge Worker（持久 Python 进程）     │
│ ├─ import cannex_doc / cannex_repo       │
│ ├─ workspace/ 只读（CANNEX_ROOT 配置）   │
│ ├─ 热文档树常驻内存缓存                  │
│ └─ JSON Lines RPC handler                │
└──────────────────────────────────────────┘
                     ▲
                     │ 启动时读取（无运行时写入）
┌────────────────────┴─────────────────────┐
│ workspace/（Phase 1 离线管道产物，静态） │
│ ├─ _meta.json                            │
│ ├─ docs/<doc_id>.json (PageIndex)        │
│ └─ repos/<name>/{repo_card, samples, .codegraph} │
└──────────────────────────────────────────┘
```

---

## 4. 组件设计

### 4.1 SKILL.md 升级（工具语义层）

**变更动机**：Phase 1/2 共享同一份 SKILL.md，但当前 SKILL.md 教的是 CLI subcommand（如 `cannex_doc.py search`），Phase 2 暴露给 Claude 的是 4 个语义化工具。需要把 SKILL.md「检索工作流」章节升级为**用语义动作描述**，附录保留 CLI 命令映射给 Phase 1 实际执行参考。

**新检索工作流章节结构**：

```markdown
## 检索工作流

你有 4 个语义化检索动作。根据用户意图选择：

### query_documentation(query, scope?)
- 用途：从 CANN 官方文档中按问题语义检索相关章节，返回原文片段 + 章节路径
- 何时用：用户问概念、原理、API 含义、安装步骤、调优思路
- 返回：结构化的章节列表，每条含 §章节路径、p页码、原文/摘要

### query_code_repo(query, repo?)
- 用途：从 ops-transformer 等代码仓中按问题检索相关代码上下文
- 何时用：用户问"找一个 X 算子的实现"、"FlashAttention 是怎么写的"
- 返回：相关文件路径 + 代码片段 + 上下文说明

### lookup_code_symbol(symbol, repo?)
- 用途：精确查找代码符号（函数/类/常量）的定义位置
- 何时用：用户问"DataCopy 在哪定义"、"这个 API 的签名"
- 返回：符号定义文件:行号 + 签名 + 简介

### list_known_resources()
- 用途：列出当前知识层有哪些文档和代码仓
- 何时用：用户问"你能查什么"、"有哪些资料"
- 返回：文档清单 + 代码仓清单

[附录：在 Claude Code（Phase 1）内的 CLI 命令映射]
- query_documentation → python3 skills/ascend-c/tools/cannex_doc.py search <doc> <query>
- query_code_repo → python3 skills/ascend-c/tools/cannex_repo.py context <repo> <query>
- lookup_code_symbol → python3 skills/ascend-c/tools/cannex_repo.py symbol <repo> <symbol>
- list_known_resources → python3 skills/ascend-c/tools/cannex_doc.py list && python3 skills/ascend-c/tools/cannex_repo.py list
```

**保留不变章节**：教学原则（苏格拉底引导、分层适配）、来源标注规则、回复格式约定。

---

### 4.2 Anthropic Tools（4 个语义化工具）

#### Tool 1: `query_documentation`

```json
{
  "name": "query_documentation",
  "description": "Search CANN official documentation by semantic query. Returns relevant section excerpts with chapter paths and page numbers. Use this for conceptual questions, API semantics, installation procedures, tuning guidance.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "The user's question or relevant keywords in Chinese or English"
      },
      "scope": {
        "type": "string",
        "enum": ["all", "install", "operator_dev", "performance_tuning", "precision_debug"],
        "default": "all",
        "description": "Document category to focus on. Default 'all' searches all indexed documents."
      }
    },
    "required": ["query"]
  }
}
```

内部实现：worker 进程调用 `cannex_doc.search(scope, query, top_k=3)` → 返回章节列表（含 §章节路径、p页码、原文片段或摘要）。

#### Tool 2: `query_code_repo`

```json
{
  "name": "query_code_repo",
  "description": "Search code repositories (e.g., ops-transformer) for implementation examples relevant to a query. Returns file paths, code snippets, and context. Use this when user wants to find example implementations.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "description": "Search query, e.g., 'FlashAttention implementation'" },
      "repo": { "type": "string", "default": "ops-transformer", "description": "Repo name from known resources" }
    },
    "required": ["query"]
  }
}
```

内部：调 `cannex_repo.context(repo, query)`。

#### Tool 3: `lookup_code_symbol`

```json
{
  "name": "lookup_code_symbol",
  "description": "Locate the definition of a specific code symbol (function/class/constant). Use when user asks where something is defined or for an exact API signature.",
  "input_schema": {
    "type": "object",
    "properties": {
      "symbol": { "type": "string", "description": "Symbol name, e.g., 'DataCopy'" },
      "repo": { "type": "string", "default": "ops-transformer" },
      "kind": { "type": "string", "enum": ["function", "class", "macro", "any"], "default": "any" }
    },
    "required": ["symbol"]
  }
}
```

内部：调 `cannex_repo.symbol(repo, symbol, kind)`。

#### Tool 4: `list_known_resources`

```json
{
  "name": "list_known_resources",
  "description": "List all available knowledge sources (documents and code repos). Use at the start when user asks what you can answer, or when you need to understand the scope of available knowledge.",
  "input_schema": { "type": "object", "properties": {} }
}
```

内部：调 `cannex_doc.list()` 拼 `cannex_repo.list()`。

---

### 4.3 Tool-use Loop（最多 3 轮）

```python
# pseudocode
def agent_loop(user_message, history, system_prompt, tools, user_api_key):
    messages = history + [{"role": "user", "content": user_message}]
    for iteration in range(3):
        response = claude_api.create(
            model="claude-sonnet-4-6",
            system=system_prompt,           # SKILL.md, with cache_control
            tools=tools,                    # 4 tools, with cache_control on definitions
            messages=messages,
            stream=True,
            api_key=user_api_key,
        )
        # stream response, accumulate tool_use blocks if any
        tool_uses, text_blocks = consume_stream(response)
        messages.append({"role": "assistant", "content": [...text + tool_uses]})
        if not tool_uses:
            return  # done, terminal text answer
        # execute tools (parallel)
        tool_results = await asyncio.gather(*[
            dispatch_tool(t.name, t.input) for t in tool_uses
        ])
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": t.id, "content": r}
            for t, r in zip(tool_uses, tool_results)
        ]})
    # 3 轮用完仍有 tool_use 请求 → 降级：再调用一次但去掉 tools，强制终答
    final = claude_api.create(model=..., messages=messages + [
        {"role": "user", "content": "请基于以上已检索到的内容直接回答用户问题，不要再调用工具。"}
    ], stream=True)
    yield from final
```

**降级语义**：3 轮用完后仍想继续检索 → 强制终答（不返回错误，给用户已有信息的答复）。

---

### 4.4 持久 Worker 进程 + JSON Lines IPC

**协议**：每行一个 JSON 消息，stdin 入 / stdout 出。

**Request**:
```json
{"id": "req_001", "method": "query_documentation", "params": {"query": "DataCopy", "scope": "all"}}
```

**Response（成功）**:
```json
{"id": "req_001", "ok": true, "result": {"sections": [{"title": "...", "page": "10-15", "text": "..."}]}}
```

**Response（失败）**:
```json
{"id": "req_001", "ok": false, "error": {"type": "WorkerError", "message": "未找到文档"}}
```

**Worker 生命周期**：
- 后端启动时 spawn 1 个 worker（社区 demo 小并发，1 个够用；预留 worker pool 扩展点）
- 健康检查：每 60s 发 `{"method": "ping"}`，超时则重启
- 崩溃自愈：subprocess 退出时自动重启，已 in-flight 的 request 重试 1 次

**Worker 内部**：
```python
# worker.py
import sys, json
from skills.ascend_c.tools import cannex_doc as doc_mod
from skills.ascend_c.tools import cannex_repo as repo_mod

HANDLERS = {
    "query_documentation": lambda p: doc_mod.search(**p),
    "query_code_repo":     lambda p: repo_mod.context(**p),
    "lookup_code_symbol":  lambda p: repo_mod.symbol(**p),
    "list_known_resources": lambda _: {"docs": doc_mod.list(), "repos": repo_mod.list()},
    "ping": lambda _: "pong",
}

for line in sys.stdin:
    req = json.loads(line)
    try:
        result = HANDLERS[req["method"]](req.get("params", {}))
        sys.stdout.write(json.dumps({"id": req["id"], "ok": True, "result": result}) + "\n")
    except Exception as e:
        sys.stdout.write(json.dumps({"id": req["id"], "ok": False,
                                      "error": {"type": type(e).__name__, "message": str(e)}}) + "\n")
    sys.stdout.flush()
```

**前置条件**：`cannex_doc.py` / `cannex_repo.py` 必须可作为 Python module import（提供函数式 API，不仅是 CLI 入口）。这是本次 spec 的一项配套改造。

---

### 4.5 workspace/ 访问约定

1. **访问路径**：webchat 后端**只**通过 worker → cannex_doc/repo 模块访问，**绝不**直接 `Path("workspace/").open()`
2. **路径配置**：`CANNEX_ROOT` 环境变量统一定位项目根。worker 启动时校验 `$CANNEX_ROOT/workspace/_meta.json` 存在，否则启动失败 + 日志
3. **更新协议**：workspace/ 改动后通过重启 worker 进程刷新。`build/monthly_update.sh` 跑完应提示用户重启 webchat
4. **只读契约**：worker 进程禁止对 workspace/ 写入（包括临时/缓存文件——内存 cache 可，落盘禁止）
5. **部署预留**：所有路径通过 `CANNEX_ROOT` 派生，禁止硬编码 `/Users/...`、`/home/...` 等绝对路径

---

### 4.6 BYOK 设计

**前端（localStorage）**:
```javascript
// 首次访问无 key 时弹窗
const apiKey = localStorage.getItem('cannex_api_key');
if (!apiKey) {
    showApiKeyDialog();  // 引导用户填入 Anthropic key
} else {
    initChat(apiKey);
}

// 每次请求 attach
fetch('/api/chat', {
    headers: { 'X-Anthropic-Key': apiKey },
    ...
});
```

**后端**:
```python
@cl.on_message
async def on_message(msg: cl.Message):
    api_key = cl.context.session.get("api_key")
    if not api_key:
        await cl.Message(content="请先在右上角配置你的 Anthropic API key").send()
        return
    # 调用 litellm 时传 api_key 参数
    ...
```

**安全契约**：
- ❌ 不写日志（key 字段在 logger 中做 redact）
- ❌ 不持久化（无数据库、无文件、无缓存）
- ❌ 不转发任何第三方（仅传给 Anthropic API）
- ✅ 仅存活在内存中本次请求生命周期

**UI 隐私声明**：固定 banner 显示「你的 API key 仅存于浏览器本地，关闭浏览器或清除缓存即删除。我们不持久化、不日志、不转发任何第三方」。

---

### 4.7 Chainlit UI 设计

**对话区**:
- 流式输出（已有）
- 每个 tool_use → 渲染为可折叠 `cl.Step`：
  - 标题示例：`🔍 查询文档：FlashAttention 实现`
  - 展开内容：input JSON（格式化）+ output 前 1000 字符（防溢出）
- 来源标注 `[来源: ...]` → 渲染为可点击 chip，点击展开原文片段（前 500 字 + "查看完整章节"按钮）

**Banner（固定顶部）**:
- 免责：「本项目内容基于 CANN 9.0.0 官方公开文档与开源代码仓，仅供学习参考，**不构成华为官方答复**」
- 版权：「文档来源：华为 CANN 社区版官方文档；代码来源：ops-transformer 等开源仓」
- 隐私：「你的 API key 仅存于浏览器，刷新页面后保留，关闭浏览器即删除」

**API key 配置入口**：右上角齿轮图标 → 弹窗配置 / 修改 / 清除 key。

---

### 4.8 限流与防滥用

- **IP 级 rate limit**：每 IP 每分钟 30 个对话消息（用 in-memory `collections.deque` 实现，重启清空，社区 demo 够用）
- **主题门控（可选，待 E2E 验证后决定）**：用户消息与 Ascend C/CANN 主题关联度极低时（如"今天天气怎么样"），由 Claude 在 system prompt 中被指示婉拒并引导
- **超时控制**：单个 tool call 60s 超时，整个 agent loop 90s 超时
- **错误降级链**：tool 失败 → 重试 1 次 → 还失败 → 返回 `{"error": "..."}` 给 Claude（不中断对话，Claude 可以告诉用户"检索遇到问题，基于已有信息回答"）

---

### 4.9 Prompt Caching

启用 Anthropic prompt caching：
- SKILL.md（system prompt） → `cache_control: {"type": "ephemeral"}`
- tools 定义（4 个 JSON schema）→ `cache_control: {"type": "ephemeral"}`
- 历史（除最后一条）→ 视情况 cache

**预期收益**：5 分钟 TTL 内重复对话，input token 减少 ~70%，延迟从 ~3s 降至 ~1s。

---

### 4.10 历史截断

**改进**：当前 `app.py` 按"最近 10 轮"截断（粗暴）。改为：
- 计算历史 token 数（用 tiktoken cl100k_base 近似）
- 若 history token > 8000 → 从最旧开始丢弃，直到 ≤ 8000
- system prompt + 当前 user message 不计入

---

### 4.11 可观测性

**日志**（Python logging，INFO 级，按日切分）:
```
logs/webchat-2026-05-24.log
```

每个请求记录:
```
2026-05-24 12:34:56 INFO  [session=abc123] query="DataCopy 是什么" intent_iter=0
2026-05-24 12:34:57 INFO  [session=abc123] tool_call: query_documentation({"query":"DataCopy"})
2026-05-24 12:34:58 INFO  [session=abc123] tool_result_len=2341 latency_ms=820
2026-05-24 12:35:01 INFO  [session=abc123] final_answer_tokens=412 total_input=1842 total_output=812
```

**敏感字段 redact**: API key、用户 IP（仅保留 hash）。

**健康检查端点**: `/health` 返回 worker 状态、最近 5min 错误率、平均延迟。

---

## 5. 错误处理与降级矩阵

| 故障 | 检测方式 | 降级行为 | 用户感知 |
|---|---|---|---|
| Anthropic API 失败 | litellm raise | 重试 1 次（指数退避 1s）→ 仍失败返回友好错误 | "服务暂时不可用，请稍后重试"（不 stack trace）|
| Worker 进程崩溃 | subprocess returncode != 0 / pipe closed | 自动重启 worker，正在 in-flight 的 request 重试 1 次 | 用户可能感知到 1-2s 卡顿，但对话继续 |
| Tool 调用失败 | worker 返回 ok=false | 把 error 作为 tool_result 返给 Claude | Claude 自然回答"检索失败，基于已有信息回答..." |
| Tool 调用超时 | 60s timeout | 同上 | 同上 |
| 用户 API key 无效 | litellm 401/403 | 提示用户更新 key | "你的 API key 无效或额度耗尽，请检查后重试" |
| Rate limit 触发 | in-memory 计数超限 | 直接拒绝 | "请求过频，请稍后重试（30 messages/min/IP）" |
| 3 轮 tool_use 用完 | 循环计数 | 移除 tools，强制 Claude 基于已有信息终答 | 答案略简，但完整 |

---

## 6. 不变契约（这些不能违反）

1. **SKILL.md 是教学原则与工具语义的唯一来源**：Phase 1 / Phase 2 都引用同一份。后端代码不允许写入第二份 system prompt
2. **workspace/ 只读**：webchat 后端、worker 进程，无任何文件写入操作（仅内存 cache）
3. **API key 仅活内存**：禁止落盘、禁止写日志、禁止入数据库
4. **CANNEX_ROOT 配置化**：所有路径派生于此环境变量，禁止硬编码
5. **Tool 接口稳定**：4 个工具的名称、input_schema 改动需 bump SKILL.md 版本号
6. **Phase 1 不受 Phase 2 影响**：Phase 2 改动仅限 `webchat/` 与 `skills/ascend-c/SKILL.md`（升级，不破坏 Phase 1 引用方式）+ 可能的 `cannex_doc.py` / `cannex_repo.py` 模块化（保持 CLI 入口向下兼容）

---

## 7. 数据流向（运行时一次完整对话）

```
1. 用户在浏览器输入"DataCopy 怎么用？"
2. 前端 attach localStorage 中的 API key → POST 到 backend
3. Backend 取 session 历史，组装 messages
4. Backend 调用 Claude API（litellm + 用户 key + system=SKILL.md + tools=[4个] + cache_control）
5. Claude 流式返回，含 tool_use 块：query_documentation({"query": "DataCopy"})
6. Backend 渲染 cl.Step("🔍 查询文档：DataCopy")
7. Backend 通过 JSON Lines 发到 worker stdin
8. Worker 调 cannex_doc.search → 返回章节列表
9. Backend 把结果作为 tool_result 加入 messages，再调 Claude
10. Claude（第 2 轮）流式返回文本答案，含 [来源: §xxx]
11. Backend 流式推到前端，渲染来源 chip
12. Backend 把本轮 messages 写入 session 历史（token 截断到 8K）
13. Logger 记录：query / tools / 轮次 / token / 耗时
```

---

## 8. 验收标准（What "Done" Means）

### 8.1 功能验收

- [ ] 6 类意图各 1 个用例（concept / howto / code_example / api_lookup / repo_navigate / debug），Claude 选择的工具 + 检索结果 + 答复正确率 ≥ 90%
- [ ] 来源标注覆盖率 ≥ 95%（每条事实断言都有 `[来源: ...]`）
- [ ] BYOK 配置流程通畅：无 key 引导填写、有 key 直接进对话、清除 key 退回引导
- [ ] 多轮对话历史正确截断（token 数 ≤ 8K）
- [ ] tool_use 在 cl.Step 中正确可视化
- [ ] 来源 chip 可点击展开

### 8.2 非功能验收

- [ ] 持久 worker：连续 50 次请求不冷启动新进程
- [ ] worker 崩溃自愈：手动 kill worker 后下一次请求触发自动重启
- [ ] Prompt caching 命中：观察 cache_read_input_tokens > 0
- [ ] IP rate limit：第 31 次/分钟请求被拒
- [ ] API key 不出现在 `logs/webchat-*.log` 任何一处
- [ ] workspace/ 在 webchat 运行期间无写入操作（用 `chmod -w workspace/` 验证）
- [ ] CANNEX_ROOT 改路径后正常工作（验证非硬编码）

### 8.3 文档验收

- [ ] SKILL.md「检索工作流」章节升级完成，4 个语义动作描述 + CLI 附录映射齐全
- [ ] 隐私声明、版权免责 Banner 在 UI 中可见
- [ ] README 包含 BYOK 使用指引

---

## 9. Out of Scope（明确不做的事）

- ❌ Docker 化、nginx 反代、HTTPS、域名（独立后续 plan）
- ❌ 多模型（DeepSeek/Qwen/GPT-4o）支持
- ❌ Pitfall 库接入（独立 Task）
- ❌ 用户注册/OAuth/邀请码鉴权（BYOK 即鉴权，社区 demo 阶段足够）
- ❌ 数据库持久化（无持久状态）
- ❌ 主题门控的硬编码黑名单（先靠 system prompt 软引导，E2E 验证后再决定是否加硬规则）
- ❌ i18n（暂中文）
- ❌ Workspace 数据增量更新协议（重启 worker 即可，不做热加载）

---

## 10. 后续 plan 索引（不在本 spec 范围）

1. **本 spec 的实施 plan**：`docs/superpowers/plans/2026-05-24-webchat-redesign.md`（待写）
2. **Webchat Docker 部署 plan**：未来独立写
3. **多模型支持 plan**：未来独立写
4. **Pitfall 库接入 plan**：未来独立写

---

## 自审（spec self-review）

1. **Placeholder 扫描**：无 TBD、TODO、待补章节
2. **内部一致性**：4 个工具名称、CANNEX_ROOT、SKILL.md 单一来源等关键概念在各章节使用一致
3. **范围检查**：聚焦代码层架构，部署/多模型/Pitfall 明确 out of scope，不会让单份 spec 装太多东西
4. **歧义检查**：
   - "3 轮 tool_use 上限"：明确定义为「迭代次数」而非「tool call 总数」
   - "workspace 只读"：明确定义为「禁止落盘」，内存 cache 允许
   - "BYOK 不持久化"：明确定义为「无日志、无数据库、无文件」
5. **不变契约**：§6 列出 6 条硬约束，覆盖最易被违反的设计纪律

无遗留问题。

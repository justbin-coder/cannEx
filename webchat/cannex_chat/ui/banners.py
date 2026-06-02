"""社区 demo 必备文案：免责、版权、隐私。"""

WELCOME_BANNER = """\
## 👋 CannEx · Ascend C 学习导师

基于 **CANN 9.0.0** 官方文档与开源算子仓，帮你**学懂 · 找到 · 避坑**。

`📦 官方文档 + 算子代码`　`🔐 配置加密存储`　`⚠️ 仅供学习参考`

---

👉 点击侧边栏 ⚙️ **Settings** 配置大模型后开始提问。
"""

NO_KEY_PROMPT = """\
🔑 **请先配置大模型**

打开左上角侧边栏 → **Settings** → 选择供应商（DeepSeek / OpenAI 兼容），填写 Base URL（如需）、模型名与 API Key。

⚠️ 模型必须支持工具调用（function calling），否则检索功能无法工作。
"""

RATE_LIMIT_MESSAGE = """\
⏱️ **请求过于频繁**

每会话每分钟最多 30 条消息，请稍后再试。
"""

KEY_INVALID_MESSAGE = """\
❌ **API key 无效或额度已耗尽**

请检查 key 是否正确、是否还有 credit，然后在 Settings 中重新填写。
"""

QUOTA_EXCEEDED_MESSAGE = """\
⏳ **供应商配额已用尽**

你配置的大模型供应商返回了**配额 / 限流**（quota / rate limit exceeded）——这是**供应商侧**的额度限制，不是 CannEx 的问题。

可以这样处理：
- 等配额窗口重置（通常按小时 / 天），稍后再试
- 打开左上角 ⚙️ **Settings** 换一个供应商，或换额度更充足的 API Key
- 确认该 Key 的套餐余量与限流档位
"""

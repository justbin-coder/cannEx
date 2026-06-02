"""BYOK v2：用 Chainlit ChatSettings 让用户配置供应商 / base_url / model / key。"""
import chainlit as cl
from chainlit.input_widget import Select, TextInput

from webchat.cannex_chat.agent import llm_config
from webchat.cannex_chat.agent.providers import PROVIDERS


def make_byok_settings(current: dict | None = None) -> cl.ChatSettings:
    current = current or {}
    # items={label: value}，回传的是 value(provider_id)
    items = {spec["label"]: pid for pid, spec in PROVIDERS.items()}
    initial_provider = current.get("provider") or next(iter(PROVIDERS))
    return cl.ChatSettings([
        Select(id="provider", label="🛰️ 供应商", items=items, initial_value=initial_provider),
        TextInput(id="base_url", label="🌐 Base URL（OpenAI 兼容档必填，DeepSeek 可留空）",
                  initial=current.get("base_url") or ""),
        TextInput(id="model", label="🤖 模型名",
                  placeholder="如 deepseek-chat（须支持工具调用，否则检索会失效）",
                  initial=current.get("model") or ""),
        TextInput(id="api_key", label="🔑 API Key",
                  placeholder="已保存则留空沿用，填写则更新", initial=""),
    ])


def validate_settings(settings: dict, existing: dict | None) -> tuple[dict | None, str | None]:
    """纯校验：成功返回 (config, None)，失败返回 (None, error_msg)。

    - provider 必须在 PROVIDERS 内；model 必填；
    - base_url_required 的供应商缺 base_url → 报错；
    - api_key 留空则沿用 existing 的 key，无既存 key → 报错。
    """
    provider = (settings.get("provider") or "").strip()
    if provider not in PROVIDERS:
        return None, "请选择供应商"
    base_url = (settings.get("base_url") or "").strip()
    model = (settings.get("model") or "").strip()
    api_key = (settings.get("api_key") or "").strip()
    if not model:
        return None, "请填写模型名"
    if PROVIDERS[provider]["base_url_required"] and not base_url:
        return None, "该供应商需要填写 Base URL"
    if not api_key:
        if existing and existing.get("api_key"):
            api_key = existing["api_key"]
        else:
            return None, "请填写 API Key"
    return {"provider": provider, "base_url": base_url,
            "model": model, "api_key": api_key}, None


async def save_llm_config(settings: dict, username: str | None) -> dict:
    """校验 + 持久化 + 写会话。返回 {ok, error?}。

    username 为 None（auth 关闭）时仅写会话，不落库。
    """
    existing = cl.user_session.get("llm_config")
    if existing is None and username:
        existing = llm_config.load_config(username)
    cfg, err = validate_settings(settings, existing)
    if err:
        return {"ok": False, "error": err}
    if username:
        llm_config.save_config(username, cfg["provider"], cfg["base_url"],
                               cfg["model"], cfg["api_key"])
    cl.user_session.set("llm_config", cfg)
    return {"ok": True}

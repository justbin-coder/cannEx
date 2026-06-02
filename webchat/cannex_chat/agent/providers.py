"""供应商注册表：把用户面概念(provider/model/base_url)翻译成 litellm 调用参数。

纯函数、零 IO。litellm 靠 model 前缀路由；通用 OpenAI 兼容端点用 openai/ 前缀 + api_base。
"""

PROVIDERS: dict[str, dict] = {
    "deepseek": {
        "label": "DeepSeek",
        "litellm_prefix": "deepseek",
        "default_base_url": "https://api.deepseek.com",
        "base_url_required": False,
    },
    "openai_compat": {
        "label": "OpenAI 兼容 (自定义端点)",
        "litellm_prefix": "openai",
        "default_base_url": "",
        "base_url_required": True,
    },
}


def resolve(provider: str, model: str, base_url: str | None = None) -> tuple[str, str]:
    """返回 (litellm_model, api_base)。

    - provider 未知 / model 为空 / base_url 必填但缺失 → ValueError。
    - base_url 留空时回落供应商 default_base_url。
    """
    spec = PROVIDERS.get(provider)
    if spec is None:
        raise ValueError(f"unknown provider: {provider!r}")
    if not model:
        raise ValueError("model is required")
    api_base = (base_url or "").strip() or spec["default_base_url"]
    if spec["base_url_required"] and not api_base:
        raise ValueError(f"provider {provider!r} requires base_url")
    return f"{spec['litellm_prefix']}/{model}", api_base

import pytest

from webchat.cannex_chat.agent.providers import PROVIDERS, resolve


def test_registry_has_deepseek_and_openai_compat():
    assert "deepseek" in PROVIDERS
    assert "openai_compat" in PROVIDERS


def test_resolve_deepseek_uses_default_base_url():
    model, api_base = resolve("deepseek", "deepseek-chat")
    assert model == "deepseek/deepseek-chat"
    assert api_base == "https://api.deepseek.com"


def test_resolve_deepseek_allows_base_url_override():
    model, api_base = resolve("deepseek", "deepseek-chat", "https://proxy.example")
    assert model == "deepseek/deepseek-chat"
    assert api_base == "https://proxy.example"


def test_resolve_openai_compat_requires_base_url():
    model, api_base = resolve("openai_compat", "qwen2", "http://localhost:8000/v1")
    assert model == "openai/qwen2"
    assert api_base == "http://localhost:8000/v1"


def test_resolve_openai_compat_without_base_url_raises():
    with pytest.raises(ValueError):
        resolve("openai_compat", "qwen2")


def test_resolve_unknown_provider_raises():
    with pytest.raises(ValueError):
        resolve("grok", "x")


def test_resolve_empty_model_raises():
    with pytest.raises(ValueError):
        resolve("deepseek", "")

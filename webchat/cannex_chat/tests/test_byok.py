from webchat.cannex_chat.ui.byok import validate_settings


def test_valid_deepseek_returns_config():
    cfg, err = validate_settings(
        {"provider": "deepseek", "base_url": "", "model": "deepseek-chat", "api_key": "k"},
        existing=None)
    assert err is None
    assert cfg == {"provider": "deepseek", "base_url": "",
                   "model": "deepseek-chat", "api_key": "k"}


def test_openai_compat_without_base_url_errors():
    cfg, err = validate_settings(
        {"provider": "openai_compat", "base_url": "", "model": "qwen", "api_key": "k"},
        existing=None)
    assert cfg is None
    assert "Base URL" in err


def test_missing_model_errors():
    cfg, err = validate_settings(
        {"provider": "deepseek", "base_url": "", "model": "", "api_key": "k"},
        existing=None)
    assert cfg is None
    assert err


def test_empty_key_reuses_existing():
    cfg, err = validate_settings(
        {"provider": "deepseek", "base_url": "", "model": "deepseek-chat", "api_key": ""},
        existing={"provider": "deepseek", "base_url": "", "model": "x", "api_key": "old-key"})
    assert err is None
    assert cfg["api_key"] == "old-key"


def test_empty_key_no_existing_errors():
    cfg, err = validate_settings(
        {"provider": "deepseek", "base_url": "", "model": "deepseek-chat", "api_key": ""},
        existing=None)
    assert cfg is None
    assert err


def test_unknown_provider_errors():
    cfg, err = validate_settings(
        {"provider": "grok", "base_url": "", "model": "m", "api_key": "k"}, existing=None)
    assert cfg is None
    assert err

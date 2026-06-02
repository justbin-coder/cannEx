import importlib

import pytest


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("CANNEX_CONFIG_SECRET", "unit-test-secret")
    mod = importlib.import_module("webchat.cannex_chat.agent.llm_config")
    monkeypatch.setattr(mod, "_DB_PATH", str(tmp_path / "cannex.db"))
    return mod


def test_save_then_load_round_trip(cfg):
    cfg.save_config("alice", "deepseek", "", "deepseek-chat", "sk-secret-123")
    out = cfg.load_config("alice")
    assert out == {"provider": "deepseek", "base_url": "",
                   "model": "deepseek-chat", "api_key": "sk-secret-123"}


def test_load_missing_user_returns_none(cfg):
    assert cfg.load_config("nobody") is None


def test_upsert_overwrites(cfg):
    cfg.save_config("bob", "deepseek", "", "deepseek-chat", "k1")
    cfg.save_config("bob", "openai_compat", "http://x/v1", "qwen", "k2")
    out = cfg.load_config("bob")
    assert out["provider"] == "openai_compat"
    assert out["model"] == "qwen"
    assert out["api_key"] == "k2"


def test_key_is_encrypted_at_rest(cfg):
    import sqlite3
    cfg.save_config("carol", "deepseek", "", "deepseek-chat", "sk-plaintext")
    with sqlite3.connect(cfg._DB_PATH) as conn:
        raw = conn.execute(
            "SELECT api_key_enc FROM cannex_llm_config WHERE username='carol'").fetchone()[0]
    assert "sk-plaintext" not in raw


def test_decrypt_failure_returns_none(cfg, monkeypatch):
    cfg.save_config("dave", "deepseek", "", "deepseek-chat", "k")
    # 轮换 secret → 旧密文无法解密
    monkeypatch.setenv("CANNEX_CONFIG_SECRET", "different-secret")
    assert cfg.load_config("dave") is None


def test_fernet_raises_when_no_secret_configured(monkeypatch):
    monkeypatch.delenv("CANNEX_CONFIG_SECRET", raising=False)
    monkeypatch.delenv("CHAINLIT_AUTH_SECRET", raising=False)
    import importlib
    mod = importlib.import_module("webchat.cannex_chat.agent.llm_config")
    with pytest.raises(RuntimeError):
        mod._fernet()

"""每用户 LLM 配置持久化（SQLite）+ api_key Fernet 加密。

表 cannex_llm_config 与认证表 cannex_users 同库不同表。
加密密钥从 env CANNEX_CONFIG_SECRET 派生（缺失回落 CHAINLIT_AUTH_SECRET）。
⚠️ 轮换该 secret 会使已存 key 无法解密 → load_config 返回 None（按未配置处理）。
"""
from __future__ import annotations

import base64
import hashlib
import os
import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_DB_PATH = os.environ.get("CANNEX_USERS_DB", "/data/cannex.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cannex_llm_config (
    username     TEXT PRIMARY KEY,
    provider     TEXT NOT NULL,
    base_url     TEXT,
    model        TEXT NOT NULL,
    api_key_enc  TEXT NOT NULL,
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _fernet() -> Fernet:
    secret = (os.environ.get("CANNEX_CONFIG_SECRET")
              or os.environ.get("CHAINLIT_AUTH_SECRET") or "")
    if not secret:
        raise RuntimeError("CANNEX_CONFIG_SECRET / CHAINLIT_AUTH_SECRET 未设置，无法加解密")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def _open() -> sqlite3.Connection:
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def save_config(username: str, provider: str, base_url: str,
                model: str, api_key: str) -> None:
    enc = _fernet().encrypt(api_key.encode()).decode()
    conn = _open()
    try:
        conn.execute(
            "INSERT INTO cannex_llm_config(username, provider, base_url, model, api_key_enc) "
            "VALUES(?, ?, ?, ?, ?) "
            "ON CONFLICT(username) DO UPDATE SET "
            "provider=excluded.provider, base_url=excluded.base_url, "
            "model=excluded.model, api_key_enc=excluded.api_key_enc, "
            "updated_at=datetime('now')",
            (username, provider, base_url, model, enc),
        )
        conn.commit()
    finally:
        conn.close()


def load_config(username: str) -> dict | None:
    conn = _open()
    try:
        row = conn.execute(
            "SELECT provider, base_url, model, api_key_enc "
            "FROM cannex_llm_config WHERE username = ?",
            (username,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    provider, base_url, model, enc = row
    try:
        api_key = _fernet().decrypt(enc.encode()).decode()
    except InvalidToken:
        return None
    return {"provider": provider, "base_url": base_url or "",
            "model": model, "api_key": api_key}

"""
CannEx webchat — SQLite-backed password authentication.

Importing this module registers Chainlit's `@cl.password_auth_callback`.
Make sure app.py imports it (side-effect import).

Schema: see deploy/seed_users.py (cannex_users table).

Env:
  CANNEX_USERS_DB — path to SQLite file (default: /data/cannex.db)
"""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

import bcrypt
import chainlit as cl

log = logging.getLogger("cannex.auth")

_DB_PATH = os.environ.get("CANNEX_USERS_DB", "/data/cannex.db")


def _fetch_hash(username: str) -> str | None:
    if not Path(_DB_PATH).exists():
        log.warning("users DB not found at %s — all logins will fail", _DB_PATH)
        return None
    conn = sqlite3.connect(_DB_PATH)
    try:
        row = conn.execute(
            "SELECT password_hash FROM cannex_users WHERE username = ?",
            (username,),
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def hash_password(plain: str) -> str:
    """Bcrypt-hash a plaintext password (cost factor 12). Used by seed script."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()


@cl.password_auth_callback
def auth_callback(username: str, password: str) -> cl.User | None:
    h = _fetch_hash(username)
    if not h:
        log.info("login denied: unknown user=%r", username)
        return None
    try:
        ok = bcrypt.checkpw(password.encode(), h.encode())
    except ValueError:
        log.exception("malformed password hash for user=%r", username)
        return None
    if not ok:
        log.info("login denied: bad password user=%r", username)
        return None
    log.info("login ok user=%r", username)
    return cl.User(identifier=username, metadata={"role": "user"})

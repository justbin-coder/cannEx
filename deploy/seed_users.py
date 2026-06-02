"""
Seed initial users into the CannEx SQLite DB.

Run inside the web container:

  # one user at a time
  docker compose exec web python /app/deploy/seed_users.py alice secret123

  # batch via stdin (one "username password" per line)
  cat users.txt | docker compose exec -T web python /app/deploy/seed_users.py --stdin

  # list users
  docker compose exec web python /app/deploy/seed_users.py --list

  # delete a user
  docker compose exec web python /app/deploy/seed_users.py --delete alice
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

# Make webchat.cannex_chat.auth importable
sys.path.insert(0, "/app")
from webchat.cannex_chat.auth import hash_password

_DB_PATH = os.environ.get("CANNEX_USERS_DB", "/data/cannex.db")
_SCHEMA = """
CREATE TABLE IF NOT EXISTS cannex_users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _open() -> sqlite3.Connection:
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def _upsert(conn: sqlite3.Connection, username: str, password: str) -> None:
    conn.execute(
        "INSERT INTO cannex_users(username, password_hash) VALUES(?, ?) "
        "ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash",
        (username, hash_password(password)),
    )
    conn.commit()
    print(f"OK seeded user: {username}")


def _list(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT username, created_at FROM cannex_users ORDER BY created_at"
    ).fetchall()
    if not rows:
        print("(no users)")
        return
    print(f"{'username':<24} created_at")
    for u, ts in rows:
        print(f"{u:<24} {ts}")


def _delete(conn: sqlite3.Connection, username: str) -> None:
    n = conn.execute(
        "DELETE FROM cannex_users WHERE username = ?", (username,)
    ).rowcount
    conn.commit()
    print(f"OK deleted {n} row(s) for: {username}")


def main() -> int:
    conn = _open()
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    if args[0] == "--list":
        _list(conn)
    elif args[0] == "--delete" and len(args) == 2:
        _delete(conn, args[1])
    elif args[0] == "--stdin":
        for line in sys.stdin:
            parts = line.strip().split()
            if len(parts) == 2:
                _upsert(conn, parts[0], parts[1])
    elif len(args) == 2:
        _upsert(conn, args[0], args[1])
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

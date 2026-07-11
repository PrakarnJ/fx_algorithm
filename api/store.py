"""SQLite store for saved Pine scripts — stdlib sqlite3, thread-locked.

Reads config.DB_PATH at call time (not import time) so tests can point it
at a temporary database.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional

import config

_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scripts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    source     TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        con = sqlite3.connect(config.DB_PATH)
        con.row_factory = sqlite3.Row
        try:
            con.executescript(_SCHEMA)
            yield con
            con.commit()
        finally:
            con.close()


def list_scripts() -> list[dict]:
    """All scripts (metadata only, no source), most recently updated first."""
    with _connect() as con:
        rows = con.execute(
            "SELECT id, name, created_at, updated_at FROM scripts ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_script(script_id: int) -> dict:
    with _connect() as con:
        row = con.execute("SELECT * FROM scripts WHERE id = ?", (script_id,)).fetchone()
    if row is None:
        raise KeyError(f"script {script_id} not found")
    return dict(row)


def create_script(name: str, source: str) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("script name must not be empty")
    now = _now()
    try:
        with _connect() as con:
            cur = con.execute(
                "INSERT INTO scripts (name, source, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (name, source, now, now),
            )
            script_id = cur.lastrowid
    except sqlite3.IntegrityError:
        raise ValueError(f"script name '{name}' already exists")
    return get_script(script_id)


def update_script(script_id: int, name: Optional[str] = None,
                  source: Optional[str] = None) -> dict:
    fields, params = [], []
    if name is not None:
        name = name.strip()
        if not name:
            raise ValueError("script name must not be empty")
        fields.append("name = ?")
        params.append(name)
    if source is not None:
        fields.append("source = ?")
        params.append(source)
    if not fields:
        return get_script(script_id)
    fields.append("updated_at = ?")
    params.append(_now())
    params.append(script_id)
    try:
        with _connect() as con:
            cur = con.execute(f"UPDATE scripts SET {', '.join(fields)} WHERE id = ?", params)
            if cur.rowcount == 0:
                raise KeyError(f"script {script_id} not found")
    except sqlite3.IntegrityError:
        raise ValueError(f"script name '{name}' already exists")
    return get_script(script_id)


def delete_script(script_id: int) -> None:
    with _connect() as con:
        cur = con.execute("DELETE FROM scripts WHERE id = ?", (script_id,))
        if cur.rowcount == 0:
            raise KeyError(f"script {script_id} not found")

"""SQLite-backed persistent storage for proxies, templates, and lot drafts."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS proxies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    label TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger TEXT NOT NULL,
    response TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lot_drafts (
    user_id INTEGER PRIMARY KEY,
    payload TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


@dataclass(slots=True)
class Proxy:
    id: int
    url: str
    label: str | None
    is_active: bool


class Database:
    """Thin async wrapper over an aiosqlite connection."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def _conn(self) -> AsyncIterator[aiosqlite.Connection]:
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            yield conn

    async def init(self) -> None:
        async with self._conn() as conn:
            await conn.executescript(SCHEMA)
            await conn.commit()

    # ----- proxies -----
    async def add_proxy(self, url: str, label: str | None = None) -> int:
        async with self._conn() as conn:
            cursor = await conn.execute(
                "INSERT OR IGNORE INTO proxies(url, label, is_active, created_at) "
                "VALUES (?, ?, 1, ?)",
                (url, label, _now()),
            )
            await conn.commit()
            if cursor.lastrowid:
                return cursor.lastrowid
            row = await (await conn.execute("SELECT id FROM proxies WHERE url = ?", (url,))).fetchone()
            return int(row["id"]) if row else 0

    async def list_proxies(self, only_active: bool = False) -> list[Proxy]:
        sql = "SELECT id, url, label, is_active FROM proxies"
        if only_active:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY id ASC"
        async with self._conn() as conn:
            rows = await (await conn.execute(sql)).fetchall()
            return [
                Proxy(id=int(r["id"]), url=r["url"], label=r["label"], is_active=bool(r["is_active"]))
                for r in rows
            ]

    async def delete_proxy(self, proxy_id: int) -> None:
        async with self._conn() as conn:
            await conn.execute("DELETE FROM proxies WHERE id = ?", (proxy_id,))
            await conn.commit()

    async def toggle_proxy(self, proxy_id: int, active: bool) -> None:
        async with self._conn() as conn:
            await conn.execute(
                "UPDATE proxies SET is_active = ? WHERE id = ?",
                (1 if active else 0, proxy_id),
            )
            await conn.commit()

    # ----- settings -----
    async def get_setting(self, key: str) -> str | None:
        async with self._conn() as conn:
            row = await (await conn.execute("SELECT value FROM settings WHERE key = ?", (key,))).fetchone()
            return row["value"] if row else None

    async def set_setting(self, key: str, value: str) -> None:
        async with self._conn() as conn:
            await conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            await conn.commit()

    # ----- lot drafts -----
    async def save_draft(self, user_id: int, payload: dict) -> None:
        async with self._conn() as conn:
            await conn.execute(
                "INSERT INTO lot_drafts(user_id, payload, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET payload=excluded.payload, "
                "updated_at=excluded.updated_at",
                (user_id, json.dumps(payload, ensure_ascii=False), _now()),
            )
            await conn.commit()

    async def load_draft(self, user_id: int) -> dict | None:
        async with self._conn() as conn:
            row = await (
                await conn.execute("SELECT payload FROM lot_drafts WHERE user_id = ?", (user_id,))
            ).fetchone()
            return json.loads(row["payload"]) if row else None

    async def delete_draft(self, user_id: int) -> None:
        async with self._conn() as conn:
            await conn.execute("DELETE FROM lot_drafts WHERE user_id = ?", (user_id,))
            await conn.commit()


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()

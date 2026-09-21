from __future__ import annotations

import secrets
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS payments (
                inv_id INTEGER PRIMARY KEY,
                amount TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'paid',
                access_token TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                used_at TEXT,
                telegram_user_id INTEGER,
                invite_link TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_payments_token ON payments(access_token);
            """
        )
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if not self._conn:
            raise RuntimeError("Database is not connected")
        return self._conn

    async def _fetchone(self, sql: str, params: tuple) -> aiosqlite.Row | None:
        cursor = await self.conn.execute(sql, params)
        row = await cursor.fetchone()
        await cursor.close()
        return row

    async def upsert_paid(self, inv_id: int, amount: str) -> str:
        """Помечает оплату и возвращает access_token (существующий или новый)."""
        existing = await self._fetchone(
            "SELECT access_token FROM payments WHERE inv_id = ?",
            (inv_id,),
        )
        if existing:
            return existing["access_token"]

        token = secrets.token_urlsafe(24)
        await self.conn.execute(
            """
            INSERT INTO payments (inv_id, amount, status, access_token, created_at)
            VALUES (?, ?, 'paid', ?, ?)
            """,
            (inv_id, amount, token, utcnow()),
        )
        await self.conn.commit()
        return token

    async def get_by_token(self, token: str) -> aiosqlite.Row | None:
        return await self._fetchone(
            "SELECT * FROM payments WHERE access_token = ?",
            (token,),
        )

    async def get_by_inv_id(self, inv_id: int) -> aiosqlite.Row | None:
        return await self._fetchone(
            "SELECT * FROM payments WHERE inv_id = ?",
            (inv_id,),
        )

    async def mark_used(
        self,
        token: str,
        telegram_user_id: int,
        invite_link: str,
    ) -> bool:
        """Помечает токен использованным. Возвращает False, если уже был использован."""
        cursor = await self.conn.execute(
            """
            UPDATE payments
            SET used_at = ?, telegram_user_id = ?, invite_link = ?
            WHERE access_token = ? AND used_at IS NULL
            """,
            (utcnow(), telegram_user_id, invite_link, token),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

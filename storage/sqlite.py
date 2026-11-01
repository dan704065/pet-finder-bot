from collections.abc import Mapping
from dataclasses import asdict
import json
import time
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey, StateType

from database.connection import Database


class SQLiteStorage(BaseStorage):
    """Durable dialog state for a single bot process with SimpleEventIsolation."""

    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def _key(key: StorageKey) -> str:
        return json.dumps(asdict(key), sort_keys=True, separators=(",", ":"))

    async def _set(self, key: StorageKey, column: str, value) -> None:
        async with self.database.connection(write=True) as connection:
            await connection.execute(
                f"""INSERT INTO dialog_sessions(session_key, user_id, {column}, updated_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(session_key) DO UPDATE SET {column} = excluded.{column}, updated_at = excluded.updated_at""",
                (self._key(key), key.user_id, value, int(time.time())),
            )
            await connection.execute("DELETE FROM dialog_sessions WHERE session_key = ? AND state IS NULL AND data = '{}'", (self._key(key),))

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        await self._set(key, "state", state.state if isinstance(state, State) else state)

    async def get_state(self, key: StorageKey) -> str | None:
        async with self.database.connection() as connection:
            async with connection.execute("SELECT state FROM dialog_sessions WHERE session_key = ?", (self._key(key),)) as cursor:
                row = await cursor.fetchone()
                return row["state"] if row is not None else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        await self._set(key, "data", json.dumps(dict(data), ensure_ascii=False))

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        async with self.database.connection() as connection:
            async with connection.execute("SELECT data FROM dialog_sessions WHERE session_key = ?", (self._key(key),)) as cursor:
                row = await cursor.fetchone()
                return json.loads(row["data"]) if row is not None else {}

    async def update_data(self, key: StorageKey, data: Mapping[str, Any]) -> dict[str, Any]:
        async with self.database.connection(write=True) as connection:
            async with connection.execute("SELECT data FROM dialog_sessions WHERE session_key = ?", (self._key(key),)) as cursor:
                row = await cursor.fetchone()
                current = json.loads(row["data"]) if row is not None else {}
            current.update(data)
            await connection.execute("""INSERT INTO dialog_sessions(session_key, user_id, data, updated_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(session_key) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at""",
                (self._key(key), key.user_id, json.dumps(current, ensure_ascii=False), int(time.time())))
            return current

    async def close(self) -> None:
        # Connections are scoped to individual operations.
        pass

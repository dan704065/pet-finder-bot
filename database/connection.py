from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    @asynccontextmanager
    async def connection(self, *, write=False):
        async with aiosqlite.connect(self.path, timeout=10) as connection:
            connection.row_factory = aiosqlite.Row
            await connection.execute("PRAGMA foreign_keys = ON")
            await connection.execute("PRAGMA busy_timeout = 10000")
            if write:
                await connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                if write:
                    await connection.commit()
            except BaseException:
                if write:
                    await connection.rollback()
                raise

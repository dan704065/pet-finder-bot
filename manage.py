"""Local outbox diagnostics; no bot token or Telegram connection required."""

import argparse
import asyncio
import os
from pathlib import Path
import sqlite3
import time

import aiosqlite

from database.connection import Database
from repositories.outbox import OutboxRepository

MAX_SQLITE_ID = 2**63 - 1


async def run(database: Database, command: str, notification_id: int | None = None) -> None:
    if not database.path.is_file() or database.path.stat().st_size == 0:
        raise SystemExit("База не найдена или пуста. Укажите --database или сначала запустите бота.")
    try:
        if command == "notifications":
            async with database.connection() as connection:
                failures = await OutboxRepository(connection).failures()
            if not failures:
                print("Неудачных уведомлений нет.")
            for item in failures:
                print(f"#{item['id']} | recipient={item['recipient_id']} | attempts={item['attempts']} | {item['last_error']}")
        else:
            if notification_id is None or not (0 < notification_id <= MAX_SQLITE_ID):
                raise SystemExit("Некорректный ID уведомления.")
            async with database.connection(write=True) as connection:
                retried = await OutboxRepository(connection).retry_failed(notification_id, int(time.time()))
            if not retried:
                raise SystemExit("Уведомление с таким ID не найдено среди failed.")
            print(f"Уведомление #{notification_id} снова поставлено в очередь.")
    except (aiosqlite.Error, sqlite3.Error) as exc:
        raise SystemExit(f"База данных не инициализирована или повреждена ({exc}). Сначала запустите бота.") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path(os.environ.get("DATABASE_PATH", Path(__file__).parent / "database.db")))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("notifications", help="List failed notifications")
    retry = commands.add_parser("retry-notification", help="Retry one failed notification")
    retry.add_argument("notification_id", type=int)
    arguments = parser.parse_args()
    asyncio.run(run(Database(arguments.database), arguments.command, getattr(arguments, "notification_id", None)))


if __name__ == "__main__":
    main()

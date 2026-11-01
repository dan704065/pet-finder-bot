"""Local outbox diagnostics; no bot token or Telegram connection required."""

import argparse
import asyncio
import os
from pathlib import Path
import time

from database.connection import Database
from repositories.outbox import OutboxRepository


async def run(database: Database, command: str, notification_id: int | None = None) -> None:
    if not database.path.is_file():
        raise SystemExit("База не найдена. Укажите --database или сначала запустите бота.")
    if command == "notifications":
        async with database.connection() as connection:
            failures = await OutboxRepository(connection).failures()
        if not failures:
            print("Неудачных уведомлений нет.")
        for item in failures:
            print(f"#{item['id']} | recipient={item['recipient_id']} | attempts={item['attempts']} | {item['last_error']}")
    else:
        async with database.connection(write=True) as connection:
            retried = await OutboxRepository(connection).retry_failed(notification_id, int(time.time()))
        if not retried:
            raise SystemExit("Уведомление с таким ID не найдено среди failed.")
        print(f"Уведомление #{notification_id} снова поставлено в очередь.")


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

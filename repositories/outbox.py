import json
import time

from domain.models import Notification, NotificationKind


class OutboxRepository:
    def __init__(self, connection):
        self.connection = connection

    async def enqueue(self, recipient_id: int, kind: NotificationKind, payload: dict, *, event_key: str, application_id=None, subject_user_id=None, now=None) -> None:
        now = int(time.time()) if now is None else now
        await self.connection.execute("""INSERT INTO notification_outbox
            (event_key, recipient_id, kind, payload, application_id, subject_user_id, available_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(event_key) DO NOTHING""",
            (event_key, recipient_id, kind.value, json.dumps(payload, ensure_ascii=False), application_id, subject_user_id, now, now))

    async def claim(self, now: int, lease_seconds=60) -> Notification | None:
        async with self.connection.execute("SELECT next_run_at FROM scheduled_jobs WHERE name = 'telegram_delivery'") as cursor:
            pause = await cursor.fetchone()
        if pause is not None and pause["next_run_at"] > now:
            return None
        async with self.connection.execute("""SELECT * FROM notification_outbox
            WHERE (status = 'pending' AND available_at <= ?)
               OR (status = 'processing' AND locked_until <= ?)
            ORDER BY available_at, id LIMIT 1""", (now, now)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        await self.connection.execute("UPDATE notification_outbox SET status = 'processing', attempts = attempts + 1, locked_until = ? WHERE id = ?", (now + lease_seconds, row["id"]))
        return Notification(row["id"], row["recipient_id"], NotificationKind(row["kind"]), json.loads(row["payload"]), row["attempts"] + 1)

    async def is_processing(self, notification_id: int) -> bool:
        async with self.connection.execute("SELECT 1 FROM notification_outbox WHERE id = ? AND status = 'processing'", (notification_id,)) as cursor:
            return await cursor.fetchone() is not None

    async def delivered(self, notification_id: int, now: int) -> None:
        await self.connection.execute("UPDATE notification_outbox SET status = 'sent', delivered_at = ?, locked_until = NULL, last_error = NULL WHERE id = ? AND status = 'processing'", (now, notification_id))

    async def failed(self, notification_id: int, error: str, available_at: int, *, permanent=False) -> None:
        await self.connection.execute("""UPDATE notification_outbox SET status = ?, available_at = ?,
            locked_until = NULL, last_error = ? WHERE id = ? AND status = 'processing'""",
            ("failed" if permanent else "pending", available_at, error[:500], notification_id))

    async def pause_delivery(self, until: int) -> None:
        await self.connection.execute("""INSERT INTO scheduled_jobs(name, next_run_at) VALUES ('telegram_delivery', ?)
            ON CONFLICT(name) DO UPDATE SET next_run_at = MAX(next_run_at, excluded.next_run_at)""", (until,))

    async def failures(self, limit=20) -> list[dict]:
        async with self.connection.execute("SELECT id, recipient_id, attempts, last_error FROM notification_outbox WHERE status = 'failed' ORDER BY id DESC LIMIT ?", (limit,)) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def retry_failed(self, notification_id: int, now: int) -> bool:
        cursor = await self.connection.execute("""UPDATE notification_outbox SET status = 'pending', attempts = 0,
            available_at = ?, locked_until = NULL, last_error = NULL WHERE id = ? AND status = 'failed'""", (now, notification_id))
        return cursor.rowcount == 1

    async def counts(self) -> tuple[int, int]:
        async with self.connection.execute("""SELECT
            COALESCE(SUM(status IN ('pending', 'processing')), 0) AS pending,
            COALESCE(SUM(status = 'failed'), 0) AS failed FROM notification_outbox""") as cursor:
            row = await cursor.fetchone()
            return row["pending"], row["failed"]

    async def cancel_application(self, application_id: int) -> None:
        await self.connection.execute("""UPDATE notification_outbox SET status = 'cancelled', locked_until = NULL
            WHERE application_id = ? AND status IN ('pending', 'processing') AND kind IN ('submitted', 'published', 'reminder')""", (application_id,))

    async def delete_application(self, application_id: int) -> None:
        await self.connection.execute("DELETE FROM notification_outbox WHERE application_id = ?", (application_id,))

    async def delete_user_data(self, user_id: int) -> None:
        await self.connection.execute("""DELETE FROM notification_outbox WHERE recipient_id = ? OR subject_user_id = ?
            OR application_id IN (SELECT id FROM applications WHERE user_id = ?)""", (user_id, user_id, user_id))

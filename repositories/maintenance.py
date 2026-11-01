class MaintenanceRepository:
    def __init__(self, connection):
        self.connection = connection

    async def due(self, name: str, now: int) -> bool:
        await self.connection.execute("INSERT INTO scheduled_jobs(name, next_run_at) VALUES (?, ?) ON CONFLICT(name) DO NOTHING", (name, now))
        async with self.connection.execute("SELECT next_run_at FROM scheduled_jobs WHERE name = ?", (name,)) as cursor:
            return (await cursor.fetchone())["next_run_at"] <= now

    async def completed(self, name: str, now: int, interval: int) -> None:
        await self.connection.execute("UPDATE scheduled_jobs SET last_run_at = ?, next_run_at = ? WHERE name = ?", (now, now + interval, name))

    async def mark_reminder(self, application_id: int, now: int) -> None:
        await self.connection.execute("INSERT INTO application_reminders(application_id, queued_at) VALUES (?, ?) ON CONFLICT(application_id) DO NOTHING", (application_id, now))

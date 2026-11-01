from domain.models import AuditEntry


class AuditRepository:
    def __init__(self, connection):
        self.connection = connection

    async def add(self, user_id: int, action: str, details="", *, subject_user_id=None, application_id=None) -> None:
        await self.connection.execute("INSERT INTO logs(user_id, action, details, subject_user_id, application_id) VALUES (?, ?, ?, ?, ?)", (user_id, action, details, subject_user_id, application_id))

    async def latest(self, limit=20) -> list[AuditEntry]:
        async with self.connection.execute("SELECT * FROM logs ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)) as cursor:
            return [AuditEntry(id=row["id"], user_id=row["user_id"], action=row["action"], details=row["details"] or "", created_at=str(row["created_at"] or "")) for row in await cursor.fetchall()]

    async def delete_user_data(self, user_id: int) -> None:
        await self.connection.execute("""DELETE FROM logs WHERE user_id = ? OR subject_user_id = ?
            OR application_id IN (SELECT id FROM applications WHERE user_id = ?)
            OR details = ? OR details LIKE ?""", (user_id, user_id, user_id, f"ID: {user_id}", f"ID: {user_id},%"))
        async with self.connection.execute("SELECT id FROM applications WHERE user_id = ?", (user_id,)) as cursor:
            app_ids = [row["id"] for row in await cursor.fetchall()]
        for app_id in app_ids:
            await self.connection.execute("DELETE FROM logs WHERE details = ? OR details LIKE ? OR details = ?", (f"#{app_id}", f"#{app_id},%", f"Анкета #{app_id}"))

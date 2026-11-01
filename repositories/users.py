from domain.models import NotificationMode, User


def user_from_row(row) -> User | None:
    if row is None:
        return None
    return User(
        id=row["user_id"], username=row["username"] or "", first_name=row["first_name"] or "",
        role=row["role"] or "user", is_banned=bool(row["is_banned"]), ban_reason=row["ban_reason"] or "",
        notification_mode=NotificationMode(row["notification_mode"] or "none"),
        district=row["district"], created_at=str(row["created_at"] or ""),
    )


class UserRepository:
    def __init__(self, connection):
        self.connection = connection

    async def get(self, user_id: int) -> User | None:
        async with self.connection.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return user_from_row(await cursor.fetchone())

    async def register(self, user_id: int, username: str, first_name: str) -> bool:
        cursor = await self.connection.execute(
            "INSERT INTO users(user_id, username, first_name) VALUES (?, ?, ?) ON CONFLICT(user_id) DO NOTHING",
            (user_id, username, first_name),
        )
        return cursor.rowcount == 1

    async def set_district(self, user_id: int, district: str) -> None:
        await self.connection.execute("UPDATE users SET district = ? WHERE user_id = ?", (district, user_id))

    async def set_notifications(self, user_id: int, mode: NotificationMode) -> None:
        await self.connection.execute("UPDATE users SET notification_mode = ? WHERE user_id = ?", (mode.value, user_id))

    async def set_ban(self, user_id: int, banned: bool, reason: str = "") -> None:
        await self.connection.execute("UPDATE users SET is_banned = ?, ban_reason = ? WHERE user_id = ?", (int(banned), reason, user_id))

    async def subscribers(self, district: str) -> list[int]:
        async with self.connection.execute("""SELECT user_id FROM users WHERE is_banned = 0 AND
            (notification_mode = 'city' OR (notification_mode = 'district' AND district = ?))""", (district,)) as cursor:
            return [row["user_id"] for row in await cursor.fetchall()]

    async def list(self, limit=20) -> list[User]:
        async with self.connection.execute("SELECT * FROM users ORDER BY created_at DESC, user_id DESC LIMIT ?", (limit,)) as cursor:
            return [user_from_row(row) for row in await cursor.fetchall()]

    async def counts(self) -> tuple[int, int]:
        async with self.connection.execute("SELECT COUNT(*) AS total, COALESCE(SUM(is_banned), 0) AS banned FROM users") as cursor:
            row = await cursor.fetchone()
            return row["total"], row["banned"]

    async def delete_data(self, user_id: int) -> None:
        async with self.connection.execute("SELECT DISTINCT application_id FROM responses WHERE user_id = ?", (user_id,)) as cursor:
            responded = [row["application_id"] for row in await cursor.fetchall()]
        await self.connection.execute("DELETE FROM responses WHERE user_id = ? OR application_id IN (SELECT id FROM applications WHERE user_id = ?)", (user_id, user_id))
        for application_id in responded:
            await self.connection.execute("UPDATE applications SET responses = (SELECT COUNT(*) FROM responses WHERE application_id = ?) WHERE id = ?", (application_id, application_id))
        await self.connection.execute("DELETE FROM complaints WHERE reporter_id = ? OR application_id IN (SELECT id FROM applications WHERE user_id = ?)", (user_id, user_id))
        await self.connection.execute("DELETE FROM dialog_sessions WHERE user_id = ?", (user_id,))
        await self.connection.execute("DELETE FROM applications WHERE user_id = ?", (user_id,))
        await self.connection.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

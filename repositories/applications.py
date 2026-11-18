import json

from domain.models import Application, ApplicationDraft, ApplicationKind, ApplicationStatus


def application_from_row(row) -> Application | None:
    if row is None:
        return None
    return Application(
        id=row["id"], user_id=row["user_id"], kind=ApplicationKind(row["type"]),
        pet_name=row["pet_name"] or "", description=row["description"] or "", district=row["district"] or "",
        additional_info=row["additional_info"] or "", photo_id=row["photo_id"] or "",
        status=ApplicationStatus(row["status"]), reject_reason=row["reject_reason"] or "",
        views=row["views"] or 0, responses=row["responses"] or 0, deleted_at=row["deleted_at"],
        created_at=str(row["created_at"] or ""), submission_key=row["submission_key"],
        photo_ids=tuple(json.loads(row["photo_ids"])) or ((row["photo_id"],) if row["photo_id"] else ()),
    )


class ApplicationRepository:
    def __init__(self, connection):
        self.connection = connection

    async def get(self, application_id: int) -> Application | None:
        async with self.connection.execute("SELECT * FROM applications WHERE id = ?", (application_id,)) as cursor:
            return application_from_row(await cursor.fetchone())

    async def create(self, user_id: int, draft: ApplicationDraft) -> tuple[Application, bool]:
        cursor = await self.connection.execute("""INSERT INTO applications
            (user_id, type, pet_name, description, district, additional_info, photo_id, submission_key, photo_ids)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(submission_key) DO NOTHING""",
            (user_id, draft.kind.value, draft.pet_name, draft.description, draft.district, draft.additional_info, draft.photo_id, draft.submission_key,
             json.dumps(draft.photo_ids or (draft.photo_id,))))
        created = cursor.rowcount == 1
        async with self.connection.execute("SELECT * FROM applications WHERE submission_key = ? AND user_id = ?", (draft.submission_key, user_id)) as existing:
            application = application_from_row(await existing.fetchone())
        if application is None:
            raise ValueError("Submission key belongs to a different user")
        return application, created

    async def list_owned(self, user_id: int) -> list[Application]:
        async with self.connection.execute("SELECT * FROM applications WHERE user_id = ? ORDER BY status = 'deleted', created_at DESC, id DESC", (user_id,)) as cursor:
            return [application_from_row(row) for row in await cursor.fetchall()]

    async def list_status(self, status: ApplicationStatus, limit=1000) -> list[Application]:
        async with self.connection.execute("SELECT * FROM applications WHERE status = ? ORDER BY created_at DESC, id DESC LIMIT ?", (status.value, limit)) as cursor:
            return [application_from_row(row) for row in await cursor.fetchall()]

    async def next_active(self, user_id: int, district: str | None, excluded_ids=()) -> Application | None:
        excluded = set(excluded_ids)
        async with self.connection.execute("""SELECT a.* FROM applications a
            LEFT JOIN users u ON u.user_id = a.user_id
            WHERE a.status = 'active' AND COALESCE(u.is_banned, 0) = 0
            AND a.user_id != ? AND (? IS NULL OR a.district = ?)
            ORDER BY a.created_at DESC, a.id DESC""",
            (user_id, district, district)) as cursor:
            async for row in cursor:
                if row["id"] not in excluded:
                    return application_from_row(row)
        return None

    async def suspend_for_banned_user(self, user_id: int, reason: str = "Автор заблокирован") -> list[int]:
        async with self.connection.execute(
            "SELECT id FROM applications WHERE user_id = ? AND status IN ('active', 'moderation')",
            (user_id,),
        ) as cursor:
            ids = [row["id"] for row in await cursor.fetchall()]
        if ids:
            await self.connection.execute(
                "UPDATE applications SET status = 'paused' WHERE user_id = ? AND status = 'active'",
                (user_id,),
            )
            await self.connection.execute(
                "UPDATE applications SET status = 'rejected', reject_reason = ? WHERE user_id = ? AND status = 'moderation'",
                (reason, user_id),
            )
        return ids

    async def transition(self, application_id: int, status: ApplicationStatus, *, expected: tuple[ApplicationStatus, ...], owner_id: int | None = None, reason="") -> bool:
        placeholders = ",".join("?" for _ in expected)
        cursor = await self.connection.execute(f"""UPDATE applications SET status = ?,
            reject_reason = CASE WHEN ? = 'rejected' THEN ? ELSE reject_reason END,
            deleted_at = CASE WHEN ? = 'deleted' THEN CURRENT_TIMESTAMP ELSE deleted_at END
            WHERE id = ? AND (? IS NULL OR user_id = ?) AND status IN ({placeholders})""",
            (status.value, status.value, reason, status.value, application_id, owner_id, owner_id, *(item.value for item in expected)))
        return cursor.rowcount == 1

    async def increment_views(self, application_id: int) -> None:
        await self.connection.execute("UPDATE applications SET views = views + 1 WHERE id = ? AND status = 'active'", (application_id,))

    async def add_response(self, application_id: int, user_id: int, location: str) -> int:
        cursor = await self.connection.execute("INSERT INTO responses(application_id, user_id, location, message) VALUES (?, ?, ?, '')", (application_id, user_id, location))
        await self.connection.execute("UPDATE applications SET responses = responses + 1 WHERE id = ?", (application_id,))
        return cursor.lastrowid

    async def delete(self, application_id: int) -> None:
        await self.connection.execute("DELETE FROM responses WHERE application_id = ?", (application_id,))
        await self.connection.execute("DELETE FROM complaints WHERE application_id = ?", (application_id,))
        await self.connection.execute("DELETE FROM applications WHERE id = ?", (application_id,))

    async def counts(self) -> dict[ApplicationStatus, int]:
        async with self.connection.execute("SELECT status, COUNT(*) AS total FROM applications GROUP BY status") as cursor:
            return {ApplicationStatus(row["status"]): row["total"] for row in await cursor.fetchall()}

    async def count_owned(self, user_id: int) -> int:
        async with self.connection.execute("SELECT COUNT(*) FROM applications WHERE user_id = ?", (user_id,)) as cursor:
            return (await cursor.fetchone())[0]

    async def expired_deleted(self) -> list[int]:
        async with self.connection.execute("SELECT id FROM applications WHERE status = 'deleted' AND datetime(deleted_at) <= datetime('now', '-7 days')") as cursor:
            return [row["id"] for row in await cursor.fetchall()]

    async def reminder_candidates(self) -> list[Application]:
        async with self.connection.execute("""SELECT a.* FROM applications a WHERE status = 'active'
            AND created_at <= datetime('now', '-7 days')
            AND NOT EXISTS (SELECT 1 FROM application_reminders r WHERE r.application_id = a.id)""") as cursor:
            return [application_from_row(row) for row in await cursor.fetchall()]

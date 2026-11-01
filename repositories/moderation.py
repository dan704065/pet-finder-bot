from domain.models import Complaint, ComplaintStatus


_COMPLAINT_QUERY = """SELECT c.*, a.pet_name AS application_name, a.district AS district, a.user_id AS author_id
    FROM complaints c LEFT JOIN applications a ON a.id = c.application_id"""


def complaint_from_row(row) -> Complaint | None:
    if row is None:
        return None
    return Complaint(
        id=row["id"], application_id=row["application_id"], reporter_id=row["reporter_id"],
        reason=row["reason"] or "", status=ComplaintStatus(row["status"]), created_at=str(row["created_at"] or ""),
        application_name=row["application_name"], district=row["district"], author_id=row["author_id"],
    )


class ComplaintRepository:
    def __init__(self, connection):
        self.connection = connection

    async def get(self, complaint_id: int) -> Complaint | None:
        async with self.connection.execute(_COMPLAINT_QUERY + " WHERE c.id = ?", (complaint_id,)) as cursor:
            return complaint_from_row(await cursor.fetchone())

    async def list(self, limit=20) -> list[Complaint]:
        async with self.connection.execute(_COMPLAINT_QUERY + " ORDER BY c.status = 'pending' DESC, c.created_at DESC, c.id DESC LIMIT ?", (limit,)) as cursor:
            return [complaint_from_row(row) for row in await cursor.fetchall()]

    async def create(self, application_id: int, reporter_id: int, reason: str) -> int:
        cursor = await self.connection.execute("INSERT INTO complaints(application_id, reporter_id, reason) VALUES (?, ?, ?)", (application_id, reporter_id, reason))
        return cursor.lastrowid

    async def resolve(self, complaint_id: int, status: ComplaintStatus) -> None:
        await self.connection.execute("UPDATE complaints SET status = ? WHERE id = ? AND status = 'pending'", (status.value, complaint_id))

    async def pending_count(self) -> int:
        async with self.connection.execute("SELECT COUNT(*) FROM complaints WHERE status = 'pending'") as cursor:
            return (await cursor.fetchone())[0]

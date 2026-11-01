import time

from database.connection import Database
from domain.models import NotificationKind
from repositories.session import Repositories


class MaintenanceService:
    def __init__(self, database: Database):
        self.database = database

    async def run_due(self, now: int | None = None) -> bool:
        now = int(time.time()) if now is None else now
        async with self.database.connection(write=True) as connection:
            repositories = Repositories(connection)
            if not await repositories.maintenance.due("daily", now):
                return False
            for application_id in await repositories.applications.expired_deleted():
                await repositories.outbox.delete_application(application_id)
                await repositories.applications.delete(application_id)
            for application in await repositories.applications.reminder_candidates():
                user = await repositories.users.get(application.user_id)
                if user is None or user.is_banned:
                    continue
                await repositories.outbox.enqueue(application.user_id, NotificationKind.REMINDER, {"application_id": application.id, "pet_name": application.pet_name}, event_key=f"week-reminder:{application.id}", application_id=application.id, subject_user_id=application.user_id, now=now)
                await repositories.maintenance.mark_reminder(application.id, now)
            await repositories.maintenance.completed("daily", now, 86400)
            return True

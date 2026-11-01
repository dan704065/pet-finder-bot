from uuid import uuid4

from database.connection import Database
from domain.errors import ApplicationUnavailable, DomainError
from domain.models import (
    Application,
    ApplicationStatus,
    Complaint,
    ComplaintStatus,
    Dashboard,
    NotificationKind,
)
from domain.validation import REASON_LIMIT, validate_text
from repositories.session import Repositories
from services.access import require_admin
from settings import Settings


class ModerationService:
    def __init__(self, database: Database, settings: Settings):
        self.database = database
        self.settings = settings

    async def application(self, actor_id: int, application_id: int) -> Application:
        require_admin(self.settings, actor_id)
        async with self.database.connection() as connection:
            application = await Repositories(connection).applications.get(application_id)
            if application is None:
                raise ApplicationUnavailable()
            return application

    async def list_applications(self, actor_id: int) -> list[Application]:
        require_admin(self.settings, actor_id)
        async with self.database.connection() as connection:
            return await Repositories(connection).applications.list_status(ApplicationStatus.MODERATION)

    async def approve(self, actor_id: int, application_id: int) -> None:
        require_admin(self.settings, actor_id)
        async with self.database.connection(write=True) as connection:
            repositories = Repositories(connection)
            if not await repositories.applications.transition(application_id, ApplicationStatus.ACTIVE, expected=(ApplicationStatus.MODERATION,)):
                raise ApplicationUnavailable()
            application = await repositories.applications.get(application_id)
            await repositories.audit.add(actor_id, "Одобрена анкета", f"#{application_id}", application_id=application_id)
            await repositories.outbox.cancel_application(application_id)
            await repositories.outbox.enqueue(application.user_id, NotificationKind.APPROVED, {"application_id": application_id}, event_key=f"approved:{application_id}", application_id=application_id, subject_user_id=application.user_id)
            for user_id in await repositories.users.subscribers(application.district):
                if user_id in self.settings.admin_ids or user_id == application.user_id:
                    continue
                await repositories.outbox.enqueue(user_id, NotificationKind.PUBLISHED, {
                    "application_id": application_id, "kind": application.kind.value,
                    "pet_name": application.pet_name, "district": application.district,
                }, event_key=f"published:{application_id}:{user_id}", application_id=application_id, subject_user_id=application.user_id)

    async def reject(self, actor_id: int, application_id: int, reason: str) -> None:
        require_admin(self.settings, actor_id)
        validate_text(reason, REASON_LIMIT)
        async with self.database.connection(write=True) as connection:
            repositories = Repositories(connection)
            if not await repositories.applications.transition(application_id, ApplicationStatus.REJECTED, expected=(ApplicationStatus.MODERATION,), reason=reason):
                raise ApplicationUnavailable()
            application = await repositories.applications.get(application_id)
            await repositories.audit.add(actor_id, "Отклонена анкета", f"#{application_id}, Причина: {reason}", application_id=application_id)
            await repositories.outbox.cancel_application(application_id)
            await repositories.outbox.enqueue(application.user_id, NotificationKind.REJECTED, {"application_id": application_id, "reason": reason}, event_key=f"rejected:{application_id}", application_id=application_id, subject_user_id=application.user_id)

    async def set_ban(self, actor_id: int, user_id: int, banned: bool, reason="") -> None:
        require_admin(self.settings, actor_id)
        if banned:
            validate_text(reason, REASON_LIMIT)
        async with self.database.connection(write=True) as connection:
            repositories = Repositories(connection)
            user = await repositories.users.get(user_id)
            if user is None:
                raise DomainError("Пользователь не найден")
            if user.is_banned == banned:
                raise DomainError("Статус пользователя уже изменился")
            await repositories.users.set_ban(user_id, banned, reason)
            await repositories.audit.add(actor_id, "Забанил пользователя" if banned else "Разбанил пользователя", f"ID: {user_id}, Причина: {reason}", subject_user_id=user_id)
            await repositories.outbox.enqueue(user_id, NotificationKind.BANNED if banned else NotificationKind.UNBANNED, {"reason": reason}, event_key=f"ban:{user_id}:{uuid4().hex}", subject_user_id=user_id)

    async def list_complaints(self, actor_id: int) -> list[Complaint]:
        require_admin(self.settings, actor_id)
        async with self.database.connection() as connection:
            return await Repositories(connection).complaints.list()

    async def complaint(self, actor_id: int, complaint_id: int) -> Complaint:
        require_admin(self.settings, actor_id)
        async with self.database.connection() as connection:
            complaint = await Repositories(connection).complaints.get(complaint_id)
            if complaint is None:
                raise DomainError("Жалоба не найдена")
            return complaint

    async def resolve_complaint(self, actor_id: int, complaint_id: int, confirmed: bool) -> None:
        require_admin(self.settings, actor_id)
        async with self.database.connection(write=True) as connection:
            repositories = Repositories(connection)
            complaint = await repositories.complaints.get(complaint_id)
            if complaint is None or complaint.status != ComplaintStatus.PENDING:
                raise DomainError("Жалоба уже обработана или удалена")
            await repositories.complaints.resolve(complaint_id, ComplaintStatus.CONFIRMED if confirmed else ComplaintStatus.REJECTED)
            await repositories.audit.add(actor_id, "Подтверждена жалоба" if confirmed else "Отклонена жалоба", f"#{complaint_id}, анкета #{complaint.application_id}", application_id=complaint.application_id)
            if confirmed:
                reason = "Анкета отклонена по результатам рассмотрения жалобы"
                changed = await repositories.applications.transition(complaint.application_id, ApplicationStatus.REJECTED, expected=(ApplicationStatus.MODERATION, ApplicationStatus.ACTIVE, ApplicationStatus.PAUSED), reason=reason)
                if changed:
                    await repositories.outbox.cancel_application(complaint.application_id)
                    await repositories.outbox.enqueue(complaint.author_id, NotificationKind.REJECTED, {"application_id": complaint.application_id, "reason": reason}, event_key=f"complaint-confirmed:{complaint_id}", application_id=complaint.application_id, subject_user_id=complaint.author_id)

    async def dashboard(self, actor_id: int) -> Dashboard:
        require_admin(self.settings, actor_id)
        async with self.database.connection() as connection:
            repositories = Repositories(connection)
            users, banned = await repositories.users.counts()
            pending, failed = await repositories.outbox.counts()
            return Dashboard(users, banned, await repositories.applications.counts(), await repositories.complaints.pending_count(), pending, failed)

    async def list_users(self, actor_id: int):
        require_admin(self.settings, actor_id)
        async with self.database.connection() as connection:
            return await Repositories(connection).users.list()

    async def user_detail(self, actor_id: int, user_id: int):
        require_admin(self.settings, actor_id)
        async with self.database.connection() as connection:
            repositories = Repositories(connection)
            user = await repositories.users.get(user_id)
            if user is None:
                raise DomainError("Пользователь не найден")
            return user, await repositories.applications.count_owned(user_id)

    async def logs(self, actor_id: int):
        require_admin(self.settings, actor_id)
        async with self.database.connection() as connection:
            return await Repositories(connection).audit.latest()

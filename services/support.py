from uuid import uuid4

from database.connection import Database
from domain.errors import ApplicationUnavailable, DomainError, ValidationError
from domain.models import ApplicationStatus, NotificationKind
from domain.validation import SUPPORT_LIMIT, validate_text
from repositories.session import Repositories
from services.access import require_user
from settings import Settings


class SupportService:
    def __init__(self, database: Database, settings: Settings):
        self.database = database
        self.settings = settings

    async def submit(self, actor_id: int, category: str, text: str, *, application_id: int | None = None) -> None:
        validate_text(text, SUPPORT_LIMIT)
        if category not in {"bug", "idea", "complaint"}:
            raise ValidationError("Неизвестный тип обращения")
        if not self.settings.admin_ids:
            raise DomainError("Поддержка временно недоступна")
        async with self.database.connection(write=True) as connection:
            repositories = Repositories(connection)
            await require_user(repositories, actor_id)
            if category == "complaint":
                application = await repositories.applications.get(application_id)
                if application is None or application.status == ApplicationStatus.DELETED:
                    raise ApplicationUnavailable()
                complaint_id = await repositories.complaints.create(application_id, actor_id, text)
                await repositories.audit.add(actor_id, "Жалоба", f"Анкета #{application_id}", application_id=application_id)
                payload = {"complaint_id": complaint_id, "application_id": application_id, "application_name": application.pet_name, "reporter_id": actor_id, "reason": text}
                for admin_id in self.settings.admin_ids:
                    await repositories.outbox.enqueue(admin_id, NotificationKind.COMPLAINT, payload, event_key=f"complaint:{complaint_id}:{admin_id}", application_id=application_id, subject_user_id=actor_id)
            else:
                event_id = uuid4().hex
                await repositories.audit.add(actor_id, "Обращение", category)
                for admin_id in self.settings.admin_ids:
                    await repositories.outbox.enqueue(admin_id, NotificationKind.SUPPORT, {"category": category, "reporter_id": actor_id, "text": text}, event_key=f"support:{event_id}:{admin_id}", subject_user_id=actor_id)

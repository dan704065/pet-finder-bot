from database.connection import Database
from domain.errors import ApplicationUnavailable
from domain.models import (
    Application,
    ApplicationDraft,
    ApplicationStatus,
    NotificationKind,
    OWNER_TRANSITIONS,
)
from domain.validation import RESPONSE_LIMIT, validate_draft, validate_district, validate_text
from repositories.session import Repositories
from services.access import require_user
from settings import Settings


class ApplicationService:
    def __init__(self, database: Database, settings: Settings):
        self.database = database
        self.settings = settings

    async def submit(self, actor_id: int, draft: ApplicationDraft) -> Application:
        validate_draft(draft)
        async with self.database.connection(write=True) as connection:
            repositories = Repositories(connection)
            await require_user(repositories, actor_id)
            application, created = await repositories.applications.create(actor_id, draft)
            if created:
                await repositories.audit.add(actor_id, "Создана анкета", f"Тип: {draft.kind.value}, ID: {application.id}", application_id=application.id)
                for admin_id in self.settings.admin_ids:
                    await repositories.outbox.enqueue(admin_id, NotificationKind.SUBMITTED, {
                        "application_id": application.id, "kind": draft.kind.value,
                        "pet_name": draft.pet_name, "district": draft.district,
                    }, event_key=f"submitted:{application.id}:{admin_id}", application_id=application.id, subject_user_id=actor_id)
            return application

    async def owned(self, actor_id: int, application_id: int) -> Application:
        async with self.database.connection() as connection:
            repositories = Repositories(connection)
            await require_user(repositories, actor_id)
            application = await repositories.applications.get(application_id)
            if application is None or application.user_id != actor_id:
                raise ApplicationUnavailable()
            return application

    async def list_owned(self, actor_id: int) -> list[Application]:
        async with self.database.connection() as connection:
            repositories = Repositories(connection)
            await require_user(repositories, actor_id)
            return await repositories.applications.list_owned(actor_id)

    async def change_status(self, actor_id: int, application_id: int, status: ApplicationStatus) -> None:
        expected = OWNER_TRANSITIONS[status]
        async with self.database.connection(write=True) as connection:
            repositories = Repositories(connection)
            await require_user(repositories, actor_id)
            if not await repositories.applications.transition(application_id, status, expected=expected, owner_id=actor_id):
                raise ApplicationUnavailable()
            if status != ApplicationStatus.ACTIVE:
                await repositories.outbox.cancel_application(application_id)
            actions = {ApplicationStatus.PAUSED: "Анкета на паузе", ApplicationStatus.ACTIVE: "Анкета возобновлена", ApplicationStatus.CLOSED: "Животное найдено", ApplicationStatus.DELETED: "Анкета удалена (мягкое)"}
            await repositories.audit.add(actor_id, actions[status], f"#{application_id}", application_id=application_id)

    async def delete_permanently(self, actor_id: int, application_id: int) -> None:
        async with self.database.connection(write=True) as connection:
            repositories = Repositories(connection)
            await require_user(repositories, actor_id)
            application = await repositories.applications.get(application_id)
            if application is None or application.user_id != actor_id or application.status != ApplicationStatus.DELETED:
                raise ApplicationUnavailable()
            await repositories.outbox.delete_application(application_id)
            await repositories.applications.delete(application_id)
            await repositories.audit.add(actor_id, "Анкета полностью удалена", f"#{application_id}", application_id=application_id)

    async def next_card(self, actor_id: int, district: str | None = None, excluded_ids=()) -> Application | None:
        if district is not None:
            validate_district(district)
        async with self.database.connection(write=True) as connection:
            repositories = Repositories(connection)
            await require_user(repositories, actor_id)
            application = await repositories.applications.next_active(actor_id, district, excluded_ids)
            if application is not None:
                await repositories.applications.increment_views(application.id)
            return application

    async def has_active(self, actor_id: int, district: str | None = None) -> bool:
        async with self.database.connection() as connection:
            repositories = Repositories(connection)
            await require_user(repositories, actor_id)
            return await repositories.applications.next_active(actor_id, district) is not None

    async def public(self, actor_id: int, application_id: int, *, count_view=False) -> Application:
        async with self.database.connection(write=count_view) as connection:
            repositories = Repositories(connection)
            await require_user(repositories, actor_id)
            application = await repositories.applications.get(application_id)
            if application is None or application.status != ApplicationStatus.ACTIVE or application.user_id == actor_id:
                raise ApplicationUnavailable()
            if count_view:
                await repositories.applications.increment_views(application_id)
            return application

    async def respond(self, actor_id: int, application_id: int, location: str) -> None:
        validate_text(location, RESPONSE_LIMIT)
        async with self.database.connection(write=True) as connection:
            repositories = Repositories(connection)
            actor = await require_user(repositories, actor_id)
            application = await repositories.applications.get(application_id)
            if application is None or application.status != ApplicationStatus.ACTIVE or application.user_id == actor_id:
                raise ApplicationUnavailable()
            response_id = await repositories.applications.add_response(application_id, actor_id, location)
            await repositories.audit.add(actor_id, "Отклик", f"Анкета #{application_id}", application_id=application_id)
            await repositories.outbox.enqueue(application.user_id, NotificationKind.RESPONSE, {
                "application_id": application_id, "location": location, "reporter": actor.display_name,
                "reporter_id": actor_id,
            }, event_key=f"response:{response_id}", application_id=application_id, subject_user_id=actor_id)

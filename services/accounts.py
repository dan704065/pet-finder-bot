from database.connection import Database
from domain.errors import ValidationError
from domain.models import NotificationMode, User
from domain.validation import validate_district
from repositories.session import Repositories
from services.access import require_user


class AccountService:
    def __init__(self, database: Database):
        self.database = database

    async def get(self, user_id: int) -> User | None:
        async with self.database.connection() as connection:
            return await Repositories(connection).users.get(user_id)

    async def register(self, user_id: int, username: str, first_name: str) -> User:
        async with self.database.connection(write=True) as connection:
            repositories = Repositories(connection)
            created = await repositories.users.register(user_id, username, first_name)
            user = await require_user(repositories, user_id)
            if created:
                await repositories.audit.add(user_id, "Согласие на ПДн")
            return user

    async def set_district(self, actor_id: int, district: str) -> None:
        validate_district(district)
        async with self.database.connection(write=True) as connection:
            repositories = Repositories(connection)
            await require_user(repositories, actor_id)
            await repositories.users.set_district(actor_id, district)

    async def set_notifications(self, actor_id: int, mode: str) -> None:
        try:
            mode = NotificationMode(mode)
        except ValueError as exc:
            raise ValidationError("Неизвестный режим уведомлений") from exc
        async with self.database.connection(write=True) as connection:
            repositories = Repositories(connection)
            await require_user(repositories, actor_id)
            await repositories.users.set_notifications(actor_id, mode)

    async def delete_data(self, actor_id: int) -> None:
        async with self.database.connection(write=True) as connection:
            repositories = Repositories(connection)
            await require_user(repositories, actor_id)
            await repositories.audit.delete_user_data(actor_id)
            await repositories.outbox.delete_user_data(actor_id)
            await repositories.users.delete_data(actor_id)

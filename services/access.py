from domain.errors import AccessDenied
from domain.models import User
from repositories.session import Repositories
from settings import Settings


def require_admin(settings: Settings, actor_id: int) -> None:
    if actor_id not in settings.admin_ids:
        raise AccessDenied()


async def require_user(repositories: Repositories, actor_id: int) -> User:
    user = await repositories.users.get(actor_id)
    if user is None:
        raise AccessDenied("Для начала работы нажмите /start и подтвердите согласие.")
    if user.is_banned:
        raise AccessDenied("Доступ ограничен. Свяжитесь с администратором.")
    return user

from datetime import datetime

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from domain.districts import NOVOSIBIRSK_DISTRICTS
from domain.errors import ValidationError
from keyboards.user_kb import get_main_menu
from services.container import Services
from utils.messages import h, safe_send


class IsAdmin(Filter):
    async def __call__(self, event, services: Services) -> bool:
        return event.from_user.id in services.settings.admin_ids


def main_menu(services: Services, user_id: int, in_admin_mode=False):
    return get_main_menu(in_admin_mode=in_admin_mode, is_admin=user_id in services.settings.admin_ids)


def get_greeting() -> str:
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "Доброе утро"
    if 12 <= hour < 17:
        return "Добрый день"
    if 17 <= hour < 22:
        return "Добрый вечер"
    return "Доброй ночи"


async def read_district(callback: CallbackQuery):
    district = callback.data.removeprefix("district_")
    if district not in NOVOSIBIRSK_DISTRICTS:
        raise ValidationError("Выберите район из списка")
    return district


def callback_id(callback: CallbackQuery) -> int:
    try:
        value = int(callback.data.rsplit("_", 1)[-1])
        if not 0 < value <= 2**63 - 1:
            raise ValueError()
        return value
    except ValueError as exc:
        raise ValidationError("Некорректная кнопка. Откройте меню заново.") from exc


async def check_banned(user_id: int, event, services: Services) -> bool:
    user = await services.accounts.get(user_id)
    if user is None or not user.is_banned:
        return False
    text = ("🚫 <b>Доступ ограничен</b>\n\nВы были заблокированы по решению администратора.\n\n"
            f"📋 <b>Причина:</b> {h(user.ban_reason or 'не указана')}\n\nДля разблокировки свяжитесь с администратором.")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 Связаться с администратором", url=services.settings.support_url)]])
    await safe_send(event, text, reply_markup=keyboard, parse_mode="HTML")
    if isinstance(event, CallbackQuery):
        await event.answer()
    return True

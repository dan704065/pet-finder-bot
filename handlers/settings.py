from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from handlers.common import main_menu, read_district, check_banned
from handlers.states import SettingsStates
from keyboards.user_kb import get_district_keyboard, get_settings_keyboard
from services.container import Services
from utils.messages import h, safe_send, send_text


async def set_district_cmd(message: Message, state: FSMContext, services: Services):
    if await check_banned(message.from_user.id, message, services=services): return
    text = "📍 <b>Смена района</b>\n\nВыберите ваш район:"
    await send_text(message.answer, text, reply_markup=get_district_keyboard(), parse_mode="HTML")
    await state.set_state(SettingsStates.choosing_district)
    await state.update_data(search_mode="settings")


async def delete_my_data_cmd(message: Message, state: FSMContext, services: Services):
    if await check_banned(message.from_user.id, message, services=services): return
    await state.clear()
    await services.accounts.delete_data(message.from_user.id)

    text = "🗑 <b>Данные удалены</b>\n\nВсе ваши данные удалены.\nНажмите /start для начала."
    await send_text(message.answer, text, parse_mode="HTML")


async def open_settings(callback: CallbackQuery, services: Services):
    if await check_banned(callback.from_user.id, callback, services=services): return
    user = await services.accounts.get(callback.from_user.id)
    mode = user.notification_mode if user else "none"

    mode_text = {
        "district": "Только мой район",
        "city": "Со всего Новосибирска",
        "none": "Отключить уведомления"
    }.get(mode, "Отключить уведомления")

    text = (
        "⚙️ <b>Настройки</b>\n\n"
        f"🔔 <b>Уведомления о новых анкетах:</b> {mode_text}\n\n"
        "Выберите желаемый режим уведомлений:"
    )
    await safe_send(callback, text, reply_markup=get_settings_keyboard(mode), parse_mode="HTML")
    await callback.answer()


async def set_notification_mode_cb(callback: CallbackQuery, services: Services):
    if await check_banned(callback.from_user.id, callback, services=services): return
    mode = callback.data.replace("set_notif_", "")
    if mode not in {"district", "city", "none"}:
        await callback.answer("Неизвестный режим уведомлений", show_alert=True)
        return
    await services.accounts.set_notifications(callback.from_user.id, mode)

    mode_text = {
        "district": "Только мой район",
        "city": "Со всего Новосибирска",
        "none": "Отключить уведомления"
    }.get(mode, "Отключить уведомления")

    text = f"✅ Настройки сохранены.\n🔔 Уведомления: {mode_text}."

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="open_settings")]
    ])

    await safe_send(callback, text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


async def save_district_settings(callback: CallbackQuery, state: FSMContext, services: Services):
    data = await state.get_data()
    if data.get("search_mode") != "settings": return

    if await check_banned(callback.from_user.id, callback, services=services): return
    district = await read_district(callback)
    if district is None: return
    await services.accounts.set_district(callback.from_user.id, district)
    await state.clear()

    text = f"✅ <b>Район изменён</b>\n\n📍 Ваш район: <b>{h(district)}</b>"
    await safe_send(callback, text, reply_markup=main_menu(services, callback.from_user.id), parse_mode="HTML")
    await callback.answer()


def create_router() -> Router:
    router = Router(name="settings")
    router.message.register(set_district_cmd, Command('set_district'))
    router.message.register(delete_my_data_cmd, Command('delete_my_data'))
    router.callback_query.register(open_settings, F.data == 'open_settings')
    router.callback_query.register(set_notification_mode_cb, F.data.startswith('set_notif_'))
    router.callback_query.register(save_district_settings, SettingsStates.choosing_district, F.data.startswith('district_'))
    return router

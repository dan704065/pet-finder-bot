from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from domain.errors import ApplicationUnavailable, DomainError, ValidationError
from handlers.common import check_access, main_menu
from handlers.states import SupportStates
from keyboards.user_kb import get_cancel_only_keyboard, get_support_main_keyboard
from services.container import Services
from utils.messages import SUPPORT_LIMIT, safe_answer, safe_send, send_text, validate_text

MAX_SQLITE_ID = 2**63 - 1
ALLOWED_SUPPORT_TYPES = {"bug", "idea", "complaint"}


async def support(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_access(callback.from_user.id, callback, services=services, state=state):
        return
    text = "💬 <b>Поддержка</b>\n\nВыберите тип обращения:"
    await safe_send(callback, text, reply_markup=get_support_main_keyboard(), parse_mode="HTML")
    await state.set_state(SupportStates.choosing_type)
    await safe_answer(callback)


async def support_type(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_access(callback.from_user.id, callback, services=services, state=state):
        return
    category = callback.data.removeprefix("support_")
    if category not in ALLOWED_SUPPORT_TYPES:
        raise ValidationError("Выберите тип обращения из меню.")
    await state.update_data(support_type=category)

    if category == "complaint":
        text = "⚠️ <b>Жалоба на анкету</b>\n\nВведите ID анкеты:"
        await safe_send(callback, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")
        await state.set_state(SupportStates.choosing_app)
    else:
        text = "💬 <b>Обращение в поддержку</b>\n\nОпишите вашу проблему или идею:"
        await safe_send(callback, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")
        await state.set_state(SupportStates.writing_message)
    await safe_answer(callback)


async def support_app(message: Message, state: FSMContext, services: Services):
    if await check_access(message.from_user.id, message, services=services, state=state):
        return
    raw = (message.text or "").strip().removeprefix("#").strip()
    try:
        app_id = int(raw)
        if not (0 < app_id <= MAX_SQLITE_ID):
            raise ValueError()
    except ValueError:
        text = "⚠️ <b>Неверный формат</b>\n\n🔢 Пожалуйста, введите корректный номер анкеты (число)."
        await send_text(message.answer, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML", preserve=True)
        return

    try:
        await services.support.validate_complaint_target(message.from_user.id, app_id)
    except ApplicationUnavailable:
        text = (
            "⚠️ <b>Анкета не найдена</b>\n\n"
            "Анкета с таким ID не существует или уже удалена.\n"
            "Введите другой номер анкеты или нажмите «Отмена»."
        )
        await send_text(message.answer, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML", preserve=True)
        return

    await state.update_data(app_id=app_id)
    await send_text(message.answer, "Опишите причину жалобы:", reply_markup=get_cancel_only_keyboard())
    await state.set_state(SupportStates.writing_message)


async def support_app_invalid(message: Message, state: FSMContext, services: Services):
    if await check_access(message.from_user.id, message, services=services, state=state):
        return
    text = "⚠️ <b>Неверный формат</b>\n\n🔢 Пожалуйста, введите число (ID анкеты)."
    await send_text(message.answer, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML", preserve=True)


async def support_message(message: Message, state: FSMContext, services: Services):
    if await check_access(message.from_user.id, message, services=services, state=state):
        return
    if not await validate_text(message, SUPPORT_LIMIT, reply_markup=get_cancel_only_keyboard()):
        return
    data = await state.get_data()
    category = data.get("support_type")
    if category not in ALLOWED_SUPPORT_TYPES:
        await state.clear()
        raise DomainError("Обращение устарело. Откройте раздел поддержки заново.")
    try:
        await services.support.submit(message.from_user.id, category, message.text, application_id=data.get("app_id"))
    except ApplicationUnavailable:
        await send_text(message.answer, "Анкета больше недоступна.", reply_markup=main_menu(services, message.from_user.id))
        await state.clear()
        return

    text = "✅ <b>Обращение принято</b>\n\nСпасибо! Мы рассмотрим ваше обращение."
    await send_text(message.answer, text, reply_markup=main_menu(services, message.from_user.id), parse_mode="HTML", keep=True)
    await state.clear()


async def support_message_invalid(message: Message, state: FSMContext, services: Services):
    if await check_access(message.from_user.id, message, services=services, state=state):
        return
    text = "⚠️ <b>Неверный формат</b>\n\n✏️ Пожалуйста, введите текстовое описание."
    await send_text(message.answer, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML", preserve=True)


def create_router() -> Router:
    router = Router(name="support")
    router.callback_query.register(support, F.data == "support")
    router.callback_query.register(support_type, SupportStates.choosing_type, F.data.startswith("support_"))
    router.message.register(support_app, SupportStates.choosing_app, F.text, ~F.text.startswith("/"))
    router.message.register(support_app_invalid, SupportStates.choosing_app, ~F.text)
    router.message.register(support_message, SupportStates.writing_message, F.text, ~F.text.startswith("/"))
    router.message.register(support_message_invalid, SupportStates.writing_message, ~F.text)
    return router

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from handlers.common import main_menu, check_banned
from handlers.states import SupportStates
from keyboards.user_kb import get_cancel_only_keyboard, get_support_main_keyboard
from services.container import Services
from utils.messages import safe_send, send_text, validate_text, SUPPORT_LIMIT


async def support(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_banned(callback.from_user.id, callback, services=services): return
    text = "💬 <b>Поддержка</b>\n\nВыберите тип обращения:"
    await safe_send(callback, text, reply_markup=get_support_main_keyboard(), parse_mode="HTML")
    await state.set_state(SupportStates.choosing_type)
    await callback.answer()


async def support_type(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_banned(callback.from_user.id, callback, services=services): return
    support_type = callback.data.replace("support_", "")
    await state.update_data(support_type=support_type)

    if support_type == "complaint":
        text = "⚠️ <b>Жалоба на анкету</b>\n\nВведите ID анкеты:"
        await safe_send(callback, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")
        await state.set_state(SupportStates.choosing_app)
    else:
        text = "💬 <b>Обращение в поддержку</b>\n\nОпишите вашу проблему или идею:"
        await safe_send(callback, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")
        await state.set_state(SupportStates.writing_message)
    await callback.answer()


async def support_app(message: Message, state: FSMContext, services: Services):
    if await check_banned(message.from_user.id, message, services=services): return
    try:
        await state.update_data(app_id=int(message.text))
    except ValueError:
        text = "⚠️ <b>Неверный формат</b>\n\n🔢 Пожалуйста, введите число (ID анкеты)."
        await send_text(message.answer, text, parse_mode="HTML")
        return
    await send_text(message.answer, "Опишите причину жалобы:", reply_markup=get_cancel_only_keyboard())
    await state.set_state(SupportStates.writing_message)


async def support_app_invalid(message: Message, services: Services):
    text = "⚠️ <b>Неверный формат</b>\n\n🔢 Пожалуйста, введите число (ID анкеты)."
    await send_text(message.answer, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")


async def support_message(message: Message, state: FSMContext, services: Services):
    if await check_banned(message.from_user.id, message, services=services): return
    if not await validate_text(message, SUPPORT_LIMIT): return
    data = await state.get_data()
    await services.support.submit(message.from_user.id, data.get("support_type"), message.text, application_id=data.get("app_id"))

    text = "✅ <b>Обращение принято</b>\n\nСпасибо! Мы рассмотрим ваше обращение."
    await state.clear()
    await send_text(message.answer, text, reply_markup=main_menu(services, message.from_user.id), parse_mode="HTML")


async def support_message_invalid(message: Message, services: Services):
    text = "⚠️ <b>Неверный формат</b>\n\n✏️ Пожалуйста, введите текстовое описание."
    await send_text(message.answer, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")


def create_router() -> Router:
    router = Router(name="support")
    router.callback_query.register(support, F.data == 'support')
    router.callback_query.register(support_type, SupportStates.choosing_type, F.data.startswith('support_'))
    router.message.register(support_app, SupportStates.choosing_app, F.text)
    router.message.register(support_app_invalid, SupportStates.choosing_app)
    router.message.register(support_message, SupportStates.writing_message, F.text)
    router.message.register(support_message_invalid, SupportStates.writing_message)
    return router

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from handlers.common import main_menu, check_banned, IsAdmin
from handlers.states import CreateApplication, FoundPet
from keyboards.user_kb import get_cancel_only_keyboard, get_back_cancel_keyboard, get_district_keyboard
from services.container import Services
from utils.messages import safe_send, send_text


async def main_menu_back(callback: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    if await check_banned(callback.from_user.id, callback, services=services): return
    await safe_send(callback, "🏠 Выберите действие:", reply_markup=main_menu(services, callback.from_user.id))
    await callback.answer()


async def cancel_handler(callback: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    if await check_banned(callback.from_user.id, callback, services=services): return
    text = "❌ <b>Действие отменено</b>\n\n🏠 Выберите действие:"
    await safe_send(callback, text, reply_markup=main_menu(services, callback.from_user.id), parse_mode="HTML")
    await callback.answer()


async def step_back(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_banned(callback.from_user.id, callback, services=services): return
    current_state = await state.get_state()

    if current_state == CreateApplication.waiting_for_name.state:
        text = "🐾 <b>Я потерял животное</b>\n\n<b>Шаг 1 из 5</b>\n\n📸 Отправьте фото питомца."
        await safe_send(callback, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")
        await state.set_state(CreateApplication.waiting_for_photo)
    elif current_state == CreateApplication.waiting_for_description.state:
        text = "🐾 <b>Я потерял животное</b>\n\n<b>Шаг 2 из 5</b>\n\n🏷 Как зовут вашего питомца?"
        await safe_send(callback, text, reply_markup=get_back_cancel_keyboard(), parse_mode="HTML")
        await state.set_state(CreateApplication.waiting_for_name)
    elif current_state == CreateApplication.waiting_for_district.state:
        text = "🐾 <b>Я потерял животное</b>\n\n<b>Шаг 3 из 5</b>\n\n📝 Опишите приметы."
        await safe_send(callback, text, reply_markup=get_back_cancel_keyboard(), parse_mode="HTML")
        await state.set_state(CreateApplication.waiting_for_description)
    elif current_state == CreateApplication.waiting_for_additional.state:
        text = "🐾 <b>Я потерял животное</b>\n\n<b>Шаг 4 из 5</b>\n\n📍 Выберите район Новосибирска:"
        await safe_send(callback, text, reply_markup=get_district_keyboard(), parse_mode="HTML")
        await state.set_state(CreateApplication.waiting_for_district)
    elif current_state == FoundPet.waiting_for_district.state:
        text = "🔍 <b>Я нашёл животное</b>\n\n<b>Шаг 1 из 4</b>\n\n📸 Отправьте фото питомца."
        await safe_send(callback, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")
        await state.set_state(FoundPet.waiting_for_photo)
    elif current_state == FoundPet.waiting_for_description.state:
        text = "🔍 <b>Я нашёл животное</b>\n\n<b>Шаг 2 из 4</b>\n\n📍 Выберите район Новосибирска:"
        await safe_send(callback, text, reply_markup=get_district_keyboard(), parse_mode="HTML")
        await state.set_state(FoundPet.waiting_for_district)
    elif current_state == FoundPet.waiting_for_confirm.state:
        text = "🔍 <b>Я нашёл животное</b>\n\n<b>Шаг 3 из 4</b>\n\n📝 Опишите животное и обстоятельства находки."
        await safe_send(callback, text, reply_markup=get_back_cancel_keyboard(), parse_mode="HTML")
        await state.set_state(FoundPet.waiting_for_description)
    else:
        await callback.answer("Назад нельзя", show_alert=True)
        return

    await callback.answer()


async def catch_all(message: Message, state: FSMContext, services: Services):
    if await check_banned(message.from_user.id, message, services=services): return

    current_state = await state.get_state()
    if current_state:
        text = (
            "⚠️ <b>Неверный ввод</b>\n\n"
            "Пожалуйста, следуйте инструкциям на экране.\n\n"
            "Если вы хотите отменить действие — нажмите кнопку \"Отмена\".\n"
            "Если хотите вернуться назад — нажмите кнопку \"Назад\"."
        )
        await send_text(message.answer, text, parse_mode="HTML")
        return

    text = (
        "🤔 <b>Не понял вас</b>\n\n"
        "Воспользуйтесь кнопками меню ниже.\n\n"
        "Если меню пропало — нажмите /start"
    )
    await send_text(message.answer, text, reply_markup=main_menu(services, message.from_user.id), parse_mode="HTML")


async def admin_access_denied(callback: CallbackQuery, services: Services):
    await callback.answer("Доступ запрещён", show_alert=True)


def create_router() -> Router:
    router = Router(name="navigation")
    router.callback_query.register(main_menu_back, F.data == 'main_menu_back')
    router.callback_query.register(cancel_handler, F.data == 'cancel')
    router.callback_query.register(step_back, F.data == 'step_back')
    router.message.register(catch_all)
    router.callback_query.register(admin_access_denied, F.data.startswith('admin_'), ~IsAdmin())
    return router

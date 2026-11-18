from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from domain.districts import get_district_prepositional
from domain.errors import ApplicationUnavailable
from handlers.common import callback_id, check_access, main_menu, read_district
from handlers.states import SwipeStates
from keyboards.user_kb import (
    get_cancel_only_keyboard,
    get_district_keyboard,
    get_help_search_keyboard,
    get_swipe_end_keyboard,
    get_swipe_keyboard,
)
from presentation.cards import application_card
from services.container import Services
from utils.messages import RESPONSE_LIMIT, h, safe_answer, safe_send, send_photo_text, send_text, validate_text


async def help_search(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_access(callback.from_user.id, callback, services=services, state=state):
        return
    await state.clear()
    await state.update_data(viewed_apps=[])
    text = (
        "🤝 <b>Помочь в поиске</b>\n\n"
        "Спасибо, что хотите помочь!\n"
        "Выберите способ поиска:"
    )
    await safe_send(callback, text, reply_markup=get_help_search_keyboard(), parse_mode="HTML")
    await safe_answer(callback)


async def help_choose_district(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_access(callback.from_user.id, callback, services=services, state=state):
        return
    await state.update_data(search_mode="district", viewed_apps=[])
    text = "📍 <b>Выбор района</b>\n\nВыберите район Новосибирска:"
    await safe_send(callback, text, reply_markup=get_district_keyboard(), parse_mode="HTML")
    await state.set_state(SwipeStates.choosing_district)
    await safe_answer(callback)


async def help_all_city(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_access(callback.from_user.id, callback, services=services, state=state):
        return
    await state.update_data(search_mode="city", viewed_apps=[])
    await safe_send(callback, "🔍 Поиск анкет по всему Новосибирску...")
    await show_next_card(callback.message, callback.from_user.id, state, services=services)
    await safe_answer(callback)


async def set_district_swipe(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_access(callback.from_user.id, callback, services=services, state=state):
        return
    district = await read_district(callback)
    if district is None:
        return
    await state.update_data(district=district, search_mode="district", viewed_apps=[])

    await services.accounts.set_district(callback.from_user.id, district)

    prep_district = get_district_prepositional(district)
    await safe_send(callback, f"🔍 Поиск анкет в {h(prep_district)} районе...", parse_mode="HTML")
    await show_next_card(callback.message, callback.from_user.id, state, services=services)
    await safe_answer(callback)


async def show_next_card(message, user_id, state, services: Services):
    data = await state.get_data()
    search_mode = data.get("search_mode", "district")
    district = data.get("district")
    viewed_apps = data.get("viewed_apps", [])

    district = None if search_mode == "city" else district
    location_text = "Новосибирске" if district is None else f"{get_district_prepositional(district)} районе"
    app = await services.applications.next_card(user_id, district, viewed_apps)
    if app is None:
        all_available = await services.applications.has_active(user_id, district)
        await state.update_data(current_app_id=None)
        if all_available and viewed_apps:
            text = (
                f"✅ <b>Вы просмотрели все анкеты</b>\n\n"
                f"В {h(location_text)} больше нет новых анкет для вас.\n\n"
                f"👀 <b>Просмотрено:</b> {len(viewed_apps)}\n\n"
                "Что хотите сделать?"
            )
            await send_text(message.answer, text, reply_markup=get_swipe_end_keyboard(), parse_mode="HTML")
            await state.set_state(SwipeStates.swiping)
            return
        text = f"🔍 <b>Поиск завершён</b>\n\nВ {h(location_text)} пока нет активных анкет."
        await send_text(message.answer, text, reply_markup=get_help_search_keyboard(), parse_mode="HTML")
        await state.clear()
        return

    app_id = app.id
    viewed_apps.append(app_id)
    await state.update_data(viewed_apps=viewed_apps)

    await send_photo_text(message, app.photo_ids or app.photo_id, application_card(app), get_swipe_keyboard(app_id))

    await state.set_state(SwipeStates.swiping)
    await state.update_data(current_app_id=app_id)


async def swipe_restart(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_access(callback.from_user.id, callback, services=services, state=state):
        return
    await state.update_data(viewed_apps=[])
    await safe_send(callback, "🔄 Начинаем просмотр заново...")
    await show_next_card(callback.message, callback.from_user.id, state, services=services)
    await safe_answer(callback)


async def swipe_finish(callback: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    if await check_access(callback.from_user.id, callback, services=services, state=state):
        return
    text = (
        "✅ <b>Просмотр завершён</b>\n\n"
        "Спасибо, что помогаете искать животных!\n\n"
        "🏠 Выберите действие:"
    )
    await safe_send(callback, text, reply_markup=main_menu(services, callback.from_user.id), parse_mode="HTML")
    await safe_answer(callback)


async def swipe_skip(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_access(callback.from_user.id, callback, services=services, state=state):
        return
    await show_next_card(callback.message, callback.from_user.id, state, services=services)
    await safe_answer(callback)


async def swipe_seen(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_access(callback.from_user.id, callback, services=services, state=state):
        return
    app_id = callback_id(callback)
    await services.applications.public(callback.from_user.id, app_id)
    data = await state.get_data()
    shown_ids = set(data.get("viewed_apps", []))
    shown_ids.add(data.get("current_app_id"))
    if app_id not in shown_ids:
        await safe_answer(callback, "Анкета больше недоступна", show_alert=True)
        return
    await state.update_data(response_app_id=app_id)
    text = (
        "👀 <b>Вы видели животное</b>\n\n"
        "Где и когда вы его видели?\n"
        "Напишите адрес или описание."
    )
    await safe_send(callback, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")
    await state.set_state(SwipeStates.writing_response)
    await safe_answer(callback)


async def write_response(message: Message, state: FSMContext, services: Services):
    if await check_access(message.from_user.id, message, services=services, state=state):
        return
    if not await validate_text(message, RESPONSE_LIMIT, reply_markup=get_cancel_only_keyboard()):
        return
    data = await state.get_data()
    try:
        await services.applications.respond(message.from_user.id, data.get("response_app_id"), message.text)
    except ApplicationUnavailable:
        await send_text(message.answer, "Анкета больше недоступна.", reply_markup=main_menu(services, message.from_user.id))
        await state.clear()
        return
    text = "✅ <b>Спасибо!</b>\n\nВаш отклик принят."
    await send_text(message.answer, text, reply_markup=main_menu(services, message.from_user.id), parse_mode="HTML", keep=True)
    await state.clear()


async def write_response_invalid(message: Message, state: FSMContext, services: Services):
    if await check_access(message.from_user.id, message, services=services, state=state):
        return
    text = "⚠️ <b>Неверный формат</b>\n\n✏️ Пожалуйста, введите текстовое описание."
    await send_text(message.answer, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML", preserve=True)


async def notify_show(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_access(callback.from_user.id, callback, services=services):
        return
    app_id = callback_id(callback)
    prior_data = await state.get_data()
    already_viewed = app_id in prior_data.get("viewed_apps", [])

    app = await services.applications.public(callback.from_user.id, app_id, count_view=not already_viewed)
    await state.clear()
    await state.update_data(search_mode="city", viewed_apps=[app_id])
    if app:
        await state.update_data(current_app_id=app_id)
        await state.set_state(SwipeStates.swiping)
        await send_photo_text(callback.message, app.photo_ids or app.photo_id, application_card(app), get_swipe_keyboard(app.id))

    await safe_answer(callback)


async def notify_skip(callback: CallbackQuery, services: Services):
    if callback.message:
        try:
            await callback.message.delete()
        except TelegramAPIError:
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except TelegramAPIError:
                pass
    await safe_answer(callback, "Пропущено")


def create_router() -> Router:
    router = Router(name="search")
    router.callback_query.register(help_search, F.data == "help_search")
    router.callback_query.register(help_choose_district, F.data == "help_choose_district")
    router.callback_query.register(help_all_city, F.data == "help_all_city")
    router.callback_query.register(set_district_swipe, SwipeStates.choosing_district, F.data.startswith("district_"))
    router.callback_query.register(swipe_restart, F.data == "swipe_restart")
    router.callback_query.register(swipe_finish, F.data == "swipe_finish")
    router.callback_query.register(swipe_skip, SwipeStates.swiping, F.data.startswith("swipe_skip_"))
    router.callback_query.register(swipe_seen, SwipeStates.swiping, F.data.startswith("swipe_seen_"))
    router.message.register(write_response, SwipeStates.writing_response, F.text, ~F.text.startswith("/"))
    router.message.register(write_response_invalid, SwipeStates.writing_response, ~F.text)
    router.callback_query.register(notify_show, F.data.startswith("notify_show_"))
    router.callback_query.register(notify_skip, F.data == "notify_skip")
    return router

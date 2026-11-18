from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from handlers.common import check_access, main_menu
from handlers.states import (
    CreateApplication,
    FoundPet,
    InitialStates,
    LocationStates,
    SettingsStates,
    SwipeStates,
)
from keyboards.user_kb import get_district_keyboard
from services.container import Services
from services.geolocation import detect_district
from utils.messages import h, safe_answer, send_text
from utils.screens import try_delete


DISTRICT_STATES = {
    InitialStates.waiting_for_district.state,
    SettingsStates.choosing_district.state,
    CreateApplication.waiting_for_district.state,
    FoundPet.waiting_for_district.state,
    SwipeStates.choosing_district.state,
}

DISTRICT_BACK_STATES = {
    CreateApplication.waiting_for_district.state,
    FoundPet.waiting_for_district.state,
}


async def request_location(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_access(callback.from_user.id, callback, services=services, state=state):
        return
    current = await state.get_state()
    if current not in DISTRICT_STATES:
        await safe_answer(callback, "Откройте выбор района заново.", show_alert=True)
        return
    await state.update_data(geo_return_state=current)
    await state.set_state(LocationStates.waiting_for_location)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Поделиться геопозицией", request_location=True)],
            [KeyboardButton(text="Выбрать район вручную")],
            [KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await send_text(
        callback.message.answer,
        "📍 Нажмите «Поделиться геопозицией» или отправьте точку через меню вложений.\n\n"
        "Координаты используются только для определения района Новосибирска. "
        "Бот не сохраняет их и не передаёт сервисам карт. После обработки сообщение с геопозицией будет удалено.\n\n"
        "Можно выбрать район вручную.",
        reply_markup=keyboard,
    )
    await safe_answer(callback)


async def process_location(message: Message, state: FSMContext, services: Services):
    # Delete first, including out-of-city points and locations sent outside this flow.
    await try_delete(message.bot, message.chat.id, message.message_id)
    if await check_access(message.from_user.id, message, services=services, state=state):
        return
    if await state.get_state() != LocationStates.waiting_for_location.state:
        await send_text(
            message.answer,
            "Чтобы определить район, нажмите «📍 Не знаю, подскажите мне» при выборе района.",
            preserve=True,
        )
        return
    if message.location.live_period:
        await send_text(
            message.answer,
            "Отправьте обычную геопозицию — без трансляции в реальном времени.",
            preserve=True,
        )
        return
    district = detect_district(message.location.latitude, message.location.longitude)
    if district is None:
        await return_to_manual(message, state)
        return
    # Only the district name enters durable FSM storage.
    await state.update_data(geo_district=district)
    await state.set_state(LocationStates.confirming_district)
    await send_text(message.answer, "Геопозиция обработана.", reply_markup=ReplyKeyboardRemove())
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Использовать: {district}", callback_data="geo_use")],
        [InlineKeyboardButton(text="Выбрать другой район", callback_data="geo_manual")],
    ])
    await send_text(
        message.answer,
        f"📍 Определён район: <b>{h(district)}</b>.\n\nВсё верно?",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def return_to_manual(message, state):
    data = await state.get_data()
    original = data.pop("geo_return_state", InitialStates.waiting_for_district.state)
    data.pop("geo_district", None)
    await state.set_data(data)
    await state.set_state(original)
    await send_text(message.answer, "Выбор района вручную.", reply_markup=ReplyKeyboardRemove())
    await send_text(
        message.answer,
        "📍 Выберите район Новосибирска. Если вы за пределами города, укажите нужный район вручную.",
        reply_markup=get_district_keyboard(include_back=original in DISTRICT_BACK_STATES),
    )


async def manual_message(message: Message, state: FSMContext, services: Services):
    if await check_access(message.from_user.id, message, services=services, state=state):
        return
    await return_to_manual(message, state)


async def manual_callback(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_access(callback.from_user.id, callback, services=services, state=state):
        return
    await return_to_manual(callback.message, state)
    await safe_answer(callback)


async def cancel_location(message: Message, state: FSMContext, services: Services):
    await state.clear()
    await send_text(message.answer, "Запрос геопозиции отменён.", reply_markup=ReplyKeyboardRemove())
    if await check_access(message.from_user.id, message, services=services, state=state):
        return
    await send_text(message.answer, "🏠 Выберите действие:", reply_markup=main_menu(services, message.from_user.id))


async def use_district(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_access(callback.from_user.id, callback, services=services, state=state):
        return
    data = await state.get_data()
    original = data.pop("geo_return_state", None)
    district = data.pop("geo_district", None)
    if original not in DISTRICT_STATES or not district:
        await safe_answer(callback, "Выберите район заново.", show_alert=True)
        return
    await state.set_data(data)
    await state.set_state(original)
    selection = callback.model_copy(update={"data": f"district_{district}"}).as_(callback.bot)
    from handlers import applications, onboarding, search, settings
    handler = {
        InitialStates.waiting_for_district.state: onboarding.save_initial_district,
        SettingsStates.choosing_district.state: settings.save_district_settings,
        CreateApplication.waiting_for_district.state: applications.process_district,
        FoundPet.waiting_for_district.state: applications.found_district,
        SwipeStates.choosing_district.state: search.set_district_swipe,
    }[original]
    await handler(selection, state, services)


async def location_hint(message: Message, state: FSMContext, services: Services):
    if await check_access(message.from_user.id, message, services=services, state=state):
        return
    await send_text(
        message.answer,
        "Нажмите «📍 Поделиться геопозицией» или «Выбрать район вручную».",
        preserve=True,
    )


def create_router():
    router = Router(name="location")
    router.callback_query.register(request_location, F.data == "detect_district")
    router.message.register(process_location, F.location, F.chat.type == "private")
    router.callback_query.register(use_district, LocationStates.confirming_district, F.data == "geo_use")
    router.callback_query.register(manual_callback, LocationStates.confirming_district, F.data == "geo_manual")
    router.message.register(manual_message, LocationStates.waiting_for_location, F.text == "Выбрать район вручную")
    router.message.register(cancel_location, LocationStates.waiting_for_location, F.text == "Отмена")
    router.message.register(location_hint, LocationStates.waiting_for_location)
    return router

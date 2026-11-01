from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from handlers.common import main_menu, get_greeting, read_district, check_banned
from handlers.states import InitialStates
from keyboards.user_kb import get_district_keyboard
from presentation.texts import DISCLAIMER_TEXT
from services.container import Services
from utils.messages import h, safe_send, send_text


async def user_start(message: Message, state: FSMContext, services: Services):
    await state.clear()
    user = await services.accounts.get(message.from_user.id)
    if user is None:
        greeting = get_greeting()
        name = message.from_user.first_name or ""
        greeting_text = f"{greeting}, <b>{h(name)}</b>!" if name else f"{greeting}!"
        text = (
            f"👋 <b>{greeting_text}</b>\n\n"
            "Это бот поиска потерянных животных в вашем районе.\n\n"
            "Перед началом работы необходимо согласие на обработку "
            "персональных данных в соответствии с 152-ФЗ.\n\n"
            "🔒 Данные не передаются третьим лицам.\n"
            "🗑 Удалить данные: /delete_my_data"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Согласен", callback_data="agree_pd")]
        ])
        await send_text(message.answer, text, reply_markup=kb, parse_mode="HTML")
    else:
        if await check_banned(message.from_user.id, message, services=services): return
        greeting = get_greeting()
        name = message.from_user.first_name or ""
        greeting_text = f"{greeting}, <b>{h(name)}</b>!" if name else f"{greeting}!"
        text = f"👋 <b>{greeting_text}</b>\n\nВыберите действие:"
        await safe_send(message, text, reply_markup=main_menu(services, message.from_user.id), parse_mode="HTML")


async def agree_pd(callback: CallbackQuery, state: FSMContext, services: Services):
    user = await services.accounts.register(callback.from_user.id, callback.from_user.username or "", callback.from_user.first_name or "")
    if not user or not user.district:
        text = "📍 Для более эффективного поиска укажите ваш район. Это позволит получать уведомления о животных рядом.\n\nВы можете указать район сейчас или сделать это позже в Настройках."
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Указать район", callback_data="prompt_initial_district")],
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_initial_district")]
        ])
        await safe_send(callback, text, reply_markup=kb, parse_mode="HTML")
        await callback.answer()
        return

    await show_main_menu_after_consent(callback, services=services)


async def prompt_initial_district(callback: CallbackQuery, state: FSMContext, services: Services):
    text = "📍 Выберите ваш район:"
    await safe_send(callback, text, reply_markup=get_district_keyboard(), parse_mode="HTML")
    await state.set_state(InitialStates.waiting_for_district)
    await callback.answer()


async def save_initial_district(callback: CallbackQuery, state: FSMContext, services: Services):
    district = await read_district(callback)
    if district is None: return
    await services.accounts.set_district(callback.from_user.id, district)
    await state.clear()
    await show_main_menu_after_consent(callback, services=services)


async def skip_initial_district(callback: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    await show_main_menu_after_consent(callback, services=services)


async def show_main_menu_after_consent(callback: CallbackQuery, services: Services):
    greeting = get_greeting()
    name = callback.from_user.first_name or ""
    greeting_text = f"{greeting}, <b>{h(name)}</b>!" if name else f"{greeting}!"
    text = f"👋 <b>{greeting_text}</b>\n\n{DISCLAIMER_TEXT}"
    await send_text(callback.message.answer, text, parse_mode="HTML")
    await send_text(callback.message.answer, "✅ Выберите действие:", reply_markup=main_menu(services, callback.from_user.id), parse_mode="HTML")
    await callback.answer()


def create_router() -> Router:
    router = Router(name="onboarding")
    router.message.register(user_start, CommandStart())
    router.callback_query.register(agree_pd, F.data == 'agree_pd')
    router.callback_query.register(prompt_initial_district, F.data == 'prompt_initial_district')
    router.callback_query.register(save_initial_district, InitialStates.waiting_for_district, F.data.startswith('district_'))
    router.callback_query.register(skip_initial_district, F.data == 'skip_initial_district')
    return router

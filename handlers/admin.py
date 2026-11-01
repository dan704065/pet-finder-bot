from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import BOT_TOKEN, ADMIN_IDS
from database.db import (
    add_user, get_all_users_count, get_applications_count,
    get_applications_by_status, add_log, ban_user, unban_user
)
from keyboards.user_kb import get_main_menu, get_cancel_only_keyboard
import aiosqlite
from database.db import DB_PATH

router = Router()


class AdminBanStates(StatesGroup):
    waiting_for_reason = State()


async def safe_send(callback_or_message, text: str, reply_markup=None, parse_mode: str = None):
    from aiogram.exceptions import TelegramBadRequest
    try:
        if isinstance(callback_or_message, CallbackQuery):
            msg = callback_or_message.message
            if msg.photo:
                await msg.edit_caption(caption=text, reply_markup=reply_markup, parse_mode=parse_mode)
            else:
                await msg.edit_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await callback_or_message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest:
        if isinstance(callback_or_message, CallbackQuery):
            await callback_or_message.message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await callback_or_message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)


# УДАЛЁН обработчик @router.message(CommandStart(), F.from_user.id.in_(ADMIN_IDS))
# Админ теперь проходит обычный путь через user.py


@router.callback_query(F.data == "admin_stats", F.from_user.id.in_(ADMIN_IDS))
async def admin_stats(callback: CallbackQuery):
    users_count = await get_all_users_count()
    apps_count = await get_applications_count()
    active_apps = await get_applications_by_status("active")
    moderation_apps = await get_applications_by_status("moderation")
    closed_apps = await get_applications_by_status("closed")
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1") as cursor:
            banned_count = (await cursor.fetchone())[0]
    
    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 <b>Пользователи:</b>\n"
        f"   Всего: {users_count}\n"
        f"   Забанено: {banned_count}\n\n"
        f"📋 <b>Анкеты:</b>\n"
        f"   Всего: {apps_count}\n"
        f"   🟢 Активных: {active_apps}\n"
        f"   ⏳ На модерации: {moderation_apps}\n"
        f"   🔴 Закрытых: {closed_apps}"
    )
    
    await safe_send(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_enter_mode")]
    ]), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_users_list", F.from_user.id.in_(ADMIN_IDS))
async def admin_users_list(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, username, first_name, is_banned, district FROM users ORDER BY created_at DESC LIMIT 20"
        ) as cursor:
            users = await cursor.fetchall()
    
    if not users:
        text = "👥 <b>Пользователи</b>\n\nПользователей пока нет."
        await safe_send(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_enter_mode")]
        ]), parse_mode="HTML")
        await callback.answer()
        return
    
    text = "👥 <b>Пользователи</b> (первые 20)\n\n"
    keyboard = []
    for u in users:
        status = "🚫" if u[3] else "✅"
        district = u[4] or "не указан"
        username = f"@{u[1]}" if u[1] else u[2]
        keyboard.append([InlineKeyboardButton(
            text=f"{status} {u[0]} | {username} | {district}",
            callback_data=f"admin_user_detail_{u[0]}"
        )])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_enter_mode")])
    
    await safe_send(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_user_detail_"), F.from_user.id.in_(ADMIN_IDS))
async def admin_user_detail(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[-1])
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
        async with db.execute("SELECT COUNT(*) FROM applications WHERE user_id = ?", (user_id,)) as cursor:
            apps_count = (await cursor.fetchone())[0]
    
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    
    status = "🚫 Заблокирован" if user[4] else "✅ Активен"
    ban_reason = user[5] if user[5] else "нет"
    district = user[6] or "не указан"
    username = f"@{user[1]}" if user[1] else user[2]
    
    text = (
        f"👤 <b>Пользователь {user[0]}</b>\n\n"
        f"📛 <b>Имя:</b> {username}\n"
        f"📍 <b>Район:</b> {district}\n"
        f"📌 <b>Статус:</b> {status}\n"
        f"📋 <b>Причина бана:</b> {ban_reason}\n"
        f"📋 <b>Анкет:</b> {apps_count}"
    )
    
    keyboard = []
    if user[4]:
        keyboard.append([InlineKeyboardButton(text="✅ Разблокировать", callback_data=f"admin_unban_{user_id}")])
    else:
        keyboard.append([InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"admin_ban_prompt_{user_id}")])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад к списку", callback_data="admin_users_list")])
    
    await safe_send(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_unban_"), F.from_user.id.in_(ADMIN_IDS))
async def admin_unban(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[-1])
    await unban_user(user_id)
    await add_log(callback.from_user.id, "Разбанил пользователя", f"ID: {user_id}")
    
    try:
        async with Bot(token=BOT_TOKEN) as bot:
            text = "✅ <b>Вы были разблокированы</b>\n\nДобро пожаловать!"
            await bot.send_message(user_id, text, parse_mode="HTML")
    except Exception:
        pass
    
    await callback.answer("Пользователь разблокирован", show_alert=True)
    await admin_user_detail(callback)


@router.callback_query(F.data.startswith("admin_ban_prompt_"), F.from_user.id.in_(ADMIN_IDS))
async def admin_ban_prompt(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[-1])
    await state.update_data(ban_target_user_id=user_id, action="ban")
    
    text = (
        f"🚫 <b>Блокировка пользователя</b>\n\n"
        f"ID: <code>{user_id}</code>\n\n"
        "Укажите причину блокировки:"
    )
    await callback.message.answer(text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")
    await state.set_state(AdminBanStates.waiting_for_reason)
    await callback.answer()


@router.callback_query(F.data == "admin_logs", F.from_user.id.in_(ADMIN_IDS))
async def admin_logs(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT action, details, created_at FROM logs ORDER BY created_at DESC LIMIT 20") as cursor:
            logs = await cursor.fetchall()
    
    text = "📜 <b>Последние действия</b>\n\n"
    if not logs:
        text += "<i>Логи пусты.</i>"
    else:
        for log in logs:
            date_str = str(log[2])[:16].replace("T", " ") if log[2] else "?"
            text += f"🕐 <code>{date_str}</code>\n"
            text += f"   {log[0]}"
            if log[1]: text += f" — <i>{log[1]}</i>"
            text += "\n\n"
            
    await safe_send(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_enter_mode")]
    ]), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_exit_mode", F.from_user.id.in_(ADMIN_IDS))
async def admin_exit_mode(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_send(callback, "✅ Вы вернулись в обычный режим.", reply_markup=get_main_menu(callback.from_user.id, in_admin_mode=False))
    await callback.answer()
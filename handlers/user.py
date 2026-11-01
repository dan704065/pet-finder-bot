from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from config import BOT_TOKEN, ADMIN_IDS
from datetime import datetime
from keyboards.user_kb import (
    get_main_menu, get_cancel_only_keyboard, get_back_cancel_keyboard, 
    get_confirm_keyboard, get_swipe_keyboard, get_swipe_end_keyboard, get_application_list_keyboard,
    get_application_manage_keyboard, get_confirm_delete_keyboard, get_support_main_keyboard,
    get_district_keyboard, get_help_search_keyboard, get_settings_keyboard
)
from database.db import (
    add_user, get_user, create_application, get_application,
    get_applications_by_status_list, get_active_applications,
    update_application_status, soft_delete_application, hard_delete_application,
    add_response, add_complaint, add_log, delete_user_data, increment_views, ban_user,
    set_notification_mode, get_users_for_notification, get_district_prepositional
)
from utils.blacklist import moderate_text
import aiosqlite
from database.db import DB_PATH
from utils.logger import logger

router = Router()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def get_greeting() -> str:
    hour = datetime.now().hour
    if 5 <= hour < 12: return "Доброе утро"
    elif 12 <= hour < 17: return "Добрый день"
    elif 17 <= hour < 22: return "Добрый вечер"
    else: return "Доброй ночи"


def format_date(date_str) -> str:
    if not date_str: return "неизвестно"
    try: return str(date_str)[:16].replace("T", " ")
    except Exception: return "неизвестно"


async def safe_send(callback_or_message, text: str, reply_markup=None, parse_mode: str = None):
    try:
        if isinstance(callback_or_message, CallbackQuery):
            msg = callback_or_message.message
            if msg.photo: await msg.edit_caption(caption=text, reply_markup=reply_markup, parse_mode=parse_mode)
            else: await msg.edit_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await callback_or_message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest:
        if isinstance(callback_or_message, CallbackQuery):
            await callback_or_message.message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await callback_or_message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)


async def check_banned(user_id: int, callback_or_message) -> bool:
    user = await get_user(user_id)
    if user and user[4] == 1:
        reason = user[5] if user[5] else "не указана"
        text = (
            "🚫 <b>Доступ ограничен</b>\n\n"
            "Вы были заблокированы по решению администратора.\n\n"
            f"📋 <b>Причина:</b> {reason}\n\n"
            "Для разблокировки свяжитесь с администратором."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Связаться с администратором", url="https://t.me/dan704035")]
        ])
        await safe_send(callback_or_message, text, reply_markup=keyboard, parse_mode="HTML")
        return True
    return False


async def notify_admins_about_new_application(app_id: int, app_type: str, pet_name: str, district: str):
    type_text = "🐾 Потерялось" if app_type == "lost" else "🔍 Найдено"
    
    admin_text = (
        f"🆕 <b>Новая анкета #{app_id}</b>\n\n"
        f"📋 <b>Тип:</b> {type_text}\n"
        f"🏷 <b>Кличка:</b> {pet_name}\n"
        f"📍 <b>Район:</b> {district}\n\n"
        "⏳ Требуется модерация."
    )
    for admin_id in ADMIN_IDS:
        try:
            async with Bot(token=BOT_TOKEN) as bot:
                await bot.send_message(
                    admin_id, admin_text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="📋 Перейти к модерации", callback_data=f"admin_moderate_{app_id}")]
                    ]),
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"Ошибка уведомления админа {admin_id}: {e}")


async def notify_users_about_approved_application(app_id: int, app_type: str, pet_name: str, district: str):
    type_text = "🐾 Потерялось" if app_type == "lost" else "🔍 Найдено"
    prep_district = get_district_prepositional(district)
    
    user_text = (
        f"🆕 <b>Новая анкета в {prep_district} районе!</b>\n\n"
        f"📋 <b>Тип:</b> {type_text}\n"
        f"🏷 <b>Кличка:</b> {pet_name}\n\n"
        f"Возможно, вы знаете, где это животное?"
    )
    
    users_to_notify = await get_users_for_notification(district)
    notified_count = 0
    
    for user_id in users_to_notify:
        if user_id in ADMIN_IDS: continue
        try:
            async with Bot(token=BOT_TOKEN) as bot:
                await bot.send_message(
                    user_id, user_text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(text="👀 Показать", callback_data=f"notify_show_{app_id}"),
                            InlineKeyboardButton(text="⏭ Пропустить", callback_data="notify_skip")
                        ]
                    ]),
                    parse_mode="HTML"
                )
                notified_count += 1
        except Exception as e:
            logger.error(f"Ошибка уведомления пользователя {user_id}: {e}")
    
    logger.info(f"Анкета #{app_id} одобрена, уведомлено пользователей: {notified_count}")


DISCLAIMER_TEXT = (
    "⚠️ <b>Важная информация</b>\n\n"
    "Наш сервис полностью безвозмездный и работает на волонтёрской основе.\n\n"
    "🔒 Мы <b>не занимаемся</b> сбором средств и не требуем оплаты.\n"
    "🚫 <b>Никогда не переводите деньги</b> пользователям или администраторам бота — "
    "все услуги оказываются бесплатно.\n"
    "💬 Если кто-то просит у вас деньги — это мошенники. Сообщите нам через поддержку.\n\n"
    "Помните: главная цель бота — помочь животным найти своих хозяев."
)


# ==================== СОСТОЯНИЯ ====================

class CreateApplication(StatesGroup):
    waiting_for_photo = State()
    waiting_for_name = State()
    waiting_for_description = State()
    waiting_for_district = State()
    waiting_for_additional = State()
    waiting_for_confirm = State()


class FoundPet(StatesGroup):
    waiting_for_photo = State()
    waiting_for_district = State()
    waiting_for_description = State()
    waiting_for_confirm = State()


class SwipeStates(StatesGroup):
    choosing_district = State()
    swiping = State()
    writing_response = State()


class SupportStates(StatesGroup):
    choosing_type = State()
    choosing_app = State()
    writing_message = State()


class AdminBanStates(StatesGroup):
    waiting_for_reason = State()


class InitialStates(StatesGroup):
    waiting_for_district = State()


# ==================== СТАРТ ====================

@router.message(CommandStart())
async def user_start(message: Message, state: FSMContext):
    await state.clear()
    user = await get_user(message.from_user.id)
    if user is None:
        greeting = get_greeting()
        name = message.from_user.first_name or ""
        greeting_text = f"{greeting}, <b>{name}</b>!" if name else f"{greeting}!"
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
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        if await check_banned(message.from_user.id, message): return
        greeting = get_greeting()
        name = message.from_user.first_name or ""
        greeting_text = f"{greeting}, <b>{name}</b>!" if name else f"{greeting}!"
        text = f"👋 <b>{greeting_text}</b>\n\nВыберите действие:"
        await safe_send(message, text, reply_markup=get_main_menu(message.from_user.id), parse_mode="HTML")


@router.callback_query(F.data == "agree_pd")
async def agree_pd(callback: CallbackQuery, state: FSMContext):
    await add_user(callback.from_user.id, callback.from_user.username or "", callback.from_user.first_name or "")
    await add_log(callback.from_user.id, "Согласие на ПДн")
    
    user = await get_user(callback.from_user.id)
    if not user or not user[7]:
        text = "📍 Для более эффективного поиска укажите ваш район. Это позволит получать уведомления о животных рядом.\n\nВы можете указать район сейчас или сделать это позже в Настройках."
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Указать район", callback_data="prompt_initial_district")],
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_initial_district")]
        ])
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await callback.answer()
        return

    await show_main_menu_after_consent(callback)


@router.callback_query(F.data == "prompt_initial_district")
async def prompt_initial_district(callback: CallbackQuery, state: FSMContext):
    text = "📍 Выберите ваш район:"
    await callback.message.edit_text(text, reply_markup=get_district_keyboard(), parse_mode="HTML")
    await state.set_state(InitialStates.waiting_for_district)
    await callback.answer()


@router.callback_query(InitialStates.waiting_for_district, F.data.startswith("district_"))
async def save_initial_district(callback: CallbackQuery, state: FSMContext):
    district = callback.data.replace("district_", "")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET district = ? WHERE user_id = ?", (district, callback.from_user.id))
        await db.commit()
    await state.clear()
    await show_main_menu_after_consent(callback)


@router.callback_query(F.data == "skip_initial_district")
async def skip_initial_district(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_main_menu_after_consent(callback)


async def show_main_menu_after_consent(callback: CallbackQuery):
    greeting = get_greeting()
    name = callback.from_user.first_name or ""
    greeting_text = f"{greeting}, <b>{name}</b>!" if name else f"{greeting}!"
    text = f"👋 <b>{greeting_text}</b>\n\n{DISCLAIMER_TEXT}"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.message.answer("✅ Выберите действие:", reply_markup=get_main_menu(callback.from_user.id), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "main_menu_back")
async def main_menu_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if await check_banned(callback.from_user.id, callback): return
    await safe_send(callback, "🏠 Выберите действие:", reply_markup=get_main_menu(callback.from_user.id))
    await callback.answer()


# ==================== НАСТРОЙКИ ====================

@router.callback_query(F.data == "open_settings")
async def open_settings(callback: CallbackQuery):
    if await check_banned(callback.from_user.id, callback): return
    user = await get_user(callback.from_user.id)
    mode = user[6] if user and len(user) > 6 else "none"

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


@router.callback_query(F.data.startswith("set_notif_"))
async def set_notification_mode_cb(callback: CallbackQuery):
    if await check_banned(callback.from_user.id, callback): return
    mode = callback.data.replace("set_notif_", "")
    await set_notification_mode(callback.from_user.id, mode)

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


# ==================== РЕЖИМ АДМИНИСТРАТОРА ====================

@router.callback_query(F.data == "admin_enter_mode")
async def admin_enter_mode(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM applications WHERE status = 'moderation'") as cursor:
            mod_count = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM complaints WHERE status = 'pending'") as cursor:
            complaints_count = (await cursor.fetchone())[0]
    
    text = (
        f"🛠 <b>Режим администратора</b>\n\n"
        f"📋 Анкет на модерации: <b>{mod_count}</b>\n"
        f"⚠️ Жалоб в очереди: <b>{complaints_count}</b>\n\n"
        "Выберите раздел:"
    )
    
    await safe_send(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📋 Модерация анкет ({mod_count})", callback_data="admin_moderation_list")],
        [InlineKeyboardButton(text=f"⚠️ Жалобы ({complaints_count})", callback_data="admin_complaints_list")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users_list")],
        [InlineKeyboardButton(text="📜 Логирование", callback_data="admin_logs")],
        [InlineKeyboardButton(text="👤 Выйти в режим пользователя", callback_data="admin_exit_mode")]
    ]), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_exit_mode")
async def admin_exit_mode(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_send(callback, "✅ Вы вернулись в обычный режим.", reply_markup=get_main_menu(callback.from_user.id, in_admin_mode=False))
    await callback.answer()


# ==================== МОДЕРАЦИЯ АНКЕТ ====================

@router.callback_query(F.data == "admin_moderation_list")
async def admin_moderation_list(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM applications WHERE status = 'moderation' ORDER BY created_at DESC LIMIT 10"
        ) as cursor:
            apps = await cursor.fetchall()
    
    if not apps:
        text = "📋 <b>Модерация анкет</b>\n\n✅ Нет анкет на модерации."
        await safe_send(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_enter_mode")]
        ]), parse_mode="HTML")
        await callback.answer()
        return
    
    keyboard = []
    for app in apps:
        status = "🐾" if app[2] == "lost" else "🔍"
        keyboard.append([InlineKeyboardButton(
            text=f"{status} #{app[0]} — {app[3]} ({app[5]})", 
            callback_data=f"admin_moderate_{app[0]}"
        )])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_enter_mode")])
    
    text = "📋 <b>Анкеты на модерации</b>"
    await safe_send(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_moderate_"))
async def admin_moderate(callback: CallbackQuery):
    app_id = int(callback.data.split("_")[-1])
    app = await get_application(app_id)
    
    if not app:
        await callback.answer("Анкета не найдена", show_alert=True)
        return
    
    type_text = "🐾 Потерялось" if app[2] == "lost" else "🔍 Найдено"
    created_at = format_date(app[12] if len(app) > 12 else None)
    
    text = (
        f"📋 <b>Анкета #{app[0]}</b>\n\n"
        f"📌 <b>Тип:</b> {type_text}\n"
        f"👤 <b>Автор ID:</b> <code>{app[1]}</code>\n"
        f"🏷 <b>Кличка:</b> {app[3]}\n"
        f"📝 <b>Приметы:</b>\n<i>{app[4]}</i>\n"
        f"📍 <b>Район:</b> {app[5]}\n"
        f"💬 <b>Дополнительная информация:</b> <i>{app[6] or 'нет'}</i>\n"
        f"🕐 <b>Создана:</b> {created_at}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"admin_approve_{app_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_reject_{app_id}")
        ],
        [InlineKeyboardButton(text="🚫 Забанить автора", callback_data=f"admin_ban_user_{app[1]}")],
        [InlineKeyboardButton(text="🔙 Назад к списку", callback_data="admin_moderation_list")]
    ])
    
    if app[7]:
        try:
            await callback.message.answer_photo(photo=app[7], caption=text, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    
    await callback.answer()


@router.callback_query(F.data.startswith("admin_approve_"))
async def admin_approve(callback: CallbackQuery):
    app_id = int(callback.data.split("_")[-1])
    await update_application_status(app_id, "active")
    await add_log(callback.from_user.id, "Одобрена анкета", f"#{app_id}")
    
    app = await get_application(app_id)
    if app:
        try:
            async with Bot(token=BOT_TOKEN) as bot:
                text = f"✅ <b>Анкета #{app_id} одобрена</b>\n\nВаша анкета опубликована и теперь видна волонтёрам."
                await bot.send_message(app[1], text, parse_mode="HTML")
        except Exception:
            pass
        
        await notify_users_about_approved_application(
            app_id=app[0],
            app_type=app[2],
            pet_name=app[3],
            district=app[5]
        )
    
    await callback.answer("Анкета одобрена", show_alert=True)
    await admin_moderation_list(callback)


@router.callback_query(F.data.startswith("admin_reject_"))
async def admin_reject_prompt(callback: CallbackQuery, state: FSMContext):
    app_id = int(callback.data.split("_")[-1])
    await state.update_data(reject_app_id=app_id, action="reject")
    
    text = (
        f"❌ <b>Отклонение анкеты #{app_id}</b>\n\n"
        "Укажите причину отклонения (она будет отправлена автору):"
    )
    await callback.message.answer(text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")
    await state.set_state(AdminBanStates.waiting_for_reason)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_ban_user_"))
async def admin_ban_user(callback: CallbackQuery, state: FSMContext):
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


@router.message(AdminBanStates.waiting_for_reason)
async def process_reason_input(message: Message, state: FSMContext):
    data = await state.get_data()
    action = data.get("action")
    
    if action == "reject":
        app_id = data.get("reject_app_id")
        reason = message.text
        
        from database.db import reject_application
        await reject_application(app_id, reason)
        await add_log(message.from_user.id, "Отклонена анкета", f"#{app_id}, Причина: {reason}")
        
        app = await get_application(app_id)
        if app:
            try:
                async with Bot(token=BOT_TOKEN) as bot:
                    text = (
                        f"❌ <b>Анкета #{app_id} отклонена</b>\n\n"
                        f"📋 <b>Причина:</b> {reason}\n\n"
                        "Вы можете создать новую анкету с учётом замечаний."
                    )
                    await bot.send_message(app[1], text, parse_mode="HTML")
            except Exception:
                pass
        
        await state.clear()
        await message.answer(
            f"✅ <b>Анкета #{app_id} отклонена</b>",
            reply_markup=get_main_menu(message.from_user.id, in_admin_mode=True),
            parse_mode="HTML"
        )
    
    elif action == "ban":
        user_id = data.get("ban_target_user_id")
        reason = message.text
        
        await ban_user(user_id, reason)
        await add_log(message.from_user.id, "Забанил пользователя", f"ID: {user_id}, Причина: {reason}")
        
        try:
            async with Bot(token=BOT_TOKEN) as bot:
                text = (
                    "🚫 <b>Доступ ограничен</b>\n\n"
                    "Вы были заблокированы по решению администратора.\n\n"
                    f"📋 <b>Причина:</b> {reason}\n\n"
                    "Для разблокировки свяжитесь с администратором."
                )
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💬 Связаться с администратором", url="https://t.me/dan704035")]
                ])
                await bot.send_message(user_id, text, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            pass
        
        await state.clear()
        await message.answer(
            f"✅ <b>Пользователь {user_id} заблокирован</b>",
            reply_markup=get_main_menu(message.from_user.id, in_admin_mode=True),
            parse_mode="HTML"
        )


# ==================== ЖАЛОБЫ ====================

@router.callback_query(F.data == "admin_complaints_list")
async def admin_complaints_list(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT c.id, c.application_id, c.reporter_id, c.reason, c.status, c.created_at,
                      a.pet_name, a.district
               FROM complaints c
               LEFT JOIN applications a ON c.application_id = a.id
               ORDER BY c.created_at DESC LIMIT 20"""
        ) as cursor:
            complaints = await cursor.fetchall()
    
    if not complaints:
        text = "⚠️ <b>Жалобы</b>\n\n✅ Жалоб нет."
        await safe_send(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_enter_mode")]
        ]), parse_mode="HTML")
        await callback.answer()
        return
    
    keyboard = []
    for c in complaints:
        status = "⏳" if c[4] == "pending" else ("✅" if c[4] == "confirmed" else "❌")
        app_name = c[6] or "анкета удалена"
        keyboard.append([InlineKeyboardButton(
            text=f"{status} #{c[0]} — {app_name} (от {c[2]})",
            callback_data=f"admin_complaint_view_{c[0]}"
        )])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_enter_mode")])
    
    text = "⚠️ <b>Жалобы</b>"
    await safe_send(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_complaint_view_"))
async def admin_complaint_view(callback: CallbackQuery):
    complaint_id = int(callback.data.split("_")[-1])
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT c.id, c.application_id, c.reporter_id, c.reason, c.status, c.created_at,
                      a.pet_name, a.district, a.user_id
               FROM complaints c
               LEFT JOIN applications a ON c.application_id = a.id
               WHERE c.id = ?""",
            (complaint_id,)
        ) as cursor:
            complaint = await cursor.fetchone()
    
    if not complaint:
        await callback.answer("Жалоба не найдена", show_alert=True)
        return
    
    status_names = {
        "pending": "⏳ На рассмотрении",
        "confirmed": "✅ Подтверждена",
        "rejected": "❌ Отклонена"
    }
    
    text = (
        f"⚠️ <b>Жалоба #{complaint[0]}</b>\n\n"
        f"📋 <b>Анкета:</b> #{complaint[1]} ({complaint[6] or 'удалена'})\n"
        f"📍 <b>Район:</b> {complaint[7] or 'неизвестно'}\n"
        f"👤 <b>Автор анкеты:</b> <code>{complaint[8] or 'неизвестно'}</code>\n\n"
        f"🚨 <b>Жалобу подал:</b> <code>{complaint[2]}</code>\n"
        f"🕐 <b>Время:</b> {format_date(complaint[5])}\n\n"
        f"📝 <b>Причина:</b>\n<i>{complaint[3]}</i>\n\n"
        f"📌 <b>Статус:</b> {status_names.get(complaint[4], complaint[4])}"
    )
    
    keyboard = []
    if complaint[4] == "pending":
        keyboard.append([
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_complaint_confirm_{complaint_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_complaint_reject_{complaint_id}")
        ])
        if complaint[8]:
            keyboard.append([InlineKeyboardButton(text="🚫 Забанить автора анкеты", callback_data=f"admin_ban_user_{complaint[8]}")])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад к списку", callback_data="admin_complaints_list")])
    
    await safe_send(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_complaint_confirm_"))
async def admin_complaint_confirm(callback: CallbackQuery):
    complaint_id = int(callback.data.split("_")[-1])
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT application_id FROM complaints WHERE id = ?", (complaint_id,)
        ) as cursor:
            row = await cursor.fetchone()
        
        if not row:
            await callback.answer("Жалоба не найдена", show_alert=True)
            return
        
        app_id = row[0]
        
        await db.execute("UPDATE complaints SET status = 'confirmed' WHERE id = ?", (complaint_id,))
        await db.execute("UPDATE applications SET status = 'rejected', reject_reason = ? WHERE id = ?",
                        ("Анкета отклонена по результатам рассмотрения жалобы", app_id))
        await db.commit()
    
    await add_log(callback.from_user.id, "Подтверждена жалоба", f"#{complaint_id}, анкета #{app_id}")
    
    app = await get_application(app_id)
    if app:
        try:
            async with Bot(token=BOT_TOKEN) as bot:
                text = (
                    f"❌ <b>Анкета #{app_id} отклонена</b>\n\n"
                    "По результатам рассмотрения жалобы ваша анкета была отклонена.\n\n"
                    "Вы можете создать новую анкету с учётом правил сервиса."
                )
                await bot.send_message(app[1], text, parse_mode="HTML")
        except Exception:
            pass
    
    await callback.answer("Жалоба подтверждена, анкета отклонена", show_alert=True)
    await admin_complaints_list(callback)


@router.callback_query(F.data.startswith("admin_complaint_reject_"))
async def admin_complaint_reject(callback: CallbackQuery):
    complaint_id = int(callback.data.split("_")[-1])
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE complaints SET status = 'rejected' WHERE id = ?", (complaint_id,))
        await db.commit()
    
    await add_log(callback.from_user.id, "Отклонена жалоба", f"#{complaint_id}")
    await callback.answer("Жалоба отклонена", show_alert=True)
    await admin_complaints_list(callback)


# ==================== СТАТИСТИКА ====================

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            users_count = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1") as cursor:
            banned_count = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM applications WHERE status != 'deleted'") as cursor:
            apps_count = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM applications WHERE status = 'active'") as cursor:
            active_apps = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM applications WHERE status = 'moderation'") as cursor:
            mod_apps = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM applications WHERE status = 'closed'") as cursor:
            closed_apps = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM complaints WHERE status = 'pending'") as cursor:
            complaints_count = (await cursor.fetchone())[0]
    
    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 <b>Пользователи:</b>\n"
        f"   Всего: {users_count}\n"
        f"   Забанено: {banned_count}\n\n"
        f"📋 <b>Анкеты:</b>\n"
        f"   Всего: {apps_count}\n"
        f"   🟢 Активных: {active_apps}\n"
        f"   ⏳ На модерации: {mod_apps}\n"
        f"   🔴 Закрытых: {closed_apps}\n\n"
        f"⚠️ <b>Жалоб в очереди:</b> {complaints_count}"
    )
    
    await safe_send(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_enter_mode")]
    ]), parse_mode="HTML")
    await callback.answer()


# ==================== ПОЛЬЗОВАТЕЛИ ====================

@router.callback_query(F.data == "admin_users_list")
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


# ==================== ЛОГИРОВАНИЕ ====================

@router.callback_query(F.data == "admin_logs")
async def admin_logs(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT action, details, created_at FROM logs ORDER BY created_at DESC LIMIT 20") as cursor:
            logs = await cursor.fetchall()
    
    text = "📜 <b>Последние действия</b>\n\n"
    if not logs:
        text += "<i>Логи пусты.</i>"
    else:
        for log in logs:
            date_str = format_date(log[2])
            text += f"🕐 <code>{date_str}</code>\n"
            text += f"   {log[0]}"
            if log[1]: text += f" — <i>{log[1]}</i>"
            text += "\n\n"
            
    await safe_send(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_enter_mode")]
    ]), parse_mode="HTML")
    await callback.answer()


# ==================== СОЗДАНИЕ АНКЕТЫ "Я ПОТЕРЯЛ" ====================

@router.callback_query(F.data == "lost_pet")
async def lost_pet(callback: CallbackQuery, state: FSMContext):
    if await check_banned(callback.from_user.id, callback): return
    
    text = (
        "🐾 <b>Я потерял животное</b>\n\n"
        "<b>Шаг 1 из 5</b>\n\n"
        "📸 Отправьте фото вашего питомца.\n\n"
        "💡 Если что-то пошло не так — нажмите /start"
    )
    await safe_send(callback, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")
    await state.set_state(CreateApplication.waiting_for_photo)
    await callback.answer()


@router.message(CreateApplication.waiting_for_photo, F.photo)
async def process_photo(message: Message, state: FSMContext):
    if await check_banned(message.from_user.id, message): return
    await state.update_data(photo_id=message.photo[-1].file_id)
    text = "🐾 <b>Я потерял животное</b>\n\n<b>Шаг 2 из 5</b>\n\n🏷 Как зовут вашего питомца?"
    await message.answer(text, reply_markup=get_back_cancel_keyboard(), parse_mode="HTML")
    await state.set_state(CreateApplication.waiting_for_name)


@router.message(CreateApplication.waiting_for_photo)
async def process_photo_invalid(message: Message):
    text = "⚠️ <b>Неверный формат</b>\n\n📸 Пожалуйста, отправьте фотографию питомца."
    await message.answer(text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")


@router.message(CreateApplication.waiting_for_name, F.text)
async def process_name(message: Message, state: FSMContext):
    if await check_banned(message.from_user.id, message): return
    is_ok, reason = moderate_text(message.text)
    if not is_ok:
        await message.answer(f"❌ Ошибка: {reason}. Попробуйте ещё раз.")
        return
    await state.update_data(pet_name=message.text)
    text = (
        "🐾 <b>Я потерял животное</b>\n\n<b>Шаг 3 из 5</b>\n\n"
        "📝 Опишите приметы (порода, окрас, ошейник).\n\n"
        "💡 <i>Пример: Рыжий кот, белое пятно на лапе, синий ошейник</i>"
    )
    await message.answer(text, reply_markup=get_back_cancel_keyboard(), parse_mode="HTML")
    await state.set_state(CreateApplication.waiting_for_description)


@router.message(CreateApplication.waiting_for_name)
async def process_name_invalid(message: Message):
    text = "⚠️ <b>Неверный формат</b>\n\n✏️ Пожалуйста, введите текстовое имя питомца."
    await message.answer(text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")


@router.message(CreateApplication.waiting_for_description, F.text)
async def process_description(message: Message, state: FSMContext):
    if await check_banned(message.from_user.id, message): return
    is_ok, reason = moderate_text(message.text)
    if not is_ok:
        await message.answer(f"❌ Ошибка: {reason}. Попробуйте ещё раз.")
        return
    await state.update_data(description=message.text)
    text = "🐾 <b>Я потерял животное</b>\n\n<b>Шаг 4 из 5</b>\n\n📍 Выберите район Новосибирска:"
    await message.answer(text, reply_markup=get_district_keyboard(), parse_mode="HTML")
    await state.set_state(CreateApplication.waiting_for_district)


@router.message(CreateApplication.waiting_for_description)
async def process_description_invalid(message: Message):
    text = "⚠️ <b>Неверный формат</b>\n\n✏️ Пожалуйста, введите текстовое описание примет."
    await message.answer(text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")


@router.callback_query(CreateApplication.waiting_for_district, F.data.startswith("district_"))
async def process_district(callback: CallbackQuery, state: FSMContext):
    if await check_banned(callback.from_user.id, callback): return
    district = callback.data.replace("district_", "")
    await state.update_data(district=district)
    text = (
        "🐾 <b>Я потерял животное</b>\n\n<b>Шаг 5 из 5</b>\n\n"
        "💬 Дополнительная информация (необязательно).\n"
        "Напишите <code>-</code> если нет."
    )
    await callback.message.edit_text(text, reply_markup=get_back_cancel_keyboard(), parse_mode="HTML")
    await state.set_state(CreateApplication.waiting_for_additional)
    await callback.answer()


@router.message(CreateApplication.waiting_for_district, F.text)
async def process_district_text_invalid(message: Message, state: FSMContext):
    text = (
        "⚠️ <b>Неверный ввод</b>\n\n"
        "📍 Пожалуйста, выберите район из списка кнопок ниже.\n\n"
        "Если вы хотите вернуться назад — нажмите кнопку \"Назад\"."
    )
    await message.answer(text, reply_markup=get_district_keyboard(), parse_mode="HTML")


@router.message(CreateApplication.waiting_for_additional, F.text)
async def process_additional(message: Message, state: FSMContext):
    if await check_banned(message.from_user.id, message): return
    text_input = message.text if message.text != "-" else ""
    if text_input:
        is_ok, reason = moderate_text(text_input)
        if not is_ok:
            await message.answer(f"❌ Ошибка: {reason}. Попробуйте ещё раз.")
            return
    
    await state.update_data(additional_info=text_input)
    data = await state.get_data()
    
    preview = (
        "📋 <b>Проверьте анкету</b>\n\n"
        f"🏷 <b>Кличка:</b> {data['pet_name']}\n"
        f"📝 <b>Приметы:</b>\n<i>{data['description']}</i>\n"
        f"📍 <b>Район:</b> {data['district']}\n"
        f"💬 <b>Дополнительная информация:</b> <i>{data['additional_info'] or 'нет'}</i>\n\n"
        "Всё верно?"
    )
    await message.answer(preview, reply_markup=get_confirm_keyboard(), parse_mode="HTML")
    await state.set_state(CreateApplication.waiting_for_confirm)


@router.message(CreateApplication.waiting_for_additional)
async def process_additional_invalid(message: Message):
    text = "⚠️ <b>Неверный формат</b>\n\n✏️ Пожалуйста, введите текст или <code>-</code>."
    await message.answer(text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")


@router.callback_query(CreateApplication.waiting_for_confirm, F.data == "confirm_ok")
async def confirm_ok(callback: CallbackQuery, state: FSMContext):
    if await check_banned(callback.from_user.id, callback): return
    data = await state.get_data()
    app_id = await create_application(
        user_id=callback.from_user.id, app_type="lost", pet_name=data["pet_name"],
        description=data["description"], district=data["district"],
        additional_info=data["additional_info"], photo_id=data["photo_id"]
    )
    await add_log(callback.from_user.id, "Создана анкета", f"Тип: lost, ID: {app_id}")
    await state.clear()
    
    await notify_admins_about_new_application(app_id, "lost", data["pet_name"], data["district"])
    
    text = (
        f"✅ <b>Анкета отправлена</b>\n\n"
        f"Ваша анкета <b>#{app_id}</b> отправлена на модерацию.\n\n"
        "После проверки она появится в ленте волонтёров.\n\n"
        "Вы можете вернуться в главное меню или создать ещё одну анкету."
    )
    
    await callback.message.answer(text, reply_markup=get_main_menu(callback.from_user.id), parse_mode="HTML")
    await callback.answer("Отправлено!", show_alert=True)


@router.callback_query(CreateApplication.waiting_for_confirm, F.data == "confirm_edit")
async def confirm_edit(callback: CallbackQuery, state: FSMContext):
    if await check_banned(callback.from_user.id, callback): return
    text = "🐾 <b>Я потерял животное</b>\n\nНачинаем заново.\n\n<b>Шаг 1 из 5</b>\n\n📸 Отправьте фото вашего питомца."
    await safe_send(callback, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")
    await state.set_state(CreateApplication.waiting_for_photo)
    await callback.answer()


# ==================== СОЗДАНИЕ АНКЕТЫ "Я НАШЁЛ" ====================

@router.callback_query(F.data == "found_pet")
async def found_pet(callback: CallbackQuery, state: FSMContext):
    if await check_banned(callback.from_user.id, callback): return
    
    text = (
        "🔍 <b>Я нашёл животное</b>\n\n"
        "<b>Шаг 1 из 4</b>\n\n"
        "📸 Отправьте фото найденного питомца.\n\n"
        "💡 Нажмите /start для сброса"
    )
    await safe_send(callback, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")
    await state.set_state(FoundPet.waiting_for_photo)
    await callback.answer()


@router.message(FoundPet.waiting_for_photo, F.photo)
async def found_photo(message: Message, state: FSMContext):
    if await check_banned(message.from_user.id, message): return
    await state.update_data(photo_id=message.photo[-1].file_id)
    text = "🔍 <b>Я нашёл животное</b>\n\n<b>Шаг 2 из 4</b>\n\n📍 Выберите район Новосибирска:"
    await message.answer(text, reply_markup=get_district_keyboard(), parse_mode="HTML")
    await state.set_state(FoundPet.waiting_for_district)


@router.message(FoundPet.waiting_for_photo)
async def found_photo_invalid(message: Message):
    text = "⚠️ <b>Неверный формат</b>\n\n📸 Пожалуйста, отправьте фотографию."
    await message.answer(text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")


@router.callback_query(FoundPet.waiting_for_district, F.data.startswith("district_"))
async def found_district(callback: CallbackQuery, state: FSMContext):
    if await check_banned(callback.from_user.id, callback): return
    district = callback.data.replace("district_", "")
    await state.update_data(district=district)
    
    text = (
        "🔍 <b>Я нашёл животное</b>\n\n"
        "<b>Шаг 3 из 4</b>\n\n"
        "📝 Опишите животное и обстоятельства находки:\n"
        "• Порода, окрас, размер\n"
        "• Поведение (пугливое, дружелюбное)\n"
        "• Где именно нашли\n"
        "• Есть ли ошейник\n\n"
        "💡 Чем подробнее — тем быстрее найдётся хозяин"
    )
    await callback.message.edit_text(text, reply_markup=get_back_cancel_keyboard(), parse_mode="HTML")
    await state.set_state(FoundPet.waiting_for_description)
    await callback.answer()


@router.message(FoundPet.waiting_for_district, F.text)
async def found_district_text_invalid(message: Message, state: FSMContext):
    text = (
        "⚠️ <b>Неверный ввод</b>\n\n"
        "📍 Пожалуйста, выберите район из списка кнопок ниже.\n\n"
        "Если вы хотите вернуться назад — нажмите кнопку \"Назад\"."
    )
    await message.answer(text, reply_markup=get_district_keyboard(), parse_mode="HTML")


@router.message(FoundPet.waiting_for_description, F.text)
async def found_description(message: Message, state: FSMContext):
    if await check_banned(message.from_user.id, message): return
    is_ok, reason = moderate_text(message.text)
    if not is_ok:
        await message.answer(f"❌ Ошибка: {reason}. Попробуйте ещё раз.")
        return
    
    await state.update_data(found_description=message.text)
    
    data = await state.get_data()
    preview = (
        "📋 <b>Проверьте анкету</b>\n\n"
        f"📍 <b>Район:</b> {data['district']}\n"
        f"📝 <b>Описание:</b>\n<i>{data['found_description']}</i>\n\n"
        "Всё верно?"
    )
    await message.answer(preview, reply_markup=get_confirm_keyboard(), parse_mode="HTML")
    await state.set_state(FoundPet.waiting_for_confirm)


@router.message(FoundPet.waiting_for_description)
async def found_description_invalid(message: Message):
    text = "⚠️ <b>Неверный формат</b>\n\n✏️ Пожалуйста, введите текстовое описание."
    await message.answer(text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")


@router.callback_query(FoundPet.waiting_for_confirm, F.data == "confirm_ok")
async def found_confirm_ok(callback: CallbackQuery, state: FSMContext):
    if await check_banned(callback.from_user.id, callback): return
    data = await state.get_data()
    app_id = await create_application(
        user_id=callback.from_user.id, app_type="found", pet_name="Неизвестно",
        description=data["found_description"], district=data["district"],
        additional_info="", photo_id=data["photo_id"]
    )
    await add_log(callback.from_user.id, "Создана анкета", f"Тип: found, ID: {app_id}")
    await state.clear()
    
    await notify_admins_about_new_application(app_id, "found", "Неизвестно", data["district"])
    
    text = (
        "✅ <b>Спасибо за помощь!</b>\n\n"
        f"Ваша анкета <b>#{app_id}</b> отправлена на модерацию.\n\n"
        "Мы постараемся быстрее найти хозяина.\n\n"
        "Вы можете вернуться в главное меню или создать ещё одну анкету."
    )
    
    await callback.message.answer(text, reply_markup=get_main_menu(callback.from_user.id), parse_mode="HTML")
    await callback.answer()


@router.callback_query(FoundPet.waiting_for_confirm, F.data == "confirm_edit")
async def found_confirm_edit(callback: CallbackQuery, state: FSMContext):
    if await check_banned(callback.from_user.id, callback): return
    text = "🔍 <b>Я нашёл животное</b>\n\nНачинаем заново.\n\n<b>Шаг 1 из 4</b>\n\n📸 Отправьте фото питомца."
    await safe_send(callback, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")
    await state.set_state(FoundPet.waiting_for_photo)
    await callback.answer()


# ==================== ОТМЕНА И НАЗАД ====================

@router.callback_query(F.data == "cancel")
async def cancel_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if await check_banned(callback.from_user.id, callback): return
    text = "❌ <b>Действие отменено</b>\n\n🏠 Выберите действие:"
    await safe_send(callback, text, reply_markup=get_main_menu(callback.from_user.id), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "step_back")
async def step_back(callback: CallbackQuery, state: FSMContext):
    if await check_banned(callback.from_user.id, callback): return
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


# ==================== ПОМОЩЬ В ПОИСКЕ ====================

@router.callback_query(F.data == "help_search")
async def help_search(callback: CallbackQuery, state: FSMContext):
    if await check_banned(callback.from_user.id, callback): return
    await state.clear()
    await state.update_data(viewed_apps=[])
    text = (
        "🤝 <b>Помочь в поиске</b>\n\n"
        "Спасибо, что хотите помочь!\n"
        "Выберите способ поиска:"
    )
    await safe_send(callback, text, reply_markup=get_help_search_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "help_choose_district")
async def help_choose_district(callback: CallbackQuery, state: FSMContext):
    if await check_banned(callback.from_user.id, callback): return
    await state.update_data(search_mode="district", viewed_apps=[])
    text = "📍 <b>Выбор района</b>\n\nВыберите район Новосибирска:"
    await safe_send(callback, text, reply_markup=get_district_keyboard(), parse_mode="HTML")
    await state.set_state(SwipeStates.choosing_district)
    await callback.answer()


@router.callback_query(F.data == "help_all_city")
async def help_all_city(callback: CallbackQuery, state: FSMContext):
    if await check_banned(callback.from_user.id, callback): return
    await state.update_data(search_mode="city", viewed_apps=[])
    await safe_send(callback, "🔍 Поиск анкет по всему Новосибирску...")
    await show_next_card(callback.message, callback.from_user.id, state)
    await callback.answer()


@router.callback_query(SwipeStates.choosing_district, F.data.startswith("district_"))
async def set_district_swipe(callback: CallbackQuery, state: FSMContext):
    if await check_banned(callback.from_user.id, callback): return
    district = callback.data.replace("district_", "")
    await state.update_data(district=district, search_mode="district", viewed_apps=[])
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET district = ? WHERE user_id = ?", (district, callback.from_user.id))
        await db.commit()
    
    prep_district = get_district_prepositional(district)
    await safe_send(callback, f"🔍 Поиск анкет в {prep_district} районе...", parse_mode="HTML")
    await show_next_card(callback.message, callback.from_user.id, state)
    await callback.answer()


async def show_next_card(message, user_id, state):
    data = await state.get_data()
    search_mode = data.get("search_mode", "district")
    district = data.get("district")
    viewed_apps = data.get("viewed_apps", [])
    
    if search_mode == "city":
        apps = await get_active_applications(limit=100)
        filtered = [a for a in apps if a[1] != user_id and a[0] not in viewed_apps]
        location_text = "Новосибирске"
    else:
        apps = await get_applications_by_status_list("active", limit=100)
        filtered = [a for a in apps if a[5] == district and a[1] != user_id and a[0] not in viewed_apps]
        prep_district = get_district_prepositional(district)
        location_text = f"{prep_district} районе"
    
    if not filtered:
        all_available = [a for a in apps if a[1] != user_id]
        if search_mode == "district":
            all_available = [a for a in all_available if a[5] == district]
        
        if all_available and viewed_apps:
            text = (
                f"✅ <b>Вы просмотрели все анкеты</b>\n\n"
                f"В {location_text} больше нет новых анкет для вас.\n\n"
                f"👀 <b>Просмотрено:</b> {len(viewed_apps)}\n\n"
                "Что хотите сделать?"
            )
            await message.answer(text, reply_markup=get_swipe_end_keyboard(), parse_mode="HTML")
            await state.set_state(SwipeStates.swiping)
            return
        else:
            hint = ""
            if apps and len(apps) > 0:
                own_apps = [a for a in apps if a[1] == user_id]
                if own_apps and len(own_apps) == len(apps):
                    hint = "\n\n💡 <b>Подсказка:</b> Все анкеты в базе — ваши собственные. Попросите кого-то создать анкету."
                elif search_mode == "district":
                    other_districts = [a[5] for a in apps if a[5] != district]
                    if other_districts:
                        hint = f"\n\n💡 <b>Подсказка:</b> В базе есть анкеты, но в других районах: {', '.join(set(other_districts))}.\nПопробуйте поиск по всему городу."
            
            text = f"🔍 <b>Поиск завершён</b>\n\nВ {location_text} пока нет активных анкет.{hint}"
            await message.answer(text, reply_markup=get_help_search_keyboard(), parse_mode="HTML")
            await state.clear()
            return
    
    app = filtered[0]
    app_id = app[0]
    
    viewed_apps.append(app_id)
    await state.update_data(viewed_apps=viewed_apps)
    
    await increment_views(app_id)
    
    type_text = "🐾 Потерялось" if app[2] == "lost" else "🔍 Найдено"
    card = (
        f"📋 <b>Анкета #{app_id}</b>\n\n"
        f"📌 <b>Тип:</b> {type_text}\n"
        f"🏷 <b>Кличка:</b> {app[3]}\n"
        f"📍 <b>Район:</b> {app[5]}\n"
        f"📝 <b>Приметы:</b>\n<i>{app[4]}</i>"
    )
    if app[6]:
        card += f"\n💬 <b>Дополнительная информация:</b>\n<i>{app[6]}</i>"
    
    if app[7]:
        try:
            await message.answer_photo(photo=app[7], caption=card, reply_markup=get_swipe_keyboard(app_id), parse_mode="HTML")
        except Exception:
            await message.answer(card, reply_markup=get_swipe_keyboard(app_id), parse_mode="HTML")
    else:
        await message.answer(card, reply_markup=get_swipe_keyboard(app_id), parse_mode="HTML")
    
    await state.set_state(SwipeStates.swiping)
    await state.update_data(current_app_id=app_id)


@router.callback_query(F.data == "swipe_restart")
async def swipe_restart(callback: CallbackQuery, state: FSMContext):
    if await check_banned(callback.from_user.id, callback): return
    await state.update_data(viewed_apps=[])
    await callback.message.edit_text("🔄 Начинаем просмотр заново...")
    await show_next_card(callback.message, callback.from_user.id, state)
    await callback.answer()


@router.callback_query(F.data == "swipe_finish")
async def swipe_finish(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "✅ <b>Просмотр завершён</b>\n\n"
        "Спасибо, что помогаете искать животных!\n\n"
        "🏠 Выберите действие:"
    )
    await safe_send(callback, text, reply_markup=get_main_menu(callback.from_user.id), parse_mode="HTML")
    await callback.answer()


@router.callback_query(SwipeStates.swiping, F.data.startswith("swipe_skip_"))
async def swipe_skip(callback: CallbackQuery, state: FSMContext):
    if await check_banned(callback.from_user.id, callback): return
    await show_next_card(callback.message, callback.from_user.id, state)
    await callback.answer()


@router.callback_query(SwipeStates.swiping, F.data.startswith("swipe_seen_"))
async def swipe_seen(callback: CallbackQuery, state: FSMContext):
    if await check_banned(callback.from_user.id, callback): return
    text = (
        "👀 <b>Вы видели животное</b>\n\n"
        "Где и когда вы его видели?\n"
        "Напишите адрес или описание."
    )
    await safe_send(callback, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")
    await state.set_state(SwipeStates.writing_response)
    await callback.answer()


@router.message(SwipeStates.writing_response, F.text)
async def write_response(message: Message, state: FSMContext):
    if await check_banned(message.from_user.id, message): return
    data = await state.get_data()
    app = await get_application(data.get("current_app_id"))
    if not app:
        await message.answer("Анкета не найдена.", reply_markup=get_main_menu(message.from_user.id))
        await state.clear()
        return
    
    await add_response(app[0], message.from_user.id, message.text, "")
    await add_log(message.from_user.id, "Отклик", f"Анкета #{app[0]}")
    
    try:
        async with Bot(token=BOT_TOKEN) as bot:
            reporter = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
            text = (
                f"🔔 <b>Отклик на анкету #{app[0]}</b>\n\n"
                f"📍 <b>Место:</b>\n<i>{message.text}</i>\n\n"
                f"👤 <b>От:</b> {reporter}"
            )
            await bot.send_message(app[1], text, parse_mode="HTML")
    except Exception:
        pass
    
    text = "✅ <b>Спасибо!</b>\n\nИнформация отправлена хозяину."
    await state.clear()
    await message.answer(text, reply_markup=get_main_menu(message.from_user.id), parse_mode="HTML")


@router.message(SwipeStates.writing_response)
async def write_response_invalid(message: Message):
    text = "⚠️ <b>Неверный формат</b>\n\n✏️ Пожалуйста, введите текстовое описание."
    await message.answer(text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")


# ==================== МОИ АНКЕТЫ ====================

@router.callback_query(F.data == "my_applications")
async def my_applications(callback: CallbackQuery):
    if await check_banned(callback.from_user.id, callback): return
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM applications WHERE user_id = ? AND status != 'deleted' ORDER BY created_at DESC",
            (callback.from_user.id,)
        ) as cursor:
            apps = await cursor.fetchall()
        
        async with db.execute(
            "SELECT * FROM applications WHERE user_id = ? AND status = 'deleted' ORDER BY created_at DESC",
            (callback.from_user.id,)
        ) as cursor:
            deleted_apps = await cursor.fetchall()
    
    all_apps = list(apps) + list(deleted_apps)
    
    if not all_apps:
        text = "📋 <b>Мои анкеты</b>\n\nУ вас пока нет анкет."
        await safe_send(callback, text, reply_markup=get_main_menu(callback.from_user.id), parse_mode="HTML")
        await callback.answer()
        return
    
    text = "📋 <b>Мои анкеты</b>\n\nНажмите на анкету для управления:"
    await safe_send(callback, text, reply_markup=get_application_list_keyboard(all_apps), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("my_app_manage_"))
async def my_app_manage(callback: CallbackQuery):
    if await check_banned(callback.from_user.id, callback): return
    app_id = int(callback.data.split("_")[-1])
    app = await get_application(app_id)
    if not app:
        await callback.answer("Анкета не найдена", show_alert=True)
        return
    
    status_names = {
        "active": "🟢 Активна",
        "paused": "🟡 На паузе",
        "closed": "🔴 Закрыта (найдено)",
        "moderation": "⏳ На модерации",
        "rejected": "❌ Отклонена",
        "deleted": "🗑 Удалена (хранится 7 дней)"
    }
    
    type_text = "🐾 Потерялось" if app[2] == "lost" else "🔍 Найдено"
    
    text = (
        f"📋 <b>Анкета #{app[0]}</b>\n\n"
        f"📌 <b>Статус:</b> {status_names.get(app[8], app[8])}\n"
        f"📎 <b>Тип:</b> {type_text}\n"
        f"🏷 <b>Кличка:</b> {app[3]}\n"
        f"📍 <b>Район:</b> {app[5]}\n"
        f"📝 <b>Приметы:</b>\n<i>{app[4]}</i>\n\n"
        f"👁 <b>Просмотров:</b> {app[10]}  |  ↩️ <b>Откликов:</b> {app[11]}"
    )
    
    if app[8] == "rejected" and app[9]:
        text += f"\n\n❌ <b>Причина отклонения:</b>\n<i>{app[9]}</i>"
    
    if app[7]:
        try:
            await callback.message.answer_photo(photo=app[7], caption=text, reply_markup=get_application_manage_keyboard(app_id, app[8]), parse_mode="HTML")
        except Exception:
            await callback.message.answer(text, reply_markup=get_application_manage_keyboard(app_id, app[8]), parse_mode="HTML")
    else:
        await callback.message.answer(text, reply_markup=get_application_manage_keyboard(app_id, app[8]), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("app_pause_"))
async def app_pause(callback: CallbackQuery):
    if await check_banned(callback.from_user.id, callback): return
    app_id = int(callback.data.split("_")[-1])
    await update_application_status(app_id, "paused")
    await add_log(callback.from_user.id, "Анкета на паузе", f"#{app_id}")
    await callback.answer("Анкета приостановлена", show_alert=True)
    await my_app_manage(callback)


@router.callback_query(F.data.startswith("app_resume_"))
async def app_resume(callback: CallbackQuery):
    if await check_banned(callback.from_user.id, callback): return
    app_id = int(callback.data.split("_")[-1])
    await update_application_status(app_id, "active")
    await add_log(callback.from_user.id, "Анкета возобновлена", f"#{app_id}")
    await callback.answer("Анкета возобновлена", show_alert=True)
    await my_app_manage(callback)


@router.callback_query(F.data.startswith("app_found_"))
async def app_found(callback: CallbackQuery):
    if await check_banned(callback.from_user.id, callback): return
    app_id = int(callback.data.split("_")[-1])
    await update_application_status(app_id, "closed")
    await add_log(callback.from_user.id, "Животное найдено", f"#{app_id}")
    
    text = (
        "🎉 <b>Поздравляем!</b>\n\n"
        "Животное нашлось! Анкета закрыта.\n\n"
        "Спасибо, что воспользовались нашим сервисом."
    )
    await safe_send(callback, text, reply_markup=get_main_menu(callback.from_user.id), parse_mode="HTML")
    await callback.answer("Поздравляем!", show_alert=True)


@router.callback_query(F.data.startswith("app_delete_"))
async def app_delete(callback: CallbackQuery):
    if await check_banned(callback.from_user.id, callback): return
    app_id = int(callback.data.split("_")[-1])
    await soft_delete_application(app_id)
    await add_log(callback.from_user.id, "Анкета удалена (мягкое)", f"#{app_id}")
    await callback.answer("Анкета удалена. Хранится 7 дней.", show_alert=True)
    await my_applications(callback)


@router.callback_query(F.data.startswith("app_hard_delete_"))
async def app_hard_delete_prompt(callback: CallbackQuery):
    if await check_banned(callback.from_user.id, callback): return
    app_id = int(callback.data.split("_")[-1])
    
    text = (
        "⚠️ <b>Подтверждение удаления</b>\n\n"
        "Вы действительно хотите <b>полностью удалить</b> анкету?\n\n"
        "Это действие <b>необратимо</b>."
    )
    await safe_send(callback, text, reply_markup=get_confirm_delete_keyboard(app_id), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("app_confirm_hard_delete_"))
async def app_confirm_hard_delete(callback: CallbackQuery):
    if await check_banned(callback.from_user.id, callback): return
    app_id = int(callback.data.split("_")[-1])
    await hard_delete_application(app_id)
    await add_log(callback.from_user.id, "Анкета полностью удалена", f"#{app_id}")
    
    text = "🗑 <b>Анкета удалена</b>\n\nАнкета полностью удалена."
    await safe_send(callback, text, reply_markup=get_main_menu(callback.from_user.id), parse_mode="HTML")
    await callback.answer("Удалено", show_alert=True)


# ==================== ПОДДЕРЖКА ====================

@router.callback_query(F.data == "support")
async def support(callback: CallbackQuery, state: FSMContext):
    if await check_banned(callback.from_user.id, callback): return
    text = "💬 <b>Поддержка</b>\n\nВыберите тип обращения:"
    await safe_send(callback, text, reply_markup=get_support_main_keyboard(), parse_mode="HTML")
    await state.set_state(SupportStates.choosing_type)
    await callback.answer()


@router.callback_query(SupportStates.choosing_type, F.data.startswith("support_"))
async def support_type(callback: CallbackQuery, state: FSMContext):
    if await check_banned(callback.from_user.id, callback): return
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


@router.message(SupportStates.choosing_app, F.text)
async def support_app(message: Message, state: FSMContext):
    if await check_banned(message.from_user.id, message): return
    try:
        await state.update_data(app_id=int(message.text))
    except ValueError:
        text = "⚠️ <b>Неверный формат</b>\n\n🔢 Пожалуйста, введите число (ID анкеты)."
        await message.answer(text, parse_mode="HTML")
        return
    await message.answer("Опишите причину жалобы:", reply_markup=get_cancel_only_keyboard())
    await state.set_state(SupportStates.writing_message)


@router.message(SupportStates.choosing_app)
async def support_app_invalid(message: Message):
    text = "⚠️ <b>Неверный формат</b>\n\n🔢 Пожалуйста, введите число (ID анкеты)."
    await message.answer(text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")


@router.message(SupportStates.writing_message, F.text)
async def support_message(message: Message, state: FSMContext):
    if await check_banned(message.from_user.id, message): return
    data = await state.get_data()
    if data.get("support_type") == "complaint":
        complaint_id = await add_complaint(data.get("app_id"), message.from_user.id, message.text)
        await add_log(message.from_user.id, "Жалоба", f"Анкета #{data.get('app_id')}")
        
        app = await get_application(data.get("app_id"))
        app_info = f"#{data.get('app_id')} ({app[3]})" if app else f"#{data.get('app_id')}"
        admin_text = (
            f"⚠️ <b>Новая жалоба #{complaint_id}</b>\n\n"
            f"📋 <b>Анкета:</b> {app_info}\n"
            f"👤 <b>От:</b> <code>{message.from_user.id}</code>\n"
            f"📝 <b>Причина:</b>\n<i>{message.text}</i>\n\n"
            "Требуется проверка."
        )
        for admin_id in ADMIN_IDS:
            try:
                async with Bot(token=BOT_TOKEN) as bot:
                    await bot.send_message(
                        admin_id, admin_text,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="📋 Рассмотреть жалобу", callback_data=f"admin_complaint_view_{complaint_id}")]
                        ]),
                        parse_mode="HTML"
                    )
            except Exception:
                pass
    else:
        try:
            async with Bot(token=BOT_TOKEN) as bot:
                await bot.send_message(ADMIN_IDS[0], f"Обращение ({data.get('support_type')}):\nОт: {message.from_user.id}\n\n{message.text}")
        except Exception:
            pass
        await add_log(message.from_user.id, "Обращение", data.get("support_type"))
    
    text = "✅ <b>Обращение отправлено</b>\n\nСпасибо! Мы рассмотрим ваше обращение."
    await state.clear()
    await message.answer(text, reply_markup=get_main_menu(message.from_user.id), parse_mode="HTML")


@router.message(SupportStates.writing_message)
async def support_message_invalid(message: Message):
    text = "⚠️ <b>Неверный формат</b>\n\n✏️ Пожалуйста, введите текстовое описание."
    await message.answer(text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")


# ==================== НАСТРОЙКИ ====================

@router.message(Command("set_district"))
async def set_district_cmd(message: Message, state: FSMContext):
    if await check_banned(message.from_user.id, message): return
    text = "📍 <b>Смена района</b>\n\nВыберите ваш район:"
    await message.answer(text, reply_markup=get_district_keyboard(), parse_mode="HTML")
    await state.set_state(SwipeStates.choosing_district)
    await state.update_data(search_mode="settings")


@router.callback_query(SwipeStates.choosing_district, F.data.startswith("district_"))
async def save_district_settings(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("search_mode") != "settings": return
    
    if await check_banned(callback.from_user.id, callback): return
    district = callback.data.replace("district_", "")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET district = ? WHERE user_id = ?", (district, callback.from_user.id))
        await db.commit()
    await state.clear()
    
    text = f"✅ <b>Район изменён</b>\n\n📍 Ваш район: <b>{district}</b>"
    await safe_send(callback, text, reply_markup=get_main_menu(callback.from_user.id), parse_mode="HTML")
    await callback.answer()


@router.message(Command("delete_my_data"))
async def delete_my_data_cmd(message: Message):
    if await check_banned(message.from_user.id, message): return
    await delete_user_data(message.from_user.id)
    await add_log(message.from_user.id, "Удалил свои данные")
    
    text = "🗑 <b>Данные удалены</b>\n\nВсе ваши данные удалены.\nНажмите /start для начала."
    await message.answer(text, parse_mode="HTML")


# ==================== УВЕДОМЛЕНИЯ О НОВЫХ АНКЕТАХ ====================

@router.callback_query(F.data.startswith("notify_show_"))
async def notify_show(callback: CallbackQuery, state: FSMContext):
    if await check_banned(callback.from_user.id, callback): return
    app_id = int(callback.data.split("_")[-1])
    
    await state.clear()
    await state.update_data(search_mode="city", viewed_apps=[])
    
    app = await get_application(app_id)
    if app:
        await callback.message.edit_text(f"📋 Анкета #{app_id}", parse_mode="HTML")
        await state.update_data(current_app_id=app_id)
        await state.set_state(SwipeStates.swiping)
        
        type_text = "🐾 Потерялось" if app[2] == "lost" else "🔍 Найдено"
        card = (
            f"📋 <b>Анкета #{app[0]}</b>\n\n"
            f"📌 <b>Тип:</b> {type_text}\n"
            f"🏷 <b>Кличка:</b> {app[3]}\n"
            f"📍 <b>Район:</b> {app[5]}\n"
            f"📝 <b>Приметы:</b>\n<i>{app[4]}</i>"
        )
        if app[6]: card += f"\n💬 <b>Дополнительная информация:</b>\n<i>{app[6]}</i>"
        
        if app[7]:
            try:
                await callback.message.answer_photo(photo=app[7], caption=card, reply_markup=get_swipe_keyboard(app[0]), parse_mode="HTML")
            except Exception:
                await callback.message.answer(card, reply_markup=get_swipe_keyboard(app[0]), parse_mode="HTML")
        else:
            await callback.message.answer(card, reply_markup=get_swipe_keyboard(app[0]), parse_mode="HTML")
            
    await callback.answer()


@router.callback_query(F.data == "notify_skip")
async def notify_skip(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer("Пропущено")


# ==================== ОБРАБОТКА ЛЮБЫХ ДРУГИХ СООБЩЕНИЙ ====================

@router.message()
async def catch_all(message: Message, state: FSMContext):
    if await check_banned(message.from_user.id, message): return
    
    current_state = await state.get_state()
    if current_state:
        text = (
            "⚠️ <b>Неверный ввод</b>\n\n"
            "Пожалуйста, следуйте инструкциям на экране.\n\n"
            "Если вы хотите отменить действие — нажмите кнопку \"Отмена\".\n"
            "Если хотите вернуться назад — нажмите кнопку \"Назад\"."
        )
        await message.answer(text, parse_mode="HTML")
        return
    
    text = (
        "🤔 <b>Не понял вас</b>\n\n"
        "Воспользуйтесь кнопками меню ниже.\n\n"
        "Если меню пропало — нажмите /start"
    )
    await message.answer(text, reply_markup=get_main_menu(message.from_user.id), parse_mode="HTML")
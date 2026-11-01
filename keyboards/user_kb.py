from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import ADMIN_IDS

def get_main_menu(user_id: int, in_admin_mode: bool = False):
    is_admin = user_id in ADMIN_IDS
    keyboard = [
        [InlineKeyboardButton(text="🐾 Я потерял животное", callback_data="lost_pet")],
        [InlineKeyboardButton(text="🔎 Я нашёл животное", callback_data="found_pet")],
        [InlineKeyboardButton(text="🤝 Помочь в поиске", callback_data="help_search")],
        [InlineKeyboardButton(text="📋 Мои анкеты", callback_data="my_applications")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="open_settings")],
        [InlineKeyboardButton(text="💬 Поддержка", callback_data="support")]
    ]
    
    if is_admin:
        if in_admin_mode:
            keyboard.append([InlineKeyboardButton(text="👤 Выйти в режим пользователя", callback_data="admin_exit_mode")])
        else:
            keyboard.append([InlineKeyboardButton(text="🛠 Войти в режим администратора", callback_data="admin_enter_mode")])
            
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_cancel_only_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

def get_back_cancel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="step_back"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
        ]
    ])

def get_confirm_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Правильно", callback_data="confirm_ok"),
            InlineKeyboardButton(text="✏️ Внести изменения", callback_data="confirm_edit")
        ]
    ])

def get_district_keyboard():
    from database.db import NOVOSIBIRSK_DISTRICTS
    keyboard = []
    for i in range(0, len(NOVOSIBIRSK_DISTRICTS), 2):
        row = [InlineKeyboardButton(text=NOVOSIBIRSK_DISTRICTS[i], callback_data=f"district_{NOVOSIBIRSK_DISTRICTS[i]}")]
        if i + 1 < len(NOVOSIBIRSK_DISTRICTS):
            row.append(InlineKeyboardButton(text=NOVOSIBIRSK_DISTRICTS[i+1], callback_data=f"district_{NOVOSIBIRSK_DISTRICTS[i+1]}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_swipe_keyboard(app_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❌ Не видел", callback_data=f"swipe_skip_{app_id}"),
            InlineKeyboardButton(text="✅ Видел", callback_data=f"swipe_seen_{app_id}")
        ],
        [InlineKeyboardButton(text="🏠 Завершить просмотр", callback_data="swipe_finish")]
    ])

def get_swipe_end_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Начать заново", callback_data="swipe_restart"),
            InlineKeyboardButton(text="🏠 Завершить", callback_data="swipe_finish")
        ]
    ])

def get_application_list_keyboard(apps):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for app in apps:
        status_emoji = {
            "active": "🟢", "paused": "🟡", "closed": "🔴", 
            "moderation": "⏳", "rejected": "❌", "deleted": "🗑"
        }
        status = status_emoji.get(app[8], "?")
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=f"{status} #{app[0]} {app[3]}", callback_data=f"my_app_manage_{app[0]}")
        ])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu_back")])
    return keyboard

def get_application_manage_keyboard(app_id: int, status: str):
    keyboard = []
    if status == "active":
        keyboard.append([InlineKeyboardButton(text="⏸ Поставить на паузу", callback_data=f"app_pause_{app_id}")])
    elif status == "paused":
        keyboard.append([InlineKeyboardButton(text="▶️ Возобновить", callback_data=f"app_resume_{app_id}")])
    
    if status in ["active", "paused"]:
        keyboard.append([InlineKeyboardButton(text="✅ Животное найдено", callback_data=f"app_found_{app_id}")])
        keyboard.append([InlineKeyboardButton(text="🗑 Удалить анкету", callback_data=f"app_delete_{app_id}")])
    
    if status == "deleted":
        keyboard.append([InlineKeyboardButton(text="🗑 Удалить навсегда", callback_data=f"app_hard_delete_{app_id}")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад к списку", callback_data="my_applications")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_confirm_delete_keyboard(app_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"my_app_manage_{app_id}"),
            InlineKeyboardButton(text="🗑 Удалить навсегда", callback_data=f"app_confirm_hard_delete_{app_id}")
        ]
    ])

def get_support_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🐛 Появилась ошибка", callback_data="support_bug")],
        [InlineKeyboardButton(text="⚠️ Пожаловаться на анкету", callback_data="support_complaint")],
        [InlineKeyboardButton(text="💡 Предложить идею", callback_data="support_idea")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu_back")]
    ])

def get_help_search_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 Выбрать район", callback_data="help_choose_district")],
        [InlineKeyboardButton(text="🏙 Помощь по всему городу", callback_data="help_all_city")],
        [InlineKeyboardButton(text="🔙 Назад в главное меню", callback_data="main_menu_back")]
    ])

def get_settings_keyboard(current_mode: str):
    def check(mode): return "✅ " if current_mode == mode else "○ "
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{check('district')}Только мой район", callback_data="set_notif_district")],
        [InlineKeyboardButton(text=f"{check('city')}Со всего Новосибирска", callback_data="set_notif_city")],
        [InlineKeyboardButton(text=f"{check('none')}Отключить уведомления", callback_data="set_notif_none")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu_back")]
    ])
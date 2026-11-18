from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from domain.districts import NOVOSIBIRSK_DISTRICTS
from domain.models import Application


def get_main_menu(*, in_admin_mode: bool = False, is_admin: bool = False):
    keyboard = [
        [InlineKeyboardButton(text="🐾 Я потерял животное", callback_data="lost_pet")],
        [InlineKeyboardButton(text="🔎 Я нашёл животное", callback_data="found_pet")],
        [InlineKeyboardButton(text="🤝 Помочь в поиске", callback_data="help_search")],
        [InlineKeyboardButton(text="📋 Мои анкеты", callback_data="my_applications")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="open_settings")],
        [InlineKeyboardButton(text="💬 Поддержка", callback_data="support")],
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
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
        ]
    ])


def get_confirm_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Правильно", callback_data="confirm_ok"),
            InlineKeyboardButton(text="✏️ Внести изменения", callback_data="confirm_edit"),
        ]
    ])


def get_district_keyboard(*, include_back: bool = False):
    keyboard = [[InlineKeyboardButton(text="📍 Не знаю, подскажите мне", callback_data="detect_district")]]
    for i in range(0, len(NOVOSIBIRSK_DISTRICTS), 2):
        row = [InlineKeyboardButton(text=NOVOSIBIRSK_DISTRICTS[i], callback_data=f"district_{NOVOSIBIRSK_DISTRICTS[i]}")]
        if i + 1 < len(NOVOSIBIRSK_DISTRICTS):
            row.append(InlineKeyboardButton(text=NOVOSIBIRSK_DISTRICTS[i + 1], callback_data=f"district_{NOVOSIBIRSK_DISTRICTS[i + 1]}"))
        keyboard.append(row)
    if include_back:
        keyboard.append([
            InlineKeyboardButton(text="◀️ Назад", callback_data="step_back"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
        ])
    else:
        keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_swipe_keyboard(app_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❌ Не видел", callback_data=f"swipe_skip_{app_id}"),
            InlineKeyboardButton(text="✅ Видел", callback_data=f"swipe_seen_{app_id}"),
        ],
        [InlineKeyboardButton(text="🏠 Завершить просмотр", callback_data="swipe_finish")],
    ])


def get_swipe_end_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Начать заново", callback_data="swipe_restart"),
            InlineKeyboardButton(text="🏠 Завершить", callback_data="swipe_finish"),
        ]
    ])


def get_application_list_keyboard(apps: list[Application], page: int = 0, page_size: int = 15):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    total_pages = max(1, (len(apps) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    status_emoji = {
        "active": "🟢", "paused": "🟡", "closed": "🔴",
        "moderation": "⏳", "rejected": "❌", "deleted": "🗑",
    }
    for app in apps[page * page_size : (page + 1) * page_size]:
        status = status_emoji.get(app.status, "?")
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=f"{status} #{app.id} {app.pet_name}", callback_data=f"my_app_manage_{app.id}")
        ])
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text=f"⬅️ Стр. {page}", callback_data=f"my_apps_page_{page - 1}"))
        if page + 1 < total_pages:
            nav.append(InlineKeyboardButton(text=f"Стр. {page + 2}/{total_pages} ➡️", callback_data=f"my_apps_page_{page + 1}"))
        if nav:
            keyboard.inline_keyboard.append(nav)
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
            InlineKeyboardButton(text="🗑 Удалить навсегда", callback_data=f"app_confirm_hard_delete_{app_id}"),
        ]
    ])


def get_support_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🐛 Появилась ошибка", callback_data="support_bug")],
        [InlineKeyboardButton(text="⚠️ Пожаловаться на анкету", callback_data="support_complaint")],
        [InlineKeyboardButton(text="💡 Предложить идею", callback_data="support_idea")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu_back")],
    ])


def get_help_search_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 Выбрать район", callback_data="help_choose_district")],
        [InlineKeyboardButton(text="🏙 Помощь по всему городу", callback_data="help_all_city")],
        [InlineKeyboardButton(text="🔙 Назад в главное меню", callback_data="main_menu_back")],
    ])


def get_settings_keyboard(current_mode: str):
    def button(mode, text):
        selected = current_mode == mode
        return InlineKeyboardButton(
            text=f"{'●' if selected else '○'} {text}",
            callback_data=f"set_notif_{mode}",
            style="primary" if selected else None,
        )

    return InlineKeyboardMarkup(inline_keyboard=[
        [button("district", "Только мой район")],
        [button("city", "Со всего Новосибирска")],
        [button("none", "Отключить уведомления")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu_back")],
    ])

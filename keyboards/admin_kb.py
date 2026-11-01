from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_admin_menu():
    """Главное меню админки"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="Анкеты", callback_data="admin_apps_menu")],
        [InlineKeyboardButton(text="Пользователи", callback_data="admin_users_menu")],
        [InlineKeyboardButton(text="Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="Логи", callback_data="admin_logs")]
    ])
    return keyboard


def get_admin_apps_menu():
    """Меню раздела Анкеты"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="На модерации", callback_data="admin_apps_moderation")],
        [InlineKeyboardButton(text="Активные", callback_data="admin_apps_active")],
        [InlineKeyboardButton(text="Закрытые", callback_data="admin_apps_closed")],
        [InlineKeyboardButton(text="Жалобы", callback_data="admin_complaints")],
        [InlineKeyboardButton(text="Назад", callback_data="admin_back")]
    ])
    return keyboard


def get_admin_users_menu():
    """Меню раздела Пользователи"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Все пользователи", callback_data="admin_users_all")],
        [InlineKeyboardButton(text="Забаненные", callback_data="admin_users_banned")],
        [InlineKeyboardButton(text="Назад", callback_data="admin_back")]
    ])
    return keyboard


def get_app_action_keyboard(app_id: int, status: str):
    """Клавиатура действий с анкетой в админке"""
    buttons = []
    
    if status == "moderation":
        buttons.append([
            InlineKeyboardButton(text="Одобрить", callback_data=f"adm_approve_{app_id}"),
            InlineKeyboardButton(text="Отклонить", callback_data=f"adm_reject_{app_id}")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="Удалить", callback_data=f"adm_delete_{app_id}"),
        InlineKeyboardButton(text="Забанить автора", callback_data=f"adm_ban_{app_id}")
    ])
    
    buttons.append([
        InlineKeyboardButton(text="Написать автору", callback_data=f"adm_write_{app_id}")
    ])
    
    buttons.append([
        InlineKeyboardButton(text="Назад", callback_data="admin_apps_menu")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_user_action_keyboard(user_id: int):
    """Клавиатура действий с пользователем в админке"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Забанить", callback_data=f"adm_userban_{user_id}"),
            InlineKeyboardButton(text="Разбанить", callback_data=f"adm_userunban_{user_id}")
        ],
        [InlineKeyboardButton(text="Написать сообщение", callback_data=f"adm_userwrite_{user_id}")],
        [InlineKeyboardButton(text="Его анкеты", callback_data=f"adm_userapps_{user_id}")],
        [InlineKeyboardButton(text="Назад", callback_data="admin_users_menu")]
    ])
    return keyboard


def get_complaint_action_keyboard(complaint_id: int, app_id: int):
    """Клавиатура действий с жалобой"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Подтвердить", callback_data=f"adm_complaint_confirm_{complaint_id}_{app_id}"),
            InlineKeyboardButton(text="Отклонить", callback_data=f"adm_complaint_reject_{complaint_id}")
        ],
        [InlineKeyboardButton(text="Посмотреть анкету", callback_data=f"adm_viewapp_{app_id}")],
        [InlineKeyboardButton(text="Назад", callback_data="admin_complaints")]
    ])
    return keyboard


def get_broadcast_keyboard():
    """Клавиатура рассылки"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Всем", callback_data="broadcast_all")],
        [InlineKeyboardButton(text="Только хозяевам", callback_data="broadcast_owners")],
        [InlineKeyboardButton(text="Только волонтёрам", callback_data="broadcast_volunteers")],
        [InlineKeyboardButton(text="Отмена", callback_data="admin_back")]
    ])
    return keyboard


def get_pagination_keyboard(prefix: str, page: int, total_pages: int):
    """Клавиатура пагинации"""
    buttons = []
    row = []
    
    if page > 1:
        row.append(InlineKeyboardButton(text="<", callback_data=f"{prefix}_page_{page-1}"))
    else:
        row.append(InlineKeyboardButton(text=" ", callback_data="noop"))
    
    row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    
    if page < total_pages:
        row.append(InlineKeyboardButton(text=">", callback_data=f"{prefix}_page_{page+1}"))
    else:
        row.append(InlineKeyboardButton(text=" ", callback_data="noop"))
    
    buttons.append(row)
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="admin_apps_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from domain.errors import DomainError
from domain.models import ApplicationStatus, ComplaintStatus
from handlers.common import IsAdmin, callback_id, main_menu
from handlers.states import AdminBanStates
from keyboards.user_kb import get_cancel_only_keyboard
from presentation.cards import application_card, format_date
from services.container import Services
from utils.messages import REASON_LIMIT, h, safe_send, send_photo_text, send_text, validate_text


def back_keyboard(callback="admin_enter_mode"):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data=callback)]])


async def admin_enter_mode(callback: CallbackQuery, services: Services):
    stats = await services.moderation.dashboard(callback.from_user.id)
    pending = stats.applications.get(ApplicationStatus.MODERATION, 0)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📋 Модерация анкет ({pending})", callback_data="admin_moderation_list")],
        [InlineKeyboardButton(text=f"⚠️ Жалобы ({stats.pending_complaints})", callback_data="admin_complaints_list")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users_list")],
        [InlineKeyboardButton(text="📜 Логирование", callback_data="admin_logs")],
        [InlineKeyboardButton(text="👤 Выйти в режим пользователя", callback_data="admin_exit_mode")],
    ])
    await safe_send(callback, f"🛠 <b>Режим администратора</b>\n\n📋 Анкет на модерации: <b>{pending}</b>\n⚠️ Жалоб в очереди: <b>{stats.pending_complaints}</b>\n\nВыберите раздел:", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


async def admin_exit_mode(callback: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    await safe_send(callback, "✅ Вы вернулись в обычный режим.", reply_markup=main_menu(services, callback.from_user.id))
    await callback.answer()


async def admin_moderation_list(callback: CallbackQuery, services: Services):
    applications = await services.moderation.list_applications(callback.from_user.id)
    rows = [[InlineKeyboardButton(text=f"#{app.id} — {app.pet_name} ({app.district})", callback_data=f"admin_moderate_{app.id}")] for app in applications]
    rows.extend(back_keyboard().inline_keyboard)
    text = "📋 <b>Анкеты на модерации</b>" if applications else "📋 <b>Модерация анкет</b>\n\n✅ Нет анкет на модерации."
    await safe_send(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await callback.answer()


async def admin_moderate(callback: CallbackQuery, services: Services):
    app = await services.moderation.application(callback.from_user.id, callback_id(callback))
    rows = []
    if app.status == ApplicationStatus.MODERATION:
        rows.append([
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"admin_approve_{app.id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_reject_{app.id}"),
        ])
    rows.append([InlineKeyboardButton(text="🚫 Забанить автора", callback_data=f"admin_ban_user_{app.user_id}")])
    rows.extend(back_keyboard("admin_moderation_list").inline_keyboard)
    await send_photo_text(callback.message, app.photo_id, application_card(app, moderator=True), InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


async def admin_approve(callback: CallbackQuery, services: Services):
    await services.moderation.approve(callback.from_user.id, callback_id(callback))
    await admin_moderation_list(callback, services)


async def admin_reject_prompt(callback: CallbackQuery, state: FSMContext, services: Services):
    app = await services.moderation.application(callback.from_user.id, callback_id(callback))
    if app.status != ApplicationStatus.MODERATION:
        raise DomainError("Анкета уже обработана или удалена")
    await state.set_data({"reject_app_id": app.id, "action": "reject"})
    await state.set_state(AdminBanStates.waiting_for_reason)
    await send_text(callback.message.answer, f"❌ <b>Отклонение анкеты #{app.id}</b>\n\nУкажите причину отклонения (она будет отправлена автору):", reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")
    await callback.answer()


async def admin_ban_prompt(callback: CallbackQuery, state: FSMContext, services: Services):
    user_id = callback_id(callback)
    await services.moderation.user_detail(callback.from_user.id, user_id)
    await state.set_data({"ban_target_user_id": user_id, "action": "ban"})
    await state.set_state(AdminBanStates.waiting_for_reason)
    await send_text(callback.message.answer, f"🚫 <b>Блокировка пользователя</b>\n\nID: <code>{user_id}</code>\n\nУкажите причину блокировки:", reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")
    await callback.answer()


async def process_reason_input(message: Message, state: FSMContext, services: Services):
    if not await validate_text(message, REASON_LIMIT):
        return
    data = await state.get_data()
    if data.get("action") == "reject":
        await services.moderation.reject(message.from_user.id, data["reject_app_id"], message.text)
        text = f"✅ Анкета #{data['reject_app_id']} отклонена"
    elif data.get("action") == "ban":
        await services.moderation.set_ban(message.from_user.id, data["ban_target_user_id"], True, message.text)
        text = f"✅ Пользователь {data['ban_target_user_id']} заблокирован"
    else:
        raise DomainError("Действие устарело. Откройте админку заново.")
    await state.clear()
    await send_text(message.answer, text, reply_markup=main_menu(services, message.from_user.id, in_admin_mode=True))


async def admin_complaints_list(callback: CallbackQuery, services: Services):
    complaints = await services.moderation.list_complaints(callback.from_user.id)
    rows = []
    for complaint in complaints:
        status = "⏳" if complaint.status == ComplaintStatus.PENDING else "✅" if complaint.status == ComplaintStatus.CONFIRMED else "❌"
        rows.append([InlineKeyboardButton(text=f"{status} #{complaint.id} — {complaint.application_name or 'анкета удалена'} (от {complaint.reporter_id})", callback_data=f"admin_complaint_view_{complaint.id}")])
    rows.extend(back_keyboard().inline_keyboard)
    await safe_send(callback, "⚠️ <b>Жалобы</b>" if complaints else "⚠️ <b>Жалобы</b>\n\n✅ Жалоб нет.", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await callback.answer()


async def admin_complaint_view(callback: CallbackQuery, services: Services):
    complaint = await services.moderation.complaint(callback.from_user.id, callback_id(callback))
    statuses = {ComplaintStatus.PENDING: "⏳ На рассмотрении", ComplaintStatus.CONFIRMED: "✅ Подтверждена", ComplaintStatus.REJECTED: "❌ Отклонена"}
    text = (f"⚠️ <b>Жалоба #{complaint.id}</b>\n\n📋 <b>Анкета:</b> #{complaint.application_id} ({h(complaint.application_name or 'удалена')})\n"
            f"📍 <b>Район:</b> {h(complaint.district or 'неизвестно')}\n👤 <b>Автор анкеты:</b> <code>{complaint.author_id or 'неизвестно'}</code>\n\n"
            f"🚨 <b>Жалобу подал:</b> <code>{complaint.reporter_id}</code>\n🕐 <b>Время:</b> {h(format_date(complaint.created_at))}\n\n"
            f"📝 <b>Причина:</b>\n<i>{h(complaint.reason)}</i>\n\n📌 <b>Статус:</b> {statuses[complaint.status]}")
    rows = []
    if complaint.status == ComplaintStatus.PENDING:
        rows.append([
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_complaint_confirm_{complaint.id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_complaint_reject_{complaint.id}"),
        ])
        if complaint.author_id is not None:
            rows.append([InlineKeyboardButton(text="🚫 Забанить автора анкеты", callback_data=f"admin_ban_user_{complaint.author_id}")])
    rows.extend(back_keyboard("admin_complaints_list").inline_keyboard)
    await safe_send(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await callback.answer()


async def admin_complaint_confirm(callback: CallbackQuery, services: Services):
    await services.moderation.resolve_complaint(callback.from_user.id, callback_id(callback), True)
    await admin_complaints_list(callback, services)


async def admin_complaint_reject(callback: CallbackQuery, services: Services):
    await services.moderation.resolve_complaint(callback.from_user.id, callback_id(callback), False)
    await admin_complaints_list(callback, services)


async def admin_stats(callback: CallbackQuery, services: Services):
    stats = await services.moderation.dashboard(callback.from_user.id)
    total = sum(count for status, count in stats.applications.items() if status != ApplicationStatus.DELETED)
    text = (f"📊 <b>Статистика бота</b>\n\n👥 <b>Пользователи:</b> {stats.users}\n🚫 Забанено: {stats.banned_users}\n\n"
            f"📋 <b>Анкеты:</b> {total}\n🟢 Активных: {stats.applications.get(ApplicationStatus.ACTIVE, 0)}\n"
            f"⏳ На модерации: {stats.applications.get(ApplicationStatus.MODERATION, 0)}\n🔴 Закрытых: {stats.applications.get(ApplicationStatus.CLOSED, 0)}\n\n"
            f"⚠️ Жалоб в очереди: {stats.pending_complaints}\n\n🔔 Уведомлений в очереди: {stats.pending_notifications}\n❌ Ошибок доставки: {stats.failed_notifications}")
    await safe_send(callback, text, reply_markup=back_keyboard(), parse_mode="HTML")
    await callback.answer()


async def admin_users_list(callback: CallbackQuery, services: Services):
    users = await services.moderation.list_users(callback.from_user.id)
    rows = [[InlineKeyboardButton(text=f"{'🚫' if user.is_banned else '✅'} {user.id} | {user.display_name} | {user.district or 'не указан'}", callback_data=f"admin_user_detail_{user.id}")] for user in users]
    rows.extend(back_keyboard().inline_keyboard)
    await safe_send(callback, "👥 <b>Пользователи</b> (первые 20)" if users else "👥 Пользователей пока нет.", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await callback.answer()


async def admin_user_detail(callback: CallbackQuery, services: Services):
    user, count = await services.moderation.user_detail(callback.from_user.id, callback_id(callback))
    text = (f"👤 <b>Пользователь {user.id}</b>\n\n📛 <b>Имя:</b> {h(user.display_name)}\n📍 <b>Район:</b> {h(user.district or 'не указан')}\n"
            f"📌 <b>Статус:</b> {'🚫 Заблокирован' if user.is_banned else '✅ Активен'}\n📋 <b>Причина бана:</b> {h(user.ban_reason or 'нет')}\n📋 <b>Анкет:</b> {count}")
    button = InlineKeyboardButton(text="✅ Разблокировать" if user.is_banned else "🚫 Заблокировать", callback_data=f"admin_unban_{user.id}" if user.is_banned else f"admin_ban_prompt_{user.id}")
    await safe_send(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[button], *back_keyboard("admin_users_list").inline_keyboard]), parse_mode="HTML")
    await callback.answer()


async def admin_unban(callback: CallbackQuery, services: Services):
    await services.moderation.set_ban(callback.from_user.id, callback_id(callback), False)
    await admin_user_detail(callback, services)


async def admin_logs(callback: CallbackQuery, services: Services):
    entries = await services.moderation.logs(callback.from_user.id)
    text = "📜 <b>Последние действия</b>\n\n"
    text += "\n\n".join(f"🕐 <code>{h(format_date(entry.created_at))}</code>\n{h(entry.action)} — <i>{h(entry.details)}</i>" for entry in entries) if entries else "<i>Логи пусты.</i>"
    await safe_send(callback, text, reply_markup=back_keyboard(), parse_mode="HTML")
    await callback.answer()


def create_router() -> Router:
    router = Router(name="moderation")
    router.callback_query.filter(IsAdmin())
    router.message.filter(IsAdmin())
    for value, handler in {
        "admin_enter_mode": admin_enter_mode, "admin_exit_mode": admin_exit_mode,
        "admin_moderation_list": admin_moderation_list, "admin_complaints_list": admin_complaints_list,
        "admin_stats": admin_stats, "admin_users_list": admin_users_list, "admin_logs": admin_logs,
    }.items():
        router.callback_query.register(handler, F.data == value)
    for prefix, handler in {
        "admin_moderate_": admin_moderate, "admin_approve_": admin_approve, "admin_reject_": admin_reject_prompt,
        "admin_ban_user_": admin_ban_prompt, "admin_ban_prompt_": admin_ban_prompt,
        "admin_complaint_view_": admin_complaint_view, "admin_complaint_confirm_": admin_complaint_confirm,
        "admin_complaint_reject_": admin_complaint_reject, "admin_user_detail_": admin_user_detail,
        "admin_unban_": admin_unban,
    }.items():
        router.callback_query.register(handler, F.data.startswith(prefix))
    router.message.register(process_reason_input, AdminBanStates.waiting_for_reason)
    return router

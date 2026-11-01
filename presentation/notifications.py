from dataclasses import dataclass

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from domain.districts import get_district_prepositional
from domain.models import Notification, NotificationKind
from settings import Settings
from utils.messages import h


@dataclass(frozen=True)
class RenderedNotification:
    text: str
    keyboard: InlineKeyboardMarkup | None = None


def _keyboard(label, callback):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=callback)]])


def render_notification(notification: Notification, settings: Settings) -> RenderedNotification:
    data = notification.payload
    kind = notification.kind
    app_id = data.get("application_id")
    if kind == NotificationKind.SUBMITTED:
        app_kind = "🐾 Потерялось" if data["kind"] == "lost" else "🔍 Найдено"
        return RenderedNotification(
            f"🆕 <b>Новая анкета #{app_id}</b>\n\n📋 <b>Тип:</b> {app_kind}\n"
            f"🏷 <b>Кличка:</b> {h(data['pet_name'])}\n📍 <b>Район:</b> {h(data['district'])}\n\n⏳ Требуется модерация.",
            _keyboard("📋 Перейти к модерации", f"admin_moderate_{app_id}"),
        )
    if kind == NotificationKind.APPROVED:
        return RenderedNotification(f"✅ <b>Анкета #{app_id} одобрена</b>\n\nВаша анкета опубликована и теперь видна волонтёрам.")
    if kind == NotificationKind.PUBLISHED:
        district = h(get_district_prepositional(data["district"]))
        app_kind = "🐾 Потерялось" if data["kind"] == "lost" else "🔍 Найдено"
        return RenderedNotification(
            f"🆕 <b>Новая анкета в {district} районе!</b>\n\n📋 <b>Тип:</b> {app_kind}\n"
            f"🏷 <b>Кличка:</b> {h(data['pet_name'])}\n\nВозможно, вы знаете, где это животное?",
            InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="👀 Показать", callback_data=f"notify_show_{app_id}"),
                InlineKeyboardButton(text="⏭ Пропустить", callback_data="notify_skip"),
            ]]),
        )
    if kind == NotificationKind.REJECTED:
        return RenderedNotification(f"❌ <b>Анкета #{app_id} отклонена</b>\n\n📋 <b>Причина:</b> {h(data['reason'])}\n\nВы можете создать новую анкету с учётом замечаний.")
    if kind == NotificationKind.BANNED:
        return RenderedNotification(
            "🚫 <b>Доступ ограничен</b>\n\nВы были заблокированы по решению администратора.\n\n"
            f"📋 <b>Причина:</b> {h(data['reason'])}\n\nДля разблокировки свяжитесь с администратором.",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 Связаться с администратором", url=settings.support_url)]]),
        )
    if kind == NotificationKind.UNBANNED:
        return RenderedNotification("✅ <b>Вы были разблокированы</b>\n\nДобро пожаловать!")
    if kind == NotificationKind.RESPONSE:
        return RenderedNotification(f"🔔 <b>Отклик на анкету #{app_id}</b>\n\n📍 <b>Место:</b>\n<i>{h(data['location'])}</i>\n\n👤 <b>От:</b> {h(data['reporter'])}")
    if kind == NotificationKind.COMPLAINT:
        complaint_id = data["complaint_id"]
        return RenderedNotification(
            f"⚠️ <b>Новая жалоба #{complaint_id}</b>\n\n📋 <b>Анкета:</b> #{app_id} ({h(data['application_name'])})\n"
            f"👤 <b>От:</b> <code>{data['reporter_id']}</code>\n📝 <b>Причина:</b>\n<i>{h(data['reason'])}</i>\n\nТребуется проверка.",
            _keyboard("📋 Рассмотреть жалобу", f"admin_complaint_view_{complaint_id}"),
        )
    if kind == NotificationKind.SUPPORT:
        return RenderedNotification(f"💬 <b>Обращение ({h(data['category'])})</b>\nОт: <code>{data['reporter_id']}</code>\n\n{h(data['text'])}")
    if kind == NotificationKind.REMINDER:
        return RenderedNotification(
            f"Напоминание об анкете #{app_id}\n\nПрошла неделя с момента публикации анкеты «{h(data['pet_name'])}».\n"
            "Удалось ли найти питомца?\n\nЕсли животное нашлось, пожалуйста, закройте анкету в разделе «Мои анкеты», чтобы волонтёры не тратили время зря."
        )
    raise ValueError(f"Unsupported notification kind: {kind}")

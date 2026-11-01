from domain.models import Application, ApplicationKind, ApplicationStatus
from utils.messages import h


STATUS_LABELS = {
    ApplicationStatus.ACTIVE: "🟢 Активна",
    ApplicationStatus.PAUSED: "🟡 На паузе",
    ApplicationStatus.CLOSED: "🔴 Закрыта (найдено)",
    ApplicationStatus.MODERATION: "⏳ На модерации",
    ApplicationStatus.REJECTED: "❌ Отклонена",
    ApplicationStatus.DELETED: "🗑 Удалена (хранится 7 дней)",
}


def format_date(value) -> str:
    return str(value)[:16].replace("T", " ") if value else "неизвестно"


def application_card(application: Application, *, owner=False, moderator=False) -> str:
    kind = "🐾 Потерялось" if application.kind == ApplicationKind.LOST else "🔍 Найдено"
    lines = [f"📋 <b>Анкета #{application.id}</b>\n"]
    if owner:
        lines.append(f"📌 <b>Статус:</b> {STATUS_LABELS[application.status]}")
    lines.append(f"📌 <b>Тип:</b> {kind}")
    if moderator:
        lines.append(f"👤 <b>Автор ID:</b> <code>{application.user_id}</code>")
    lines.extend((
        f"🏷 <b>Кличка:</b> {h(application.pet_name)}",
        f"📍 <b>Район:</b> {h(application.district)}",
        f"📝 <b>Приметы:</b>\n<i>{h(application.description)}</i>",
    ))
    if application.additional_info:
        lines.append(f"💬 <b>Дополнительная информация:</b>\n<i>{h(application.additional_info)}</i>")
    if moderator:
        lines.append(f"🕐 <b>Создана:</b> {h(format_date(application.created_at))}")
    if owner:
        lines.append(f"\n👁 <b>Просмотров:</b> {application.views}  |  ↩️ <b>Откликов:</b> {application.responses}")
        if application.status == ApplicationStatus.REJECTED and application.reject_reason:
            lines.append(f"\n❌ <b>Причина отклонения:</b>\n<i>{h(application.reject_reason)}</i>")
    return "\n".join(lines)

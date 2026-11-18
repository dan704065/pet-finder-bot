"""Track disposable UI separately from persistent dialogs and important receipts."""

from contextvars import ContextVar
from dataclasses import dataclass, field

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message


@dataclass
class ScreenScope:
    durable_source: bool = False
    current: list[int] = field(default_factory=list)
    stale: set[int] = field(default_factory=set)
    receipts: set[int] = field(default_factory=set)
    wrote: bool = False

    def record(self, result, *, keep=False, append=False):
        messages = result if isinstance(result, (list, tuple)) else [result]
        ids = [message.message_id for message in messages if isinstance(message, Message)]
        if not ids:
            return
        self.wrote = True
        if keep:
            self.receipts.update(ids)
        else:
            if not append:
                self.stale.update(self.current)
                self.current = []
            self.current.extend(ids)


screen_scope: ContextVar[ScreenScope | None] = ContextVar("screen_scope", default=None)


def record_screen(result, *, keep=False, append=False):
    scope = screen_scope.get()
    if scope:
        scope.record(result, keep=keep, append=append)
    return result


def important_message(message):
    text = message.text or message.caption or ""
    return any(marker in text for marker in (
        "отправлена на модерацию", "Анкета отправлена", "Спасибо за помощь!",
        "Новая анкета", "Отклик на анкету", "Ваш отклик принят", "Обращение отправлено",
        "Данные удалены", "Животное нашлось", "Анкета полностью удалена",
    ))


async def try_delete(bot, chat_id, message_id):
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramAPIError:
        # Old or manually removed messages must not prevent navigation.
        pass


class ScreenMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        message = event.message if isinstance(event, CallbackQuery) else event
        if not isinstance(message, Message) or message.chat.type != "private":
            return await handler(event, data)
        database = data["services"].database
        chat_id = message.chat.id
        async with database.connection() as connection:
            async with connection.execute("SELECT message_id, durable FROM chat_screens WHERE chat_id = ?", (chat_id,)) as cursor:
                previous = dict(await cursor.fetchall())
        callback = isinstance(event, CallbackQuery)
        durable = callback and (bool(previous.get(message.message_id)) or important_message(message)
                               or (event.data or "").startswith(("notify_", "admin_approve_", "admin_reject_")))
        scope = ScreenScope(durable_source=durable)
        token = screen_scope.set(scope)
        try:
            result = await handler(event, data)
        finally:
            screen_scope.reset(token)
        if not scope.wrote:
            # An additional photo in an album does not create another prompt.
            if not callback and (message.location or (message.photo and data.get("raw_state"))):
                await try_delete(data["bot"], chat_id, message.message_id)
            return result
        keep_ids = set(scope.current) | scope.receipts
        obsolete = {mid for mid, permanent in previous.items() if not permanent} | scope.stale
        if callback:
            if durable:
                scope.receipts.add(message.message_id)
                # Preserve the receipt, but don't leave an obsolete menu attached.
                if message.reply_markup:
                    try:
                        await message.edit_reply_markup(reply_markup=None)
                    except TelegramAPIError:
                        pass
            else:
                obsolete.add(message.message_id)
        else:
            obsolete.add(message.message_id)
        for mid in obsolete - keep_ids - scope.receipts:
            await try_delete(data["bot"], chat_id, mid)
        async with database.connection(write=True) as connection:
            await connection.execute("DELETE FROM chat_screens WHERE chat_id = ? AND durable = 0", (chat_id,))
            for mid in scope.current:
                await connection.execute("INSERT OR REPLACE INTO chat_screens VALUES (?, ?, 0)", (chat_id, mid))
            for mid in scope.receipts:
                await connection.execute("INSERT OR REPLACE INTO chat_screens VALUES (?, ?, 1)", (chat_id, mid))
        return result

"""Track disposable UI separately from persistent dialogs and important receipts."""

from contextvars import ContextVar
from dataclasses import dataclass, field

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from handlers.states import LocationStates


@dataclass
class ScreenScope:
    durable_source: bool = False
    current: list[int] = field(default_factory=list)
    stale: set[int] = field(default_factory=set)
    receipts: set[int] = field(default_factory=set)
    wrote: bool = False
    preserve_previous: bool = True
    reply_kb_removed: bool = False

    def record(self, result, *, keep=False, append=False, preserve=False):
        messages = result if isinstance(result, (list, tuple)) else [result]
        ids = [message.message_id for message in messages if isinstance(message, Message)]
        if not ids:
            return
        self.wrote = True
        if keep:
            self.preserve_previous = False
            self.receipts.update(ids)
        elif preserve:
            self.current.extend(ids)
        else:
            if not append:
                self.preserve_previous = False
                self.stale.update(self.current)
                self.current = []
            self.current.extend(ids)


screen_scope: ContextVar[ScreenScope | None] = ContextVar("screen_scope", default=None)


def record_screen(result, *, keep=False, append=False, preserve=False, reply_markup=None):
    scope = screen_scope.get()
    if scope:
        if isinstance(reply_markup, ReplyKeyboardRemove):
            scope.reply_kb_removed = True
        scope.record(result, keep=keep, append=append, preserve=preserve)
    return result


def important_message(message):
    text = message.text or message.caption or ""
    return any(marker in text for marker in (
        "отправлена на модерацию", "Анкета отправлена", "Спасибо за помощь!",
        "Новая анкета", "Новая жалоба", "Отклик на анкету", "Ваш отклик принят",
        "Обращение отправлено", "Обращение принято", "Данные удалены",
        "Животное нашлось", "Анкета полностью удалена",
    ))


async def try_delete(bot, chat_id, message_id):
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramAPIError:
        # Old or manually removed messages must not prevent navigation.
        pass


async def _clear_reply_keyboard_if_left_location(bot, chat_id: int, was_location: bool, state, scope: ScreenScope):
    if not was_location or scope.reply_kb_removed or state is None:
        return
    if await state.get_state() == LocationStates.waiting_for_location.state:
        return
    try:
        msg = await bot.send_message(chat_id=chat_id, text="Запрос геопозиции закрыт.", reply_markup=ReplyKeyboardRemove())
        scope.reply_kb_removed = True
        if isinstance(msg, Message):
            await try_delete(bot, chat_id, msg.message_id)
    except TelegramAPIError:
        pass


async def _strip_reply_markup(message: Message):
    if message.reply_markup:
        try:
            await message.edit_reply_markup(reply_markup=None)
        except TelegramAPIError:
            pass


class ScreenMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        message = event.message if isinstance(event, CallbackQuery) else event
        if not isinstance(message, Message) or message.chat.type != "private":
            return await handler(event, data)
        database = data["services"].database
        state = data.get("state")
        was_location = (
            (await state.get_state()) == LocationStates.waiting_for_location.state
            if state is not None
            else data.get("raw_state") == LocationStates.waiting_for_location.state
        )
        chat_id = message.chat.id
        async with database.connection() as connection:
            async with connection.execute("SELECT message_id, durable FROM chat_screens WHERE chat_id = ?", (chat_id,)) as cursor:
                previous = dict(await cursor.fetchall())
        callback = isinstance(event, CallbackQuery)
        cb_data = (event.data or "") if callback else ""
        durable = callback and (
            bool(previous.get(message.message_id))
            or important_message(message)
            or cb_data.startswith(("notify_", "admin_approve_", "admin_reject_", "admin_moderate_", "admin_complaint_view_"))
        )
        scope = ScreenScope(durable_source=durable)
        token = screen_scope.set(scope)
        error: BaseException | None = None
        result = None
        try:
            result = await handler(event, data)
        except BaseException as exc:
            error = exc
        finally:
            screen_scope.reset(token)

        if error is None:
            await _clear_reply_keyboard_if_left_location(data["bot"], chat_id, was_location, state, scope)

        if not scope.wrote:
            if callback and durable and cb_data.startswith(("admin_approve_", "admin_reject_")):
                await _strip_reply_markup(message)
            # An additional photo in an album does not create another prompt.
            if not callback and (message.location or (message.photo and data.get("raw_state"))):
                await try_delete(data["bot"], chat_id, message.message_id)
            if error is not None:
                raise error
            return result

        prev_disposable = {mid for mid, permanent in previous.items() if not permanent}
        if scope.preserve_previous:
            keep_ids = prev_disposable | set(scope.current) | scope.receipts
            obsolete = set(scope.stale)
        else:
            keep_ids = set(scope.current) | scope.receipts
            obsolete = prev_disposable | scope.stale

        if callback:
            if durable:
                scope.receipts.add(message.message_id)
                if not scope.preserve_previous:
                    await _strip_reply_markup(message)
            elif not scope.preserve_previous:
                obsolete.add(message.message_id)
        else:
            obsolete.add(message.message_id)

        for mid in obsolete - keep_ids - scope.receipts:
            await try_delete(data["bot"], chat_id, mid)

        next_disposable = (list(prev_disposable) + scope.current) if scope.preserve_previous else scope.current
        async with database.connection(write=True) as connection:
            await connection.execute("DELETE FROM chat_screens WHERE chat_id = ? AND durable = 0", (chat_id,))
            for mid in dict.fromkeys(next_disposable):
                await connection.execute("INSERT OR REPLACE INTO chat_screens VALUES (?, ?, 0)", (chat_id, mid))
            for mid in scope.receipts:
                await connection.execute("INSERT OR REPLACE INTO chat_screens VALUES (?, ?, 1)", (chat_id, mid))

        if error is not None:
            raise error
        return result

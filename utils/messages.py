"""Safe rendering and delivery of Telegram text, including legacy long records."""

from html import escape
from html.parser import HTMLParser

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InputMediaPhoto

from domain.errors import ValidationError
from domain.validation import (
    ADDITIONAL_LIMIT,
    DESCRIPTION_LIMIT,
    NAME_LIMIT,
    REASON_LIMIT,
    RESPONSE_LIMIT,
    SUPPORT_LIMIT,
    text_length,
    validate_text as validate_content,
)
from utils.screens import record_screen, screen_scope


def h(value) -> str:
    return escape(str(value) if value is not None else "")


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(text: str, parse_mode=None) -> str:
    if parse_mode != "HTML":
        return text
    parser = _PlainText()
    parser.feed(text)
    parser.close()
    return "".join(parser.parts)


def split_text(text: str, limit: int = 4096) -> list[str]:
    chunks, start, size = [], 0, 0
    for index, char in enumerate(text):
        width = 2 if ord(char) > 0xFFFF else 1
        if size + width > limit:
            chunks.append(text[start:index])
            start, size = index, 0
        size += width
    if start < len(text):
        chunks.append(text[start:])
    return chunks or [text]


async def safe_answer(callback: CallbackQuery, text: str | None = None, *, show_alert: bool = False) -> None:
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest as exc:
        msg = exc.message.lower()
        if "query is too old" in msg or "query id is invalid" in msg:
            return
        raise


async def send_text(send, text: str, reply_markup=None, parse_mode=None, *, keep=False, append=False, preserve=False, **kwargs):
    plain = plain_text(text, parse_mode)
    if text_length(plain) <= 4096:
        return record_screen(
            await send(text=text, reply_markup=reply_markup, parse_mode=parse_mode, **kwargs),
            keep=keep, append=append, preserve=preserve, reply_markup=reply_markup,
        )
    # Oversized legacy records remain readable without splitting HTML tags/entities.
    chunks = split_text(plain)
    result = None
    messages = []
    for index, chunk in enumerate(chunks):
        is_last = index == len(chunks) - 1
        mk = reply_markup if is_last else None
        result = await send(
            text=chunk, parse_mode=None,
            reply_markup=mk,
            **kwargs,
        )
        messages.append(result)
    record_screen(messages, keep=keep, append=append, preserve=preserve, reply_markup=reply_markup)
    return result


async def safe_send(callback_or_message, text: str, reply_markup=None, parse_mode=None, *, keep=False):
    if not isinstance(callback_or_message, CallbackQuery):
        return await send_text(callback_or_message.answer, text, reply_markup, parse_mode, keep=keep)
    message = callback_or_message.message
    scope = screen_scope.get()
    # Screens with photos are replaced, so old photos never accompany unrelated text.
    if message and not message.photo and not (scope and scope.durable_source) and text_length(plain_text(text, parse_mode)) <= 4096:
        try:
            return record_screen(
                await message.edit_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode),
                keep=keep, reply_markup=reply_markup,
            )
        except TelegramBadRequest as exc:
            if "message is not modified" in exc.message.lower():
                record_screen(message, keep=keep, reply_markup=reply_markup)
                return None
    return await send_text(message.answer, text, reply_markup, parse_mode, keep=keep)


async def send_photo_text(message, photo, text: str, reply_markup=None, *, keep=False):
    raw_photos = list(photo) if isinstance(photo, (list, tuple)) else ([photo] if photo else [])
    photos = [pid for pid in raw_photos if isinstance(pid, str) and pid.strip()][:10]
    if len(photos) > 1:
        # Telegram albums cannot carry inline keyboards. Keep all photos together
        # and put the text/actions immediately below the album.
        try:
            album = await message.answer_media_group(media=[InputMediaPhoto(media=pid) for pid in photos])
            record_screen(album, keep=keep)
            return await send_text(message.answer, text, reply_markup, "HTML", keep=keep, append=True)
        except TelegramBadRequest:
            photos = photos[:1]
    if photos:
        try:
            if text_length(plain_text(text, "HTML")) <= 1024:
                return record_screen(await message.answer_photo(
                    photo=photos[0], caption=text, reply_markup=reply_markup, parse_mode="HTML",
                ), keep=keep, reply_markup=reply_markup)
            record_screen(await message.answer_photo(photo=photos[0]), keep=keep)
            return await send_text(message.answer, text, reply_markup, "HTML", keep=keep, append=True)
        except TelegramBadRequest:
            pass
    return await send_text(message.answer, text, reply_markup, "HTML", keep=keep, append=False)


async def validate_text(message, limit: int, reply_markup=None) -> bool:
    try:
        validate_content(message.text, limit)
    except ValidationError as exc:
        await send_text(message.answer, str(exc), reply_markup=reply_markup, preserve=True)
        return False
    return True

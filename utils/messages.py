"""Safe rendering and delivery of Telegram text, including legacy long records."""

from html import escape
from html.parser import HTMLParser

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from aiogram.types import InputMediaPhoto
from utils.screens import record_screen, screen_scope
from domain.errors import ValidationError
from domain.validation import (
    NAME_LIMIT, DESCRIPTION_LIMIT, ADDITIONAL_LIMIT, RESPONSE_LIMIT, SUPPORT_LIMIT, REASON_LIMIT,
    text_length, validate_text as validate_content,
)


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


async def send_text(send, text: str, reply_markup=None, parse_mode=None, *, keep=False, append=False, **kwargs):
    plain = plain_text(text, parse_mode)
    if text_length(plain) <= 4096:
        return record_screen(await send(text=text, reply_markup=reply_markup, parse_mode=parse_mode, **kwargs), keep=keep, append=append)
    # Oversized legacy records remain readable without splitting HTML tags/entities.
    chunks = split_text(plain)
    result = None
    messages = []
    for index, chunk in enumerate(chunks):
        result = await send(
            text=chunk, parse_mode=None,
            reply_markup=reply_markup if index == len(chunks) - 1 else None,
            **kwargs,
        )
        messages.append(result)
    record_screen(messages, keep=keep, append=append)
    return result


async def safe_send(callback_or_message, text: str, reply_markup=None, parse_mode=None, *, keep=False):
    if not isinstance(callback_or_message, CallbackQuery):
        return await send_text(callback_or_message.answer, text, reply_markup, parse_mode, keep=keep)
    message = callback_or_message.message
    scope = screen_scope.get()
    # Screens with photos are replaced, so old photos never accompany unrelated text.
    if not message.photo and not (scope and scope.durable_source) and text_length(plain_text(text, parse_mode)) <= 4096:
        try:
            return record_screen(await message.edit_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode), keep=keep)
        except TelegramBadRequest as exc:
            if "message is not modified" in exc.message.lower():
                record_screen(message, keep=keep)
                return None
    return await send_text(message.answer, text, reply_markup, parse_mode, keep=keep)


async def send_photo_text(message, photo, text: str, reply_markup=None, *, keep=False):
    photos = list(photo) if isinstance(photo, (list, tuple)) else ([photo] if photo else [])
    if len(photos) > 1:
        # Telegram albums cannot carry inline keyboards. Keep all photos together
        # and put the text/actions immediately below the album.
        album = await message.answer_media_group(media=[InputMediaPhoto(media=pid) for pid in photos])
        record_screen(album, keep=keep)
        return await send_text(message.answer, text, reply_markup, "HTML", keep=keep, append=True)
    if photos:
        try:
            if text_length(plain_text(text, "HTML")) <= 1024:
                return record_screen(await message.answer_photo(
                    photo=photos[0], caption=text, reply_markup=reply_markup, parse_mode="HTML",
                ), keep=keep)
            record_screen(await message.answer_photo(photo=photos[0]), keep=keep)
        except TelegramBadRequest:
            pass
    return await send_text(message.answer, text, reply_markup, "HTML", keep=keep, append=bool(photos))


async def validate_text(message, limit: int) -> bool:
    try:
        validate_content(message.text, limit)
    except ValidationError as exc:
        await send_text(message.answer, str(exc))
        return False
    return True

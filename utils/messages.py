"""Safe rendering and delivery of Telegram text, including legacy long records."""

from html import escape
from html.parser import HTMLParser

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery
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


async def send_text(send, text: str, reply_markup=None, parse_mode=None, **kwargs):
    plain = plain_text(text, parse_mode)
    if text_length(plain) <= 4096:
        return await send(text=text, reply_markup=reply_markup, parse_mode=parse_mode, **kwargs)
    # Oversized legacy records remain readable without splitting HTML tags/entities.
    chunks = split_text(plain)
    result = None
    for index, chunk in enumerate(chunks):
        result = await send(
            text=chunk, parse_mode=None,
            reply_markup=reply_markup if index == len(chunks) - 1 else None,
            **kwargs,
        )
    return result


async def safe_send(callback_or_message, text: str, reply_markup=None, parse_mode=None):
    if not isinstance(callback_or_message, CallbackQuery):
        return await send_text(callback_or_message.answer, text, reply_markup, parse_mode)
    message = callback_or_message.message
    limit = 1024 if message.photo else 4096
    if text_length(plain_text(text, parse_mode)) <= limit:
        try:
            if message.photo:
                return await message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode=parse_mode)
            return await message.edit_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
        except TelegramBadRequest as exc:
            if "message is not modified" in exc.message.lower():
                return None
    return await send_text(message.answer, text, reply_markup, parse_mode)


async def send_photo_text(message, photo, text: str, reply_markup=None):
    if photo:
        try:
            if text_length(plain_text(text, "HTML")) <= 1024:
                return await message.answer_photo(
                    photo=photo, caption=text, reply_markup=reply_markup, parse_mode="HTML",
                )
            await message.answer_photo(photo=photo)
        except TelegramAPIError:
            pass
    return await send_text(message.answer, text, reply_markup, "HTML")


async def validate_text(message, limit: int) -> bool:
    try:
        validate_content(message.text, limit)
    except ValidationError as exc:
        await message.answer(str(exc))
        return False
    return True

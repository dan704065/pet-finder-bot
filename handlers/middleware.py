import logging

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery

from domain.errors import DomainError
from utils.messages import safe_answer, send_text


logger = logging.getLogger(__name__)


class DomainErrorMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except DomainError as exc:
            if isinstance(event, CallbackQuery):
                await safe_answer(event, str(exc), show_alert=True)
            else:
                await send_text(event.answer, str(exc), preserve=True)
            return None

import logging

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery

from domain.errors import DomainError


logger = logging.getLogger(__name__)


class DomainErrorMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except DomainError as exc:
            if isinstance(event, CallbackQuery):
                await event.answer(str(exc), show_alert=True)
            else:
                await event.answer(str(exc))
            return None

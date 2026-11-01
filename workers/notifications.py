import asyncio
import logging
import time

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from database.connection import Database
from presentation.notifications import render_notification
from repositories.outbox import OutboxRepository
from settings import Settings
from utils.messages import send_text


logger = logging.getLogger(__name__)


class NotificationWorker:
    def __init__(self, database: Database, bot: Bot, settings: Settings, *, clock=time.time):
        self.database = database
        self.bot = bot
        self.settings = settings
        self.clock = clock

    async def process_one(self) -> bool:
        now = int(self.clock())
        async with self.database.connection(write=True) as connection:
            notification = await OutboxRepository(connection).claim(now)
        if notification is None:
            return False
        async with self.database.connection() as connection:
            if not await OutboxRepository(connection).is_processing(notification.id):
                return True
        error = None
        permanent = False
        rate_limited = False
        delay = min(3600, 2 ** min(notification.attempts, 12))
        try:
            rendered = render_notification(notification, self.settings)
            await send_text(self.bot.send_message, rendered.text, chat_id=notification.recipient_id, reply_markup=rendered.keyboard, parse_mode="HTML")
        except TelegramRetryAfter as exc:
            error, delay = exc, max(1, exc.retry_after)
            rate_limited = True
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            error, permanent = exc, True
        except (TelegramAPIError, OSError, TimeoutError) as exc:
            error, permanent = exc, notification.attempts >= 8
        except Exception as exc:
            # Bad payloads/template bugs must not block every later notification.
            logger.exception("Cannot render notification id=%s", notification.id)
            error, permanent = exc, True
        async with self.database.connection(write=True) as connection:
            outbox = OutboxRepository(connection)
            if error is None:
                await outbox.delivered(notification.id, int(self.clock()))
            else:
                safe_error = str(error).replace(self.settings.bot_token, "[redacted]") if self.settings.bot_token else str(error)
                await outbox.failed(notification.id, safe_error, int(self.clock()) + delay, permanent=permanent)
                if rate_limited:
                    await outbox.pause_delivery(int(self.clock()) + delay)
                logger.warning("Notification id=%s delivery %s: %s", notification.id, "failed" if permanent else "deferred", type(error).__name__)
        return True

    async def drain(self, limit=1000) -> int:
        processed = 0
        while processed < limit and await self.process_one():
            processed += 1
        return processed

    async def run(self) -> None:
        while True:
            try:
                if not await self.process_one():
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Notification worker failed; retrying")
                await asyncio.sleep(5)

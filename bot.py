import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation

from database.migrations import migrate
from handlers import create_router
from services.container import Services
from settings import Settings
from storage.sqlite import SQLiteStorage
from utils.logger import configure_logging
from workers.notifications import NotificationWorker


logger = logging.getLogger(__name__)


def create_dispatcher(services: Services) -> Dispatcher:
    dispatcher = Dispatcher(storage=SQLiteStorage(services.database), events_isolation=SimpleEventIsolation())
    dispatcher["services"] = services
    dispatcher.include_router(create_router())
    return dispatcher


async def maintenance_loop(services: Services) -> None:
    while True:
        try:
            if await services.maintenance.run_due():
                logger.info("Daily maintenance completed")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Daily maintenance failed; retrying")
        await asyncio.sleep(60)


async def main(settings: Settings | None = None) -> None:
    settings = settings or Settings.load()
    configure_logging(settings.log_path)
    services = Services.create(settings)
    await migrate(services.database)
    bot = Bot(token=settings.bot_token)
    dispatcher = create_dispatcher(services)
    worker = NotificationWorker(services.database, bot, settings)
    tasks = [
        asyncio.create_task(worker.run(), name="notifications"),
        asyncio.create_task(maintenance_loop(services), name="maintenance"),
    ]
    logger.info("Bot started")
    try:
        await dispatcher.start_polling(bot, close_bot_session=False)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await dispatcher.fsm.close()
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

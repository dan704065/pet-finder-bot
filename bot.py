import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from handlers import user, admin
from database.db import init_db, get_7_day_reminder_applications, cleanup_old_deleted_applications
from utils.logger import logger

async def daily_maintenance_task(bot: Bot):
    while True:
        await asyncio.sleep(86400)
        try:
            logger.info("Запуск ежедневного обслуживания...")
            
            await cleanup_old_deleted_applications()
            logger.info("Очистка старых анкет завершена.")
            
            apps = await get_7_day_reminder_applications()
            for app in apps:
                app_id, user_id, pet_name = app
                try:
                    text = (
                        f"Напоминание об анкете #{app_id}\n\n"
                        f"Прошла неделя с момента публикации анкеты «{pet_name}».\n"
                        f"Удалось ли найти питомца?\n\n"
                        f"Если животное нашлось, пожалуйста, закройте анкету в разделе «Мои анкеты», "
                        f"чтобы волонтёры не тратили время зря."
                    )
                    await bot.send_message(user_id, text, parse_mode="HTML")
                    logger.info(f"Отправлено напоминание пользователю {user_id} по анкете {app_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки напоминания {app_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Ошибка в фоновой задаче обслуживания: {e}")

async def main():
    aiogram_logger = logging.getLogger("aiogram.event")
    aiogram_logger.addHandler(logging.FileHandler("logs/bot.log", encoding='utf-8'))
    
    await init_db()
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    dp.include_router(admin.router)
    dp.include_router(user.router)
    
    logger.info("Бот запущен!")
    print("Бот запущен! Нажми Ctrl+C для остановки.")
    
    maintenance_task = asyncio.create_task(daily_maintenance_task(bot))
    
    try:
        await dp.start_polling(bot)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен пользователем.")
    finally:
        maintenance_task.cancel()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nБот остановлен.")
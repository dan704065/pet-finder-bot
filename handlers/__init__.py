from aiogram import F, Router
from aiogram.types import CallbackQuery

from handlers import applications, location, moderation, navigation, onboarding, search, settings, support
from handlers.middleware import DomainErrorMiddleware
from utils.messages import safe_answer
from utils.screens import ScreenMiddleware


async def _non_private_callback(callback: CallbackQuery):
    await safe_answer(callback, "Бот работает только в личных сообщениях.", show_alert=True)


def create_router() -> Router:
    root = Router(name="pet_finder")

    group_guard = Router(name="group_guard")
    group_guard.callback_query.register(_non_private_callback, F.message.chat.type != "private")
    root.include_router(group_guard)

    private_router = Router(name="pet_finder_private")
    private_router.message.filter(F.chat.type == "private")
    private_router.callback_query.filter(F.message.chat.type == "private")
    private_router.message.outer_middleware(ScreenMiddleware())
    private_router.callback_query.outer_middleware(ScreenMiddleware())
    private_router.message.outer_middleware(DomainErrorMiddleware())
    private_router.callback_query.outer_middleware(DomainErrorMiddleware())

    # Global commands must precede broad message handlers for individual FSM steps.
    for module in (onboarding, settings, moderation, location, applications, search, support, navigation):
        private_router.include_router(module.create_router())

    root.include_router(private_router)
    return root

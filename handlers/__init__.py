from aiogram import Router

from handlers import applications, moderation, navigation, onboarding, search, settings, support, location
from handlers.middleware import DomainErrorMiddleware
from utils.screens import ScreenMiddleware


def create_router() -> Router:
    router = Router(name="pet_finder")
    router.message.outer_middleware(ScreenMiddleware())
    router.callback_query.outer_middleware(ScreenMiddleware())
    router.message.outer_middleware(DomainErrorMiddleware())
    router.callback_query.outer_middleware(DomainErrorMiddleware())
    # Global commands must precede broad message handlers for individual FSM steps.
    for module in (onboarding, settings, moderation, location, applications, search, support, navigation):
        router.include_router(module.create_router())
    return router

from aiogram import Router

from handlers import applications, moderation, navigation, onboarding, search, settings, support
from handlers.middleware import DomainErrorMiddleware


def create_router() -> Router:
    router = Router(name="pet_finder")
    router.message.outer_middleware(DomainErrorMiddleware())
    router.callback_query.outer_middleware(DomainErrorMiddleware())
    # Global commands must precede broad message handlers for individual FSM steps.
    for module in (onboarding, settings, moderation, applications, search, support, navigation):
        router.include_router(module.create_router())
    return router

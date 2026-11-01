from aiogram.fsm.state import State, StatesGroup


class CreateApplication(StatesGroup):
    waiting_for_photo = State()
    waiting_for_name = State()
    waiting_for_description = State()
    waiting_for_district = State()
    waiting_for_additional = State()
    waiting_for_confirm = State()


class FoundPet(StatesGroup):
    waiting_for_photo = State()
    waiting_for_district = State()
    waiting_for_description = State()
    waiting_for_confirm = State()


class SwipeStates(StatesGroup):
    choosing_district = State()
    swiping = State()
    writing_response = State()


class SupportStates(StatesGroup):
    choosing_type = State()
    choosing_app = State()
    writing_message = State()


class AdminBanStates(StatesGroup):
    waiting_for_reason = State()


class InitialStates(StatesGroup):
    waiting_for_district = State()


class SettingsStates(StatesGroup):
    choosing_district = State()

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from uuid import uuid4

from domain.models import ApplicationDraft, ApplicationKind, ApplicationStatus
from handlers.common import callback_id, main_menu, read_district, check_banned
from handlers.states import CreateApplication, FoundPet
from keyboards.user_kb import (
    get_cancel_only_keyboard,
    get_back_cancel_keyboard,
    get_confirm_keyboard,
    get_application_list_keyboard,
    get_application_manage_keyboard,
    get_confirm_delete_keyboard,
    get_district_keyboard,
)
from presentation.cards import application_card
from services.container import Services
from utils.blacklist import moderate_text
from utils.messages import (
    h,
    safe_send,
    send_text,
    send_photo_text,
    validate_text,
    NAME_LIMIT,
    DESCRIPTION_LIMIT,
    ADDITIONAL_LIMIT,
)


async def lost_pet(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_banned(callback.from_user.id, callback, services=services): return
    await state.set_data({"submission_key": uuid4().hex})

    text = (
        "🐾 <b>Я потерял животное</b>\n\n"
        "<b>Шаг 1 из 5</b>\n\n"
        "📸 Отправьте фото вашего питомца.\n\n"
        "💡 Если что-то пошло не так — нажмите /start"
    )
    await safe_send(callback, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")
    await state.set_state(CreateApplication.waiting_for_photo)
    await callback.answer()


async def process_photo(message: Message, state: FSMContext, services: Services):
    if await check_banned(message.from_user.id, message, services=services): return
    await state.update_data(photo_id=message.photo[-1].file_id)
    text = "🐾 <b>Я потерял животное</b>\n\n<b>Шаг 2 из 5</b>\n\n🏷 Как зовут вашего питомца?"
    await send_text(message.answer, text, reply_markup=get_back_cancel_keyboard(), parse_mode="HTML")
    await state.set_state(CreateApplication.waiting_for_name)


async def process_photo_invalid(message: Message, services: Services):
    text = "⚠️ <b>Неверный формат</b>\n\n📸 Пожалуйста, отправьте фотографию питомца."
    await send_text(message.answer, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")


async def process_name(message: Message, state: FSMContext, services: Services):
    if await check_banned(message.from_user.id, message, services=services): return
    if not await validate_text(message, NAME_LIMIT): return
    is_ok, reason = moderate_text(message.text)
    if not is_ok:
        await send_text(message.answer, f"❌ Ошибка: {reason}. Попробуйте ещё раз.")
        return
    await state.update_data(pet_name=message.text)
    text = (
        "🐾 <b>Я потерял животное</b>\n\n<b>Шаг 3 из 5</b>\n\n"
        "📝 Опишите приметы (порода, окрас, ошейник).\n\n"
        "💡 <i>Пример: Рыжий кот, белое пятно на лапе, синий ошейник</i>"
    )
    await send_text(message.answer, text, reply_markup=get_back_cancel_keyboard(), parse_mode="HTML")
    await state.set_state(CreateApplication.waiting_for_description)


async def process_name_invalid(message: Message, services: Services):
    text = "⚠️ <b>Неверный формат</b>\n\n✏️ Пожалуйста, введите текстовое имя питомца."
    await send_text(message.answer, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")


async def process_description(message: Message, state: FSMContext, services: Services):
    if await check_banned(message.from_user.id, message, services=services): return
    if not await validate_text(message, DESCRIPTION_LIMIT): return
    is_ok, reason = moderate_text(message.text)
    if not is_ok:
        await send_text(message.answer, f"❌ Ошибка: {reason}. Попробуйте ещё раз.")
        return
    await state.update_data(description=message.text)
    text = "🐾 <b>Я потерял животное</b>\n\n<b>Шаг 4 из 5</b>\n\n📍 Выберите район Новосибирска:"
    await send_text(message.answer, text, reply_markup=get_district_keyboard(), parse_mode="HTML")
    await state.set_state(CreateApplication.waiting_for_district)


async def process_description_invalid(message: Message, services: Services):
    text = "⚠️ <b>Неверный формат</b>\n\n✏️ Пожалуйста, введите текстовое описание примет."
    await send_text(message.answer, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")


async def process_district(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_banned(callback.from_user.id, callback, services=services): return
    district = await read_district(callback)
    if district is None: return
    await state.update_data(district=district)
    text = (
        "🐾 <b>Я потерял животное</b>\n\n<b>Шаг 5 из 5</b>\n\n"
        "💬 Дополнительная информация (необязательно).\n"
        "Напишите <code>-</code> если нет."
    )
    await safe_send(callback, text, reply_markup=get_back_cancel_keyboard(), parse_mode="HTML")
    await state.set_state(CreateApplication.waiting_for_additional)
    await callback.answer()


async def process_district_text_invalid(message: Message, state: FSMContext, services: Services):
    text = (
        "⚠️ <b>Неверный ввод</b>\n\n"
        "📍 Пожалуйста, выберите район из списка кнопок ниже.\n\n"
        "Если вы хотите вернуться назад — нажмите кнопку \"Назад\"."
    )
    await send_text(message.answer, text, reply_markup=get_district_keyboard(), parse_mode="HTML")


async def process_additional(message: Message, state: FSMContext, services: Services):
    if await check_banned(message.from_user.id, message, services=services): return
    if not await validate_text(message, ADDITIONAL_LIMIT): return
    text_input = message.text if message.text != "-" else ""
    if text_input:
        is_ok, reason = moderate_text(text_input)
        if not is_ok:
            await send_text(message.answer, f"❌ Ошибка: {reason}. Попробуйте ещё раз.")
            return

    await state.update_data(additional_info=text_input)
    data = await state.get_data()

    preview = (
        "📋 <b>Проверьте анкету</b>\n\n"
        f"🏷 <b>Кличка:</b> {h(data['pet_name'])}\n"
        f"📝 <b>Приметы:</b>\n<i>{h(data['description'])}</i>\n"
        f"📍 <b>Район:</b> {h(data['district'])}\n"
        f"💬 <b>Дополнительная информация:</b> <i>{h(data['additional_info'] or 'нет')}</i>\n\n"
        "Всё верно?"
    )
    await send_text(message.answer, preview, reply_markup=get_confirm_keyboard(), parse_mode="HTML")
    await state.set_state(CreateApplication.waiting_for_confirm)


async def process_additional_invalid(message: Message, services: Services):
    text = "⚠️ <b>Неверный формат</b>\n\n✏️ Пожалуйста, введите текст или <code>-</code>."
    await send_text(message.answer, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")


async def confirm_ok(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_banned(callback.from_user.id, callback, services=services): return
    data = await state.get_data()
    app = await services.applications.submit(callback.from_user.id, ApplicationDraft(
        kind=ApplicationKind.LOST, pet_name=data["pet_name"], description=data["description"],
        district=data["district"], additional_info=data["additional_info"],
        photo_id=data["photo_id"], submission_key=data["submission_key"],
    ))
    app_id = app.id
    await state.clear()

    text = (
        f"✅ <b>Анкета отправлена</b>\n\n"
        f"Ваша анкета <b>#{app_id}</b> отправлена на модерацию.\n\n"
        "После проверки она появится в ленте волонтёров.\n\n"
        "Вы можете вернуться в главное меню или создать ещё одну анкету."
    )

    await send_text(callback.message.answer, text, reply_markup=main_menu(services, callback.from_user.id), parse_mode="HTML")
    await callback.answer("Отправлено!", show_alert=True)


async def confirm_edit(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_banned(callback.from_user.id, callback, services=services): return
    await state.set_data({"submission_key": uuid4().hex})
    text = "🐾 <b>Я потерял животное</b>\n\nНачинаем заново.\n\n<b>Шаг 1 из 5</b>\n\n📸 Отправьте фото вашего питомца."
    await safe_send(callback, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")
    await state.set_state(CreateApplication.waiting_for_photo)
    await callback.answer()


async def found_pet(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_banned(callback.from_user.id, callback, services=services): return
    await state.set_data({"submission_key": uuid4().hex})

    text = (
        "🔍 <b>Я нашёл животное</b>\n\n"
        "<b>Шаг 1 из 4</b>\n\n"
        "📸 Отправьте фото найденного питомца.\n\n"
        "💡 Нажмите /start для сброса"
    )
    await safe_send(callback, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")
    await state.set_state(FoundPet.waiting_for_photo)
    await callback.answer()


async def found_photo(message: Message, state: FSMContext, services: Services):
    if await check_banned(message.from_user.id, message, services=services): return
    await state.update_data(photo_id=message.photo[-1].file_id)
    text = "🔍 <b>Я нашёл животное</b>\n\n<b>Шаг 2 из 4</b>\n\n📍 Выберите район Новосибирска:"
    await send_text(message.answer, text, reply_markup=get_district_keyboard(), parse_mode="HTML")
    await state.set_state(FoundPet.waiting_for_district)


async def found_photo_invalid(message: Message, services: Services):
    text = "⚠️ <b>Неверный формат</b>\n\n📸 Пожалуйста, отправьте фотографию."
    await send_text(message.answer, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")


async def found_district(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_banned(callback.from_user.id, callback, services=services): return
    district = await read_district(callback)
    if district is None: return
    await state.update_data(district=district)

    text = (
        "🔍 <b>Я нашёл животное</b>\n\n"
        "<b>Шаг 3 из 4</b>\n\n"
        "📝 Опишите животное и обстоятельства находки:\n"
        "• Порода, окрас, размер\n"
        "• Поведение (пугливое, дружелюбное)\n"
        "• Где именно нашли\n"
        "• Есть ли ошейник\n\n"
        "💡 Чем подробнее — тем быстрее найдётся хозяин"
    )
    await safe_send(callback, text, reply_markup=get_back_cancel_keyboard(), parse_mode="HTML")
    await state.set_state(FoundPet.waiting_for_description)
    await callback.answer()


async def found_district_text_invalid(message: Message, state: FSMContext, services: Services):
    text = (
        "⚠️ <b>Неверный ввод</b>\n\n"
        "📍 Пожалуйста, выберите район из списка кнопок ниже.\n\n"
        "Если вы хотите вернуться назад — нажмите кнопку \"Назад\"."
    )
    await send_text(message.answer, text, reply_markup=get_district_keyboard(), parse_mode="HTML")


async def found_description(message: Message, state: FSMContext, services: Services):
    if await check_banned(message.from_user.id, message, services=services): return
    if not await validate_text(message, DESCRIPTION_LIMIT): return
    is_ok, reason = moderate_text(message.text)
    if not is_ok:
        await send_text(message.answer, f"❌ Ошибка: {reason}. Попробуйте ещё раз.")
        return

    await state.update_data(found_description=message.text)

    data = await state.get_data()
    preview = (
        "📋 <b>Проверьте анкету</b>\n\n"
        f"📍 <b>Район:</b> {h(data['district'])}\n"
        f"📝 <b>Описание:</b>\n<i>{h(data['found_description'])}</i>\n\n"
        "Всё верно?"
    )
    await send_text(message.answer, preview, reply_markup=get_confirm_keyboard(), parse_mode="HTML")
    await state.set_state(FoundPet.waiting_for_confirm)


async def found_description_invalid(message: Message, services: Services):
    text = "⚠️ <b>Неверный формат</b>\n\n✏️ Пожалуйста, введите текстовое описание."
    await send_text(message.answer, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")


async def found_confirm_ok(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_banned(callback.from_user.id, callback, services=services): return
    data = await state.get_data()
    app = await services.applications.submit(callback.from_user.id, ApplicationDraft(
        kind=ApplicationKind.FOUND, pet_name="Неизвестно", description=data["found_description"],
        district=data["district"], additional_info="", photo_id=data["photo_id"], submission_key=data["submission_key"],
    ))
    app_id = app.id
    await state.clear()

    text = (
        "✅ <b>Спасибо за помощь!</b>\n\n"
        f"Ваша анкета <b>#{app_id}</b> отправлена на модерацию.\n\n"
        "Мы постараемся быстрее найти хозяина.\n\n"
        "Вы можете вернуться в главное меню или создать ещё одну анкету."
    )

    await send_text(callback.message.answer, text, reply_markup=main_menu(services, callback.from_user.id), parse_mode="HTML")
    await callback.answer()


async def found_confirm_edit(callback: CallbackQuery, state: FSMContext, services: Services):
    if await check_banned(callback.from_user.id, callback, services=services): return
    await state.set_data({"submission_key": uuid4().hex})
    text = "🔍 <b>Я нашёл животное</b>\n\nНачинаем заново.\n\n<b>Шаг 1 из 4</b>\n\n📸 Отправьте фото питомца."
    await safe_send(callback, text, reply_markup=get_cancel_only_keyboard(), parse_mode="HTML")
    await state.set_state(FoundPet.waiting_for_photo)
    await callback.answer()


async def my_applications(callback: CallbackQuery, services: Services):
    if await check_banned(callback.from_user.id, callback, services=services): return

    all_apps = await services.applications.list_owned(callback.from_user.id)

    if not all_apps:
        text = "📋 <b>Мои анкеты</b>\n\nУ вас пока нет анкет."
        await safe_send(callback, text, reply_markup=main_menu(services, callback.from_user.id), parse_mode="HTML")
        await callback.answer()
        return

    text = "📋 <b>Мои анкеты</b>\n\nНажмите на анкету для управления:"
    await safe_send(callback, text, reply_markup=get_application_list_keyboard(all_apps), parse_mode="HTML")
    await callback.answer()


async def my_app_manage(callback: CallbackQuery, services: Services):
    app_id = callback_id(callback)
    app = await services.applications.owned(callback.from_user.id, app_id)
    await send_photo_text(callback.message, app.photo_id, application_card(app, owner=True), get_application_manage_keyboard(app.id, app.status))
    await callback.answer()


async def app_pause(callback: CallbackQuery, services: Services):
    if await check_banned(callback.from_user.id, callback, services=services): return
    app_id = callback_id(callback)
    await services.applications.change_status(callback.from_user.id, app_id, ApplicationStatus.PAUSED)
    await callback.answer("Анкета приостановлена", show_alert=True)
    await my_app_manage(callback, services=services)


async def app_resume(callback: CallbackQuery, services: Services):
    if await check_banned(callback.from_user.id, callback, services=services): return
    app_id = callback_id(callback)
    await services.applications.change_status(callback.from_user.id, app_id, ApplicationStatus.ACTIVE)
    await callback.answer("Анкета возобновлена", show_alert=True)
    await my_app_manage(callback, services=services)


async def app_found(callback: CallbackQuery, services: Services):
    if await check_banned(callback.from_user.id, callback, services=services): return
    app_id = callback_id(callback)
    await services.applications.change_status(callback.from_user.id, app_id, ApplicationStatus.CLOSED)

    text = (
        "🎉 <b>Поздравляем!</b>\n\n"
        "Животное нашлось! Анкета закрыта.\n\n"
        "Спасибо, что воспользовались нашим сервисом."
    )
    await safe_send(callback, text, reply_markup=main_menu(services, callback.from_user.id), parse_mode="HTML")
    await callback.answer("Поздравляем!", show_alert=True)


async def app_delete(callback: CallbackQuery, services: Services):
    if await check_banned(callback.from_user.id, callback, services=services): return
    app_id = callback_id(callback)
    await services.applications.change_status(callback.from_user.id, app_id, ApplicationStatus.DELETED)
    await callback.answer("Анкета удалена. Хранится 7 дней.", show_alert=True)
    await my_applications(callback, services=services)


async def app_hard_delete_prompt(callback: CallbackQuery, services: Services):
    if await check_banned(callback.from_user.id, callback, services=services): return
    app_id = callback_id(callback)
    app = await services.applications.owned(callback.from_user.id, app_id)
    if not app or app.status != "deleted":
        await callback.answer("Анкета недоступна или её статус изменился", show_alert=True)
        return

    text = (
        "⚠️ <b>Подтверждение удаления</b>\n\n"
        "Вы действительно хотите <b>полностью удалить</b> анкету?\n\n"
        "Это действие <b>необратимо</b>."
    )
    await safe_send(callback, text, reply_markup=get_confirm_delete_keyboard(app_id), parse_mode="HTML")
    await callback.answer()


async def app_confirm_hard_delete(callback: CallbackQuery, services: Services):
    if await check_banned(callback.from_user.id, callback, services=services): return
    app_id = callback_id(callback)
    await services.applications.delete_permanently(callback.from_user.id, app_id)

    text = "🗑 <b>Анкета удалена</b>\n\nАнкета полностью удалена."
    await safe_send(callback, text, reply_markup=main_menu(services, callback.from_user.id), parse_mode="HTML")
    await callback.answer("Удалено", show_alert=True)


def create_router() -> Router:
    router = Router(name="applications")
    router.callback_query.register(lost_pet, F.data == 'lost_pet')
    router.message.register(process_photo, CreateApplication.waiting_for_photo, F.photo)
    router.message.register(process_photo_invalid, CreateApplication.waiting_for_photo)
    router.message.register(process_name, CreateApplication.waiting_for_name, F.text)
    router.message.register(process_name_invalid, CreateApplication.waiting_for_name)
    router.message.register(process_description, CreateApplication.waiting_for_description, F.text)
    router.message.register(process_description_invalid, CreateApplication.waiting_for_description)
    router.callback_query.register(process_district, CreateApplication.waiting_for_district, F.data.startswith('district_'))
    router.message.register(process_district_text_invalid, CreateApplication.waiting_for_district, F.text)
    router.message.register(process_additional, CreateApplication.waiting_for_additional, F.text)
    router.message.register(process_additional_invalid, CreateApplication.waiting_for_additional)
    router.callback_query.register(confirm_ok, CreateApplication.waiting_for_confirm, F.data == 'confirm_ok')
    router.callback_query.register(confirm_edit, CreateApplication.waiting_for_confirm, F.data == 'confirm_edit')
    router.callback_query.register(found_pet, F.data == 'found_pet')
    router.message.register(found_photo, FoundPet.waiting_for_photo, F.photo)
    router.message.register(found_photo_invalid, FoundPet.waiting_for_photo)
    router.callback_query.register(found_district, FoundPet.waiting_for_district, F.data.startswith('district_'))
    router.message.register(found_district_text_invalid, FoundPet.waiting_for_district, F.text)
    router.message.register(found_description, FoundPet.waiting_for_description, F.text)
    router.message.register(found_description_invalid, FoundPet.waiting_for_description)
    router.callback_query.register(found_confirm_ok, FoundPet.waiting_for_confirm, F.data == 'confirm_ok')
    router.callback_query.register(found_confirm_edit, FoundPet.waiting_for_confirm, F.data == 'confirm_edit')
    router.callback_query.register(my_applications, F.data == 'my_applications')
    router.callback_query.register(my_app_manage, F.data.startswith('my_app_manage_'))
    router.callback_query.register(app_pause, F.data.startswith('app_pause_'))
    router.callback_query.register(app_resume, F.data.startswith('app_resume_'))
    router.callback_query.register(app_found, F.data.startswith('app_found_'))
    router.callback_query.register(app_delete, F.data.startswith('app_delete_'))
    router.callback_query.register(app_hard_delete_prompt, F.data.startswith('app_hard_delete_'))
    router.callback_query.register(app_confirm_hard_delete, F.data.startswith('app_confirm_hard_delete_'))
    return router

from domain.errors import ValidationError
from domain.models import ApplicationDraft
from domain.districts import NOVOSIBIRSK_DISTRICTS
from utils.blacklist import moderate_text


NAME_LIMIT = 80
DESCRIPTION_LIMIT = 2000
ADDITIONAL_LIMIT = 1000
RESPONSE_LIMIT = 2000
SUPPORT_LIMIT = 2000
REASON_LIMIT = 1000


def text_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def validate_text(text: str, limit: int, *, optional=False, moderate=False) -> None:
    if not isinstance(text, str) or (not optional and not text.strip()):
        raise ValidationError("Пожалуйста, отправьте непустой текст.")
    if text_length(text) > limit:
        raise ValidationError(f"Слишком длинный текст. Максимум: {limit} символов.")
    if moderate and text:
        valid, reason = moderate_text(text)
        if not valid:
            raise ValidationError(reason)


def validate_district(district: str) -> None:
    if district not in NOVOSIBIRSK_DISTRICTS:
        raise ValidationError("Выберите район из списка")


def validate_draft(draft: ApplicationDraft) -> None:
    validate_text(draft.pet_name, NAME_LIMIT, moderate=True)
    validate_text(draft.description, DESCRIPTION_LIMIT, moderate=True)
    validate_text(draft.additional_info, ADDITIONAL_LIMIT, optional=True, moderate=True)
    validate_district(draft.district)
    if not draft.photo_id or not draft.submission_key or len(draft.submission_key) > 128:
        raise ValidationError("Анкета не заполнена. Начните создание заново.")

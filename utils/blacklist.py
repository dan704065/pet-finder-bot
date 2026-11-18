import re

# Запрещённые слова и словосочетания (мошенничество) — по границам слов,
# чтобы не блокировать «насчет», «мусоросборник», «Донателло», «Декарта», «поплатился».
FRAUD_PATTERNS = [
    r"\bсбор(?:ы|а|у|ом|е|ов|ам|средств)?\b",
    r"\bреквизит\w*\b",
    r"\bкарт(?:а|у|ы|ой|е|очк\w*)\b",
    r"\bперевед(?:и|ите)\b",
    r"\bперевод\s+денег\b",
    r"\bденьг\w*\b",
    r"\bденег\b",
    r"\bденежн\w*\b",
    r"\bрубл(?:ь|я|ей|ям|ями|ях)\b",
    r"\bдонат(?:ы|а|у|ом|е|ов|ить|ьте)?\b",
    r"\bпожертвован\w*\b",
    r"\bсч[её]т(?:а|у|ом|е|ов|ам)?\b",
    r"\bоплат(?:а|ы|у|ой|е|ить|ите)\b",
]

# Запрещённые паттерны (ссылки, контакты, карты) с числовыми границами,
# чтобы не блокировать 15-значные ISO-микрочипы животных.
FORBIDDEN_PATTERNS = [
    r"https?://\S+",              # http/https ссылки
    r"www\.\S+",                  # www ссылки
    r"t\.me/\S+",                 # telegram ссылки
    r"(?<!\w)@[a-zA-Z0-9_]{3,}",  # @username
    r"(?<!\d)\+7\d{10}(?!\d)",    # телефоны +7XXXXXXXXXX
    r"(?<!\d)8\d{10}(?!\d)",      # телефоны 8XXXXXXXXXX
    r"(?<!\d)\d{16}(?!\d)",       # 16-значные номера банковских карт
]

# Замены символов для обхода фильтра внутри кириллических слов
REPLACEMENTS = {
    'а': ['a', '@', '4'],
    'о': ['o', '0'],
    'е': ['e', '3'],
    'и': ['u', '1', 'i'],
    'с': ['c', '$'],
    'р': ['p'],
    'у': ['y'],
    'к': ['k'],
    'л': ['l'],
    'н': ['h'],
    'д': ['d'],
    'м': ['m'],
    'п': ['n'],
    'г': ['g'],
    'т': ['t'],
    'б': ['b', '6'],
    'з': ['3'],
    'ч': ['4'],
    'ш': ['w'],
    'ж': ['v'],
    'х': ['x'],
}

_CYRILLIC_RE = re.compile(r"[а-яё]")
_PROFANITY_RE = re.compile(
    r"\b(?:(?:за|на|по|вы|отъ?|при|до|пере|подъ?|разъ?|съ|объ|о|а|у|не|долбо)?"
    r"(?:еб|пизд|ху[йяеюи])\w*|бля(?:д\w*|ть|т)?|сук(?:а|и|ой|у|ам|ами|ах))\b"
)


def check_fraud_words(text: str) -> bool:
    """Проверяет текст на мошеннические слова по границам слов."""
    text_lower = text.lower()
    return any(re.search(pattern, text_lower) for pattern in FRAUD_PATTERNS)


def check_forbidden_patterns(text: str) -> bool:
    """Проверяет текст на ссылки, телефоны и номера карт."""
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in FORBIDDEN_PATTERNS)


def _normalize_word(token: str) -> str:
    # Не превращаем обычные числа ("36", "436") и чисто латинские слова ("ebony") в мат.
    if not _CYRILLIC_RE.search(token):
        return token
    out = token
    for original, replacements in REPLACEMENTS.items():
        for repl in replacements:
            out = out.replace(repl, original)
    return out


def check_profanity(text: str) -> bool:
    """Проверяет слова, не склеивая обычные слова и не блокируя числа вроде «36»."""
    text_clean = text.lower().replace("ё", "е")
    # Склеиваем намеренно разделённые одиночные буквы ("х у й"), сохраняя границы обычных слов.
    text_clean = re.sub(
        r"(?<!\w)(?:[a-zа-я0-9@$][\s.\-_,;:!?]+)+[a-zа-я0-9@$](?!\w)",
        lambda match: re.sub(r"[\s.\-_,;:!?]+", "", match.group()),
        text_clean,
    )
    text_clean = re.sub(
        r"[a-zа-я0-9@$]+",
        lambda match: _normalize_word(match.group()),
        text_clean,
    )
    return bool(_PROFANITY_RE.search(text_clean))


def moderate_text(text: str) -> tuple[bool, str]:
    """
    Модерирует текст.
    Возвращает (прошёл_модерацию, причина_отказа)
    """
    if check_fraud_words(text):
        return False, "Обнаружены подозрительные слова (возможно мошенничество)"

    if check_forbidden_patterns(text):
        return False, "Обнаружены ссылки или контакты (запрещено)"

    if check_profanity(text):
        return False, "Обнаружена нецензурная лексика"

    return True, ""

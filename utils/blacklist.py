import re

# Запрещённые слова (мошенничество)
FRAUD_WORDS = [
    "сбор", "реквизит", "карта", "переведите", "деньги", "рубль",
    "помощь деньгами", "донат", "пожертвование", "счет", "оплат"
]

# Запрещённые паттерны (ссылки, контакты)
FORBIDDEN_PATTERNS = [
    r"https?://\S+",  # http/https ссылки
    r"www\.\S+",      # www ссылки
    r"t\.me/\S+",     # telegram ссылки
    r"@\w+",          # @username
    r"\+7\d{10}",     # телефоны
    r"8\d{10}",       # телефоны
    r"\b\d{16}\b",    # номера карт
]

# Маты (основные корни)
PROFANITY_ROOTS = [
    "хуй", "пизд", "еб", "бля", "сука"
]

# Замены букв для обхода
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
    'й': ['u', 'i'],
    'ы': ['u'],
    'э': ['e'],
    'ю': ['u'],
    'я': ['ya'],
}


def check_fraud_words(text: str) -> bool:
    """Проверяет текст на мошеннические слова"""
    text_lower = text.lower()
    for word in FRAUD_WORDS:
        if word in text_lower:
            return True
    return False


def check_forbidden_patterns(text: str) -> bool:
    """Проверяет текст на ссылки и контакты"""
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


def check_profanity(text: str) -> bool:
    """Проверяет текст на маты"""
    text_lower = text.lower()
    
    # Убираем разделители
    text_clean = re.sub(r'[\s\.\-_,;:!?]+', '', text_lower)
    
    # Заменяем обходы на оригинальные буквы
    for original, replacements in REPLACEMENTS.items():
        for repl in replacements:
            text_clean = text_clean.replace(repl, original)
    
    # Проверяем корни
    for root in PROFANITY_ROOTS:
        if root in text_clean:
            return True
    
    return False


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
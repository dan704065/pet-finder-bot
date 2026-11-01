class DomainError(Exception):
    """An expected domain rejection that can be shown to the user."""


class AccessDenied(DomainError):
    def __init__(self, message="Доступ запрещён"):
        super().__init__(message)


class ApplicationUnavailable(DomainError):
    def __init__(self):
        super().__init__("Анкета недоступна или её статус изменился")


class ValidationError(DomainError):
    pass

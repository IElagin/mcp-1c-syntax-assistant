"""Ошибки приложения, различимые обработчиками FastAPI."""


class ValidationError(Exception):
    """Входные данные не прошли проверку."""


class FilePathError(Exception):
    """Путь к файлу не проходит проверку."""

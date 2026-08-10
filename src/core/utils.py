"""
Безопасные утилиты для системных операций.
"""

from pathlib import Path
from typing import List, Optional
import logging

from src.core.errors import FilePathError

logger = logging.getLogger(__name__)


def validate_file_path(file_path: Path, allowed_extensions: Optional[List[str]] = None) -> bool:
    """
    Валидация пути к файлу.

    Args:
        file_path: Путь к файлу
        allowed_extensions: Список разрешенных расширений

    Returns:
        True если путь валиден

    Raises:
        FilePathError: При невалидном пути
    """
    if not file_path.exists():
        raise FilePathError(f"Файл не существует: {file_path}")

    if not file_path.is_file():
        raise FilePathError(f"Путь не является файлом: {file_path}")

    # Проверка на path traversal
    try:
        file_path.resolve(strict=True)
    except Exception:
        raise FilePathError(f"Невалидный путь: {file_path}")

    if allowed_extensions:
        if file_path.suffix.lower() not in allowed_extensions:
            raise FilePathError(
                f"Недопустимое расширение файла: {file_path.suffix}. "
                f"Разрешены: {allowed_extensions}"
            )

    return True

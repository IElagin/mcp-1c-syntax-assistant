"""
Безопасные утилиты для системных операций.
"""

from pathlib import Path
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class SafeSubprocessError(Exception):
    """Исключение для ошибок безопасного subprocess."""
    pass


def canonical_source_file(source_file: Optional[str]) -> str:
    """Внутрикнижный путь страницы через прямой слэш.

    Разделитель приходит из вывода 7zip и зависит от платформы сборки, а путь
    служит ключом склейки русской и английской книг.
    """
    return (source_file or "").replace("\\", "/")


def validate_file_path(file_path: Path, allowed_extensions: Optional[List[str]] = None) -> bool:
    """
    Валидация пути к файлу.
    
    Args:
        file_path: Путь к файлу
        allowed_extensions: Список разрешенных расширений
        
    Returns:
        True если путь валиден
        
    Raises:
        SafeSubprocessError: При невалидном пути
    """
    if not file_path.exists():
        raise SafeSubprocessError(f"Файл не существует: {file_path}")
    
    if not file_path.is_file():
        raise SafeSubprocessError(f"Путь не является файлом: {file_path}")
    
    # Проверка на path traversal
    try:
        file_path.resolve(strict=True)
    except Exception:
        raise SafeSubprocessError(f"Невалидный путь: {file_path}")
    
    if allowed_extensions:
        if file_path.suffix.lower() not in allowed_extensions:
            raise SafeSubprocessError(
                f"Недопустимое расширение файла: {file_path.suffix}. "
                f"Разрешены: {allowed_extensions}"
            )
    
    return True

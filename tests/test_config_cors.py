"""Разбор списка разрешённых origins из переменной окружения."""

import pytest

from src.core.config import Settings


@pytest.mark.unit
def test_cors_origins_default_is_wildcard():
    """По умолчанию разрешены все источники — сервер рассчитан на локальный контур."""
    assert Settings().cors_origins == ["*"]


@pytest.mark.unit
def test_cors_origins_splits_comma_separated_list():
    """Несколько источников задаются через запятую."""
    settings = Settings(cors_allow_origins="http://localhost:3000,https://example.com")
    assert settings.cors_origins == ["http://localhost:3000", "https://example.com"]


@pytest.mark.unit
def test_cors_origins_trims_spaces_and_drops_empty():
    """Пробелы и пустые элементы не должны превращаться в мусорный origin."""
    settings = Settings(cors_allow_origins=" http://a.test , , http://b.test ")
    assert settings.cors_origins == ["http://a.test", "http://b.test"]

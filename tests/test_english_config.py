"""Настройки английской книги и второго индекса."""

import pytest

from src.core.config import Settings


pytestmark = pytest.mark.unit


def test_defaults_point_at_the_english_book():
    settings = Settings()

    assert settings.hbk_directory_en == "data/hbk-en"
    assert settings.hbk_filename_en == "shcntx_root.hbk"
    assert settings.elasticsearch_index_en == "help1c_docs_en"
    assert settings.default_help_lang == "ru"


def test_data_config_carries_english_book_paths():
    settings = Settings()

    assert settings.data.hbk_directory_en == "data/hbk-en"
    assert settings.data.hbk_filename_en == "shcntx_root.hbk"


def test_unknown_default_language_is_rejected_at_startup():
    """Опечатка в DEFAULT_HELP_LANG обязана ронять старт, а не молча давать ru.

    Сервер, тихо ответивший по-русски англоязычной команде, выглядит исправным:
    расхождение обнаружится только по языку карточек.
    """
    with pytest.raises(ValueError):
        Settings(default_help_lang="english")

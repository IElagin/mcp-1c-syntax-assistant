"""Строки ответа — таблица на язык, а не литералы в коде сборки."""

import dataclasses

import pytest

from src.handlers.ui_strings import EN_STRINGS, RU_STRINGS, strings_for


pytestmark = pytest.mark.unit


def test_strings_for_known_languages():
    assert strings_for("ru") is RU_STRINGS
    assert strings_for("en") is EN_STRINGS


def test_strings_for_rejects_unknown_language():
    with pytest.raises(ValueError):
        strings_for("de")


def test_both_languages_fill_every_field():
    """Незаполненное поле в английской таблице напечатало бы русскую строку.

    Смешанная карточка — «Call: … Доступность: …» — выглядит как ошибка данных,
    а не как незаконченная локализация, и разбирается дольше, чем стоила бы
    проверка здесь.
    """
    for field in dataclasses.fields(RU_STRINGS):
        ru_value = getattr(RU_STRINGS, field.name)
        en_value = getattr(EN_STRINGS, field.name)
        assert en_value, f"в EN_STRINGS не заполнено {field.name}"
        if field.name != "lang":
            assert en_value != ru_value, f"{field.name} не переведено"

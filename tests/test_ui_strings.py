"""Строки ответа — таблица на язык, а не литералы в коде сборки."""

import dataclasses
import re

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
        if field.name == "lang" or _is_bare_placeholder(ru_value):
            continue
        assert en_value != ru_value, f"{field.name} не переведено"


def _is_bare_placeholder(value) -> bool:
    """Шаблон без единого слова — переводить в нём нечего."""
    return isinstance(value, str) and bool(re.fullmatch(r"\{\w+\}", value))


def test_handler_messages_are_translated():
    """Сообщения обработчиков — такая же часть ответа, как карточка."""
    assert "not found" in EN_STRINGS.object_not_found.lower()
    assert "не найден" in RU_STRINGS.object_not_found.lower()


def test_message_templates_use_the_same_placeholders():
    """Разошедшиеся подстановки роняют форматирование в проде, а не в тесте.

    Раньше здесь были перечислены три поля вручную, и добавление нового поля с
    расхождением прошло бы мимо теста молча. Прогон по всем строковым полям
    таблицы закрывает это раз и навсегда — новое поле проверяется само, без
    правки теста.
    """
    import re

    for field in dataclasses.fields(RU_STRINGS):
        if field.type is not str:
            continue
        ru_keys = set(re.findall(r"\{(\w+)\}", getattr(RU_STRINGS, field.name)))
        en_keys = set(re.findall(r"\{(\w+)\}", getattr(EN_STRINGS, field.name)))
        assert ru_keys == en_keys, field.name

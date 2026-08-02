"""Диалект справки: таблица строк вместо захардкоженных литералов."""

import pytest

from src.parsers.dialects import RU_DIALECT, Chapter, dialect_for


pytestmark = pytest.mark.parser


def test_chapter_recognized_by_exact_heading():
    assert RU_DIALECT.chapter_of("Доступность:") is Chapter.AVAILABILITY
    assert RU_DIALECT.chapter_of("Примечание:") is Chapter.NOTE
    assert RU_DIALECT.chapter_of("Синтаксис:") is Chapter.SYNTAX


def test_usage_and_version_headings_are_different_chapters():
    """«Использование:» — доступ к свойству, «Использование в версии:» — версия.

    Прежний код различал их сравнением на точное равенство, и потеря этого
    различия дала бы свойству доступ вида «доступен, начиная с версии 8.0».
    """
    assert RU_DIALECT.chapter_of("Использование:") is Chapter.USAGE
    assert RU_DIALECT.chapter_of("Использование в версии:") is Chapter.VERSION


def test_syntax_variant_heading_carries_its_name():
    heading = "Вариант синтаксиса: По индексу"
    assert RU_DIALECT.chapter_of(heading) is Chapter.SYNTAX_VARIANT
    assert RU_DIALECT.variant_name(heading) == "По индексу"


def test_syntax_variant_does_not_swallow_plain_syntax():
    """«Синтаксис:» не должен опознаваться как вариант, и наоборот."""
    assert RU_DIALECT.chapter_of("Синтаксис:") is not Chapter.SYNTAX_VARIANT


def test_unknown_heading_gives_none():
    assert RU_DIALECT.chapter_of("Методическая информация") is None


def test_parameter_flag_maps_to_requiredness():
    assert RU_DIALECT.required_from_flag("обязательный") is True
    assert RU_DIALECT.required_from_flag("необязательный") is False
    assert RU_DIALECT.required_from_flag("") is None


def test_version_markers():
    assert RU_DIALECT.is_version_available("Доступен, начиная с версии 8.0.")
    assert RU_DIALECT.is_version_changed("Описание изменено в версии 8.3.20.")


def test_dialect_for_rejects_unknown_language():
    with pytest.raises(ValueError):
        dialect_for("de")

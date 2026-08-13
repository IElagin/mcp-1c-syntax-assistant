"""Тесты нормализации текста справки."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parsers.text_utils import (
    split_type_and_note,
    normalize_whitespace,
    clean_description,
    normalize_lines,
    clean_prose,
    restore_space_after_punctuation,
)


@pytest.mark.unit
def test_non_breaking_spaces_are_removed():
    """Код с неразрывными пробелами не компилируется в 1С."""
    assert normalize_whitespace("Отбор\xa0=\xa0Новый\xa0Структура();") == \
        "Отбор = Новый Структура();"


@pytest.mark.unit
def test_space_after_period_is_restored():
    assert clean_description("не по ссылке.Не работает") == "не по ссылке. Не работает"


@pytest.mark.unit
def test_version_number_is_not_broken():
    """8.0 — не граница фразы, точку между цифрами не трогаем."""
    assert clean_description("Доступен с версии 8.0 и выше") == \
        "Доступен с версии 8.0 и выше"


@pytest.mark.unit
def test_type_from_link():
    html = 'Тип: <a href="v8help://x/Array.html">Массив</a>. <br>Массив строк.'
    type_name, note = split_type_and_note(html)
    assert type_name == "Массив"
    assert note == "Массив строк."


@pytest.mark.unit
def test_type_enumeration_is_preserved():
    """Выбирать один тип из перечисления сервер не вправе."""
    type_name, _ = split_type_and_note("Тип: Строка, Число. <br>Что-то.")
    assert type_name == "Строка, Число"


@pytest.mark.unit
def test_type_is_empty_without_type_section():
    """Нет раздела «Тип:» — поле пустое, а не заполненное заглушкой."""
    type_name, note = split_type_and_note("Просто описание без типа.")
    assert type_name == ""
    assert note == "Просто описание без типа."


@pytest.mark.unit
def test_line_normalization_keeps_the_shape_of_a_code_block():
    text = "Для <Имя> = 1 По 10 Цикл\n  // Операторы\nКонецЦикла;"
    assert normalize_lines(text).splitlines() == [
        "Для <Имя> = 1 По 10 Цикл",
        "// Операторы",
        "КонецЦикла;",
    ]


@pytest.mark.unit
def test_line_normalization_collapses_a_run_of_blank_lines():
    """Разметка даёт подряд идущие пустые строки, читателю хватает одной."""
    assert normalize_lines("Абзац\n\n\n\n\nСледующий") == \
        "Абзац\n\nСледующий"


@pytest.mark.unit
def test_line_normalization_still_squeezes_spaces_inside_a_line():
    assert normalize_lines("Отбор\xa0=\xa0Новый\n   Структура ( ) ;") == \
        "Отбор = Новый\nСтруктура ( ) ;"


def test_a_lost_space_after_a_colon_is_restored():
    assert restore_space_after_punctuation(
        "следующих действий:открытие панели"
    ) == "следующих действий: открытие панели"


def test_a_lost_space_after_a_comma_is_restored():
    assert restore_space_after_punctuation(
        "панели ввода,отображение клавиатуры"
    ) == "панели ввода, отображение клавиатуры"


def test_the_product_name_keeps_its_colon():
    """«1С:Предприятие» — имя, а не потерянный пробел; так же и «1C:Enterprise»."""
    for name in ("режимов запуска 1С:Предприятия", "the 1C:Enterprise server"):
        assert restore_space_after_punctuation(name) == name


def test_a_decimal_number_is_not_split():
    assert restore_space_after_punctuation("точность 1,5 знака") == "точность 1,5 знака"


def test_a_time_is_not_split():
    assert restore_space_after_punctuation("в 12:30 по расписанию") == "в 12:30 по расписанию"


def test_a_url_is_not_split():
    text = "см. http://v8.1c.ru/8.1/data/core"
    assert restore_space_after_punctuation(text) == text


def test_a_closing_bracket_before_the_comma_still_counts():
    assert restore_space_after_punctuation(
        "ПанельРазделов (SectionsPanel),ПанельИзбранного"
    ) == "ПанельРазделов (SectionsPanel), ПанельИзбранного"


def test_prose_cleaning_restores_both_the_period_and_the_comma():
    assert clean_prose(
        "типов:Строка,Число.Значение произвольно"
    ) == "типов: Строка, Число. Значение произвольно"

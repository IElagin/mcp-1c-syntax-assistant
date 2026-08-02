"""Английское имя объекта лежит в русской книге — его нельзя выбрасывать."""

import pytest

from src.parsers.indexer import split_name_ru_en
from tests.test_parser_element_card import parse_fixture


pytestmark = pytest.mark.parser


def test_object_page_keeps_its_english_name():
    """«Массив (Array)» — так напечатано в русской книге у 2 905 объектов из 3 063.

    Парсер отрезал скобку до индексатора, и поиск по ValueTable не находил
    объект, хотя имя лежало в заголовке справки.
    """
    doc = parse_fixture("array_object.html")

    assert doc.name == "Массив (Array)"
    assert split_name_ru_en(doc.name) == ("Массив", "Array")


def test_derived_fields_stay_russian():
    """full_path и name_ru строятся из русской части и меняться не должны."""
    doc = parse_fixture("array_object.html")
    doc.build_call_strings()

    assert doc.name_ru() == "Массив"
    assert doc.full_path == "Массив"


def test_member_page_carries_english_object_name():
    """У метода английское имя объекта берётся из V8SH_title: «ТаблицаЗначений (ValueTable)»."""
    doc = parse_fixture("valuetable_findrows.html")

    assert doc.object_ru == "ТаблицаЗначений"
    assert doc.object_en == "ValueTable"


def test_object_with_dotted_placeholder_name_splits_by_russian_part():
    """«СправочникМенеджер.<Имя справочника> (CatalogManager.<Catalog name>)».

    Точка есть и в русской, и в английской половине заголовка. Разбиение по
    первой точке всей строки дало бы имя с обломком английской части.
    """
    doc = parse_fixture("catalogmanager_object.html")

    assert doc.name.startswith("<Имя справочника>")
    assert "CatalogManager" not in doc.name_ru()

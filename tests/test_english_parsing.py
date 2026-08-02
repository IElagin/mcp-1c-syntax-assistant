"""Разбор английской страницы справки даёт ту же структуру, что русской.

Тип документа парсер выводит из пути в архиве, а пути в книгах совпадают —
поэтому английская страница проходит тот же конвейер, что русская, и отдельного
определения типа для неё не нужно.
"""

from pathlib import Path

import pytest

from src.parsers.dialects import EN_DIALECT
from src.parsers.html_parser import HTMLParser


pytestmark = pytest.mark.parser

FIXTURES = Path(__file__).parent / "fixtures" / "hbk-en"

ARCHIVE_PATHS = {
    "array_add.html": "objects/catalog234/Array/methods/Add772.html",
    "array_object.html": "objects/catalog234/Array.html",
    "valuetable_findrows.html":
        "objects/catalog234/catalog236/ValueTable/methods/FindRows646.html",
    "valuetable_ctor_auto.html":
        "objects/catalog234/catalog236/ValueTable/ctors/ctor_Auto.html",
    "valuetable_columns.html":
        "objects/catalog234/catalog236/ValueTable/properties/Columns1030.html",
}


def parse_fixture(fixture_name: str):
    """Разбирает английскую фикстуру английским диалектом."""
    content = (FIXTURES / fixture_name).read_bytes()
    parser = HTMLParser(dialect=EN_DIALECT)
    return parser.parse_html_content(content, ARCHIVE_PATHS[fixture_name])


def test_english_method_page_gives_full_card_data():
    doc = parse_fixture("array_add.html")

    assert doc.name == "Add"
    assert doc.object == "Array"
    assert doc.description == "Adds an element to the end of the array."
    assert doc.note.startswith("When an element is added")
    assert doc.version_from == "8.0"
    assert "thin client" in [a.lower() for a in doc.availability]


def test_english_parameters_carry_type_and_requiredness():
    doc = parse_fixture("array_add.html")

    variant = doc.variants[0]
    assert variant.syntax == "Add(<Value>)"
    assert len(variant.parameters) == 1

    parameter = variant.parameters[0]
    assert parameter.name == "Value"
    assert parameter.type == "Arbitrary"
    assert parameter.required is False
    assert "Added value" in parameter.description


def test_english_example_is_extracted():
    doc = parse_fixture("array_add.html")

    assert doc.examples
    assert 'Array.Add("First");' in doc.examples[0]


def test_english_object_page_lists_its_members():
    doc = parse_fixture("array_object.html")

    assert doc.name == "Array"
    assert any(m.name == "Add" for m in doc.methods)


def test_english_property_carries_its_value_type():
    doc = parse_fixture("valuetable_columns.html")

    assert doc.value_type
    assert doc.usage

"""Constructor lines are worded by handlers, in the answer's language."""

import pytest

from src.handlers.mcp_handlers import constructor_lines
from src.handlers.ui_strings import EN_STRINGS, RU_STRINGS

pytestmark = pytest.mark.unit


def test_variant_label_speaks_the_answer_language():
    calls = [
        ("New COMSafeArray(<Source>)", "From COMSafeArray"),
        ("New COMSafeArray(<Array>, <ElementType>)", "From array 2"),
    ]

    lines = constructor_lines(calls, EN_STRINGS)

    assert lines == [
        'New COMSafeArray(<Source>) — variant "From COMSafeArray"',
        'New COMSafeArray(<Array>, <ElementType>) — variant "From array 2"',
    ]
    assert not any("Ѐ" <= char <= "ӿ" for line in lines for char in line), lines


def test_variant_label_is_unchanged_in_russian():
    calls = [
        ("New COMSafeArray(<Source>)", "From COMSafeArray"),
        ("New COMSafeArray(<Array>, <ElementType>)", "From array 2"),
    ]

    assert constructor_lines(calls, RU_STRINGS) == [
        "New COMSafeArray(<Source>) — вариант «From COMSafeArray»",
        "New COMSafeArray(<Array>, <ElementType>) — вариант «From array 2»",
    ]


def test_single_call_has_no_variant_suffix():
    assert constructor_lines([("New ValueTable", "ValueTable")], EN_STRINGS) == [
        "New ValueTable"
    ]


def test_call_without_a_variant_name_prints_bare():
    calls = [("New Array", ""), ("New Array(<Count>)", "From count")]

    assert constructor_lines(calls, EN_STRINGS) == [
        "New Array",
        'New Array(<Count>) — variant "From count"',
    ]

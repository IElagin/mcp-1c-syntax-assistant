"""Тесты нормализации текста справки."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parsers.text_utils import (
    split_type_and_note,
    normalize_whitespace,
    clean_description,
)


@pytest.mark.unit
def test_nerazryvnye_probely_ubirayutsya():
    """Код с неразрывными пробелами не компилируется в 1С."""
    assert normalize_whitespace("Отбор\xa0=\xa0Новый\xa0Структура();") == \
        "Отбор = Новый Структура();"


@pytest.mark.unit
def test_probel_posle_tochki_vosstanavlivaetsya():
    assert clean_description("не по ссылке.Не работает") == "не по ссылке. Не работает"


@pytest.mark.unit
def test_versiya_ne_lomaetsya():
    """8.0 — не граница фразы, точку между цифрами не трогаем."""
    assert clean_description("Доступен с версии 8.0 и выше") == \
        "Доступен с версии 8.0 и выше"


@pytest.mark.unit
def test_tip_iz_ssylki():
    html = 'Тип: <a href="v8help://x/Array.html">Массив</a>. <br>Массив строк.'
    tip, poyasnenie = split_type_and_note(html)
    assert tip == "Массив"
    assert poyasnenie == "Массив строк."


@pytest.mark.unit
def test_perechislenie_tipov_sohranyaetsya():
    """Выбирать один тип из перечисления сервер не вправе."""
    tip, _ = split_type_and_note("Тип: Строка, Число. <br>Что-то.")
    assert tip == "Строка, Число"


@pytest.mark.unit
def test_bez_razdela_tipa_tip_pustoy():
    """Нет раздела «Тип:» — поле пустое, а не заполненное заглушкой."""
    tip, poyasnenie = split_type_and_note("Просто описание без типа.")
    assert tip == ""
    assert poyasnenie == "Просто описание без типа."

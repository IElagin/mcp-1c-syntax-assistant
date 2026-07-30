"""Тесты замеров полноты карточки.

Замер — измерительный инструмент, и он обязан быть верным: если он врёт,
мы «улучшим» метрику, не улучшив ответы.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval_search import neunikalnye_imena, zamer_odnoznachnosti, zamer_polnoty


@pytest.mark.unit
def test_protivorechie_obyazatelnosti_lovitsya():
    """required=True при '(необязательный)' в описании — это противоречие."""
    docs = [
        {"type": "object_function", "parameters": [
            {"name": "А", "type": "Строка", "required": True,
             "description": "(необязательный) Что-то."},
            {"name": "Б", "type": "Строка", "required": True,
             "description": "(обязательный) Что-то."},
        ]},
    ]

    itogi = zamer_polnoty(docs)

    assert itogi["param_protivorechie"] == 1
    assert itogi["param_vsego"] == 2


@pytest.mark.unit
def test_tip_vozvrata_abzats_otlichaetsya_ot_tipa():
    """Тип длиной в три предложения типом не считается."""
    docs = [
        {"type": "object_function", "variants": [
            {"return_type": "Массив"},
            {"return_type": "Тип: Массив. Массив строк таблицы значений, "
                            "соответствующих условиям поиска. Замечание! Массив хранит ссылки."},
        ]},
    ]

    itogi = zamer_polnoty(docs)

    assert itogi["vozvrat_tip"] == 1
    assert itogi["vozvrat_abzats"] == 1


@pytest.mark.unit
def test_s_dostupnostyu_pustoy_spisok_ne_schitaetsya():
    """Пустой список availability — то же, что его отсутствие: доступность неизвестна."""
    docs = [
        {"type": "object_function", "availability": ["Тонкий клиент", "Сервер"]},
        {"type": "object_function", "availability": []},
        {"type": "object_function"},
    ]

    itogi = zamer_polnoty(docs)

    assert itogi["s_dostupnostyu"] == 1
    assert itogi["vsego"] == 3


@pytest.mark.unit
def test_svoystv_s_tipom_i_dostupom_schitayutsya_tolko_u_svoystv():
    """svoystv (и производные от него) считает только object_property.

    Функция или процедура с непустыми value_type/usage не должна попасть
    в счётчики свойств — этих полей у неё в модели просто нет.
    """
    docs = [
        {"type": "object_property", "value_type": "Строка", "usage": "Чтение"},
        {"type": "object_property"},
        {"type": "object_function", "value_type": "Строка", "usage": "Чтение"},
    ]

    itogi = zamer_polnoty(docs)

    assert itogi["svoystv"] == 2
    assert itogi["svoystv_s_tipom"] == 1
    assert itogi["svoystv_s_dostupom"] == 1


@pytest.mark.unit
def test_mnogo_variantov_schitaet_tolko_bolshe_odnogo():
    """Один вариант вызова — норма, больше одного — то, что считаем отдельно."""
    docs = [
        {"type": "object_function", "variants": [
            {"return_type": "Число"}, {"return_type": "Строка"},
        ]},
        {"type": "object_function", "variants": [{"return_type": "Число"}]},
    ]

    itogi = zamer_polnoty(docs)

    assert itogi["mnogo_variantov"] == 1


@pytest.mark.unit
def test_param_bez_obyazatelnosti_tolko_dlya_none():
    """required=None — обязательность неизвестна; True и False — известна."""
    docs = [
        {"type": "object_function", "parameters": [
            {"name": "А", "required": None},
            {"name": "Б", "required": True},
            {"name": "В", "required": False},
        ]},
    ]

    itogi = zamer_polnoty(docs)

    assert itogi["param_bez_obyazatelnosti"] == 1
    assert itogi["param_vsego"] == 3


@pytest.mark.unit
def test_neunikalnye_imena_nahodyatsya():
    """Имя, встречающееся у нескольких объектов, попадает в набор омонимов."""
    docs = [
        {"name_ru": "Количество", "object": "Массив"},
        {"name_ru": "Количество", "object": "Структура"},
        {"name_ru": "НайтиСтроки", "object": "ТаблицаЗначений"},
    ]

    omonimy = neunikalnye_imena(docs)

    assert omonimy["Количество"] == 2
    assert "НайтиСтроки" not in omonimy


class _PodstavnoyServis:
    """Знает ответ на имя заранее — без реального поиска по индексу."""

    def __init__(self, otvety):
        self._otvety = otvety

    async def kartochka_elementa(self, imya):
        return self._otvety[imya]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_zamer_odnoznachnosti_schitaet_po_kind():
    """soobshchil/molcha_vybral считаются по полю kind, а не по факту вызова."""
    docs = [
        {"name_ru": "Количество", "object": "Массив"},
        {"name_ru": "Количество", "object": "Структура"},
        {"name_ru": "Найти", "object": "Строка"},
        {"name_ru": "Найти", "object": "Массив"},
    ]
    service = _PodstavnoyServis({
        "Количество": {"kind": "ambiguous"},
        "Найти": {"kind": "card"},
    })

    itogi = await zamer_odnoznachnosti(service, docs, razmer=2)

    assert itogi["vsego"] == 2
    assert itogi["soobshchil"] == 1
    assert itogi["molcha_vybral"] == 1

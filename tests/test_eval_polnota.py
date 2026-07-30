"""Тесты замеров полноты карточки.

Замер — измерительный инструмент, и он обязан быть верным: если он врёт,
мы «улучшим» метрику, не улучшив ответы.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval_search import zamer_polnoty


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


from eval_search import neunikalnye_imena


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

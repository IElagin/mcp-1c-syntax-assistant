"""Тесты замеров полноты карточки.

Замер — измерительный инструмент, и он обязан быть верным: если он врёт,
мы «улучшим» метрику, не улучшив ответы.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval_search import ambiguous_names, measure_completeness, measure_disambiguation


@pytest.mark.unit
def test_protivorechie_obyazatelnosti_lovitsya():
    """required=True при '(необязательный)' префиксом описания — это противоречие."""
    docs = [
        {"type": "object_function", "parameters": [
            {"name": "А", "type": "Строка", "required": True,
             "description": "(необязательный) Что-то."},
            {"name": "Б", "type": "Строка", "required": True,
             "description": "(обязательный) Что-то."},
        ]},
    ]

    totals = measure_completeness(docs)

    assert totals["param_contradiction"] == 1
    assert totals["param_total"] == 2


@pytest.mark.unit
def test_metka_vnutri_opisaniya_ne_protivorechie():
    """Метка обязательности внутри описания (не префиксом) — не противоречие.

    Так размечена справка структуры-аргумента: параметр 'Параметры' у
    'ПолучитьДанныеВыбора' сам обязателен (required=True), а метка
    '(необязательный)' внутри его описания относится к вложенному ключу
    структуры, а не к самому параметру. Substring-проверка ловила это как
    противоречие и как дубль — оба ложноположительные.
    """
    docs = [
        {"type": "object_function", "parameters": [
            {"name": "Параметры", "type": "Структура", "required": True,
             "description": "Содержит ключи структуры: Отбор - тип Структура. "
                             "ВыборГруппИЭлементов (необязательный) - тип "
                             "ИспользованиеГруппИЭлементов."},
        ]},
    ]

    totals = measure_completeness(docs)

    assert totals["param_contradiction"] == 0
    assert totals["param_duplicated_in_description"] == 0


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

    totals = measure_completeness(docs)

    assert totals["return_as_type"] == 1
    assert totals["return_as_paragraph"] == 1


@pytest.mark.unit
def test_perechislenie_tipov_cherez_zapyatuyu_eto_tip():
    """Перечисление нескольких типов через запятую — тип, не абзац.

    Выбирать один тип из перечисления сервер не вправе (спека §4.2), значит
    метрика не должна штрафовать длинную строку из нескольких типов только
    за длину — важно, что каждый элемент однословный.
    """
    docs = [
        {"type": "object_function", "variants": [
            {"return_type": "Null, Булево, Число, Строка, Дата, УникальныйИдентификатор"},
        ]},
    ]

    totals = measure_completeness(docs)

    assert totals["return_as_type"] == 1
    assert totals["return_as_paragraph"] == 0


@pytest.mark.unit
def test_dlinnoe_odnoslovnoe_imya_tipa_ne_rezhetsya_dlinoy():
    """Настоящее имя типа длиннее 40 символов не должно резаться по длине."""
    docs = [
        {"type": "object_function", "variants": [
            {"return_type": "ПериодРазделенияХраненияДанныхЖурналаРегистрации"},
        ]},
    ]

    totals = measure_completeness(docs)

    assert totals["return_as_type"] == 1
    assert totals["return_as_paragraph"] == 0


@pytest.mark.unit
def test_fraza_s_mnogoslovnymi_elementami_ne_tip():
    """Перечисление, где среди элементов есть многословная фраза, — не тип."""
    docs = [
        {"type": "object_function", "variants": [
            {"return_type": "ТабличныйДокумент, ТекстовыйДокумент, другой объект, "
                            "который может быть макетом"},
        ]},
    ]

    totals = measure_completeness(docs)

    assert totals["return_as_type"] == 0
    assert totals["return_as_paragraph"] == 1


@pytest.mark.unit
def test_s_dostupnostyu_pustoy_spisok_ne_schitaetsya():
    """Пустой список availability — то же, что его отсутствие: доступность неизвестна."""
    docs = [
        {"type": "object_function", "availability": ["Тонкий клиент", "Сервер"]},
        {"type": "object_function", "availability": []},
        {"type": "object_function"},
    ]

    totals = measure_completeness(docs)

    assert totals["with_availability"] == 1
    assert totals["total"] == 3


@pytest.mark.unit
def test_svoystv_s_tipom_i_dostupom_schitayutsya_tolko_u_svoystv():
    """properties (и производные от него) считает только object_property.

    Функция или процедура с непустыми value_type/usage не должна попасть
    в счётчики свойств — этих полей у неё в модели просто нет.
    """
    docs = [
        {"type": "object_property", "value_type": "Строка", "usage": "Чтение"},
        {"type": "object_property"},
        {"type": "object_function", "value_type": "Строка", "usage": "Чтение"},
    ]

    totals = measure_completeness(docs)

    assert totals["properties"] == 2
    assert totals["properties_with_type"] == 1
    assert totals["properties_with_usage"] == 1


@pytest.mark.unit
def test_mnogo_variantov_schitaet_tolko_bolshe_odnogo():
    """Один вариант вызова — норма, больше одного — то, что считаем отдельно."""
    docs = [
        {"type": "object_function", "variants": [
            {"return_type": "Число"}, {"return_type": "Строка"},
        ]},
        {"type": "object_function", "variants": [{"return_type": "Число"}]},
    ]

    totals = measure_completeness(docs)

    assert totals["many_variants"] == 1


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

    totals = measure_completeness(docs)

    assert totals["param_without_required"] == 1
    assert totals["param_total"] == 3


@pytest.mark.unit
def test_neunikalnye_imena_nahodyatsya():
    """Имя, встречающееся у нескольких объектов, попадает в набор омонимов."""
    docs = [
        {"name_ru": "Количество", "object": "Массив"},
        {"name_ru": "Количество", "object": "Структура"},
        {"name_ru": "НайтиСтроки", "object": "ТаблицаЗначений"},
    ]

    homonyms = ambiguous_names(docs)

    assert homonyms["Количество"] == 2
    assert "НайтиСтроки" not in homonyms


class _PodstavnoyServis:
    """Знает ответ на имя заранее — без реального поиска по индексу."""

    def __init__(self, otvety):
        self._otvety = otvety

    async def element_card(self, imya):
        return self._otvety[imya]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_zamer_odnoznachnosti_schitaet_po_kind():
    """reported/chose_silently считаются по полю kind, а не по факту вызова."""
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

    totals = await measure_disambiguation(service, docs, size=2)

    assert totals["total"] == 2
    assert totals["reported"] == 1
    assert totals["chose_silently"] == 1

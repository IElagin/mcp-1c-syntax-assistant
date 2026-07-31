"""Тесты однозначности выбора элемента.

69,1% документов индекса имеют неуникальное имя: «Количество» встречается у 275
элементов, «Добавить» — у 197. Прежний get_syntax_info выполнял запрос с size:1
и возвращал один документ из 275, ничем не сообщая о выборе. Агент принимал
чужую карточку за единственную.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.elasticsearch import es_client
from src.search.search_service import SearchService


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_omonim_ne_vybiraetsya_molcha():
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        otvet = await SearchService(es_client).kartochka_elementa("Количество")

        assert otvet["kind"] == "ambiguous", otvet.get("kind")
        assert otvet["total"] > 100
        assert otvet["candidates"], "перечень кандидатов пуст"
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_utochnennyy_obekt_daet_kartochku():
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        otvet = await SearchService(es_client).kartochka_elementa(
            "НайтиСтроки", "ТаблицаЗначений"
        )

        assert otvet["kind"] == "card"
        assert otvet["document"]["object"] == "ТаблицаЗначений"
        assert otvet["document"]["name_ru"] == "НайтиСтроки"
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_nesushchestvuyushchiy_obekt_ne_podmenyaetsya_molcha():
    """«ФоновыеЗадания» — идентификатор из кода, в справке объект зовётся иначе.

    Прежде сервис молча искал по одному имени метода и отдавал элементы чужих
    объектов, не сообщая о подмене.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        otvet = await SearchService(es_client).kartochka_elementa(
            "Выполнить", "ФоновыеЗадания"
        )

        assert otvet["kind"] == "object_not_found"
        assert otvet["object"] == "ФоновыеЗадания"
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_kandidaty_nachinayutsya_s_nastoyashchih_tipov():
    """Настоящие типы важнее заголовков разделов справки вида «ОбъектМетаданных: Х»."""
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        otvet = await SearchService(es_client).kartochka_elementa("Количество")

        pervyy = otvet["candidates"][0]["object"] or ""
        assert " " not in pervyy and ":" not in pervyy, pervyy
    finally:
        await es_client.disconnect()

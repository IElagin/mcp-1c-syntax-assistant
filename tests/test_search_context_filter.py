"""Регрессионные тесты фильтра по объекту в find_help_filtered.

Дефект: фильтр по object_name складывался с фильтрами по типу элемента в один
bool.should, то есть через ИЛИ. Любой объектный метод удовлетворял условию по
типу, и ограничение по объекту не сужало выборку — параметр молча не работал.
Инструмент search_by_context, который проверял этот файл, упразднён: его роль
перешла к find_1c_help вместе с методом сервиса find_help_filtered.
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
async def test_object_filter_narrows_selection():
    """Фильтр по объекту обязан сужать выдачу.

    Прежде условия по типу и по объекту складывались в один should, и фильтр по
    объекту не сужал ничего: условие по типу выполнялось само по себе.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)

        without_filter = await service.find_help_filtered("Количество", [], None, 20)
        with_filter = await service.find_help_filtered(
            "Количество", ["object_function"], "ТаблицаЗначений", 20
        )

        assert with_filter["results"], "фильтр по объекту не должен обнулять выдачу"
        assert all(r.get("object") == "ТаблицаЗначений" for r in with_filter["results"])
        assert with_filter["total"] < without_filter["total"]
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_dotted_path_finds_its_own_document():
    """Точечный путь из справки обязан находить документ, чей это путь.

    Прежний разбор «Объект.Элемент» был синтаксическим и запрещал пробелы: одна
    точка, ни одного пробела. Имена объектов справки этому не подчиняются —
    у 3 172 документов (15,7% всех точечных путей корпуса) путь содержит пробел
    или лишнюю точку, и все они уходили в семантический поиск. По запросу
    «Расширение формы клиентского приложения для плана видов
    характеристик.РежимВыбора» выдача начиналась с ВидДекорацииФормы,
    ВидПоляФормы и ВидГруппыФормы — три чужих объекта вместо запрошенного.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)

        paths = [
            # Пробелы в имени объекта.
            "Расширение формы клиентского приложения для плана видов "
            "характеристик.РежимВыбора",
            # Имя объекта само содержит точку — разрез обязан идти по последней
            # известной границе, а не по первой попавшейся.
            "WSСсылкаМенеджер.<Имя WS-Ссылки>.ПолучитьWSОпределения",
            # Обычный путь, работавший и раньше, — он не должен сломаться.
            "ТаблицаЗначений.НайтиСтроки",
        ]
        for path in paths:
            result = await service.find_help_filtered(path, None, None, 5)
            found = [r.get("full_path") for r in result.get("results", [])]
            assert path in found, (path, found[:3])
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_free_text_with_a_period_is_not_read_as_an_object():
    """Точка в предложении — не обращение к элементу объекта.

    Разрез проверяется по индексу именно поэтому: расширить синтаксическое
    правило до пробелов, не спрашивая справку, значило бы превратить
    «Как добавить строку. Пример кода» в поиск элемента «Пример кода»
    у несуществующего объекта «Как добавить строку» — то есть обменять один
    класс промахов на другой.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)

        assert await service._qualified_split("Как добавить строку. Пример кода") is None
        assert await service._qualified_split("версия 8.3.14") is None
        assert await service._qualified_split("Массив.Добавить") == ("Массив", "Добавить")

        # Объекта нет в справке — разрез сохраняется узким синтаксическим
        # разбором, чтобы фильтр по объекту остался и пустая выдача честно
        # называла причину («ФоновыеЗадания» — идентификатор из кода, в справке
        # объект зовётся МенеджерФоновыхЗаданий).
        assert await service._qualified_split("ФоновыеЗадания.Выполнить") == (
            "ФоновыеЗадания", "Выполнить"
        )
    finally:
        await es_client.disconnect()

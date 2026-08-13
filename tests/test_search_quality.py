"""Тесты качества поиска: точечная запись и точное совпадение имени.

Замер до правок (150 элементов эталона из индекса):
  - запрос 'Объект.Метод'  — 2.0% попаданий в топ-5, 60.7% пустых ответов;
  - голое имя метода       — 26.7% на первом месте.

Причины:
  - full_path имеет тип keyword, а запрашивался через match/match_phrase,
    которые для keyword требуют совпадения строки целиком;
  - name хранит русское и английское имя слитно ("Добавить (Add)"), поэтому
    term по name.keyword со значением "Добавить" не срабатывал никогда —
    буст на точное совпадение был мёртвым.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.elasticsearch import es_client
from src.search.search_service import SearchService


def names(results):
    return [(r.get("object"), r.get("name")) for r in results]


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.real_index
@pytest.mark.search
@pytest.mark.asyncio
async def test_dotted_query_finds_exactly_that_method():
    """'ТаблицаЗначений.Добавить' возвращает нужный элемент первым.

    Так разработчик пишет запрос естественнее всего — копирует выражение
    из кода. До правки такой запрос возвращал мусор или пустоту.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        res = await service.find_help_by_query("ТаблицаЗначений.Добавить", limit=5)

        assert not res.get("error"), res.get("error")
        results = res.get("results", [])
        assert results, "Пустой ответ на точечную запись"

        first = results[0]
        assert first.get("object") == "ТаблицаЗначений", names(results)
        assert first.get("name", "").startswith("Добавить"), names(results)
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.real_index
@pytest.mark.search
@pytest.mark.asyncio
async def test_dotted_query_admits_no_foreign_objects():
    """В выдаче по 'Объект.Метод' нет элементов других объектов."""
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        res = await service.find_help_by_query("МенеджерФоновыхЗаданий.ПолучитьФоновыеЗадания", limit=5)

        results = res.get("results", [])
        assert results, "Пустой ответ на точечную запись"

        foreign = sorted({
            r.get("object") for r in results
            if r.get("object") != "МенеджерФоновыхЗаданий"
        })
        assert not foreign, f"Просочились чужие объекты: {foreign}"
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.real_index
@pytest.mark.search
@pytest.mark.asyncio
async def test_exact_name_ranks_above_partial():
    """Точное совпадение имени ранжируется выше частичного.

    'Записать' — точное имя метода у многих объектов; 'ЗаписатьАтрибут',
    'ЗаписатьТекст' и подобные не должны обгонять его.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        res = await service.find_help_by_query("Записать", limit=5)

        results = res.get("results", [])
        assert results, "Пустой ответ"

        first_name = results[0].get("name", "")
        # name хранится как "Записать (Write)" — сравниваем русскую часть
        assert first_name.split(" (")[0] == "Записать", (
            f"Первым пришло частичное совпадение: {names(results)}"
        )
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.real_index
@pytest.mark.search
@pytest.mark.asyncio
async def test_search_by_english_name_is_exact():
    """Английское имя находит тот же элемент: ValueIsFilled."""
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        res = await service.find_help_by_query("ValueIsFilled", limit=5)

        results = res.get("results", [])
        assert results, "Пустой ответ"
        assert any(
            "ЗначениеЗаполнено" in (r.get("name") or "") for r in results[:3]
        ), names(results)
    finally:
        await es_client.disconnect()


@pytest.mark.unit
@pytest.mark.search
def test_queries_do_not_reference_removed_fields():
    """Буст по несуществующему полю — тихий ноль, а не ошибка.

    syntax_en был пуст у 100% методов и всё равно стоял в бустах; parameters.*
    в плоском match по nested-полю не находил ничего (0 попаданий против 11 у
    nested-запроса). Такие бусты создают ложное чувство настроенного поиска.
    """
    import json

    from src.search.query_builder import QueryBuilder

    builder = QueryBuilder()
    queries = [
        builder.build_search_query("ЗначениеЗаполнено", 10, "exact"),
        builder.build_search_query("как получить количество строк", 10, "semantic"),
        builder.build_search_query("ТаблицаЗначений.Добавить", 10, "auto"),
        builder.build_search_query("найти строки", 10, "multi_match"),
        builder.build_search_query("НайтиСтроки", 10, "fuzzy"),
        builder.build_exact_query("Добавить"),
    ]

    text = json.dumps(queries, ensure_ascii=False)
    for field in ("syntax_ru", "syntax_en", "parameters.name", "parameters.description"):
        assert field not in text, f"запрос ссылается на удалённое поле {field}"

    assert "syntax_all" in text, "поисковое поле синтаксиса не используется"


@pytest.mark.unit
@pytest.mark.search
def test_formatter_does_not_lose_card_fields():
    """Форматтер, вырезающий поля, делает карточку неполной ещё до рендера."""
    from src.search.formatter import SearchFormatter

    doc = {
        "name": "НайтиСтроки (FindRows)", "name_ru": "НайтиСтроки",
        "type": "object_function", "element_kind": "функция",
        "object": "ТаблицаЗначений", "object_ru": "ТаблицаЗначений",
        "full_path": "ТаблицаЗначений.НайтиСтроки",
        "call_primary": "ТаблицаЗначений.НайтиСтроки(<ПараметрыОтбора>)",
        "variants": [{"variant": "", "syntax": "НайтиСтроки(<ПараметрыОтбора>)",
                      "call": "ТаблицаЗначений.НайтиСтроки(<ПараметрыОтбора>)",
                      "parameters": [], "return_type": "Массив",
                      "return_description": ""}],
        "availability": ["сервер"], "usage": None, "value_type": "",
        "note": "Примечание.", "description": "Поиск строк.",
        "version_from": "8.0", "examples": [],
    }

    result = SearchFormatter().format_search_results(
        [{"document": doc, "score": 12.5}]
    )[0]

    for field in ("availability", "variants", "call_primary", "note", "element_kind"):
        assert field in result, f"форматтер потерял поле {field}"
    assert result["_score"] == 12.5

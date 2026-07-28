"""Регрессионные тесты фильтра по объекту в search_with_context_filter.

Дефект: фильтр по object_name складывался с фильтрами по типу элемента в один
bool.should, то есть через ИЛИ. Любой объектный метод удовлетворял условию по
типу, и ограничение по объекту не сужало выборку — параметр молча не работал.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.elasticsearch import es_client
from src.search.search_service import SearchService


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.search
@pytest.mark.asyncio
async def test_object_name_ogranichivaet_vyborku_odnim_obektom():
    """object_name оставляет только элементы указанного объекта.

    'Добавить' есть у многих объектов (ДанныеФормыКоллекция, УсловноеОформление,
    ТаблицаЗначений и др.), поэтому запрос без фильтра гарантированно приносит
    чужие объекты — на этом дефект и ловится.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        search_service = SearchService(es_client)

        results = await search_service.search_with_context_filter(
            "Добавить", "object", "ТаблицаЗначений", limit=10
        )

        assert not results.get("error"), results.get("error")

        found = results.get("results", [])
        assert found, "Ожидали найти ТаблицаЗначений.Добавить"

        chuzhie = sorted({
            r.get("object") for r in found if r.get("object") != "ТаблицаЗначений"
        })
        assert not chuzhie, f"Фильтр по объекту не сработал, пришли чужие: {chuzhie}"
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.search
@pytest.mark.asyncio
async def test_object_name_ne_lomaet_filtr_po_tipu():
    """Вместе с object_name продолжает действовать фильтр по контексту.

    Страховка от «починки» через замену should на must только для объекта:
    результаты обязаны остаться элементами объектного контекста.
    """
    OBJEKTNYE_TIPY = {
        "object_function",
        "object_procedure",
        "object_property",
        "object_event",
        "object_constructor",
    }

    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        search_service = SearchService(es_client)

        results = await search_service.search_with_context_filter(
            "Добавить", "object", "ТаблицаЗначений", limit=10
        )

        assert not results.get("error"), results.get("error")

        found = results.get("results", [])
        assert found, "Ожидали найти ТаблицаЗначений.Добавить"

        lishnie_tipy = sorted({
            r.get("type") for r in found if r.get("type") not in OBJEKTNYE_TIPY
        })
        assert not lishnie_tipy, f"Фильтр по контексту потерян, типы: {lishnie_tipy}"
    finally:
        await es_client.disconnect()

"""Регрессионные тесты фильтра по объекту в find_help_filtered.

Дефект: фильтр по object_name складывался с фильтрами по типу элемента в один
bool.should, то есть через ИЛИ. Любой объектный метод удовлетворял условию по
типу, и ограничение по объекту не сужало выборку — параметр молча не работал.
Инструмент search_by_context, который проверял этот файл, упразднён (Task 13):
его роль перешла к find_1c_help вместе с методом сервиса
find_help_filtered.
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
async def test_filtr_po_obektu_suzhaet_vyborku():
    """Фильтр по объекту обязан сужать выдачу.

    Прежде условия по типу и по объекту складывались в один should, и фильтр по
    объекту не сужал ничего: условие по типу выполнялось само по себе.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)

        bez_filtra = await service.find_help_filtered("Количество", [], None, 20)
        s_filtrom = await service.find_help_filtered(
            "Количество", ["object_function"], "ТаблицаЗначений", 20
        )

        assert s_filtrom["results"], "фильтр по объекту не должен обнулять выдачу"
        assert all(r.get("object") == "ТаблицаЗначений" for r in s_filtrom["results"])
        assert s_filtrom["total"] < bez_filtra["total"]
    finally:
        await es_client.disconnect()

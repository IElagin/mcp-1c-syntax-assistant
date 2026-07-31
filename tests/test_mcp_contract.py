"""Тесты контракта MCP-инструментов.

Описания и схемы — это текст, который читает модель. Расхождение схемы с
поведением агент не может ни увидеть, ни проверить: раньше схема обещала limit
по умолчанию 10, а модель подставляла 5.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.mcp_tools import TOOLS

IMENA = {"find_1c_help", "get_1c_element", "list_1c_object_members"}


@pytest.mark.unit
def test_rovno_tri_instrumenta_bez_peresecheniy():
    assert {t["name"] for t in TOOLS} == IMENA


@pytest.mark.unit
def test_schema_zadaet_enum_i_default():
    """Без enum и default модель угадывает допустимые значения."""
    po_imeni = {t["name"]: t for t in TOOLS}

    poisk = po_imeni["find_1c_help"]["inputSchema"]
    assert poisk["properties"]["kind"]["enum"] == [
        "any", "global", "method", "property", "event", "constructor"
    ]
    assert poisk["properties"]["kind"]["default"] == "any"
    assert poisk["properties"]["limit"]["default"] == 10
    assert poisk["properties"]["limit"]["minimum"] == 1
    assert poisk["properties"]["limit"]["maximum"] == 200
    assert poisk["required"] == ["query"]
    assert poisk["additionalProperties"] is False

    sostav = po_imeni["list_1c_object_members"]["inputSchema"]
    assert sostav["properties"]["members"]["enum"] == [
        "all", "methods", "properties", "events", "constructors"
    ]
    assert sostav["properties"]["limit"]["default"] == 100


@pytest.mark.unit
def test_default_v_scheme_sovpadaet_s_modelyu():
    """Схема обещает — модель обязана делать то же."""
    from src.models.mcp_models import Find1CHelpRequest, List1CObjectMembersRequest

    po_imeni = {t["name"]: t for t in TOOLS}

    assert Find1CHelpRequest(query="х").limit == \
        po_imeni["find_1c_help"]["inputSchema"]["properties"]["limit"]["default"]
    assert List1CObjectMembersRequest(object="х").limit == \
        po_imeni["list_1c_object_members"]["inputSchema"]["properties"]["limit"]["default"]


@pytest.mark.unit
def test_opisanie_govorit_kogda_ne_vyzyvat():
    """Разграничение инструментов должно быть в тексте, а не в догадках модели."""
    po_imeni = {t["name"]: t for t in TOOLS}

    assert "get_1c_element" in po_imeni["find_1c_help"]["description"]
    assert "find_1c_help" in po_imeni["get_1c_element"]["description"]
    assert "get_1c_element" in po_imeni["list_1c_object_members"]["description"]


@pytest.mark.unit
def test_element_prinimaet_object_i_variant():
    element = {t["name"]: t for t in TOOLS}["get_1c_element"]["inputSchema"]

    assert element["required"] == ["name"]
    assert set(element["properties"]) == {"name", "object", "variant"}


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_oshibka_pomechaetsya_kak_oshibka():
    """isError обязан отражать реальность, иначе агент примет отказ за успех."""
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        otvet = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_1c_element", "arguments": {}},
        })

    telo = otvet.json()
    assert telo["result"]["isError"] is True, telo
    assert telo["result"]["content"], "текст ошибки не передан агенту"


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_kartochka_prihodit_tekstom():
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        otvet = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "get_1c_element",
                       "arguments": {"name": "НайтиСтроки", "object": "ТаблицаЗначений"}},
        })

    text = otvet.json()["result"]["content"][0]["text"]
    assert "Вызов: ТаблицаЗначений.НайтиСтроки" in text
    assert "Доступность:" in text

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


# --- Фикс-раунд 1: три Important из ревью Task 13 ---


@pytest.mark.unit
@pytest.mark.parametrize("model_cls, kwargs", [
    ("Find1CHelpRequest", {"query": "х", "object_name": "Массив"}),
    ("Get1CElementRequest", {"name": "х", "object_name": "Массив"}),
    ("List1CObjectMembersRequest", {"object": "х", "member_type": "all"}),
])
def test_lishnii_argument_ne_proglatyvaetsya_molcha(model_cls, kwargs):
    """additionalProperties: false в схеме обязан работать и в модели.

    Раньше pydantic по умолчанию тихо отбрасывал незнакомые поля: вызов со
    старым именем параметра object_name молча превращался в вызов без него, и
    агент получал не тот ответ, о котором просил, не зная об этом.
    """
    import src.models.mcp_models as mcp_models
    from pydantic import ValidationError

    model = getattr(mcp_models, model_cls)
    with pytest.raises(ValidationError):
        model(**kwargs)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_error_kind_stanovitsya_oshibkoi_a_ne_tihim_otvetom(monkeypatch):
    """kartochka_elementa помечает сбой ES kind="error" — обработчик обязан
    вернуть isError, а не "элемент не найден".

    Ручной прогон Task 13 проверил только пять честных исходов и живые вызовы
    — этот сбой без мока не воспроизвести (нужен настоящий обрыв ES), поэтому
    здесь подменяем сервис.
    """
    from src.handlers.mcp_handlers import handle_get_1c_element
    from src.models.mcp_models import Get1CElementRequest
    from src.search.search_service import SearchService

    async def fake_kartochka_elementa(self, name, object_name=None, variant=None):
        return {"kind": "error", "name": name, "error": "Elasticsearch недоступен"}

    monkeypatch.setattr(SearchService, "kartochka_elementa", fake_kartochka_elementa)

    result = await handle_get_1c_element(Get1CElementRequest(name="Х"), es_client=None)

    assert result.error, "сбой сервиса обязан попасть в MCPResponse.error"
    assert "недоступен" in result.error


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_initialize_ne_obeshchaet_lishnih_capabilities():
    """resources/prompts/roots/sampling убраны: заявленное, но не работающее
    хуже отсутствующего — клиент узнаёт о расхождении не заранее, а на вызове.
    """
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        otvet = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 40, "method": "initialize", "params": {},
        })

    assert otvet.json()["result"]["capabilities"] == {"tools": {}}


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_prompts_list_chestno_vozvrashchaet_metod_ne_naiden():
    """prompts/list раньше отдавал пустой список при неснятой capability —
    теперь метод не объявлен, и клиент честно получает -32601."""
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        otvet = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 41, "method": "prompts/list", "params": {},
        })

    assert otvet.json()["error"]["code"] == -32601


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_sostav_ne_otritsaet_obekt_iz_za_otsutstviya_odnogo_vida():
    """У ТаблицаЗначений нет событий, но сама она есть — инструмент не должен
    называть её "не найденной" и тут же предлагать её же как похожую."""
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        otvet = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 42, "method": "tools/call",
            "params": {"name": "list_1c_object_members",
                       "arguments": {"object": "ТаблицаЗначений", "members": "events"}},
        })

    text = otvet.json()["result"]["content"][0]["text"]
    assert "не найден" not in text, text
    assert "ТаблицаЗначений" in text


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_sovet_v_kartochke_omonima_vypolnim():
    """Совет "вызовите find_1c_help с limit=N" обязан укладываться в тот же
    потолок, что и схема find_1c_help, иначе агент получит validation error
    вместо списка, следуя честному на вид совету карточки."""
    import re
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        otvet = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 43, "method": "tools/call",
            "params": {"name": "get_1c_element", "arguments": {"name": "Количество"}},
        })

    text = otvet.json()["result"]["content"][0]["text"]
    sovpadenie = re.search(r"limit=(\d+)", text)
    assert sovpadenie, text
    predlozhennyi = int(sovpadenie.group(1))
    assert predlozhennyi <= 200, "совет превышает потолок схемы find_1c_help"

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        provereno = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 44, "method": "tools/call",
            "params": {"name": "find_1c_help",
                       "arguments": {"query": "Количество", "limit": predlozhennyi}},
        })

    telo = provereno.json()
    assert telo["result"]["isError"] is False, telo


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_staroe_imya_parametra_daet_oshibku_a_ne_tihoe_otbrasyvanie():
    """object_name — упразднённое имя параметра get_1c_element (актуальное —
    object). Раньше pydantic тихо отбрасывал незнакомое поле, и вызов уходил
    без фильтра по объекту, возвращая список омонимов вместо карточки."""
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        otvet = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 45, "method": "tools/call",
            "params": {"name": "get_1c_element",
                       "arguments": {"name": "НайтиСтроки", "object_name": "ТаблицаЗначений"}},
        })

    telo = otvet.json()
    assert telo["result"]["isError"] is True, telo

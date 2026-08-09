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

TOOL_NAMES = {"find_1c_help", "get_1c_element", "list_1c_object_members"}


@pytest.mark.unit
def test_exactly_three_tools_without_overlap():
    assert {t["name"] for t in TOOLS} == TOOL_NAMES


@pytest.mark.unit
def test_schema_defines_enum_and_default():
    """Без enum и default модель угадывает допустимые значения."""
    by_name = {t["name"]: t for t in TOOLS}

    search = by_name["find_1c_help"]["inputSchema"]
    assert search["properties"]["kind"]["enum"] == [
        "any", "global", "method", "property", "event", "constructor"
    ]
    assert search["properties"]["kind"]["default"] == "any"
    assert search["properties"]["limit"]["default"] == 10
    assert search["properties"]["limit"]["minimum"] == 1
    assert search["properties"]["limit"]["maximum"] == 200
    assert search["required"] == ["query"]
    assert search["additionalProperties"] is False

    members_schema = by_name["list_1c_object_members"]["inputSchema"]
    assert members_schema["properties"]["members"]["enum"] == [
        "all", "methods", "properties", "events", "constructors"
    ]
    assert members_schema["properties"]["limit"]["default"] == 100


@pytest.mark.unit
def test_schema_default_matches_the_model():
    """Схема обещает — модель обязана делать то же."""
    from src.models.mcp_models import Find1CHelpRequest, List1CObjectMembersRequest

    by_name = {t["name"]: t for t in TOOLS}

    assert Find1CHelpRequest(query="х").limit == \
        by_name["find_1c_help"]["inputSchema"]["properties"]["limit"]["default"]
    assert List1CObjectMembersRequest(object="х").limit == \
        by_name["list_1c_object_members"]["inputSchema"]["properties"]["limit"]["default"]


@pytest.mark.unit
def test_description_states_when_not_to_call():
    """Разграничение инструментов должно быть в тексте, а не в догадках модели."""
    by_name = {t["name"]: t for t in TOOLS}

    assert "get_1c_element" in by_name["find_1c_help"]["description"]
    assert "find_1c_help" in by_name["get_1c_element"]["description"]
    assert "get_1c_element" in by_name["list_1c_object_members"]["description"]


@pytest.mark.unit
def test_element_tool_accepts_object_and_variant():
    element = {t["name"]: t for t in TOOLS}["get_1c_element"]["inputSchema"]

    assert element["required"] == ["name"]
    assert set(element["properties"]) == {"name", "object", "variant", "lang"}


@pytest.mark.unit
def test_schema_and_model_share_one_members_limit_ceiling():
    """A literal 1000 in the model would drift from the schema silently."""
    from src.core.constants import MEMBERS_LIMIT_MAX
    from src.models.mcp_models import List1CObjectMembersRequest

    schema = next(t for t in TOOLS if t["name"] == "list_1c_object_members")
    declared = schema["inputSchema"]["properties"]["limit"]["maximum"]
    accepted = List1CObjectMembersRequest.model_fields["limit"].metadata

    assert declared == MEMBERS_LIMIT_MAX
    assert any(
        getattr(rule, "le", None) == MEMBERS_LIMIT_MAX for rule in accepted
    ), accepted


@pytest.mark.unit
def test_schema_and_model_share_one_search_limit_ceiling():
    """A literal 200 in the model would drift from the schema silently."""
    from src.core.constants import SEARCH_LIMIT_MAX
    from src.models.mcp_models import Find1CHelpRequest

    schema = next(t for t in TOOLS if t["name"] == "find_1c_help")
    declared = schema["inputSchema"]["properties"]["limit"]["maximum"]
    accepted = Find1CHelpRequest.model_fields["limit"].metadata

    assert declared == SEARCH_LIMIT_MAX
    assert any(
        getattr(rule, "le", None) == SEARCH_LIMIT_MAX for rule in accepted
    ), accepted


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_error_is_marked_as_error():
    """isError обязан отражать реальность, иначе агент примет отказ за успех."""
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        response = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_1c_element", "arguments": {}},
        })

    body = response.json()
    assert body["result"]["isError"] is True, body
    assert body["result"]["content"], "текст ошибки не передан агенту"


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_card_arrives_as_text():
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        response = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "get_1c_element",
                       "arguments": {"name": "НайтиСтроки", "object": "ТаблицаЗначений"}},
        })

    text = response.json()["result"]["content"][0]["text"]
    assert "Вызов: ТаблицаЗначений.НайтиСтроки" in text
    assert "Доступность:" in text


@pytest.mark.unit
@pytest.mark.parametrize("model_cls, kwargs", [
    ("Find1CHelpRequest", {"query": "х", "object_name": "Массив"}),
    ("Get1CElementRequest", {"name": "х", "object_name": "Массив"}),
    ("List1CObjectMembersRequest", {"object": "х", "member_type": "all"}),
])
def test_extra_argument_is_not_swallowed_silently(model_cls, kwargs):
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
def test_schema_declares_the_same_minimum_length_as_the_models():
    """Схема, обещающая больше, чем принимает сервер, отправляет модель в отказ.

    Модели запросов отвергают пустое имя (иначе term по пустой строке
    совпадает со всем индексом). Схема — единственное, по чему модель судит о
    допустимых значениях, и молчание схемы об этом ограничении означало бы, что
    об отказе она узнаёт только на живом вызове.
    """
    by_name = {t["name"]: t["inputSchema"]["properties"] for t in TOOLS}

    for tool, fields in (
        ("find_1c_help", ("query", "object")),
        ("get_1c_element", ("name", "object", "variant")),
        ("list_1c_object_members", ("object",)),
    ):
        for field in fields:
            assert by_name[tool][field].get("minLength") == 1, f"{tool}.{field}"


@pytest.mark.unit
@pytest.mark.parametrize("model_cls, kwargs", [
    ("Find1CHelpRequest", {"query": ""}),
    ("Find1CHelpRequest", {"query": "х", "object": ""}),
    ("Get1CElementRequest", {"name": ""}),
    ("Get1CElementRequest", {"name": "х", "object": ""}),
    ("Get1CElementRequest", {"name": "х", "variant": ""}),
    ("List1CObjectMembersRequest", {"object": ""}),
])
def test_empty_name_is_rejected_instead_of_matching_everything(model_cls, kwargs):
    """Пустая строка — не «фильтр не задан», а фильтр, совпадающий со всем.

    term по name_en.keyword == "" совпадает со всеми документами английского
    индекса: английские заголовки скобок не несут, поле пустое почти везде.
    get_1c_element(name="", lang="en") отвечал «имя принадлежит 10 000
    элементов» — то есть на явную ошибку вызова сервер отвечал длинным
    правдоподобным текстом, а не отказом.
    """
    import src.models.mcp_models as mcp_models
    from pydantic import ValidationError

    model = getattr(mcp_models, model_cls)
    with pytest.raises(ValidationError):
        model(**kwargs)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_error_kind_becomes_an_error_not_a_quiet_answer(monkeypatch):
    """element_card помечает сбой ES kind="error" — обработчик обязан
    вернуть isError, а не "элемент не найден".

    Ручной прогон проверил только пять честных исходов и живые вызовы — этот
    сбой без мока не воспроизвести (нужен настоящий обрыв ES), поэтому здесь
    подменяем сервис.
    """
    from src.handlers.mcp_handlers import handle_get_1c_element
    from src.models.mcp_models import Get1CElementRequest
    from src.search.search_service import SearchService

    async def fake_element_card(self, name, object_name=None, variant=None):
        return {"kind": "error", "name": name, "error": "Elasticsearch недоступен"}

    monkeypatch.setattr(SearchService, "element_card", fake_element_card)

    result = await handle_get_1c_element(Get1CElementRequest(name="Х"), es_client=None)

    assert result.error, "сбой сервиса обязан попасть в MCPResponse.error"
    assert "недоступен" in result.error


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_initialize_promises_no_extra_capabilities():
    """resources/prompts/roots/sampling убраны: заявленное, но не работающее
    хуже отсутствующего — клиент узнаёт о расхождении не заранее, а на вызове.
    """
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        response = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 40, "method": "initialize", "params": {},
        })

    assert response.json()["result"]["capabilities"] == {"tools": {}}


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_prompts_list_honestly_returns_method_not_found():
    """prompts/list раньше отдавал пустой список при неснятой capability —
    теперь метод не объявлен, и клиент честно получает -32601."""
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        response = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 41, "method": "prompts/list", "params": {},
        })

    assert response.json()["error"]["code"] == -32601


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_member_list_does_not_deny_object_over_one_missing_kind():
    """У ТаблицаЗначений нет событий, но сама она есть — инструмент не должен
    называть её "не найденной" и тут же предлагать её же как похожую."""
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        response = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 42, "method": "tools/call",
            "params": {"name": "list_1c_object_members",
                       "arguments": {"object": "ТаблицаЗначений", "members": "events"}},
        })

    text = response.json()["result"]["content"][0]["text"]
    assert "не найден" not in text, text
    assert "ТаблицаЗначений" in text


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_object_without_members_promises_no_phantom_element_on_all():
    """members="all" — значение по умолчанию, основной путь. У JSON нет ни
    одного настоящего метода/свойства/события/конструктора: раньше запрос
    ловил документ самого объекта (у него object тоже равен "JSON"), и ответ
    выглядел как "Показано 0 из 1" — агенту обещался скрытый элемент, а
    ветка "объект есть, но пуст" не срабатывала."""
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        response = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 46, "method": "tools/call",
            "params": {"name": "list_1c_object_members",
                       "arguments": {"object": "JSON", "members": "all"}},
        })

    text = response.json()["result"]["content"][0]["text"]
    assert "Показано 0 из 1" not in text, (
        "документ самого объекта не должен обещаться как скрытый член: " + text
    )
    assert "ни методов, ни свойств, ни событий, ни конструкторов у него не найдено" in text, text


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_hint_in_homonym_card_is_executable():
    """Совет "вызовите find_1c_help с limit=N" обязан укладываться в тот же
    потолок, что и схема find_1c_help, иначе агент получит validation error
    вместо списка, следуя честному на вид совету карточки."""
    import re
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        response = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 43, "method": "tools/call",
            "params": {"name": "get_1c_element", "arguments": {"name": "Количество"}},
        })

    text = response.json()["result"]["content"][0]["text"]
    match = re.search(r"limit=(\d+)", text)
    assert match, text
    suggested = int(match.group(1))
    assert suggested <= 200, "совет превышает потолок схемы find_1c_help"

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        verification = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 44, "method": "tools/call",
            "params": {"name": "find_1c_help",
                       "arguments": {"query": "Количество", "limit": suggested}},
        })

    body = verification.json()
    assert body["result"]["isError"] is False, body


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_old_param_name_gives_error_not_silent_drop():
    """object_name — упразднённое имя параметра get_1c_element (актуальное —
    object). Раньше pydantic тихо отбрасывал незнакомое поле, и вызов уходил
    без фильтра по объекту, возвращая список омонимов вместо карточки."""
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        response = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 45, "method": "tools/call",
            "params": {"name": "get_1c_element",
                       "arguments": {"name": "НайтиСтроки", "object_name": "ТаблицаЗначений"}},
        })

    body = response.json()
    assert body["result"]["isError"] is True, body


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_empty_search_result_distinguishes_no_element_from_no_object():
    """find_1c_help с object= обязан отличать «нет элемента» от «нет объекта».

    ФоновыеЗадания — канонический пример спеки §3.6: идентификатор из кода не
    совпадает с именем объекта справки (МенеджерФоновыхЗаданий). get_1c_element
    этот случай различал, а поиск с тем же аргументом отвечал «по запросу
    ничего не найдено» и советовал посмотреть состав несуществующего объекта.
    """
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        response = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 47, "method": "tools/call",
            "params": {"name": "find_1c_help",
                       "arguments": {"query": "Выполнить", "object": "ФоновыеЗадания"}},
        })

    text = response.json()["result"]["content"][0]["text"]
    assert "«ФоновыеЗадания» в справке не найден" in text, text
    assert "МенеджерФоновыхЗаданий" in text, text
    assert 'list_1c_object_members(object="ФоновыеЗадания")' not in text, (
        "состав несуществующего объекта советовать нельзя: " + text
    )


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_empty_search_result_names_the_kind_filter():
    """Если выдачу обнулил фильтр kind, об этом сказано прямо."""
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        response = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 48, "method": "tools/call",
            "params": {"name": "find_1c_help",
                       "arguments": {"query": "НайтиСтроки", "kind": "event"}},
        })

    text = response.json()["result"]["content"][0]["text"]
    assert 'kind="event"' in text, text
    assert 'kind="any"' in text, text


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_paging_hint_promises_nothing_impossible():
    """«Повторите с limit=200 за остальными» вернёт те же первые 200.

    Параметра смещения у find_1c_help нет, поэтому обещать «остальные» нельзя:
    рядом, в карточке омонимов, та же ситуация давно описана честно.
    """
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        response = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 49, "method": "tools/call",
            "params": {"name": "find_1c_help", "arguments": {"query": "Добавить"}},
        })

    text = response.json()["result"]["content"][0]["text"]
    assert "за остальными" not in text, text
    assert "За один вызов можно получить не более 200" in text, text


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_object_card_hint_is_executable():
    """Карточка объекта советует list_1c_object_members — совет обязан работать.

    Раньше в совет уходил удвоенный full_path
    («ТаблицаЗначений.ТаблицаЗначений»), и дословное исполнение совета
    отвечало «объект в справке не найден».
    """
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        card = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 50, "method": "tools/call",
            "params": {"name": "get_1c_element",
                       "arguments": {"name": "ТаблицаЗначений"}},
        })
        text = card.json()["result"]["content"][0]["text"]

        assert "Новый ТаблицаЗначений" in text, text
        assert 'list_1c_object_members(object="ТаблицаЗначений")' in text, text

        members_response = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 51, "method": "tools/call",
            "params": {"name": "list_1c_object_members",
                       "arguments": {"object": "ТаблицаЗначений"}},
        })

    members_text = members_response.json()["result"]["content"][0]["text"]
    assert "не найден" not in members_text, members_text
    assert "ТаблицаЗначений.НайтиСтроки" in members_text, members_text


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_unknown_tool_is_a_call_error_not_a_server_failure():
    """Промах по имени инструмента обязан читаться как промах вызывающего.

    Раньше MCPRequest бросал ValidationError на enum, тот долетал до общего
    except и возвращался как -32603 Internal error с трейсом pydantic. Агент
    делает из «internal error» вывод «сервер сломался» и прекращает попытки,
    вместо того чтобы исправить имя — а исправить было можно.
    """
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        response = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 52, "method": "tools/call",
            "params": {"name": "get_1c_help", "arguments": {"query": "x"}},
        })

    body = response.json()
    assert response.status_code == 400, body
    assert body["error"]["code"] == -32602, body

    message = body["error"]["message"]
    assert "get_1c_help" in message, message
    # Перечень имён — то, чем промах чинится: без него агент знает только, что
    # ошибся, но не знает чем заменить.
    for name in TOOL_NAMES:
        assert name in message, message
    assert "Internal error" not in message, message
    assert "pydantic" not in message, message


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_non_object_arguments_are_also_a_call_error():
    """arguments строкой вместо объекта — тот же класс: виноват вызов."""
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        response = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 53, "method": "tools/call",
            "params": {"name": "find_1c_help", "arguments": "query=x"},
        })

    body = response.json()
    assert response.status_code == 400, body
    assert body["error"]["code"] == -32602, body
    assert "Internal error" not in body["error"]["message"], body

"""Конверт JSON-RPC: что сервер отвечает, когда до инструмента дело не дошло.

Агент читает не текст ответа, а его форму. Ответ без jsonrpc и id читается
строгим клиентом как поломка транспорта, а не как ответ сервера.
"""

import httpx
import pytest

from src.api.dependencies import get_elasticsearch_client
from src.api.routes.mcp import TOOL_NAMES

pytestmark = pytest.mark.unit


async def _rpc(payload=None, content=None):
    """Запрос к /mcp внутри процесса: тот же роутер, без сервера и порта."""
    from unittest.mock import AsyncMock

    from src.main import app

    app.dependency_overrides.clear()
    app.dependency_overrides[get_elasticsearch_client] = lambda: AsyncMock()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            if content is not None:
                return await http.post(
                    "/mcp", content=content,
                    headers={"Content-Type": "application/json"},
                )
            return await http.post("/mcp", json=payload)
    finally:
        app.dependency_overrides.clear()


async def test_initialize_answers_with_the_handshake():
    response = await _rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize"})

    body = response.json()
    assert body["id"] == 1
    assert body["result"]["protocolVersion"]
    assert body["result"]["serverInfo"]["name"] == "1c-syntax-helper-mcp"


async def test_tools_list_names_every_tool_and_nothing_else():
    response = await _rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

    listed = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert listed == set(TOOL_NAMES)


async def test_an_unknown_method_is_method_not_found():
    response = await _rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/dance"})

    body = response.json()
    assert body["error"]["code"] == -32601
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 3


async def test_malformed_json_is_a_parse_error_that_still_looks_like_a_response():
    response = await _rpc(content=b"{ not json")

    body = response.json()
    assert body["error"]["code"] == -32700
    assert body["jsonrpc"] == "2.0"
    assert body["id"] is None


async def test_a_body_without_the_protocol_version_is_an_invalid_request():
    response = await _rpc({"id": 4, "method": "tools/list"})

    body = response.json()
    assert body["error"]["code"] == -32600
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 4

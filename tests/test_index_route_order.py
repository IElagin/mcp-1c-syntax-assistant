"""POST /index/rebuild проверяет отсутствие книги раньше, чем Elasticsearch.

Обе проверки в rebuild_index дешёвая (Path.exists) и сетевая
(es_client.is_connected). Порядок важен: при недоступном Elasticsearch и
отсутствующей книге вызывающий должен узнать про книгу — иначе после починки
Elasticsearch запрос всё равно упадёт, теперь по настоящей причине.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI

from src.api.dependencies import get_elasticsearch_client
from src.api.routes.index import router as index_router


pytestmark = pytest.mark.unit


def make_app(es_client) -> FastAPI:
    app = FastAPI()
    app.include_router(index_router)
    app.dependency_overrides[get_elasticsearch_client] = lambda: es_client
    return app


async def test_missing_book_is_reported_even_when_elasticsearch_is_down():
    """Книга отсутствует и Elasticsearch недоступен — ответ про книгу, не про Elasticsearch."""
    es_client = AsyncMock()
    es_client.is_connected = AsyncMock(return_value=False)

    app = make_app(es_client)
    transport = httpx.ASGITransport(app=app)

    with patch("src.api.routes.index.resolve_hbk_file", return_value=None):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/index/rebuild")

    assert response.status_code == 400, response.text
    assert "не найдена" in response.json()["detail"]

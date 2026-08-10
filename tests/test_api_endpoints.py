"""Ответы /health и /index/status — как их видит клиент, а не как их пишет код.

Оба эндпоинта не имели ни одного теста, и дефект «index_exists сериализуется в
{} вместо true» прожил из-за этого восемь месяцев: клиент читал {} как
отсутствие индекса при полном индексе. Поэтому здесь проверяется именно JSON
ответа, а index_exists мокается настоящим HeadApiResponse — тем самым типом,
который возвращает elasticsearch.indices.exists().

Мок, возвращающий готовый bool (как все прочие моки набора), эту регрессию не
поймал бы: bool сериализуется правильно и без обёртки в коде.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from elastic_transport import ApiResponseMeta, HeadApiResponse, HttpHeaders, NodeConfig
from fastapi import FastAPI

from src.api.dependencies import get_elasticsearch_client, get_indexing_manager
from src.api.routes.health import router as health_router
from src.api.routes.index import router as index_router
from src.core.config import settings
from src.models.index_status import IndexingStatus, IndexProgressInfo
from tests.conftest import write_book


pytestmark = pytest.mark.unit

_NODE = NodeConfig(scheme="http", host="localhost", port=9200)


def head_response(exists: bool) -> HeadApiResponse:
    """Ровно то, что отдаёт elasticsearch.indices.exists(): не bool.

    HeadApiResponse истинен по HTTP-статусу и при этом сериализуется в {} —
    в этом и был дефект. Подделывать его классом-заглушкой нельзя: заглушка
    сериализуется иначе, и тест перестал бы проверять исходный случай.
    """
    meta = ApiResponseMeta(
        status=200 if exists else 404,
        http_version="1.1",
        headers=HttpHeaders({}),
        duration=0.0,
        node=_NODE,
    )
    return HeadApiResponse(meta=meta)


def make_client(
    *,
    connected: bool = True,
    ru_index: bool = True,
    en_index: bool = True,
    ru_docs: int = 23125,
    en_docs: int = 23104,
) -> AsyncMock:
    """Клиент ES, отвечающий как настоящий: HeadApiResponse, а не bool."""
    client = AsyncMock()
    client.is_connected = AsyncMock(return_value=connected)

    async def index_exists(index=None):
        return head_response(en_index if index == settings.elasticsearch_index_en
                             else ru_index)

    async def documents_count(index=None):
        return en_docs if index == settings.elasticsearch_index_en else ru_docs

    client.index_exists = AsyncMock(side_effect=index_exists)
    client.get_documents_count = AsyncMock(side_effect=documents_count)
    return client


def make_manager(active: bool = False) -> MagicMock:
    manager = MagicMock()
    manager.get_status = AsyncMock(return_value=IndexProgressInfo(
        status=IndexingStatus.COMPLETED, total_documents=23125,
        indexed_documents=23125,
    ))
    manager.is_indexing = MagicMock(return_value=active)
    return manager


def make_app(es_client, manager) -> FastAPI:
    """Приложение из тех же роутеров, что и прод, но без ES и lifespan.

    Роутеры подключаются настоящие: дефект был в сериализации ответа FastAPI,
    и прямой вызов функции-обработчика его бы не показал — она возвращает
    правильный объект, а неправильным становится JSON.
    """
    app = FastAPI()
    app.include_router(health_router)
    app.include_router(index_router)
    app.dependency_overrides[get_elasticsearch_client] = lambda: es_client
    app.dependency_overrides[get_indexing_manager] = lambda: manager
    return app


async def get_json(app: FastAPI, url: str) -> dict:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(url)
    assert response.status_code == 200, response.text
    return response.json()


async def test_health_reports_index_presence_as_a_json_boolean():
    """index_exists обязан приехать true, а не {}.

    Дефект (7dcc1cc8, восемь месяцев в проде) выглядел именно так: клиент,
    ждущий готовности индекса, читал {} как «индекса нет» при 23 125
    документах в нём.
    """
    body = await get_json(make_app(make_client(), make_manager()), "/health")

    assert body["index_exists"] is True
    assert body["index_en_exists"] is True
    assert body["documents_count"] == 23125
    assert body["documents_count_en"] == 23104
    assert body["status"] == "healthy"


async def test_index_status_reports_index_presence_as_a_json_boolean():
    """Та же проверка для второй ручки: обёртку сняли именно здесь."""
    body = await get_json(make_app(make_client(), make_manager()), "/index/status")

    assert body["index_exists"] is True
    assert body["elasticsearch_connected"] is True
    assert body["documents_count"] == 23125
    assert body["index_name"] == settings.elasticsearch.index_name


async def test_health_says_english_index_is_absent_without_calling_it_unhealthy():
    """Английская книга необязательна: её отсутствие — не болезнь сервера."""
    client = make_client(en_index=False)

    body = await get_json(make_app(client, make_manager()), "/health")

    assert body["status"] == "healthy"
    assert body["index_exists"] is True
    assert body["index_en_exists"] is False
    assert body["documents_count_en"] is None


async def test_health_without_elasticsearch_is_unhealthy_and_claims_no_indexes():
    """Без связи с ES о наличии индексов ничего не известно — значит False.

    Здесь важно, что index_exists не вызывается вовсе: ответ «индекс есть»,
    полученный при оборванной связи, был бы выдумкой.
    """
    client = make_client(connected=False)

    body = await get_json(make_app(client, make_manager()), "/health")

    assert body["status"] == "unhealthy"
    assert body["index_exists"] is False
    assert body["index_en_exists"] is False
    assert body["documents_count"] is None
    client.index_exists.assert_not_called()


async def test_index_status_carries_the_background_indexing_block():
    body = await get_json(make_app(make_client(), make_manager(active=True)),
                          "/index/status")

    assert body["indexing"]["is_active"] is True
    assert body["indexing"]["status"] == IndexingStatus.COMPLETED.value


async def test_health_reports_the_article_books_missing_from_each_language(tmp_path, monkeypatch):
    """missing_article_books/_en идут через настоящий обработчик, а не мимо него."""
    ru_dir, en_dir = tmp_path / "ru", tmp_path / "en"
    ru_dir.mkdir()
    en_dir.mkdir()
    write_book(ru_dir / "shlang_ru.hbk", {"struct_For": b"<h1>For</h1>"})
    write_book(en_dir / "shlang_root.hbk", {"struct_For": b"<h1>For</h1>"})
    monkeypatch.setattr(settings, "hbk_directory", str(ru_dir))
    monkeypatch.setattr(settings, "hbk_directory_en", str(en_dir))

    body = await get_json(make_app(make_client(), make_manager()), "/health")

    assert body["missing_article_books"] == ["shquery", "shclang", "dcsui"]
    assert body["missing_article_books_en"] == ["shquery", "shclang", "dcsui"]

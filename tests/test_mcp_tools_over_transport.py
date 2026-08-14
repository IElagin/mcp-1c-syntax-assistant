"""Инструменты через /mcp: тот же роутер, что у агента, но внутри процесса.

Раньше эти проверки требовали живого сервера на :8000 и заполненного боевого
индекса, поэтому в CI не запускались ни разу. Индекс здесь свой, фикстурный, а
до роутера дотягивается ASGI — сервер не нужен.
"""

import httpx
import pytest

from src.api.dependencies import get_elasticsearch_client
from src.core.elasticsearch import ElasticsearchClient
from src.handlers.ui_strings import EN_STRINGS, RU_STRINGS
from src.models.doc_models import HBKFile, ParsedHBK
from src.parsers.article_books import parse_article_books
from src.parsers.hbk_parser import HBKParser
from src.parsers.indexer import ElasticsearchIndexer

pytestmark = [pytest.mark.integration, pytest.mark.elasticsearch]


@pytest.fixture
async def transport_on_a_fixture_index(
    hbk_fixture_archive, article_books_directory, isolated_index, monkeypatch
):
    """Клиент к /mcp, за которым лежат фикстурные карточки и статьи."""
    parsed = HBKParser().parse_file(str(hbk_fixture_archive))
    assert parsed is not None, "парсер не открыл фикстурную книгу карточек"
    articles, _ = parse_article_books(str(article_books_directory), "ru")
    parsed.documentation.extend(articles)

    client = ElasticsearchClient()
    assert await client.connect(), "Elasticsearch недоступен"
    try:
        assert await ElasticsearchIndexer(client, index=isolated_index).reindex_all(parsed)
        await client.refresh_index(index=isolated_index)
        monkeypatch.setattr(
            "src.handlers.mcp_handlers.index_for", lambda lang: isolated_index
        )

        from src.main import app

        app.dependency_overrides.clear()
        app.dependency_overrides[get_elasticsearch_client] = lambda: client
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            yield http
        app.dependency_overrides.clear()
    finally:
        await client.disconnect()


async def _call(http, tool: str, arguments: dict, request_id: int = 1):
    response = await http.post("/mcp", json={
        "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    })
    return response.json()["result"]


async def test_a_refused_call_is_marked_as_an_error(transport_on_a_fixture_index):
    """isError обязан отражать реальность, иначе агент примет отказ за успех."""
    result = await _call(transport_on_a_fixture_index, "get_1c_element", {})

    assert result["isError"] is True, result
    assert result["content"], "текст ошибки не передан агенту"


async def test_a_card_arrives_as_text(transport_on_a_fixture_index):
    result = await _call(
        transport_on_a_fixture_index, "get_1c_element", {"name": "Массив"}
    )

    text = result["content"][0]["text"]
    assert result["isError"] is False, result
    assert text.splitlines()[0] == f"Массив — {RU_STRINGS.object_word}", text


@pytest.fixture
async def transport_on_an_english_index(
    article_books_directory, isolated_index, monkeypatch
):
    """Клиент к /mcp, за которым лежат английские фикстурные статьи."""
    articles, _ = parse_article_books(str(article_books_directory), "en")
    assert articles, "английские фикстурные книги не дали ни одной статьи"

    parsed = ParsedHBK(
        file_info=HBKFile(path="fixture-en", size=0, modified=0.0),
        documentation=articles,
    )

    client = ElasticsearchClient()
    assert await client.connect(), "Elasticsearch недоступен"
    try:
        assert await ElasticsearchIndexer(client, index=isolated_index).reindex_all(parsed)
        await client.refresh_index(index=isolated_index)
        monkeypatch.setattr(
            "src.handlers.mcp_handlers.index_for", lambda lang: isolated_index
        )

        from src.main import app

        app.dependency_overrides.clear()
        app.dependency_overrides[get_elasticsearch_client] = lambda: client
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            yield http
        app.dependency_overrides.clear()
    finally:
        await client.disconnect()


@pytest.mark.parametrize("article_books_directory", ["en"], indirect=True)
async def test_an_english_article_travels_the_whole_path(transport_on_an_english_index):
    """Английская книга, английский индекс, английские подписи — до ответа агенту."""
    result = await _call(
        transport_on_an_english_index, "get_1c_article",
        {"name": "Array", "lang": "en"},
    )

    text = result["content"][0]["text"]
    assert result["isError"] is False, result
    assert EN_STRINGS.article_book.format(book=EN_STRINGS.book_names["shlang"]) in text, text
    assert "stores values by index" in text, text

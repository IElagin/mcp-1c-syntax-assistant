"""Карточка и статья с одним именем лежат в одном индексе и не спорят.

Регрессия 2.3.0: get_1c_element считал статью кандидатом, и «Массив» переставал
быть однозначным. Ни один тест не мог этого увидеть — карточки и статьи никогда
не попадали в один индекс.
"""

import pytest

from src.core.elasticsearch import ElasticsearchClient
from src.handlers.mcp_handlers import (
    handle_find_1c_help, handle_get_1c_article, handle_get_1c_element,
)
from src.handlers.ui_strings import RU_STRINGS
from src.models.mcp_models import (
    Find1CHelpRequest, Get1CArticleRequest, Get1CElementRequest,
)
from src.parsers.article_books import parse_article_books
from src.parsers.hbk_parser import HBKParser
from src.parsers.indexer import ElasticsearchIndexer

pytestmark = [pytest.mark.integration, pytest.mark.elasticsearch, pytest.mark.indexer]

COLLIDING_NAME = "Массив"


def _text(response) -> str:
    return response.content[0]["text"]


@pytest.fixture
async def client_on_a_mixed_index(
    hbk_fixture_archive, article_books_directory, isolated_index, monkeypatch
):
    """Клиент к индексу, где лежат и фикстурные карточки, и фикстурные статьи."""
    parsed = HBKParser().parse_file(str(hbk_fixture_archive))
    assert parsed is not None, "парсер не открыл фикстурную книгу карточек"
    articles, absent = parse_article_books(str(article_books_directory), "ru")
    assert absent == ["shclang"], absent
    parsed.documentation.extend(articles)

    client = ElasticsearchClient()
    assert await client.connect(), "Elasticsearch недоступен"
    try:
        assert await ElasticsearchIndexer(client, index=isolated_index).reindex_all(parsed)
        await client.refresh_index(index=isolated_index)
        monkeypatch.setattr(
            "src.handlers.mcp_handlers.index_for", lambda lang: isolated_index
        )
        yield client
    finally:
        await client.disconnect()


async def test_the_card_tool_answers_with_the_card_not_the_article(client_on_a_mixed_index):
    response = await handle_get_1c_element(
        Get1CElementRequest(name=COLLIDING_NAME), client_on_a_mixed_index
    )

    text = _text(response)
    assert text.splitlines()[0] == f"{COLLIDING_NAME} — {RU_STRINGS.object_word}", text
    assert "хранит значения по индексу" not in text, text


async def test_the_article_tool_answers_with_the_article_not_the_card(client_on_a_mixed_index):
    response = await handle_get_1c_article(
        Get1CArticleRequest(name=COLLIDING_NAME), client_on_a_mixed_index
    )

    text = _text(response)
    assert RU_STRINGS.article_book.format(book=RU_STRINGS.book_names["shlang"]) in text, text
    assert "хранит значения по индексу" in text, text


async def test_the_hint_names_the_tool_that_will_answer(client_on_a_mixed_index):
    """Выдача смешанная — совет обязан назвать оба инструмента."""
    response = await handle_find_1c_help(
        Find1CHelpRequest(query=COLLIDING_NAME, limit=20), client_on_a_mixed_index
    )

    text = _text(response)
    assert RU_STRINGS.full_card_hint_generic in text, text
    assert RU_STRINGS.full_article_hint_generic in text, text

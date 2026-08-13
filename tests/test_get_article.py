"""Инструмент get_1c_article."""

import pytest

from src.handlers.element_card import render_article
from src.handlers.ui_strings import EN_STRINGS, RU_STRINGS
from src.models.mcp_models import Get1CArticleRequest, MCPToolType

ARTICLE = {
    "type": "article",
    "element_kind": "статья",
    "name": "Для (For)",
    "name_ru": "Для",
    "name_en": "For",
    "book": "shlang",
    "full_path": "shlang/struct_For",
    "description": "Для (For) Синтаксис: Для <Имя переменной> = <Выражение 1> По <Выражение 2> Цикл. Оператор цикла Для предназначен для циклического повторения операторов.",
}


def test_article_request_accepts_a_book_and_rejects_unknown_fields():
    request = Get1CArticleRequest(name="Для", book="shlang")
    assert request.name == "Для"
    assert request.book == "shlang"
    with pytest.raises(ValueError):
        Get1CArticleRequest(name="Для", object="Массив")


def test_the_tool_has_its_own_name():
    assert MCPToolType.GET_1C_ARTICLE.value == "get_1c_article"


def test_rendered_article_names_its_book_and_keeps_the_whole_text():
    card = render_article(ARTICLE, RU_STRINGS)
    assert "Для (For)" in card
    assert "язык 1С" in card
    assert "циклического повторения" in card


from unittest.mock import AsyncMock

from src.search.search_service import SearchService


def _hits(*sources) -> dict:
    return {"hits": {"hits": [{"_source": s} for s in sources],
                     "total": {"value": len(sources)}}}


async def test_one_matching_article_comes_back_as_the_article():
    client = AsyncMock()
    client.search = AsyncMock(return_value=_hits(ARTICLE))

    answer = await SearchService(client).article("Для (For)")

    assert answer["kind"] == "article"
    assert answer["document"]["book"] == "shlang"


async def test_a_title_in_two_books_comes_back_ambiguous():
    """Кандидаты названы вместе с книгами, чтобы повтор был однозначным."""
    other = dict(ARTICLE, book="shquery", full_path="shquery/root.html")
    client = AsyncMock()
    client.search = AsyncMock(return_value=_hits(ARTICLE, other))

    answer = await SearchService(client).article("Синтаксис")

    assert answer["kind"] == "ambiguous"
    assert {c["book"] for c in answer["candidates"]} == {"shlang", "shquery"}


async def test_an_index_without_articles_says_so_instead_of_not_found():
    """«Не проиндексировано» и «не найдено» — разные ответы."""
    client = AsyncMock()
    client.search = AsyncMock(side_effect=[_hits(), _hits()])

    answer = await SearchService(client).article("Для (For)")

    assert answer["kind"] == "not_indexed"


async def test_an_index_with_articles_reports_a_missing_one_as_not_found():
    client = AsyncMock()
    client.search = AsyncMock(side_effect=[
        _hits(),                    # точного совпадения нет
        _hits(ARTICLE),             # но статьи в индексе есть
        _hits(ARTICLE),             # похожие по имени
    ])

    answer = await SearchService(client).article("Пока чего-нибудь")

    assert answer["kind"] == "not_found"
    assert answer["similar"]


async def test_book_narrows_an_ambiguous_title():
    client = AsyncMock()
    client.search = AsyncMock(return_value=_hits(ARTICLE))

    await SearchService(client).article("Синтаксис", book="shlang")

    body = client.search.await_args.args[0]
    assert {"term": {"book": "shlang"}} in body["query"]["bool"]["filter"]


def test_not_indexed_message_does_not_claim_the_books_are_missing():
    """Проверялся индекс, а не каталог: утверждать про файлы сервер не вправе.

    Английские книги статей могут лежать на диске, а в индексе их не быть —
    именно так и было на рабочем контуре, а сообщение заявляло, что книг нет.
    """
    for strings in (RU_STRINGS, EN_STRINGS):
        message = strings.articles_not_indexed
        assert "нет в каталоге" not in message
        assert "are absent from" not in message
        assert "missing_article_books" in message

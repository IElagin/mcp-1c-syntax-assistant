"""Ни одна беда книги статей не стоит индексации книги карточек."""

from unittest.mock import AsyncMock, patch

import pytest

import src.parsers.article_books as article_books
from src.infrastructure.indexing import index_hbk_file
from src.parsers.article_books import parse_article_books
from tests.conftest import write_book

pytestmark = [pytest.mark.unit, pytest.mark.parser]

CARD_PAGE = "<html><h1>Массив (Array)</h1></html>".encode("utf-8")
ARTICLE_PAGE = "<h1>Для (For)</h1><p>Оператор цикла встроенного языка.</p>".encode("utf-8")
BOOKS_WITHOUT_SHLANG = ["shquery", "shclang", "dcsui"]


def test_a_book_path_that_is_not_a_readable_file_costs_only_that_book(tmp_path):
    """Каталог с именем книги: чтение падает раньше HelpBookArchiveError."""
    write_book(tmp_path / "shlang_ru.hbk", {"struct_For": ARTICLE_PAGE})
    (tmp_path / "shquery_ru.hbk").mkdir()

    articles, absent = parse_article_books(str(tmp_path), "ru")

    assert [article.name for article in articles] == ["Для (For)"]
    assert absent == BOOKS_WITHOUT_SHLANG


def test_a_file_whose_parse_raises_costs_only_that_file(tmp_path):
    """Разбор статьи бросает так же, как чтение и декодирование, и стоит того же."""
    write_book(
        tmp_path / "shlang_ru.hbk", {"struct_For": ARTICLE_PAGE, "struct_While": ARTICLE_PAGE}
    )
    parse_one_file = article_books.parse_article_file

    def parse_but_break_on_one_file(book, file_name, html):
        if file_name == "struct_While":
            raise RecursionError("разметка вложена глубже, чем разбирает bs4")
        return parse_one_file(book, file_name, html)

    with patch("src.parsers.article_books.parse_article_file", parse_but_break_on_one_file):
        articles, absent = parse_article_books(str(tmp_path), "ru")

    assert [article.source_file for article in articles] == ["shlang/struct_For"]
    assert absent == BOOKS_WITHOUT_SHLANG


async def test_the_card_book_is_indexed_although_an_article_book_is_unreadable(tmp_path):
    """23125 карточек не должны зависеть от одной необязательной книги на 170 КБ."""
    card_book = write_book(tmp_path / "shcntx_ru.hbk", {"objects/catalog1.html": CARD_PAGE})
    write_book(tmp_path / "shlang_ru.hbk", {"struct_For": ARTICLE_PAGE})
    (tmp_path / "shquery_ru.hbk").mkdir()

    with patch(
        "src.parsers.indexer.ElasticsearchIndexer.reindex_all", new=AsyncMock(return_value=True)
    ) as reindex:
        result = await index_hbk_file(str(card_book), AsyncMock(), index="ignored")

    assert result is True
    reindex.assert_awaited_once()
    indexed = reindex.await_args.args[0].documentation
    assert [document.name for document in indexed if document.book == "shlang"] == ["Для (For)"]

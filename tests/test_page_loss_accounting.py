"""Потерянная страница считается потерянной, чем бы разбор ни кончился."""

from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.indexing import index_hbk_file
from src.models.doc_models import Documentation, DocumentType
from src.parsers.dialects import dialect_for
from src.parsers.hbk_parser import HBKParser
from tests.conftest import write_book

pytestmark = [pytest.mark.unit, pytest.mark.parser, pytest.mark.indexer]

PAGES = 100


def _book_of_object_pages(tmp_path, pages: int = PAGES):
    return write_book(
        tmp_path / "shcntx_ru.hbk",
        {
            f"objects/catalog{number}.html":
                f"<html><h1>Метод{number}</h1></html>".encode("utf-8")
            for number in range(pages)
        },
    )


def _card(number: int) -> Documentation:
    return Documentation(
        id=f"doc{number}", type=DocumentType.OBJECT_FUNCTION, name=f"Метод{number}"
    )


def _parser_that_survives_only_the_first_page(outcome_for_the_rest):
    """Разбор HTML, который отдаёт документ по первой странице и спотыкается на прочих."""
    pages_seen = []

    def parse_html_content(self, content, file_path):
        pages_seen.append(file_path)
        if len(pages_seen) == 1:
            return _card(0)
        if isinstance(outcome_for_the_rest, Exception):
            raise outcome_for_the_rest
        return outcome_for_the_rest

    return parse_html_content


def _parse_book(path, outcome_for_the_rest):
    with patch(
        "src.parsers.html_parser.HTMLParser.parse_html_content",
        _parser_that_survives_only_the_first_page(outcome_for_the_rest),
    ):
        return HBKParser(dialect=dialect_for("ru")).parse_file(str(path))


def test_a_page_the_html_parser_returns_nothing_for_counts_as_lost(tmp_path):
    parsed = _parse_book(_book_of_object_pages(tmp_path), outcome_for_the_rest=None)

    assert parsed.pages_attempted == PAGES
    assert parsed.pages_parsed == 1
    assert parsed.lost_pages_share == pytest.approx(0.99)
    assert parsed.errors == [], "нечитаемых страниц не было — список ошибок остаётся пустым"


def test_a_page_whose_parse_raises_counts_as_lost(tmp_path):
    parsed = _parse_book(
        _book_of_object_pages(tmp_path),
        outcome_for_the_rest=RuntimeError("разметка страницы сломалась"),
    )

    assert parsed.pages_attempted == PAGES
    assert parsed.pages_parsed == 1
    assert parsed.lost_pages_share == pytest.approx(0.99)
    assert parsed.errors == []


async def test_a_book_that_lost_almost_all_pages_to_parsing_never_reaches_the_index(tmp_path):
    """Ровно та подмена, ради которой существует порог: 23125 документов на один."""
    path = _book_of_object_pages(tmp_path)

    with patch(
        "src.parsers.html_parser.HTMLParser.parse_html_content",
        _parser_that_survives_only_the_first_page(RuntimeError("разметка страницы сломалась")),
    ), patch(
        "src.parsers.indexer.ElasticsearchIndexer.reindex_all", new=AsyncMock(return_value=True)
    ) as reindex:
        result = await index_hbk_file(str(path), AsyncMock(), index="ignored")

    assert not result.ok, result
    reindex.assert_not_awaited()


def test_pages_dropped_by_deduplication_are_not_counted_as_lost(tmp_path):
    """Английская книга законно даёт 23125 разобранных страниц и 23104 документа."""
    path = _book_of_object_pages(tmp_path, pages=3)
    parsed_pages = iter([
        Documentation(
            id="Массив", type=DocumentType.OBJECT, name="Массив", description="Коллекция значений"
        ),
        Documentation(id="Массив", type=DocumentType.OBJECT, name="Массив"),
        Documentation(
            id="Структура", type=DocumentType.OBJECT, name="Структура", description="Коллекция"
        ),
    ])

    with patch(
        "src.parsers.html_parser.HTMLParser.parse_html_content",
        lambda self, content, file_path: next(parsed_pages),
    ):
        parsed = HBKParser(dialect=dialect_for("ru")).parse_file(str(path))

    assert parsed.pages_attempted == 3
    assert parsed.pages_parsed == 3
    assert len(parsed.documentation) == 2
    assert parsed.lost_pages_share == 0.0

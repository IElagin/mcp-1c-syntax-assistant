"""Индексация называет, чем кончилась, а не отвечает булевым."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.indexing import index_hbk_file
from src.models.doc_models import Documentation, DocumentType, HBKFile, ParsedHBK
from src.models.indexing_outcome import IndexingOutcome, OutcomeKind

pytestmark = [pytest.mark.unit, pytest.mark.indexer]

BOOK = "data/hbk/shcntx_ru.hbk"


def _parsed(documents: int = 1, attempted: int = 1, parsed_pages: int = 1) -> ParsedHBK:
    book = ParsedHBK(file_info=HBKFile(path=BOOK, size=0, modified=0.0))
    book.documentation = [
        Documentation(
            id=f"doc{number}", name=f"Элемент{number}",
            type=DocumentType.OBJECT_PROPERTY, source_file=f"objects/p{number}.html",
        )
        for number in range(documents)
    ]
    book.pages_attempted = attempted
    book.pages_parsed = parsed_pages
    return book


async def _outcome_of(parse_result, *, reindex=True) -> IndexingOutcome:
    with patch("src.parsers.hbk_parser.HBKParser.parse_file", return_value=parse_result), \
         patch("src.parsers.article_books.parse_article_books", return_value=([], [])), \
         patch("src.parsers.indexer.ElasticsearchIndexer.reindex_all",
               new=AsyncMock(return_value=reindex)):
        client = AsyncMock()
        client.get_documents_count = AsyncMock(return_value=1)
        return await index_hbk_file(BOOK, client, index="ignored")


async def test_a_book_that_does_not_parse_says_so():
    outcome = await _outcome_of(None)

    assert outcome.kind is OutcomeKind.PARSE_FAILED
    assert outcome.details["file_path"] == BOOK
    assert not outcome.ok


async def test_a_book_that_parses_into_nothing_is_not_the_same_as_a_parse_failure():
    outcome = await _outcome_of(_parsed(documents=0))

    assert outcome.kind is OutcomeKind.NOTHING_TO_INDEX
    assert outcome.details["file_path"] == BOOK


async def test_a_book_that_lost_too_many_pages_carries_the_numbers():
    outcome = await _outcome_of(_parsed(documents=1, attempted=100, parsed_pages=90))

    assert outcome.kind is OutcomeKind.PAGE_LOSS_TOO_HIGH
    assert outcome.details["parsed"] == 90
    assert outcome.details["attempted"] == 100
    assert outcome.details["share"] == pytest.approx(0.1)


async def test_a_refused_write_is_not_a_parse_failure():
    outcome = await _outcome_of(_parsed(), reindex=False)

    assert outcome.kind is OutcomeKind.INDEX_WRITE_FAILED
    assert outcome.details["index"] == "ignored"


async def test_a_successful_run_counts_what_it_indexed():
    outcome = await _outcome_of(_parsed(documents=3))

    assert outcome.kind is OutcomeKind.INDEXED
    assert outcome.ok
    assert outcome.details["documents"] == 3
    assert outcome.details["articles"] == 0


async def test_an_escaping_exception_carries_its_text():
    with patch("src.parsers.hbk_parser.HBKParser.parse_file",
               side_effect=MemoryError("не хватило памяти")):
        outcome = await index_hbk_file(BOOK, AsyncMock(), index="ignored")

    assert outcome.kind is OutcomeKind.ERROR
    assert "не хватило памяти" in outcome.details["error"]


async def test_five_refusals_are_five_different_kinds():
    """Один и тот же ответ на пять разных причин — это и был дефект."""
    kinds = {
        (await _outcome_of(None)).kind,
        (await _outcome_of(_parsed(documents=0))).kind,
        (await _outcome_of(_parsed(documents=1, attempted=100, parsed_pages=90))).kind,
        (await _outcome_of(_parsed(), reindex=False)).kind,
    }

    assert len(kinds) == 4

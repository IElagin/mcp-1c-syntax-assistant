"""index_hbk_file отличает царапину книги от её ампутации по доле потерянных страниц."""

import logging
from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.indexing import index_hbk_file
from src.models.doc_models import Documentation, DocumentType, HBKFile, ParsedHBK

pytestmark = [pytest.mark.unit, pytest.mark.indexer]


def _parsed(documentation, errors, pages_attempted=None):
    """Книга, у которой страниц было pages_attempted, а документов вышло len(documentation)."""
    return ParsedHBK(
        file_info=HBKFile(path="test.hbk", size=0, modified=0.0),
        documentation=documentation,
        errors=errors,
        pages_attempted=pages_attempted if pages_attempted is not None else len(documentation),
        pages_parsed=len(documentation),
    )


def _docs(count: int):
    docs = []
    for n in range(count):
        doc = Documentation(id=f"doc{n}", type=DocumentType.OBJECT_FUNCTION, name=f"Метод{n}")
        doc.build_call_strings()
        docs.append(doc)
    return docs


async def test_a_book_that_lost_a_small_share_of_pages_is_still_indexed(tmp_path, caplog):
    """1 страница из 100 (1%) — ниже порога, книга индексируется, потеря видна в предупреждении."""
    parsed = _parsed(_docs(99), errors=["страница X не читается"], pages_attempted=100)

    with patch("src.parsers.hbk_parser.HBKParser.parse_file", return_value=parsed), \
         patch(
             "src.parsers.indexer.ElasticsearchIndexer.reindex_all",
             new=AsyncMock(return_value=True),
         ) as reindex:
        with caplog.at_level(logging.WARNING):
            result = await index_hbk_file(str(tmp_path / "book.hbk"), AsyncMock(), index="ignored")

    assert result is True
    reindex.assert_awaited_once()
    assert any("потеряно страниц" in message for message in caplog.messages)


async def test_a_book_that_lost_most_of_its_pages_is_refused_and_the_index_is_left_alone(tmp_path, caplog):
    """95 страниц из 100 (95%) — выше порога, переиндексация не запускается, старый индекс цел."""
    parsed = _parsed(
        _docs(5), errors=[f"страница {n} не читается" for n in range(95)], pages_attempted=100
    )

    with patch("src.parsers.hbk_parser.HBKParser.parse_file", return_value=parsed), \
         patch(
             "src.parsers.indexer.ElasticsearchIndexer.reindex_all",
             new=AsyncMock(return_value=True),
         ) as reindex:
        with caplog.at_level(logging.ERROR):
            result = await index_hbk_file(str(tmp_path / "book.hbk"), AsyncMock(), index="ignored")

    assert result is False
    reindex.assert_not_awaited()
    assert any("отклонена" in message for message in caplog.messages)


async def test_a_book_that_produced_no_documentation_is_refused_without_indexing(tmp_path):
    parsed = _parsed([], errors=["книгу не удалось открыть"])

    with patch("src.parsers.hbk_parser.HBKParser.parse_file", return_value=parsed), \
         patch(
             "src.parsers.indexer.ElasticsearchIndexer.reindex_all",
             new=AsyncMock(return_value=True),
         ) as reindex:
        result = await index_hbk_file(str(tmp_path / "book.hbk"), AsyncMock(), index="ignored")

    assert result is False
    reindex.assert_not_awaited()

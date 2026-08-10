"""index_hbk_file отличает потерю нескольких страниц от полной неудачи чтения книги."""

import logging
from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.indexing import index_hbk_file
from src.models.doc_models import Documentation, DocumentType, HBKFile, ParsedHBK

pytestmark = [pytest.mark.unit, pytest.mark.indexer]


def _parsed(documentation, errors):
    return ParsedHBK(
        file_info=HBKFile(path="test.hbk", size=0, modified=0.0),
        documentation=documentation,
        errors=errors,
    )


def _doc(name: str) -> Documentation:
    doc = Documentation(id=name, type=DocumentType.OBJECT_FUNCTION, name=name)
    doc.build_call_strings()
    return doc


async def test_a_book_that_lost_some_pages_is_still_indexed(tmp_path, caplog):
    parsed = _parsed([_doc("Добавить"), _doc("Удалить")], errors=["страница X не читается"])

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

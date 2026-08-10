"""Фоновая индексация при старте идёт тем же путём, что и ручная переиндексация."""

from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.background.indexing_manager import BackgroundIndexingManager
from src.models.doc_models import Documentation, DocumentType
from src.models.index_status import IndexingStatus
from tests.conftest import write_book

pytestmark = [pytest.mark.unit, pytest.mark.indexer]

CARD_PAGE = "<html><h1>Массив (Array)</h1></html>".encode("utf-8")
ARTICLE_PAGE = "<h1>Для (For)</h1><p>Оператор цикла встроенного языка.</p>".encode("utf-8")


def _card_book_next_to_an_article_book(tmp_path, card_pages: int = 1):
    write_book(
        tmp_path / "shcntx_ru.hbk",
        {f"objects/catalog{number}.html": CARD_PAGE for number in range(card_pages)},
    )
    write_book(tmp_path / "shlang_ru.hbk", {"struct_For": ARTICLE_PAGE})
    return tmp_path / "shcntx_ru.hbk"


async def test_background_indexing_carries_the_articles_of_the_neighbouring_books(tmp_path):
    """Сервер, поднятый с четырьмя книгами статей, обязан отвечать на get_1c_article."""
    card_book = _card_book_next_to_an_article_book(tmp_path)
    manager = BackgroundIndexingManager()

    with patch(
        "src.parsers.indexer.ElasticsearchIndexer.reindex_all", new=AsyncMock(return_value=True)
    ) as reindex:
        await manager._do_indexing(str(card_book), AsyncMock(), index="ignored", lang="ru")

    indexed = reindex.await_args.args[0].documentation
    assert DocumentType.ARTICLE.value in [document.type.value for document in indexed]
    assert (await manager.get_status()).status is IndexingStatus.COMPLETED


async def test_background_indexing_refuses_a_book_that_lost_too_many_pages(tmp_path):
    """Порог потерь защищает живой индекс и на фоновом пути, а не только на ручном."""
    card_book = _card_book_next_to_an_article_book(tmp_path, card_pages=100)
    manager = BackgroundIndexingManager()
    pages_seen = []

    def only_the_first_page_parses(self, content, file_path):
        pages_seen.append(file_path)
        if len(pages_seen) == 1:
            return Documentation(
                id="doc0", type=DocumentType.OBJECT_FUNCTION, name="Метод"
            )
        raise RuntimeError("разметка страницы сломалась")

    with patch(
        "src.parsers.html_parser.HTMLParser.parse_html_content", only_the_first_page_parses
    ), patch(
        "src.parsers.indexer.ElasticsearchIndexer.reindex_all", new=AsyncMock(return_value=True)
    ) as reindex:
        await manager._do_indexing(str(card_book), AsyncMock(), index="ignored", lang="ru")

    reindex.assert_not_awaited()
    assert (await manager.get_status()).status is IndexingStatus.FAILED

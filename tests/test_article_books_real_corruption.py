"""Битая запись внутри настоящей книги статей стоит только себя, а не всей индексации.

Поведенческое закрепление находки 1 (round 1 ревью задачи 6): archive.read()
на одной записи книги может бросить zipfile.BadZipFile/zlib.error/RuntimeError,
и раньше это исключение покидало parse_article_books целиком — терялись статьи
уже собранных книг, а index_hbk_file падал в except Exception и возвращал
False для всей карточечной книги. Тест ломает ровно одну запись настоящей
книги (без синтетических фикстур) и показывает, что остальные книги статей
и сама карточечная книга всё равно доходят до индексации.
"""

import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

import src.parsers.v8_container as v8_container
from src.infrastructure.indexing import index_hbk_file
from src.models.doc_models import Documentation, DocumentType, HBKFile, ParsedHBK
from src.parsers.article_books import parse_article_books

pytestmark = pytest.mark.slow

BOOKS_DIR = Path(__file__).resolve().parent.parent / "data" / "hbk"
CORRUPT_BOOK = "shquery"
CORRUPT_FILE = "ENDOFPERIOD"


def _skip_unless_all_books_present():
    required = ("shlang_ru.hbk", "shquery_ru.hbk", "shclang_ru.hbk", "dcsui_ru.hbk")
    if not all((BOOKS_DIR / name).exists() for name in required):
        pytest.skip(f"книги статей не найдены в {BOOKS_DIR} на этой машине")


@pytest.fixture
def one_entry_reads_as_corrupt(monkeypatch):
    """archive.read(CORRUPT_FILE) в книге shquery ведёт себя как повреждённая запись zip."""
    original_read = v8_container.HelpBookArchive.read

    def flaky_read(self, name):
        if name == CORRUPT_FILE:
            raise zipfile.BadZipFile("Bad CRC-32 for file (симулировано тестом)")
        return original_read(self, name)

    monkeypatch.setattr(v8_container.HelpBookArchive, "read", flaky_read)


def test_a_corrupt_entry_in_one_book_does_not_cost_the_other_books(one_entry_reads_as_corrupt):
    _skip_unless_all_books_present()

    articles, missing = parse_article_books(str(BOOKS_DIR), "ru")

    assert missing == []
    by_book = {}
    for article in articles:
        by_book[article.book] = by_book.get(article.book, 0) + 1

    assert by_book["shlang"] == 39
    assert by_book["shclang"] == 60
    assert by_book["dcsui"] == 139
    assert by_book[CORRUPT_BOOK] == 127, "ENDOFPERIOD даёт ровно одну статью — теряется только она"


async def test_index_hbk_file_still_indexes_the_card_book_despite_one_bad_article_entry(
    one_entry_reads_as_corrupt,
):
    _skip_unless_all_books_present()

    card_doc = Documentation(id="card", type=DocumentType.OBJECT_FUNCTION, name="КарточкаЭлемента")
    parsed = ParsedHBK(
        file_info=HBKFile(path="shcntx_ru.hbk", size=0, modified=0.0),
        documentation=[card_doc],
    )
    main_book_path_for_its_parent_directory_only = BOOKS_DIR / "shcntx_ru.hbk"

    with patch("src.parsers.hbk_parser.HBKParser.parse_file", return_value=parsed), \
         patch(
             "src.parsers.indexer.ElasticsearchIndexer.reindex_all",
             new=AsyncMock(return_value=True),
         ) as reindex:
        result = await index_hbk_file(
            str(main_book_path_for_its_parent_directory_only), AsyncMock(), index="ignored"
        )

    assert result is True
    reindex.assert_awaited_once()
    indexed = reindex.call_args.args[0]
    assert indexed.documentation[0].id == "card"
    assert len(indexed.documentation) == 1 + 39 + 127 + 60 + 139

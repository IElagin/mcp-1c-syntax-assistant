"""«Книги нет» и «книга не читается» — разные ответы /health."""

import pytest

from src.api.routes.health import _article_book_state
from tests.conftest import write_book

pytestmark = [pytest.mark.unit, pytest.mark.parser]

ARTICLE_PAGE = "<h1>Для (For)</h1><p>Оператор цикла встроенного языка.</p>".encode("utf-8")


def test_a_directory_without_books_reports_all_four_missing_and_none_unreadable(tmp_path):
    missing, unreadable = _article_book_state(str(tmp_path), "ru")

    assert missing == ["shlang", "shquery", "shclang", "dcsui"]
    assert unreadable == []


def test_a_readable_book_is_neither_missing_nor_unreadable(tmp_path):
    write_book(tmp_path / "shlang_ru.hbk", {"struct_For": ARTICLE_PAGE})

    missing, unreadable = _article_book_state(str(tmp_path), "ru")

    assert "shlang" not in missing
    assert unreadable == []


def test_a_present_but_broken_book_is_unreadable_not_missing(tmp_path):
    """Обрезанный файл лежит на месте — и молча не даёт ни одной статьи."""
    (tmp_path / "shlang_ru.hbk").write_bytes(b"\x00" * 64)

    missing, unreadable = _article_book_state(str(tmp_path), "ru")

    assert "shlang" not in missing
    assert unreadable == ["shlang"]


def test_a_book_that_is_a_directory_is_unreadable_not_missing(tmp_path):
    (tmp_path / "shquery_ru.hbk").mkdir()

    missing, unreadable = _article_book_state(str(tmp_path), "ru")

    assert "shquery" not in missing
    assert unreadable == ["shquery"]

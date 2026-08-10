"""Сбор статей всех книг перед индексацией."""

from pathlib import Path

from src.core.constants import ARTICLE_BOOKS
from src.parsers.article_books import parse_article_books
from tests.conftest import write_book as _book

ARTICLE = "<h1>Для (For)</h1><p>Оператор цикла.</p>".encode("utf-8")
UNDECODABLE = b"\x98broken"


def test_registry_names_four_books_with_both_languages():
    assert [b.key for b in ARTICLE_BOOKS] == ["shlang", "shquery", "shclang", "dcsui"]
    assert all(b.ru.endswith("_ru.hbk") and b.en.endswith("_root.hbk") for b in ARTICLE_BOOKS)


def test_articles_of_present_books_are_collected(tmp_path):
    _book(tmp_path / "shlang_ru.hbk", {"struct_For": ARTICLE})
    articles, missing = parse_article_books(str(tmp_path), "ru")
    assert [a.name for a in articles] == ["Для (For)"]
    assert [a.book for a in articles] == ["shlang"]


def test_missing_books_are_named_not_silently_skipped(tmp_path):
    _book(tmp_path / "shlang_ru.hbk", {"struct_For": ARTICLE})
    articles, missing = parse_article_books(str(tmp_path), "ru")
    assert missing == ["shquery", "shclang", "dcsui"]


def test_unreadable_book_does_not_cost_the_other_books(tmp_path):
    _book(tmp_path / "shlang_ru.hbk", {"struct_For": ARTICLE})
    (tmp_path / "shquery_ru.hbk").write_bytes(b"not a container" * 20)
    articles, missing = parse_article_books(str(tmp_path), "ru")
    assert [a.name for a in articles] == ["Для (For)"]
    assert "shquery" in missing


def test_english_run_reads_the_english_file_names(tmp_path):
    _book(tmp_path / "shlang_root.hbk", {"struct_For": "<h1>For</h1><p>Loop operator.</p>".encode("utf-8")})
    articles, missing = parse_article_books(str(tmp_path), "en")
    assert [a.name for a in articles] == ["For"]


def test_undecodable_file_does_not_cost_the_rest_of_its_book(tmp_path):
    _book(tmp_path / "shlang_ru.hbk", {"struct_For": ARTICLE, "struct_While": UNDECODABLE})
    articles, missing = parse_article_books(str(tmp_path), "ru")
    assert [a.name for a in articles] == ["Для (For)"]
    assert missing == ["shquery", "shclang", "dcsui"]


def test_health_names_the_article_books_that_are_absent(tmp_path, monkeypatch):
    """Отсутствие книги видно в статусе, а не только в логе."""
    from src.core.config import settings

    monkeypatch.setattr(settings, "hbk_directory", str(tmp_path))
    _book(tmp_path / "shlang_ru.hbk", {"struct_For": b"<h1>For</h1>"})

    missing = [
        book.key for book in ARTICLE_BOOKS
        if not (Path(settings.data.hbk_directory) / book.ru).exists()
    ]
    assert missing == ["shquery", "shclang", "dcsui"]

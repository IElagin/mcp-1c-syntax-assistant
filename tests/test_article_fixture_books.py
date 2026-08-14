"""Книги статей из фикстурных страниц собираются и читаются как настоящие."""

import pytest

from src.parsers.article_books import parse_article_books

pytestmark = [pytest.mark.unit, pytest.mark.parser]

EVERY_FIXTURE_ARTICLE = [
    "dcsui/functions_group.html",
    "dcsui/functions_group.html#Agregate",
    "dcsui/functions_group.html#Date",
    "dcsui/functions_group.html#String",
    "dcsui/saving_settings.html",
    "shlang/array_article.html",
    "shlang/struct_for.html",
    "shquery/overall_totals.html",
    "shquery/union_section.html",
]


def test_three_books_are_read_and_the_fourth_is_reported_absent(article_books_directory):
    """Шесть страниц дают девять статей: у одной из них три раздела с якорями."""
    articles, absent = parse_article_books(str(article_books_directory), "ru")

    assert sorted(article.id for article in articles) == EVERY_FIXTURE_ARTICLE
    assert absent == ["shclang"]


EVERY_ENGLISH_FIXTURE_ARTICLE = [
    "shlang/array_article.html",
    "shlang/struct_for.html",
    "shquery/union_section.html",
]


@pytest.mark.parametrize("article_books_directory", ["en"], indirect=True)
def test_english_books_are_found_by_their_own_file_names(article_books_directory):
    """Английские книги зовутся *_root.hbk — по русским именам их не найти."""
    articles, absent = parse_article_books(str(article_books_directory), "en")

    assert sorted(article.id for article in articles) == EVERY_ENGLISH_FIXTURE_ARTICLE
    assert sorted(absent) == ["dcsui", "shclang"]

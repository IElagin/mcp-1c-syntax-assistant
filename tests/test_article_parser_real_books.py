"""Разбор настоящих книг статей: то, что не проверить на выдуманной строке."""

from pathlib import Path

import pytest

from src.parsers.article_parser import decode_article, is_article_file, parse_article_file
from src.parsers.v8_container import HelpBookArchive

BOOKS = Path(__file__).resolve().parents[1] / "data" / "hbk"

pytestmark = pytest.mark.real_book


def _archive(book: str) -> HelpBookArchive:
    path = BOOKS / f"{book}_ru.hbk"
    if not path.exists():
        pytest.skip(f"книга {path} не найдена на этой машине")
    return HelpBookArchive(path)


def test_language_book_keeps_the_articles_7zip_used_to_lose():
    """expressions_logical.html — одна из тринадцати страниц, которых 7-Zip не видел."""
    with _archive("shlang") as archive:
        names = archive.names()
    assert len(names) == 62
    assert "expressions_logical.html" in names
    assert "expression_priorities.html" in names
    assert "operator_await.html" in names


def test_dcs_expression_functions_split_out_under_their_group_article():
    """Вступление файла — перечень группы, за ним по статье на функцию."""
    with _archive("dcsui") as archive:
        html = decode_article(archive.read("SKD_Functions_Expressions"))
    articles = parse_article_file("dcsui", "SKD_Functions_Expressions", html)
    assert [a.name for a in articles] == [
        "Работа с выражениями",
        "Вычислить (Eval)",
        "ВычислитьВыражение (EvalExpression)",
        "ВычислитьВыражениеСГруппировкойМассив (EvalExpressionWithGroupArray)",
        "ВычислитьВыражениеСГруппировкойТаблицаЗначений (EvalExpressionWithGroupValueTable)",
    ]
    assert articles[0].source_file == "dcsui/SKD_Functions_Expressions"
    assert articles[1].source_file == "dcsui/SKD_Functions_Expressions#calculate"


@pytest.mark.parametrize("book,files,units", [
    ("shlang", 39, 39),
    ("shquery", 128, 128),
    ("shclang", 26, 60),
    ("dcsui", 23, 139),
])
def test_each_book_yields_the_measured_number_of_articles(book, files, units):
    with _archive(book) as archive:
        names = [n for n in archive.names() if is_article_file(book, n)]
        produced = sum(
            len(parse_article_file(book, n, decode_article(archive.read(n))))
            for n in names
        )
    assert len(names) == files
    assert produced == units

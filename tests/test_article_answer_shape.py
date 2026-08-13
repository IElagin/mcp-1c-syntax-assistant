"""Ответ get_1c_article целиком — от страницы книги до отрендеренного текста.

Каждая страница держит свой класс дефекта:

  struct_for.html        — заголовок печатался трижды; строки склеивались
                           в одну; подвал за <hr> утекал в текст
  union_section.html     — строка таблицы печаталась по ячейке на строку;
                           «<Описание запроса>» разрывалось пробелами
  overall_totals.html    — точка в «Документ.РасхНакл.Состав» принималась
                           за конец предложения; <BR> в ячейке терялся
  functions_group.html   — раздел повторял собственный заголовок
  saving_settings.html   — закомментированная разметка печаталась как текст
  array_article.html     — заголовок статьи совпадает с именем карточки
"""

from pathlib import Path

import pytest

from src.handlers.element_card import render_article
from src.handlers.ui_strings import RU_STRINGS
from src.parsers.article_books import parse_article_books
from src.parsers.indexer import ElasticsearchIndexer

pytestmark = [pytest.mark.unit, pytest.mark.parser]

EXPECTED_ANSWERS = Path(__file__).parent / "fixtures" / "articles" / "expected_answers.txt"


def _whole_answer(directory) -> str:
    """Все статьи фикстурных книг так, как их печатает инструмент."""
    articles, _ = parse_article_books(str(directory), "ru")
    indexer = ElasticsearchIndexer(None)
    documents = sorted(
        (indexer._prepare_document(article) for article in articles),
        key=lambda document: document["id"],
    )
    blocks = [
        f"### {document['id']}\n{render_article(document, RU_STRINGS)}"
        for document in documents
    ]
    return "\n\n".join(blocks) + "\n"


def test_every_fixture_article_reads_exactly_as_recorded(article_books_directory):
    assert _whole_answer(article_books_directory) == EXPECTED_ANSWERS.read_text(
        encoding="utf-8"
    )

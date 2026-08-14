"""Английский ответ get_1c_article целиком — от книги до отрендеренного текста.

Форму текста держит русский золотой файл: код разбора и рендера общий. Здесь
проверяется то, что от языка зависит, — что книги найдены по английским именам
и что подписи пришли из EN_STRINGS.

Золотой файл руками не правят: когда форма ответа меняется намеренно, новый
текст берут из вывода этого же теста.
"""

from pathlib import Path

import pytest

from src.handlers.element_card import render_article
from src.handlers.ui_strings import EN_STRINGS
from src.parsers.article_books import parse_article_books
from src.parsers.indexer import ElasticsearchIndexer

pytestmark = [pytest.mark.unit, pytest.mark.parser]

EXPECTED_ANSWERS = Path(__file__).parent / "fixtures" / "articles" / "expected_answers_en.txt"


def _whole_answer(directory) -> str:
    """Все статьи английских фикстурных книг так, как их печатает инструмент."""
    articles, _ = parse_article_books(str(directory), "en")
    indexer = ElasticsearchIndexer(None)
    documents = sorted(
        (indexer._prepare_document(article) for article in articles),
        key=lambda document: document["id"],
    )
    blocks = [
        f"### {document['id']}\n{render_article(document, EN_STRINGS)}"
        for document in documents
    ]
    return "\n\n".join(blocks) + "\n"


@pytest.mark.parametrize("article_books_directory", ["en"], indirect=True)
def test_every_english_fixture_article_reads_exactly_as_recorded(article_books_directory):
    produced = _whole_answer(article_books_directory)
    expected = EXPECTED_ANSWERS.read_text(encoding="utf-8")

    assert produced.splitlines(keepends=True) == expected.splitlines(keepends=True)

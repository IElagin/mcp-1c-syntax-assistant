"""Английский ответ get_1c_article целиком — от книги до отрендеренного текста.

Форму текста держит русский золотой файл: код разбора и рендера общий. Здесь
проверяется то, что от языка зависит, — что книги найдены по английским именам
и что подписи пришли из EN_STRINGS.

Золотой файл руками не правят: когда форма ответа меняется намеренно, новый
текст берут из вывода этого же теста.
"""

from pathlib import Path

import pytest

from src.handlers.ui_strings import EN_STRINGS
from tests.conftest import whole_article_answer

pytestmark = [pytest.mark.unit, pytest.mark.parser]

EXPECTED_ANSWERS = Path(__file__).parent / "fixtures" / "articles" / "expected_answers_en.txt"


@pytest.mark.parametrize("article_books_directory", ["en"], indirect=True)
def test_every_english_fixture_article_reads_exactly_as_recorded(article_books_directory):
    produced = whole_article_answer(article_books_directory, "en", EN_STRINGS)
    expected = EXPECTED_ANSWERS.read_text(encoding="utf-8")

    assert produced.splitlines(keepends=True) == expected.splitlines(keepends=True)

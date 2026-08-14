"""Ответ get_1c_article целиком — от страницы книги до отрендеренного текста.

Каждая страница держит свой класс дефекта:

  struct_for.html        — заголовок печатался трижды; строки склеивались
                           в одну; подвал за <hr> утекал в текст
  union_section.html     — строка таблицы печаталась по ячейке на строку;
                           «<Описание запроса>» разрывалось пробелами; перевод
                           строки в разметке считался значимым
  overall_totals.html    — точка в «Документ.РасхНакл.Состав» принималась
                           за конец предложения; <BR> в ячейке терялся
  functions_group.html   — раздел повторял собственный заголовок
  saving_settings.html   — закомментированная разметка печаталась как текст
  array_article.html     — заголовок статьи совпадает с именем карточки

Золотой файл руками не правят: когда форма ответа меняется намеренно, новый
текст берут из вывода этого же теста.
"""

from pathlib import Path

import pytest

from src.handlers.ui_strings import RU_STRINGS
from tests.conftest import whole_article_answer

pytestmark = [pytest.mark.unit, pytest.mark.parser]

EXPECTED_ANSWERS = Path(__file__).parent / "fixtures" / "articles" / "expected_answers.txt"


def test_every_fixture_article_reads_exactly_as_recorded(article_books_directory):
    produced = whole_article_answer(article_books_directory, "ru", RU_STRINGS)
    expected = EXPECTED_ANSWERS.read_text(encoding="utf-8")

    assert produced.splitlines(keepends=True) == expected.splitlines(keepends=True)

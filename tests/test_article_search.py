"""Статьи в общей выдаче поиска."""

from src.core.constants import KIND_TO_TYPE
from src.handlers.element_card import list_line
from src.handlers.ui_strings import EN_STRINGS, RU_STRINGS
from src.models.mcp_models import SearchKind
from src.search.ranker import SearchRanker
from src.search.search_service import LIST_LINE_FIELDS

ARTICLE = {
    "type": "article",
    "element_kind": "статья",
    "name": "Функция МЕСЯЦ",
    "name_ru": "Функция МЕСЯЦ",
    "book": "shquery",
    "full_path": "shquery/MONTH",
    "description": "Данная функция предназначена для вычисления номера месяца из значения типа ДАТА.",
}

CARD = {
    "type": "global_function",
    "element_kind": "функция",
    "name": "Найти (Find)",
    "name_ru": "Найти",
    "full_path": "Найти",
    "call_primary": "Найти(<Подстрока>)",
    "description": "Ищет подстроку.",
    "syntax_all": "Найти(<Подстрока>)",
    "variants": [{"syntax": "Найти(<Подстрока>)", "parameters": [{"name": "Подстрока", "description": "что искать"}], "return_type": "Число"}],
}


def test_article_kind_selects_only_articles():
    assert SearchKind.ARTICLE.value == "article"
    assert KIND_TO_TYPE["article"] == ["article"]


def test_search_result_lines_carry_the_book():
    assert "book" in LIST_LINE_FIELDS


def test_article_line_names_its_book_instead_of_a_call_string():
    line = list_line(ARTICLE, RU_STRINGS)
    assert "Функция МЕСЯЦ" in line
    assert "язык запросов" in line
    assert "shquery/MONTH" not in line


def test_article_line_is_translated_for_the_english_answer():
    assert "query language" in list_line(ARTICLE, EN_STRINGS)


def test_card_outranks_an_article_on_an_exact_card_name():
    """Точное имя карточки не должно проигрывать статье."""
    ranker = SearchRanker()
    ranked = ranker.rank_results(
        [{"_source": ARTICLE, "_score": 10.0}, {"_source": CARD, "_score": 10.0}],
        "Найти",
    )
    assert ranked[0]["document"]["name"] == "Найти (Find)"

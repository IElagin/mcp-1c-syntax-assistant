"""Answers an agent gets right on the first call: words of compound names,
conversions phrased in several words, constructors by variant, honest counts
and a not-found answer that names the help version."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.handlers.mcp_handlers import _element_missing
from src.handlers.ui_strings import EN_STRINGS, RU_STRINGS
from src.parsers.indexer import name_words
from src.search import search_service as search_module
from src.search.query_builder import _conversion_queries
from src.search.search_service import MEMBER_KINDS_BY_GROUP, SearchService

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(("names", "words"), [
    (("ТекущаяДатаСеанса", "CurrentSessionDate"), "Текущая Дата Сеанса Current Session Date"),
    (("ПолучитьBase64СтрокуИзДвоичныхДанных", ""), "Получить Base64 Строку Из Двоичных Данных"),
    (("HTTPСоединение", "HTTPConnection"), "HTTP Соединение HTTP Connection"),
    (("СокрЛП", None), "Сокр Сократить ЛП"),
    (("СтрЗаменить", "StrReplace"), "Стр Строка Заменить Str Replace"),
])
def test_compound_names_are_indexed_as_words(names, words):
    assert name_words(*names) == words


def test_conversion_of_a_several_word_source_prefers_the_requested_return_type():
    clauses = _conversion_queries("преобразовать двоичные данные в строку Base64")

    assert len(clauses) == 1
    conditions = clauses[0]["constant_score"]["filter"]["bool"]["filter"]
    assert conditions[0] == {"terms": {"variants.return_type": ["Строка", "String"]}}
    assert conditions[1]["match_phrase"]["description"]["query"] == "двоичные данные в строку"


def hits(*documents):
    return {"hits": {"total": {"value": len(documents)},
                     "hits": [{"_source": document} for document in documents]}}


HTTP_CONNECTION = {"name": "HTTPСоединение", "name_ru": "HTTPСоединение",
                   "element_kind": "объект", "object": "HTTPСоединение",
                   "full_path": "HTTPСоединение"}
DEFAULT_CONSTRUCTOR = {"name_ru": "По умолчанию", "type": "object_constructor",
                       "object": "HTTPСоединение",
                       "variants": [{"variant": "По умолчанию"}]}
BY_SERVER_CONSTRUCTOR = {"name_ru": "По указанному серверу", "type": "object_constructor",
                         "object": "HTTPСоединение",
                         "variants": [{"variant": "По указанному серверу"}]}


async def test_a_variant_shown_on_an_object_card_opens_that_constructor():
    client = AsyncMock()
    client.search = AsyncMock(side_effect=[
        hits(HTTP_CONNECTION), hits(BY_SERVER_CONSTRUCTOR, DEFAULT_CONSTRUCTOR),
    ])

    answer = await SearchService(client).element_card("HTTPСоединение", variant="По умолчанию")

    assert answer == {"kind": "card", "document": DEFAULT_CONSTRUCTOR}


async def test_an_unknown_variant_of_an_object_lists_its_constructors():
    client = AsyncMock()
    client.search = AsyncMock(side_effect=[
        hits(HTTP_CONNECTION), hits(BY_SERVER_CONSTRUCTOR, DEFAULT_CONSTRUCTOR),
    ])

    answer = await SearchService(client).element_card("HTTPСоединение", variant="Без прокси")

    assert answer["kind"] == "variant_not_found"
    assert answer["variants"] == ["По указанному серверу", "По умолчанию"]


def test_constructors_are_not_counted_as_methods():
    assert "object_constructor" not in MEMBER_KINDS_BY_GROUP["methods"]
    assert MEMBER_KINDS_BY_GROUP["constructors"] == ["object_constructor"]


async def test_help_version_is_the_latest_available_from_version():
    search_module._HELP_VERSION_BY_INDEX.clear()
    client = AsyncMock()
    client.search = AsyncMock(return_value={"aggregations": {"versions": {"buckets": [
        {"key": "8.3.9"}, {"key": "8.3.20"}, {"key": "8.3.13"}, {"key": "8.2"},
    ]}}})

    assert await SearchService(client, index="help_version_probe").help_version() == "8.3.20"


async def test_an_empty_index_has_no_help_version_and_is_asked_again():
    search_module._HELP_VERSION_BY_INDEX.clear()
    client = AsyncMock()
    client.search = AsyncMock(return_value={"aggregations": {"versions": {"buckets": []}}})
    service = SearchService(client, index="help_version_empty")

    assert await service.help_version() is None
    assert await service.help_version() is None
    assert client.search.await_count == 2


@pytest.mark.parametrize("strings", [RU_STRINGS, EN_STRINGS])
def test_not_found_without_similar_names_says_which_version_the_help_is(strings):
    answer = {"similar": [], "article_exists": False, "help_version": "8.3.20"}

    text = _element_missing(answer, SimpleNamespace(name="СтрНайтиПоРегулярномуВыражению"), strings)

    assert "8.3.20" in text
    assert strings.no_similar not in text


def test_not_found_without_a_known_version_keeps_the_spelling_hint():
    answer = {"similar": [], "article_exists": False, "help_version": None}

    text = _element_missing(answer, SimpleNamespace(name="СтрНайтиПоРегулярномуВыражению"), RU_STRINGS)

    assert RU_STRINGS.no_similar in text

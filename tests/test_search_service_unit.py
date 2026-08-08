"""Слой поиска: форма запросов и форма результата — без Elasticsearch.

Слой поиска не собирает текст для человека: он отдаёт данные и признаки
исхода, а слова подбирает handlers. Тесты здесь проверяют форму того, что
отдаётся, — и что фильтр подсказки знает оба имени объекта.
"""

from unittest.mock import AsyncMock

import pytest

from src.handlers.ui_strings import EN_STRINGS, RU_STRINGS
from src.search.search_service import SearchService


pytestmark = pytest.mark.unit


def _two_constructors() -> dict:
    """ES response for an object with two constructors — COMSafeArray."""
    return {
        "hits": {
            "hits": [
                {
                    "_source": {
                        "call_primary": "New COMSafeArray(<Source>)",
                        "name_ru": "From COMSafeArray",
                        "variants": [{"variant": "From COMSafeArray"}],
                    }
                },
                {
                    "_source": {
                        "call_primary": "New COMSafeArray(<Array>, <ElementType>)",
                        "name_ru": "From array 2",
                        "variants": [{"variant": "From array 2"}],
                    }
                },
            ]
        }
    }


async def test_constructor_calls_carry_no_worded_text():
    client = AsyncMock()
    client.search = AsyncMock(return_value=_two_constructors())

    calls = await SearchService(client).constructor_calls("COMSafeArray")

    assert calls == [
        ("New COMSafeArray(<Source>)", "From COMSafeArray"),
        ("New COMSafeArray(<Array>, <ElementType>)", "From array 2"),
    ]


async def test_pages_without_a_call_string_are_dropped():
    client = AsyncMock()
    client.search = AsyncMock(return_value={
        "hits": {"hits": [
            {"_source": {"call_primary": "", "name_ru": "Empty page"}},
            {"_source": {"call_primary": "New ValueTable", "name_ru": "ValueTable"}},
        ]}
    })

    assert await SearchService(client).constructor_calls("ValueTable") == [
        ("New ValueTable", "ValueTable")
    ]


async def test_failed_search_is_marked_not_worded():
    client = AsyncMock()
    client.search = AsyncMock(return_value=None)

    result = await SearchService(client).find_help_filtered("Add", [], None, 10)

    assert result["search_failed"] is True
    assert "error" not in result


async def test_similar_objects_matches_english_name_too():
    """Опечатка в английском имени объекта обязана давать подсказку.

    object="ТаблицаЗначенй" давал «ТаблицаЗначений», а object="ValuTable" —
    «подходящих не найдено», хотя английское имя объекта задачи 11 и 12 уже
    сделали полноправным входом. Агент читает молчание как «объекта в справке
    нет» и прекращает поиск.

    Проверяется форма запроса, а не выдача: выдачу решает Elasticsearch, а
    потеря name_en в списке полей — ровно та правка, которая вернёт дефект и
    останется незамеченной на моке любой формы.
    """
    client = AsyncMock()
    client.search = AsyncMock(return_value={"hits": {"hits": []}})

    await SearchService(client).similar_objects("ValuTable")

    body = client.search.call_args.args[0]
    matcher = body["query"]["bool"]["must"][0]
    assert "multi_match" in matcher, matcher
    assert set(matcher["multi_match"]["fields"]) == {"name_ru", "name_en"}
    assert matcher["multi_match"]["fuzziness"] == "AUTO"

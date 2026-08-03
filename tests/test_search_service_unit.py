"""Слой поиска: язык ответа и форма запросов — без Elasticsearch.

Оба дефекта, ради которых написан файл, ветка пропустила по одной причине:
search_service.py не считался «слоем, который печатает пользователю», хотя
собирает и строки ответа (constructor_lines), и текст ошибки. Тесты здесь
проверяют именно это — что видимая строка приходит из таблицы языка, а фильтр
подсказки знает про оба имени объекта.
"""

from unittest.mock import AsyncMock

import pytest

from src.handlers.ui_strings import EN_STRINGS, RU_STRINGS
from src.search.search_service import SearchService


pytestmark = pytest.mark.unit


def _two_constructors() -> dict:
    """Ответ ES для объекта с двумя конструкторами — COMSafeArray из ревью."""
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


async def test_constructor_variant_label_speaks_the_answer_language():
    """Английская карточка не должна печатать русское «— вариант «…»».

    get_1c_element(name="COMSafeArray", lang="en") отдавал
    'New COMSafeArray(<Source>) — вариант «From COMSafeArray»': русское слово и
    русские кавычки в карточке, целиком заявленной английской. Строка
    собиралась в search_service — единственной функции сборки ответа, которую
    не протянули через таблицу строк.
    """
    client = AsyncMock()
    client.search = AsyncMock(return_value=_two_constructors())

    lines = await SearchService(client).constructor_lines("COMSafeArray", EN_STRINGS)

    assert lines == [
        'New COMSafeArray(<Source>) — variant "From COMSafeArray"',
        'New COMSafeArray(<Array>, <ElementType>) — variant "From array 2"',
    ]
    # Проверка на кириллицу, а не только на точные строки: она поймает любую
    # новую захардкоженную русскую метку, а не одну известную.
    assert not any(
        "Ѐ" <= char <= "ӿ" for line in lines for char in line
    ), lines


async def test_constructor_variant_label_is_unchanged_in_russian():
    """Русский ответ обязан остаться прежним — формулировка списана дословно."""
    client = AsyncMock()
    client.search = AsyncMock(return_value=_two_constructors())

    lines = await SearchService(client).constructor_lines("COMSafeArray", RU_STRINGS)

    assert lines == [
        "New COMSafeArray(<Source>) — вариант «From COMSafeArray»",
        "New COMSafeArray(<Array>, <ElementType>) — вариант «From array 2»",
    ]


async def test_single_constructor_has_no_variant_suffix():
    """У единственного конструктора имя варианта не различает ничего."""
    client = AsyncMock()
    client.search = AsyncMock(return_value={
        "hits": {"hits": [{"_source": {
            "call_primary": "New ValueTable",
            "name_ru": "ValueTable",
            "variants": [{"variant": "ValueTable"}],
        }}]}
    })

    assert await SearchService(client).constructor_lines("ValueTable", EN_STRINGS) == [
        "New ValueTable"
    ]


async def test_search_failure_detail_speaks_the_answer_language():
    """Заголовок ошибки переведён, деталь приходит отсюда — переведём и её."""
    client = AsyncMock()
    client.search = AsyncMock(return_value=None)

    result = await SearchService(client).find_help_filtered(
        "Add", [], None, 10, EN_STRINGS
    )

    assert result["error"] == EN_STRINGS.search_failed
    assert result["error"] != RU_STRINGS.search_failed


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

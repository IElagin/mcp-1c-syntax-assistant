"""Параметр lang выбирает индекс и язык ответа."""

from unittest.mock import AsyncMock

import pytest

from src.api.mcp_tools import TOOLS
from src.handlers.mcp_handlers import (
    handle_find_1c_help, handle_get_1c_element, handle_list_1c_object_members,
    has_cyrillic,
)
from src.models.mcp_models import (
    Find1CHelpRequest, Get1CElementRequest, List1CObjectMembersRequest, Lang,
)


pytestmark = pytest.mark.unit


def test_every_tool_schema_declares_lang():
    for tool in TOOLS:
        properties = tool["inputSchema"]["properties"]
        assert "lang" in properties, tool["name"]
        assert properties["lang"]["enum"] == ["ru", "en"], tool["name"]


def test_lang_defaults_to_server_setting():
    request = Find1CHelpRequest(query="Добавить")

    assert request.lang is Lang.RU


def test_unknown_lang_is_rejected():
    with pytest.raises(ValueError):
        Find1CHelpRequest(query="Add", lang="english")


def test_index_is_chosen_by_language():
    from src.core.config import settings
    from src.handlers.mcp_handlers import index_for

    assert index_for("ru") == settings.elasticsearch_index
    assert index_for("en") == settings.elasticsearch_index_en


def test_cyrillic_detection():
    assert has_cyrillic("Добавить")
    assert not has_cyrillic("Add")
    assert has_cyrillic("Add (Добавить)")


async def test_russian_name_with_english_lang_says_why(es_client_without_en_index):
    """Молчаливое «не найдено» здесь — прямая ложь: элемент существует."""
    response = await handle_get_1c_element(
        Get1CElementRequest(name="Добавить", lang="en"), es_client_without_en_index
    )

    text = response.content[0]["text"]
    assert "Russian" in text or "russian" in text
    assert 'lang="ru"' in text


async def test_missing_english_index_is_named_not_hidden(es_client_without_en_index):
    response = await handle_get_1c_element(
        Get1CElementRequest(name="Add", lang="en"), es_client_without_en_index
    )

    text = response.content[0]["text"]
    assert "shcntx_root.hbk" in text
    assert "data/hbk-en" in text


async def test_cyrillic_object_filter_with_english_lang_says_why(es_client_without_en_index):
    response = await handle_list_1c_object_members(
        List1CObjectMembersRequest(object="Массив", lang="en"),
        es_client_without_en_index,
    )

    assert 'lang="ru"' in response.content[0]["text"]


# Раунд правок 1: регрессия обнаружилась ровно там, где единственная фикстура
# выше (индекса нет) не могла её увидеть — при существующем индексе. Три
# теста ниже используют es_client_with_en_index и покрывают то место, где
# ревью нашло дефект: find_1c_help.query больше не блокируется по одной
# кириллице в строке (латинская часть смешанного запроса реально находит
# совпадения — 3 510 попаданий на живом индексе, см. отчёт), а объясняется
# только если результат и правда пуст.

async def test_cyrillic_name_still_caught_when_english_index_exists(es_client_with_en_index):
    """Кириллица в имени ловится сама по себе, а не как следствие того, что
    индекса нет: с прежней единственной фикстурой (индекс отсутствует) эта
    ветка не отличалась от проверки на отсутствие индекса вовсе."""
    response = await handle_get_1c_element(
        Get1CElementRequest(name="Добавить", lang="en"), es_client_with_en_index
    )

    text = response.content[0]["text"]
    assert "Russian" in text or "russian" in text
    assert 'lang="ru"' in text
    # Точное совпадение по кириллице не найти ни при каких условиях (в
    # английском индексе кириллицы нет ни в одном поле), поэтому проверка
    # обязана отсечь запрос до обращения в Elasticsearch.
    es_client_with_en_index.search.assert_not_called()


async def test_mixed_query_is_not_blocked_from_a_working_search(es_client_with_en_index):
    """find_1c_help(query="Add (Добавить)", lang="en") — рабочий запрос.

    "РусскоеИмя (EnglishName)" — формат заголовков самой справки (см.
    src/parsers/indexer.py, split_name_ru_en); multi_match с fuzziness,
    которым ищет find_1c_help, матчит по латинской части независимо от
    кириллической. Блокировать такой запрос на входе значило бы отказывать в
    поиске, который реально находит (проверено на живом индексе — 3 510
    попаданий с оценками до 266, см. отчёт).
    """
    response = await handle_find_1c_help(
        Find1CHelpRequest(query="Add (Добавить)", lang="en"), es_client_with_en_index
    )

    text = response.content[0]["text"]
    assert "cannot match anything" not in text
    es_client_with_en_index.search.assert_called()


async def test_pure_cyrillic_find_1c_help_query_explains_empty_result():
    """find_1c_help("Добавить", lang="en") — мотивирующий пример из задачи.

    Чисто кириллический запрос до Elasticsearch доходит (в отличие от
    смешанного, блокировать его на входе было бы неверно и для него — причина
    не в запросе, а в том, что искать нечего), но в английском индексе
    кириллицы нет нигде, и реальный поиск вернёт пусто. Пустая выдача обязана
    объясниться, а не молчать — это и есть исходный порок, ради которого
    заведена вся задача 10.
    """
    from unittest.mock import AsyncMock

    client = AsyncMock()
    client.index_exists = AsyncMock(return_value=True)
    client.search = AsyncMock(return_value={"hits": {"hits": [], "total": {"value": 0}}})

    response = await handle_find_1c_help(
        Find1CHelpRequest(query="Добавить", lang="en"), client
    )

    text = response.content[0]["text"]
    assert "Russian" in text or "russian" in text
    assert 'lang="ru"' in text
    client.search.assert_called()

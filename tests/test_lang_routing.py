"""Параметр lang выбирает индекс и язык ответа."""

from unittest.mock import AsyncMock

import pytest

from src.api.mcp_tools import TOOLS
from src.handlers.mcp_handlers import (
    handle_get_1c_element, handle_list_1c_object_members, has_cyrillic,
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

"""Параметр lang выбирает индекс и язык ответа."""

import pytest

from src.api.mcp_tools import TOOLS
from src.models.mcp_models import Find1CHelpRequest, Lang


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

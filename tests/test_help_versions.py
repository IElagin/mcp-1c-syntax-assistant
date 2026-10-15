"""Справка по версиям платформы: у каждой версии своя книга и свой индекс."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.core.config import Settings, settings
from src.core.versions import (
    UNVERSIONED, UnknownVersionError, all_versions, default_version, resolve_version,
)

pytestmark = pytest.mark.unit

VERSIONS = "8.3.27.2342, 8.5.1.1529,8.3.20.1914"


@pytest.fixture
def three_versions(monkeypatch):
    monkeypatch.setattr(settings, "help_versions", VERSIONS)
    monkeypatch.setattr(settings, "default_help_version", "8.3.27.2342")


def test_without_versions_the_single_book_keeps_its_old_index():
    assert default_version() == UNVERSIONED
    book = resolve_version(None)
    assert book.index == settings.elasticsearch_index
    assert book.hbk_directory == settings.data.hbk_directory


def test_version_number_typo_stops_the_server_start():
    with pytest.raises(ValueError):
        Settings(help_versions="8.3.27")
    with pytest.raises(ValueError):
        Settings(help_versions="8.3.27.2342", default_help_version="8.5.1.1529")


def test_each_version_has_its_own_directory_and_index(three_versions):
    books = all_versions()
    assert [b.name for b in books] == ["8.3.27.2342", "8.5.1.1529", "8.3.20.1914"]
    assert len({b.index for b in books}) == 3
    assert all(b.index != settings.elasticsearch_index for b in books)
    assert Path(books[1].hbk_directory) == Path(settings.data.hbk_directory) / "8.5.1.1529"
    assert resolve_version(None).name == "8.3.27.2342"
    assert resolve_version("8.5.1.1529").index == books[1].index


def test_unknown_version_names_the_available_ones(three_versions):
    with pytest.raises(UnknownVersionError) as caught:
        resolve_version("8.2.19.130")
    assert caught.value.available == ["8.3.27.2342", "8.5.1.1529", "8.3.20.1914"]


def test_handlers_route_by_version_and_refuse_unknown(three_versions):
    from src.handlers.mcp_handlers import index_for, version_refusal
    from src.handlers.ui_strings import RU_STRINGS

    assert index_for("ru", "8.3.20.1914") == resolve_version("8.3.20.1914").index
    assert index_for("ru") == resolve_version("8.3.27.2342").index
    assert index_for("en", "8.3.27.2342") == settings.elasticsearch_index_en
    assert version_refusal("ru", "8.5.1.1529", RU_STRINGS) is None
    refusal = version_refusal("ru", "8.2.19.130", RU_STRINGS)
    assert "8.2.19.130" in refusal and "8.5.1.1529" in refusal
    assert 'lang="ru"' in version_refusal("en", "8.5.1.1529", RU_STRINGS)
    assert version_refusal("en", None, RU_STRINGS) is None


async def test_get_element_answers_unknown_version_with_the_list(three_versions):
    from src.handlers.mcp_handlers import handle_get_1c_element
    from src.models.mcp_models import Get1CElementRequest

    es_client = AsyncMock()
    response = await handle_get_1c_element(
        Get1CElementRequest(name="ВидПоляФормы", version="8.2.19.130"), es_client
    )
    text = response.content[0]["text"]
    assert "8.2.19.130" in text and "list_1c_versions" in text
    es_client.search.assert_not_awaited()


def test_every_tool_schema_offers_configured_versions(three_versions):
    from src.api.mcp_tools import version_schema

    schema = version_schema()
    assert schema["enum"] == ["8.3.27.2342", "8.5.1.1529", "8.3.20.1914"]
    assert schema["default"] == "8.3.27.2342"


def test_tools_declare_version_except_the_version_list():
    from src.api.mcp_tools import TOOLS

    for tool in TOOLS:
        has_version = "version" in tool["inputSchema"]["properties"]
        assert has_version == (tool["name"] != "list_1c_versions"), tool["name"]


async def test_version_list_marks_default_and_unindexed(three_versions):
    from src.handlers.mcp_handlers import handle_list_1c_versions
    from src.models.mcp_models import List1CVersionsRequest

    indexed = {resolve_version("8.3.27.2342").index: 23491, resolve_version("8.5.1.1529").index: 23900}
    es_client = AsyncMock()
    es_client.index_exists = AsyncMock(side_effect=lambda index: index in indexed)
    es_client.get_documents_count = AsyncMock(side_effect=lambda index: indexed[index])

    text = (await handle_list_1c_versions(List1CVersionsRequest(), es_client)).content[0]["text"]
    lines = text.splitlines()
    assert lines[1] == "8.3.27.2342 (по умолчанию) — документов 23491"
    assert lines[2] == "8.5.1.1529 — документов 23900"
    assert lines[3].startswith("8.3.20.1914 — не проиндексирована")
    assert "8.3.20.1914/shcntx_ru.hbk" in lines[3]


async def test_version_list_without_versions_says_so():
    from src.handlers.mcp_handlers import handle_list_1c_versions
    from src.models.mcp_models import List1CVersionsRequest

    es_client = AsyncMock()
    es_client.index_exists = AsyncMock(return_value=True)
    es_client.get_documents_count = AsyncMock(return_value=5)
    text = (await handle_list_1c_versions(List1CVersionsRequest(), es_client)).content[0]["text"]
    assert text.startswith("Версии не настроены") and "5" in text


async def test_startup_puts_each_version_book_into_its_own_index(three_versions):
    from src.infrastructure.indexing import _run_queue_then_backfill

    manager = MagicMock()
    manager.is_indexing = MagicMock(return_value=False)
    calls = []

    async def fake_start_indexing(path, es_client, index=None, lang="ru"):
        calls.append((path, index, lang))

    manager.start_indexing = AsyncMock(side_effect=fake_start_indexing)
    books = [(Path("a/shcntx_ru.hbk"), "idx_a"), (Path("b/shcntx_ru.hbk"), "idx_b")]
    backfill = AsyncMock(return_value=0)
    with patch("src.infrastructure.indexing.get_indexing_manager", return_value=manager), \
         patch("src.infrastructure.indexing.backfill_english_names", new=backfill):
        await _run_queue_then_backfill(AsyncMock(), None, "en.hbk", books)

    assert calls[:2] == [(str(Path("a/shcntx_ru.hbk")), "idx_a", "ru"), (str(Path("b/shcntx_ru.hbk")), "idx_b", "ru")]
    assert calls[2][1:] == (settings.elasticsearch_index_en, "en")
    assert [c.args[1] for c in backfill.await_args_list] == [b.index for b in all_versions()]


async def test_name_table_pages_through_the_whole_index():
    from src.search.search_service import NAME_TABLE_PAGE, SearchService

    def page(start, size):
        return {"hits": {"hits": [
            {"_source": {"type": "object", "name_ru": f"Т{i}", "availability": []}, "sort": [f"id{i}"]}
            for i in range(start, start + size)
        ]}}

    es_client = AsyncMock()
    es_client.search = AsyncMock(side_effect=[page(0, NAME_TABLE_PAGE), page(NAME_TABLE_PAGE, 3)])
    table = await SearchService(es_client, index="i").name_table()
    assert len(table) == NAME_TABLE_PAGE + 3
    second_query = es_client.search.await_args_list[1].args[0]
    assert second_query["search_after"] == [f"id{NAME_TABLE_PAGE - 1}"]
    assert table[0] == {"type": "object", "name_ru": "Т0", "name_en": None, "object": None, "availability": []}


async def test_rebuild_and_names_reject_unknown_version(three_versions):
    from src.api.routes.index import name_table, rebuild_index

    with pytest.raises(HTTPException) as caught:
        await rebuild_index(version="8.2.19.130", es_client=AsyncMock())
    assert caught.value.status_code == 400
    with pytest.raises(HTTPException) as caught:
        await name_table(version="8.2.19.130", es_client=AsyncMock())
    assert caught.value.status_code == 400

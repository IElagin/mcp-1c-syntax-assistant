"""Имя индекса — явный аргумент, а не единственное значение из конфигурации."""

from unittest.mock import AsyncMock

import pytest

from src.core.elasticsearch import ElasticsearchClient
from src.search.search_service import SearchService


pytestmark = pytest.mark.unit


@pytest.fixture
def client():
    es = ElasticsearchClient()
    es._client = AsyncMock()
    es._client.search = AsyncMock(return_value={"hits": {"hits": [], "total": {"value": 0}}})
    return es


async def test_search_uses_configured_index_by_default(client):
    await client.search({"query": {"match_all": {}}})

    assert client._client.search.call_args.kwargs["index"] == client._config.index_name


async def test_search_uses_explicit_index_when_given(client):
    await client.search({"query": {"match_all": {}}}, index="help1c_docs_en")

    assert client._client.search.call_args.kwargs["index"] == "help1c_docs_en"


async def test_search_service_routes_every_query_to_its_index(client):
    service = SearchService(client, index="help1c_docs_en")

    await service.object_exists("Array")

    assert client._client.search.call_args.kwargs["index"] == "help1c_docs_en"


async def test_reindex_all_deletes_and_creates_its_own_index(client):
    """reindex_all не должен трогать чужой индекс.

    Переиндексация английской книги, стирающая русский индекс по ошибке в
    выборе имени, — самый дорогой дефект этой задачи: обнаружился бы только
    по составу ответов, а не по сбою вызова.
    """
    from src.models.doc_models import ParsedHBK, HBKFile
    from src.parsers.indexer import ElasticsearchIndexer

    empty_hbk = ParsedHBK(
        file_info=HBKFile(path="test.hbk", size=0, modified=0.0, entries_count=0),
        documentation=[],
        categories={},
        stats={},
        errors=[],
    )

    indexer = ElasticsearchIndexer(client, index="help1c_docs_en")
    await indexer.reindex_all(empty_hbk)

    assert client._client.indices.delete.call_args.kwargs["index"] == "help1c_docs_en"
    assert client._client.indices.create.call_args.kwargs["index"] == "help1c_docs_en"

"""Сторож: писать в боевой индекс тест не вправе, читать — вправе."""

from unittest.mock import AsyncMock

import pytest

from src.core.config import settings
from src.core.elasticsearch import ElasticsearchClient
from src.parsers.indexer import ElasticsearchIndexer

pytestmark = pytest.mark.unit


async def test_reindex_of_the_configured_index_is_refused():
    indexer = ElasticsearchIndexer(AsyncMock(), index=None)

    with pytest.raises(pytest.fail.Exception, match="боевой индекс"):
        await indexer.reindex_all(None)


async def test_reindex_of_the_configured_index_is_refused_when_named_explicitly():
    indexer = ElasticsearchIndexer(AsyncMock(), index=settings.elasticsearch_index)

    with pytest.raises(pytest.fail.Exception, match="боевой индекс"):
        await indexer.reindex_all(None)


async def test_reindex_of_the_english_index_is_refused():
    indexer = ElasticsearchIndexer(AsyncMock(), index=settings.elasticsearch_index_en)

    with pytest.raises(pytest.fail.Exception, match="боевой индекс"):
        await indexer.reindex_all(None)


async def test_batch_indexing_of_the_configured_index_is_refused():
    indexer = ElasticsearchIndexer(AsyncMock(), index=None)

    with pytest.raises(pytest.fail.Exception, match="боевой индекс"):
        await indexer.index_documentation(None)


async def test_batch_indexing_of_the_configured_index_is_refused_when_named_explicitly():
    indexer = ElasticsearchIndexer(AsyncMock(), index=settings.elasticsearch_index)

    with pytest.raises(pytest.fail.Exception, match="боевой индекс"):
        await indexer.index_documentation(None)


async def test_batch_indexing_of_the_english_index_is_refused():
    indexer = ElasticsearchIndexer(AsyncMock(), index=settings.elasticsearch_index_en)

    with pytest.raises(pytest.fail.Exception, match="боевой индекс"):
        await indexer.index_documentation(None)


async def test_a_single_document_write_to_the_configured_index_is_refused():
    client = ElasticsearchClient()
    client._client = AsyncMock()

    with pytest.raises(pytest.fail.Exception, match="боевой индекс"):
        await client.index_document({"id": "probe"})


async def test_a_single_document_write_to_the_production_index_is_refused():
    client = ElasticsearchClient()
    client._client = AsyncMock()

    with pytest.raises(pytest.fail.Exception, match="боевой индекс"):
        await client.index_document(
            {"id": "probe"}, index=settings.elasticsearch_index
        )


async def test_a_single_document_write_to_the_english_index_is_refused():
    client = ElasticsearchClient()
    client._client = AsyncMock()

    with pytest.raises(pytest.fail.Exception, match="боевой индекс"):
        await client.index_document(
            {"id": "probe"}, index=settings.elasticsearch_index_en
        )

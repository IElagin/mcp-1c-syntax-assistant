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


async def test_a_bulk_write_to_the_production_index_is_refused():
    """Достройка имён ходила в боевой индекс через сырой клиент, мимо сторожа."""
    from src.core.elasticsearch import ElasticsearchClient

    client = ElasticsearchClient()
    client._client = AsyncMock()

    with pytest.raises(pytest.fail.Exception, match="боевой индекс"):
        await client.bulk_update([
            {"update": {"_index": settings.elasticsearch_index, "_id": "probe"}},
            {"doc": {"name_en": "Probe"}},
        ])


async def test_a_bulk_write_to_the_english_production_index_is_refused():
    from src.core.elasticsearch import ElasticsearchClient

    client = ElasticsearchClient()
    client._client = AsyncMock()

    with pytest.raises(pytest.fail.Exception, match="боевой индекс"):
        await client.bulk_update([
            {"update": {"_index": settings.elasticsearch_index_en, "_id": "probe"}},
            {"doc": {"name_en": "Probe"}},
        ])


async def test_a_bulk_operation_without_an_index_is_refused():
    """Без _index операция метит в индекс по умолчанию, а он боевой."""
    from src.core.elasticsearch import ElasticsearchClient

    client = ElasticsearchClient()
    client._client = AsyncMock()

    with pytest.raises(pytest.fail.Exception, match="боевой индекс"):
        await client.bulk_update([
            {"update": {"_id": "probe"}},
            {"doc": {"name_en": "Probe"}},
        ])


async def test_a_bulk_write_to_its_own_index_goes_through():
    """Сторож закрывает боевые индексы, а не запись вообще."""
    from src.core.elasticsearch import ElasticsearchClient

    client = ElasticsearchClient()
    client._client = AsyncMock()
    client._client.bulk = AsyncMock(return_value={"items": []})

    result = await client.bulk_update([
        {"update": {"_index": "help1c_docs_test", "_id": "probe"}},
        {"doc": {"name_en": "Probe"}},
    ])

    assert result == {"items": []}

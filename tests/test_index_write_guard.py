"""Сторож: писать в боевой индекс тест не вправе, читать — вправе."""

from unittest.mock import AsyncMock

import pytest

from src.core.config import settings
from src.parsers.indexer import ElasticsearchIndexer

pytestmark = pytest.mark.unit


async def test_reindex_of_the_configured_index_is_refused():
    indexer = ElasticsearchIndexer(AsyncMock(), index=None)

    with pytest.raises(AssertionError, match="боевой индекс"):
        await indexer.reindex_all(None)


async def test_reindex_of_the_configured_index_is_refused_when_named_explicitly():
    indexer = ElasticsearchIndexer(AsyncMock(), index=settings.elasticsearch_index)

    with pytest.raises(AssertionError, match="боевой индекс"):
        await indexer.reindex_all(None)

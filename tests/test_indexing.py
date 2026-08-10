"""Сквозная индексация: архив -> разбор -> свой индекс."""

import pytest

from src.core.elasticsearch import ElasticsearchClient
from src.core.utils import canonical_source_file
from src.parsers.hbk_parser import HBKParser
from src.parsers.indexer import ElasticsearchIndexer
from tests.conftest import ARCHIVE_PATHS_RU

pytestmark = [
    pytest.mark.integration,
    pytest.mark.elasticsearch,
    pytest.mark.indexer,
]


async def test_every_fixture_page_reaches_its_own_index(
    hbk_fixture_archive, isolated_index
):
    """Считаем по source_file: счётчик скрыл бы потерю одной страницы и дубль другой."""
    parser = HBKParser()
    parsed = parser.parse_file(str(hbk_fixture_archive))
    assert parsed is not None, "парсер не открыл фикстурный архив"

    parsed_paths = {
        canonical_source_file(doc.source_file) for doc in parsed.documentation
    }
    assert parsed_paths == set(ARCHIVE_PATHS_RU.values())

    client = ElasticsearchClient()
    assert await client.connect(), "Elasticsearch недоступен"
    try:
        indexer = ElasticsearchIndexer(client, index=isolated_index)
        assert await indexer.reindex_all(parsed)

        await client.refresh_index(index=isolated_index)
        indexed = await client.get_documents_count(index=isolated_index)
        assert indexed == len(set(ARCHIVE_PATHS_RU.values()))
    finally:
        await client.disconnect()

"""Статья доходит до индекса и находится по типу."""

import pytest

from src.core.elasticsearch import ElasticsearchClient
from src.models.doc_models import HBKFile, ParsedHBK
from src.parsers.article_parser import parse_article_file
from src.parsers.indexer import ElasticsearchIndexer

pytestmark = [pytest.mark.integration, pytest.mark.elasticsearch, pytest.mark.indexer]

ARTICLE_HTML = "<h1>Для (For)</h1><p>Оператор цикла Для повторяет операторы внутри конструкции.</p>"


async def test_article_reaches_the_index_as_its_own_type(isolated_index):
    parsed = ParsedHBK(file_info=HBKFile(path="test", size=0, modified=0.0))
    parsed.documentation = parse_article_file("shlang", "struct_For", ARTICLE_HTML)

    client = ElasticsearchClient()
    assert await client.connect(), "Elasticsearch недоступен"
    try:
        indexer = ElasticsearchIndexer(client, index=isolated_index)
        assert await indexer.reindex_all(parsed)
        await client.refresh_index(index=isolated_index)

        assert await client.get_documents_count(index=isolated_index) == 1
        response = await client.search(
            {"query": {"bool": {"filter": [{"term": {"type": "article"}}]}}},
            index=isolated_index,
        )
        found = response["hits"]["hits"][0]["_source"]
        assert found["book"] == "shlang"
        assert found["name_ru"] == "Для"
        assert found["name_en"] == "For"
    finally:
        await client.disconnect()

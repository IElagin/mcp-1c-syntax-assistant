"""Статья доходит до индекса и находится по типу."""

import pytest

from src.core.elasticsearch import ElasticsearchClient
from src.models.doc_models import HBKFile, ParsedHBK
from src.parsers.article_parser import parse_article_file
from src.parsers.indexer import ElasticsearchIndexer
from src.search.search_service import SearchService

pytestmark = [pytest.mark.integration, pytest.mark.elasticsearch, pytest.mark.indexer]

ARTICLE_HTML = "<h1>Для (For)</h1><p>Оператор цикла Для повторяет операторы внутри конструкции.</p>"

SHARED_TITLE_SHLANG_HTML = (
    "<h1>Синтаксис</h1>"
    "<p>Общий синтаксис модуля описывает разделы объявлений, "
    "обработчиков и операторов встроенного языка.</p>"
)

SHARED_TITLE_SHQUERY_HTML = (
    "<h1>Синтаксис</h1>"
    "<p>Синтаксис языка запросов описывает предложения ВЫБРАТЬ, ИЗ, "
    "ГДЕ и СГРУППИРОВАТЬ ПО.</p>"
)

ANCHORED_SECTION_HTML = (
    "<h1>Операторы</h1>"
    '<h2><a name="AssignOperator"></a>Оператор присваивания</h2>'
    "<p>Оператор присваивания записывает значение выражения в "
    "переменную или свойство объекта.</p>"
)


async def _indexed(client: ElasticsearchClient, index: str) -> SearchService:
    """Индексирует статьи четырёх файлов книг и возвращает сервис поиска по ним.

    Заголовки и ключи берутся из настоящего parse_article_file, а не собраны
    руками: мок AsyncMock проверяет только форму ответа Elasticsearch, а не то,
    находит ли term по id и name.keyword реальный документ на реальном
    маппинге — это как раз то, что подделать мок не может.
    """
    documentation = [
        *parse_article_file("shlang", "struct_For", ARTICLE_HTML),
        *parse_article_file("shlang", "syntax_overview", SHARED_TITLE_SHLANG_HTML),
        *parse_article_file("shquery", "syntax_overview", SHARED_TITLE_SHQUERY_HTML),
        *parse_article_file("shclang", "operators", ANCHORED_SECTION_HTML),
    ]
    parsed = ParsedHBK(file_info=HBKFile(path="test", size=0, modified=0.0))
    parsed.documentation = documentation

    indexer = ElasticsearchIndexer(client, index=index)
    assert await indexer.reindex_all(parsed)
    await client.refresh_index(index=index)

    return SearchService(client, index=index)


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


async def test_article_service_answers_come_from_a_real_index(isolated_index):
    """SearchService.article() против настоящего Elasticsearch, а не мока.

    Мок из tests/test_get_article.py проверяет только форму ответа: какой
    kind вернётся на такую-то форму hits. Он не может сказать, находит ли
    настоящий маппинг term по id или name.keyword — а именно это решает,
    работает ли инструмент на боевых данных.
    """
    client = ElasticsearchClient()
    assert await client.connect(), "Elasticsearch недоступен"
    try:
        service = await _indexed(client, isolated_index)

        unique_answer = await service.article("Для (For)")
        assert unique_answer["kind"] == "article"
        assert unique_answer["document"]["full_path"] == "shlang/struct_For"

        ambiguous_answer = await service.article("Синтаксис")
        assert ambiguous_answer["kind"] == "ambiguous"
        assert {c["book"] for c in ambiguous_answer["candidates"]} == {"shlang", "shquery"}

        narrowed_answer = await service.article("Синтаксис", book="shquery")
        assert narrowed_answer["kind"] == "article"
        assert narrowed_answer["document"]["book"] == "shquery"
        assert narrowed_answer["document"]["full_path"] == "shquery/syntax_overview"

        anchor_key = "shclang/operators#AssignOperator"
        by_key_answer = await service.article(anchor_key)
        assert by_key_answer["kind"] == "article"
        assert by_key_answer["document"]["full_path"] == anchor_key
    finally:
        await client.disconnect()

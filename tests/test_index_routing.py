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

    Переиндексация одной книги, стирающая индекс другой по ошибке в выборе
    имени, — самый дорогой дефект этой задачи: обнаружился бы только по
    составу ответов, а не по сбою вызова.
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

    indexer = ElasticsearchIndexer(client, index="help1c_docs_test")
    await indexer.reindex_all(empty_hbk)

    assert client._client.indices.delete.call_args.kwargs["index"] == "help1c_docs_test"
    assert client._client.indices.create.call_args.kwargs["index"] == "help1c_docs_test"


@pytest.mark.parametrize("lang, index, dialect_name", [
    ("ru", None, "RU_DIALECT"),
    ("en", "help1c_docs_en", "EN_DIALECT"),
])
async def test_background_job_carries_lang_and_index_to_the_workers(
    mock_parsed_hbk, tmp_path, lang, index, dialect_name
):
    """Аргументы очереди обязаны доезжать до разбора и до записи.

    Потеря lang дала бы ~23 тысячи английских страниц, разобранных русским
    диалектом: заголовки глав не опознаются, и от документа остаётся только то,
    что выводится из пути. Потеря index — английскую книгу в русском индексе.
    Ни то, ни другое не роняет ни одного вызова, поэтому без этой проверки обе
    подмены проходили весь набор зелёными.
    """
    from unittest.mock import MagicMock, patch

    import src.parsers.dialects as dialects
    from src.infrastructure.background.indexing_manager import BackgroundIndexingManager
    from src.models.index_status import IndexingStatus

    book = tmp_path / "book.hbk"
    # Содержимое не важно: parse_file замокан, важно лишь, что файл есть —
    # _do_indexing проверяет существование до разбора.
    book.write_bytes(b"not a real archive")

    parser_cls = MagicMock()
    parser_cls.return_value.parse_file = MagicMock(return_value=mock_parsed_hbk)

    indexer_cls = MagicMock()
    indexer_cls.return_value.reindex_all = AsyncMock(return_value=True)

    manager = BackgroundIndexingManager()

    with patch("src.parsers.hbk_parser.HBKParser", parser_cls), \
         patch("src.parsers.indexer.ElasticsearchIndexer", indexer_cls):
        await manager._do_indexing(str(book), AsyncMock(), index=index, lang=lang)

    status = (await manager.get_status()).status
    assert status is IndexingStatus.COMPLETED, "индексация обязана дойти до конца"
    assert parser_cls.call_args.kwargs["dialect"] is getattr(dialects, dialect_name)
    assert indexer_cls.call_args.kwargs["index"] == index

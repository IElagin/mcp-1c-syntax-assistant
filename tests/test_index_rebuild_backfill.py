"""POST /index/rebuild не должен оставлять английские имена недостроенными.

Ручная переиндексация — тот же разрыв, что и старт сервера (задача 13): до
707 страниц не несут английского имени в самой русской книге и получают его
только из английского индекса. Документация (docs/CONFIGURATION.md) предлагает
завершать замену книги именно этим эндпоинтом, без перезапуска сервера — если
эндпоинт не достраивает имена сам, разрыв закрывается только случайным
следующим рестартом.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import settings
from src.api.routes.index import rebuild_index
from src.models.indexing_outcome import IndexingOutcome


pytestmark = pytest.mark.unit


async def test_successful_rebuild_triggers_backfill(tmp_path):
    """После успешной переиндексации достройка вызывается сама, без рестарта."""
    hbk_file = tmp_path / "shcntx_ru.hbk"
    hbk_file.write_bytes(b"")

    es_client = AsyncMock()
    es_client.is_connected = AsyncMock(return_value=True)
    es_client.get_documents_count = AsyncMock(return_value=23125)

    with patch("src.api.routes.index.resolve_hbk_file", return_value=hbk_file), \
         patch(
             "src.api.routes.index.index_hbk_file",
             new=AsyncMock(return_value=IndexingOutcome.indexed(documents=23125, articles=366)),
         ), \
         patch(
             "src.api.routes.index.backfill_english_names", new=AsyncMock(return_value=42)
         ) as fake_backfill:
        result = await rebuild_index(es_client=es_client)

    fake_backfill.assert_awaited_once()
    assert result["status"] == "success"


async def test_failed_reindex_does_not_trigger_backfill(tmp_path):
    """Неудачная переиндексация не должна достраивать имена по недостроенному индексу."""
    hbk_file = tmp_path / "shcntx_ru.hbk"
    hbk_file.write_bytes(b"")

    es_client = AsyncMock()
    es_client.is_connected = AsyncMock(return_value=True)

    with patch("src.api.routes.index.resolve_hbk_file", return_value=hbk_file), \
         patch(
             "src.api.routes.index.index_hbk_file",
             new=AsyncMock(return_value=IndexingOutcome.parse_failed(str(hbk_file))),
         ), \
         patch("src.api.routes.index.backfill_english_names", new=AsyncMock()) as fake_backfill:
        with pytest.raises(Exception):
            await rebuild_index(es_client=es_client)

    fake_backfill.assert_not_awaited()


async def test_backfill_failure_does_not_fail_the_whole_request(tmp_path):
    """Достройка — доп. шаг после успеха, не условие успеха: её сбой не
    должен превращать успешную переиндексацию в ошибку HTTP-запроса.
    """
    hbk_file = tmp_path / "shcntx_ru.hbk"
    hbk_file.write_bytes(b"")

    es_client = AsyncMock()
    es_client.is_connected = AsyncMock(return_value=True)
    es_client.get_documents_count = AsyncMock(return_value=23125)

    with patch("src.api.routes.index.resolve_hbk_file", return_value=hbk_file), \
         patch(
             "src.api.routes.index.index_hbk_file",
             new=AsyncMock(return_value=IndexingOutcome.indexed(documents=23125, articles=366)),
         ), \
         patch(
             "src.api.routes.index.backfill_english_names",
             new=AsyncMock(side_effect=RuntimeError("boom")),
         ):
        result = await rebuild_index(es_client=es_client)

    assert result["status"] == "success"


async def test_backfill_silently_skipped_without_english_index(tmp_path):
    """Достройка требует обоих индексов: без английского — тихо не делает
    ничего, как и при старте. Это поведение самой backfill_english_names
    (index_exists) — здесь проверяем, что эндпоинт ей не мешает.
    """
    hbk_file = tmp_path / "shcntx_ru.hbk"
    hbk_file.write_bytes(b"")

    es_client = AsyncMock()
    es_client.is_connected = AsyncMock(return_value=True)
    es_client.get_documents_count = AsyncMock(return_value=23125)
    es_client.index_exists = AsyncMock(return_value=False)

    with patch("src.api.routes.index.resolve_hbk_file", return_value=hbk_file), \
         patch(
             "src.api.routes.index.index_hbk_file",
             new=AsyncMock(return_value=IndexingOutcome.indexed(documents=23125, articles=366)),
         ):
        # backfill_english_names настоящая (не мокнута) — сама должна
        # молча вернуть 0, увидев отсутствие английского индекса.
        result = await rebuild_index(es_client=es_client)

    assert result["status"] == "success"
    es_client.index_exists.assert_awaited_once_with(index=settings.elasticsearch_index_en)

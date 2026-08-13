"""Переиндексация по языку: один вызов, отдельный исход на каждую книгу."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.api.dependencies import get_elasticsearch_client
from src.core.config import settings
from src.models.indexing_outcome import IndexingOutcome

pytestmark = pytest.mark.unit


async def _rebuild(query: str, outcomes=None, missing_books=()):
    from src.main import app

    calls = []
    outcomes = outcomes or {}

    async def remember(file_path, es_client, index=None, lang="ru", progress_callback=None):
        calls.append({"file_path": file_path, "index": index, "lang": lang})
        return outcomes.get(lang, IndexingOutcome.indexed(documents=10, articles=1))

    def resolve(directory, filename):
        return None if filename in missing_books else f"{directory}/{filename}"

    client = AsyncMock()
    client.is_connected = AsyncMock(return_value=True)
    client.get_documents_count = AsyncMock(return_value=10)

    app.dependency_overrides.clear()
    app.dependency_overrides[get_elasticsearch_client] = lambda: client
    try:
        with patch("src.api.routes.index.index_hbk_file", side_effect=remember), \
             patch("src.api.routes.index.backfill_english_names", new=AsyncMock(return_value=0)), \
             patch("src.api.routes.index.resolve_hbk_file", side_effect=resolve):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
                response = await http.post(f"/index/rebuild{query}")
    finally:
        app.dependency_overrides.clear()

    return response, calls, client


async def test_without_lang_only_the_russian_book_is_rebuilt():
    """Умолчание совпадает с прежним поведением: молчаливой смены языка нет."""
    response, calls, client = await _rebuild("")

    assert response.status_code == 200
    assert [call["lang"] for call in calls] == ["ru"]
    assert client.get_documents_count.await_count == 1


async def test_lang_en_rebuilds_the_english_index_and_only_it():
    response, calls, client = await _rebuild("?lang=en")

    assert response.status_code == 200
    assert [call["lang"] for call in calls] == ["en"]
    assert calls[0]["index"] == settings.elasticsearch_index_en
    assert settings.data.hbk_directory_en in calls[0]["file_path"]
    client.get_documents_count.assert_awaited_once_with(index=settings.elasticsearch_index_en)


async def test_lang_both_rebuilds_two_books_and_reports_two_outcomes():
    """«Русский собран, английской книги нет» — два факта, а не один статус."""
    response, calls, client = await _rebuild("?lang=both")

    assert [call["lang"] for call in calls] == ["ru", "en"]
    body = response.json()
    assert body["status"] == "success"
    assert set(body["languages"]) == {"ru", "en"}
    assert body["languages"]["ru"]["message"]
    assert body["languages"]["en"]["message"]
    assert client.get_documents_count.await_count == 2


async def test_one_book_rebuilt_and_one_failed_answers_partial_instead_of_success():
    """Отказ английской книги не должен звучать так же, как успех обеих."""
    response, _, client = await _rebuild(
        "?lang=both", outcomes={"en": IndexingOutcome.parse_failed("shcntx_root.hbk")}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial"
    assert body["languages"]["ru"]["status"] == "success"
    assert body["languages"]["en"]["status"] == "failed"
    assert body["languages"]["en"]["message"]
    client.get_documents_count.assert_awaited_once_with(index=None)


async def test_a_book_absent_next_to_a_rebuilt_one_also_answers_partial():
    """Пропущенная книга — тоже не успех: запрошены две, собрана одна."""
    response, _, client = await _rebuild(
        "?lang=both", missing_books=(settings.data.hbk_filename_en,)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial"
    assert body["languages"]["ru"]["status"] == "success"
    assert body["languages"]["en"]["status"] == "skipped"
    client.get_documents_count.assert_awaited_once_with(index=None)


async def test_an_unknown_lang_is_rejected_instead_of_silently_meaning_russian():
    response, calls, client = await _rebuild("?lang=de")

    assert response.status_code == 422
    assert calls == []
    client.get_documents_count.assert_not_awaited()


async def test_lang_both_with_neither_book_present_reports_a_skipped_verdict_for_each():
    """Ни одной книги нет на диске — 400 с исходом на каждый язык, а не общей фразой."""
    from src.main import app

    client = AsyncMock()
    client.is_connected = AsyncMock(return_value=True)

    app.dependency_overrides.clear()
    app.dependency_overrides[get_elasticsearch_client] = lambda: client
    try:
        with patch("src.api.routes.index.resolve_hbk_file", return_value=None):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
                response = await http.post("/index/rebuild?lang=both")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    languages = response.json()["detail"]["languages"]
    assert languages["ru"]["status"] == "skipped"
    assert languages["en"]["status"] == "skipped"

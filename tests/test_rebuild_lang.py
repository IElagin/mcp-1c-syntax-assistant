"""Переиндексация по языку: один вызов, отдельный исход на каждую книгу."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.core.config import settings
from src.models.indexing_outcome import IndexingOutcome

pytestmark = pytest.mark.unit


async def _rebuild(query: str, indexed=None):
    from src.main import app

    calls = []

    async def remember(file_path, es_client, index=None, lang="ru", progress_callback=None):
        calls.append({"file_path": file_path, "index": index, "lang": lang})
        return IndexingOutcome.indexed(documents=10, articles=1)

    client = AsyncMock()
    client.is_connected = AsyncMock(return_value=True)
    client.get_documents_count = AsyncMock(return_value=10)

    with patch("src.api.routes.index.index_hbk_file", side_effect=remember), \
         patch("src.api.routes.index.backfill_english_names", new=AsyncMock(return_value=0)), \
         patch("src.api.routes.index.resolve_hbk_file",
               side_effect=lambda directory, filename: f"{directory}/{filename}"), \
         patch("src.api.dependencies.get_elasticsearch_client", return_value=client):
        app.dependency_overrides.clear()
        from src.api.dependencies import get_elasticsearch_client
        app.dependency_overrides[get_elasticsearch_client] = lambda: client
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            response = await http.post(f"/index/rebuild{query}")
        app.dependency_overrides.clear()

    return response, calls


async def test_without_lang_only_the_russian_book_is_rebuilt():
    """Умолчание совпадает с прежним поведением: молчаливой смены языка нет."""
    response, calls = await _rebuild("")

    assert response.status_code == 200
    assert [call["lang"] for call in calls] == ["ru"]


async def test_lang_en_rebuilds_the_english_index_and_only_it():
    response, calls = await _rebuild("?lang=en")

    assert response.status_code == 200
    assert [call["lang"] for call in calls] == ["en"]
    assert calls[0]["index"] == settings.elasticsearch_index_en
    assert settings.data.hbk_directory_en in calls[0]["file_path"]


async def test_lang_both_rebuilds_two_books_and_reports_two_outcomes():
    """«Русский собран, английской книги нет» — два факта, а не один статус."""
    response, calls = await _rebuild("?lang=both")

    assert [call["lang"] for call in calls] == ["ru", "en"]
    body = response.json()
    assert set(body["languages"]) == {"ru", "en"}
    assert body["languages"]["ru"]["message"]
    assert body["languages"]["en"]["message"]


async def test_an_unknown_lang_is_rejected_instead_of_silently_meaning_russian():
    response, calls = await _rebuild("?lang=de")

    assert response.status_code == 422
    assert calls == []


async def test_lang_both_with_neither_book_present_reports_a_skipped_verdict_for_each():
    """Ни одной книги нет на диске — 400 с исходом на каждый язык, а не общей фразой."""
    from src.main import app

    client = AsyncMock()
    client.is_connected = AsyncMock(return_value=True)

    with patch("src.api.routes.index.resolve_hbk_file", return_value=None), \
         patch("src.api.dependencies.get_elasticsearch_client", return_value=client):
        app.dependency_overrides.clear()
        from src.api.dependencies import get_elasticsearch_client
        app.dependency_overrides[get_elasticsearch_client] = lambda: client
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            response = await http.post("/index/rebuild?lang=both")
        app.dependency_overrides.clear()

    assert response.status_code == 400
    languages = response.json()["detail"]["languages"]
    assert languages["ru"]["status"] == "skipped"
    assert languages["en"]["status"] == "skipped"

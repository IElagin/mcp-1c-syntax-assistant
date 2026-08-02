"""Английская книга индексируется отдельно и необязательна."""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.startup import auto_index_on_startup


pytestmark = pytest.mark.integration


async def test_missing_english_book_does_not_break_startup(tmp_path):
    """Нет английской книги — сервер поднимается, английского индекса нет.

    Книга проприетарная и есть не у всех; отсутствие второй книги не может
    быть отказом в обслуживании первой.
    """
    es_client = AsyncMock()
    es_client.index_exists = AsyncMock(return_value=True)
    es_client.get_documents_count = AsyncMock(return_value=23025)

    with patch("src.core.startup.settings") as fake_settings:
        fake_settings.data.hbk_directory = str(tmp_path)
        fake_settings.data.hbk_filename = "shcntx_ru.hbk"
        fake_settings.data.hbk_directory_en = str(tmp_path / "nope")
        fake_settings.data.hbk_filename_en = "shcntx_root.hbk"
        fake_settings.should_reindex_on_startup = False

        await auto_index_on_startup(es_client)

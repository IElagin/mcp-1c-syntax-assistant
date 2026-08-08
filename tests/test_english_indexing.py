"""Английская книга индексируется отдельно и необязательна."""

from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.indexing import auto_index_on_startup


pytestmark = pytest.mark.integration


async def test_missing_english_book_does_not_break_startup(tmp_path):
    """Нет английской книги — сервер поднимается, английского индекса нет.

    Книга проприетарная и есть не у всех; отсутствие второй книги не может
    быть отказом в обслуживании первой. Без assert-ов (как тест был впервые
    написан) он проходил бы при любом поведении _schedule_book — в том числе
    при падении с необработанным исключением после первой строки лога, если
    бы вызов дошёл до asyncio.create_task; проверяем именно то, ради чего
    тест задуман: не падает и не планирует индексацию ни для одной книги
    (ни .hbk-файла русской книги, ни каталога английской в этом тесте нет).
    """
    es_client = AsyncMock()
    es_client.index_exists = AsyncMock(return_value=True)
    es_client.get_documents_count = AsyncMock(return_value=23025)

    with patch("src.infrastructure.indexing.settings") as fake_settings, \
         patch("src.infrastructure.indexing.asyncio.create_task") as fake_create_task:
        fake_settings.data.hbk_directory = str(tmp_path)
        fake_settings.data.hbk_filename = "shcntx_ru.hbk"
        fake_settings.data.hbk_directory_en = str(tmp_path / "nope")
        fake_settings.data.hbk_filename_en = "shcntx_root.hbk"
        fake_settings.should_reindex_on_startup = False

        # Не должно бросить исключение — сервер обязан подняться и без
        # английской книги.
        await auto_index_on_startup(es_client)

        # Ни для одной книги не должна была планироваться фоновая индексация:
        # resolve_hbk_file возвращает None и для отсутствующей английской
        # книги, и для несуществующего пути русской в этом тесте — обе ветки
        # обязаны остановиться раньше, чем дойдут до asyncio.create_task.
        fake_create_task.assert_not_called()

    # До проверки состояния индекса дело не должно было дойти ни для одной
    # книги: раз .hbk-файла нет, index_exists/get_documents_count незачем
    # вызывать вовсе.
    es_client.index_exists.assert_not_called()
    es_client.get_documents_count.assert_not_called()

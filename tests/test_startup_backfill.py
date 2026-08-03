"""Достройка английских имён — последний шаг после обеих индексаций, не гонка с ней.

Задача 6 сделала индексацию последовательной очередью
(BackgroundIndexingManager): обе книги, какие есть, встают в одну очередь и
обрабатываются одна за одной. Раньше каждая книга планировалась отдельной
задачей с собственной 5-секундной паузой — у двух независимо запущенных
задержек нет гарантии порядка. Задача 13 объединяет оба запуска в одну
задачу (_run_queue_then_backfill), чтобы порядок «сначала обе книги встали в
очередь, потом дождались опустошения, потом достройка» был гарантирован
последовательностью await, а не почти-одновременными таймерами.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config import settings
from src.core.startup import _run_queue_then_backfill


pytestmark = pytest.mark.unit


async def test_backfill_runs_only_after_queue_is_idle():
    """backfill не должен вызваться, пока is_indexing() отвечает True."""
    es_client = AsyncMock()
    manager = MagicMock()
    manager.is_indexing = MagicMock(side_effect=[True, True, False])

    call_order = []

    async def fake_start_indexing(*args, **kwargs):
        call_order.append(("start_indexing", kwargs.get("lang")))

    manager.start_indexing = AsyncMock(side_effect=fake_start_indexing)

    async def fake_backfill(*args, **kwargs):
        call_order.append(("backfill",))
        return 5

    with patch("src.core.startup.get_indexing_manager", return_value=manager), \
         patch("src.core.startup.backfill_english_names", side_effect=fake_backfill) as fake_backfill_mock, \
         patch("src.core.startup.asyncio.sleep", new=AsyncMock()):
        await _run_queue_then_backfill(es_client, ru_file="ru.hbk", en_file="en.hbk")

    assert call_order == [
        ("start_indexing", "ru"),
        ("start_indexing", "en"),
        ("backfill",),
    ], "обе книги должны встать в очередь до достройки, достройка — после её опустошения"
    fake_backfill_mock.assert_awaited_once()


async def test_backfill_runs_even_when_english_book_is_absent():
    """Английская книга необязательна: индексируется только русская, но
    достройка всё равно вызывается — молчаливый выход без английского
    индекса это обязанность backfill_english_names (index_exists), а не
    оркестратора в startup.py.
    """
    es_client = AsyncMock()
    manager = MagicMock()
    manager.is_indexing = MagicMock(side_effect=[False])

    call_order = []

    async def fake_start_indexing(*args, **kwargs):
        call_order.append(kwargs.get("lang"))

    manager.start_indexing = AsyncMock(side_effect=fake_start_indexing)

    async def fake_backfill(*args, **kwargs):
        call_order.append("backfill")
        return 0

    with patch("src.core.startup.get_indexing_manager", return_value=manager), \
         patch("src.core.startup.backfill_english_names", side_effect=fake_backfill):
        await _run_queue_then_backfill(es_client, ru_file="ru.hbk", en_file=None)

    assert call_order == ["ru", "backfill"]
    manager.start_indexing.assert_awaited_once()


async def test_indexing_failure_does_not_block_startup():
    """Если постановка книги в очередь бросает исключение, достройка не
    запускается «на всякий случай» с недостроенными индексами, но и сам
    сервер не должен упасть — это фоновая задача.
    """
    es_client = AsyncMock()
    manager = MagicMock()
    manager.start_indexing = AsyncMock(side_effect=RuntimeError("boom"))
    manager.is_indexing = MagicMock(return_value=False)

    with patch("src.core.startup.get_indexing_manager", return_value=manager), \
         patch("src.core.startup.backfill_english_names", new=AsyncMock()) as fake_backfill_mock:
        await _run_queue_then_backfill(es_client, ru_file="ru.hbk", en_file="en.hbk")

    fake_backfill_mock.assert_not_awaited()


async def test_each_book_goes_to_its_own_index():
    """Индекс назначения — самая дорогая ошибка ветки, и она была не покрыта.

    Уберите index= у второго вызова — английская книга проиндексируется в
    help1c_docs, а reindex_all перед этим удалит русский индекс целиком.
    Пользователь получает сервер, у которого /health показывает 23 104
    «здоровых» документа, а все русские запросы отвечают «не найдено».

    Прежний фейк записывал только lang, поэтому эту подмену не замечал ни один
    тест во всём наборе: порядок ("ru", "en") от потери index= не менялся.
    """
    es_client = AsyncMock()
    manager = MagicMock()
    manager.is_indexing = MagicMock(return_value=False)

    calls = []

    async def fake_start_indexing(*args, **kwargs):
        calls.append({"lang": kwargs.get("lang"), "index": kwargs.get("index")})

    manager.start_indexing = AsyncMock(side_effect=fake_start_indexing)

    with patch("src.core.startup.get_indexing_manager", return_value=manager), \
         patch("src.core.startup.backfill_english_names", new=AsyncMock()):
        await _run_queue_then_backfill(es_client, ru_file="ru.hbk", en_file="en.hbk")

    assert calls == [
        # None — «индекс из конфигурации», то есть русский. Явный None здесь
        # значим: он отличает «индекс не задан намеренно» от «аргумент потеряли».
        {"lang": "ru", "index": None},
        {"lang": "en", "index": settings.elasticsearch_index_en},
    ], calls


async def test_english_book_never_goes_to_the_russian_index():
    """Отдельная проверка того же с другой стороны: перепутанный index=.

    Равенство списков выше упало бы и от перестановки книг местами; здесь
    утверждается именно то, чего нельзя допустить, — английская книга не имеет
    права попасть в индекс русской ни при каком составе очереди.
    """
    es_client = AsyncMock()
    manager = MagicMock()
    manager.is_indexing = MagicMock(return_value=False)

    by_lang = {}

    async def fake_start_indexing(*args, **kwargs):
        by_lang[kwargs.get("lang")] = kwargs.get("index")

    manager.start_indexing = AsyncMock(side_effect=fake_start_indexing)

    with patch("src.core.startup.get_indexing_manager", return_value=manager), \
         patch("src.core.startup.backfill_english_names", new=AsyncMock()):
        await _run_queue_then_backfill(es_client, ru_file="ru.hbk", en_file="en.hbk")

    english_index = by_lang["en"] or settings.elasticsearch_index
    assert english_index == settings.elasticsearch_index_en
    assert english_index != settings.elasticsearch_index

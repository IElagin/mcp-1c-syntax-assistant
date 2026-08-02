"""Startup logic для приложения."""

import asyncio
from pathlib import Path
from typing import Optional

from src.core.config import settings
from src.core.logging import get_logger
from src.core.elasticsearch import ElasticsearchClient
from src.infrastructure.background.indexing_manager import get_indexing_manager
from src.parsers.dialects import dialect_for

logger = get_logger(__name__)


def resolve_hbk_file(hbk_directory: str, filename: str) -> Optional[Path]:
    """Путь к книге справки, которую следует индексировать.

    Возвращает None, если книги нет: подменять её первым попавшимся .hbk
    нельзя. Сервер с чужой книгой в индексе выглядит исправным — отвечает,
    документов много, — и расхождение обнаруживается только по языку ответов.
    """
    path = Path(hbk_directory) / filename
    return path if path.exists() else None


async def _schedule_book(
    es_client: ElasticsearchClient,
    directory: str,
    filename: str,
    index: Optional[str],
    lang: str,
) -> None:
    """Планирует индексацию одной книги в свой индекс.

    Отсутствие книги — не ошибка: английская поставляется не всем, а русская
    может быть ещё не скопирована в data/hbk при первом запуске.
    """
    hbk_file = resolve_hbk_file(directory, filename)
    if hbk_file is None:
        logger.info(f"Книга {filename} не найдена в {directory} — индекс {index} не строится")
        return

    if not settings.should_reindex_on_startup:
        if await es_client.index_exists(index=index):
            docs_count = await es_client.get_documents_count(index=index)
            if docs_count > 0:
                logger.info(f"Индекс {index} уже содержит {docs_count} документов")
                return

    logger.info(f"Запланирована фоновая индексация файла: {hbk_file} -> {index}")
    asyncio.create_task(
        _delayed_background_indexing(str(hbk_file), es_client, index=index, lang=lang)
    )


async def auto_index_on_startup(es_client: ElasticsearchClient):
    """
    Автоматическая индексация обеих книг в фоновом режиме при запуске.

    Русская и английская книги независимы: у каждой свой каталог, свой индекс
    и свой диалект разбора. Каждая планируется отдельным вызовом
    _schedule_book, поэтому отсутствие или готовность одной книги не влияет
    на решение по другой.

    Args:
        es_client: Подключённый клиент Elasticsearch
    """
    try:
        await _schedule_book(
            es_client,
            settings.data.hbk_directory,
            settings.data.hbk_filename,
            index=None,  # None -> settings.elasticsearch_index, как раньше
            lang="ru",
        )
        await _schedule_book(
            es_client,
            settings.data.hbk_directory_en,
            settings.data.hbk_filename_en,
            index=settings.elasticsearch_index_en,
            lang="en",
        )
    except Exception as e:
        logger.error(f"Ошибка при планировании автоиндексации: {e}")


async def _delayed_background_indexing(
    file_path: str,
    es_client: ElasticsearchClient,
    index: Optional[str] = None,
    lang: str = "ru",
):
    """
    Отложенная фоновая индексация одной книги.

    Даёт приложению время на полный запуск перед началом индексации, затем
    передаёт книгу общему менеджеру фоновой индексации. Русская и английская
    книги планируются почти одновременно (обе с этой же 5-секундной паузой),
    но менеджер не запускает их параллельно — он держит один активный слот и
    ставит вторую книгу в очередь. Это осознанный выбор, а не ограничение:
    Elasticsearch поднят с кучей 1 ГБ, и обе книги всё равно строятся в фоне,
    так что параллельный разбор не ускорил бы ответ пользователю, а только
    боролся бы за память. Последовательная очередь даёт заодно честный
    /health.indexing_active: он остаётся True, пока не готовы обе книги, а не
    только первая.

    Args:
        file_path: Путь к .hbk файлу
        es_client: Клиент Elasticsearch
        index: Индекс назначения (None — индекс из конфигурации)
        lang: Язык книги — выбирает диалект разбора
    """
    # Даём приложению 5 секунд на полный запуск
    await asyncio.sleep(5)

    logger.info(f"Начинаем фоновую индексацию ({lang}): {file_path}")

    try:
        manager = get_indexing_manager()
        await manager.start_indexing(file_path=file_path, es_client=es_client, index=index, lang=lang)
    except Exception as e:
        logger.error(f"Ошибка при запуске фоновой индексации ({lang}): {e}")


async def index_hbk_file(
    file_path: str,
    es_client: ElasticsearchClient,
    index: Optional[str] = None,
    lang: str = "ru",
) -> bool:
    """
    Индексирует .hbk файл в Elasticsearch (используется и для ручной
    индексации через API, и для фоновой индексации при запуске).

    Args:
        file_path: Путь к .hbk файлу
        es_client: Подключённый клиент Elasticsearch
        index: Индекс назначения (None — индекс из конфигурации)
        lang: Язык книги — выбирает диалект разбора HTML

    Returns:
        bool: True если индексация успешна, False иначе
    """
    try:
        from src.parsers.hbk_parser import HBKParser
        from src.parsers.indexer import ElasticsearchIndexer

        logger.info(f"Начинаем синхронную индексацию файла: {file_path}")

        # Парсим .hbk файл в отдельном потоке (не блокируем event loop)
        parser = HBKParser(dialect=dialect_for(lang))
        logger.info("Запускаем парсинг HBK файла в отдельном потоке...")
        parsed_hbk = await asyncio.to_thread(parser.parse_file, file_path)
        logger.info("Парсинг HBK файла завершен")

        if not parsed_hbk:
            logger.error("Ошибка парсинга .hbk файла")
            return False

        if not parsed_hbk.documentation:
            logger.warning("В файле не найдена документация для индексации")
            return False

        logger.info(f"Найдено {len(parsed_hbk.documentation)} документов для индексации")

        # Индексируем в Elasticsearch
        indexer = ElasticsearchIndexer(es_client, index=index)
        success = await indexer.reindex_all(parsed_hbk)

        if success:
            docs_count = await es_client.get_documents_count(index=index)
            logger.info(f"Индексация завершена. Документов в индексе: {docs_count}")

        return success

    except Exception as e:
        logger.error(f"Ошибка индексации файла {file_path}: {e}")
        return False

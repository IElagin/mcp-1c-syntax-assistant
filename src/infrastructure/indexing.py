"""Индексация книг справки: разовая, по запросу и фоновая при запуске."""

import asyncio
from pathlib import Path
from typing import Callable, Optional

from src.core.config import settings
from src.core.constants import MAX_TOLERATED_PAGE_LOSS_SHARE
from src.core.logging import get_logger
from src.core.elasticsearch import ElasticsearchClient
from src.infrastructure.background.indexing_manager import get_indexing_manager
from src.models.doc_models import ParsedHBK
from src.parsers.dialects import dialect_for
from src.parsers.name_backfill import backfill_english_names

logger = get_logger(__name__)

ProgressCallback = Callable[[int, int], None]


def _book_lost_too_many_pages(parsed_hbk: ParsedHBK) -> bool:
    """Книга потеряла столько страниц, что заменять ею живой индекс нельзя."""
    lost_pages = parsed_hbk.pages_attempted - parsed_hbk.pages_parsed
    if not lost_pages:
        return False

    lost_share = parsed_hbk.lost_pages_share
    if lost_share > MAX_TOLERATED_PAGE_LOSS_SHARE:
        logger.error(
            f"Книга потеряла {lost_pages} страниц из {parsed_hbk.pages_attempted} "
            f"({lost_share:.0%}) — это больше допустимых "
            f"{MAX_TOLERATED_PAGE_LOSS_SHARE:.0%}, переиндексация отклонена, "
            f"текущий индекс не тронут"
        )
        return True

    logger.warning(
        f"Книга прочитана не полностью: потеряно страниц — {lost_pages} из "
        f"{parsed_hbk.pages_attempted}, из них не прочитано — {len(parsed_hbk.errors)}; "
        f"в индекс всё равно уйдут разобранные {parsed_hbk.pages_parsed}"
    )
    return False


def resolve_hbk_file(hbk_directory: str, filename: str) -> Optional[Path]:
    """Путь к книге справки, которую следует индексировать.

    Возвращает None, если книги нет: подменять её первым попавшимся .hbk
    нельзя. Сервер с чужой книгой в индексе выглядит исправным — отвечает,
    документов много, — и расхождение обнаруживается только по языку ответов.
    """
    path = Path(hbk_directory) / filename
    return path if path.exists() else None


async def _needs_indexing(
    es_client: ElasticsearchClient,
    directory: str,
    filename: str,
    index: Optional[str],
) -> Optional[Path]:
    """Решает, нужна ли книге индексация, и возвращает её файл, если да.

    Только решение — без побочных эффектов и без паузы. Раньше это же
    решение сразу порождало отложенную задачу для книги (см. историю); задаче
    13 нужно знать результат по обеим книгам ДО того, как что-либо запущено,
    чтобы после запустить ровно одну задачу на обе книги и дождаться именно
    её конца, а не гадать по независимым таймерам, когда закончилась вторая
    (см. auto_index_on_startup и _run_queue_then_backfill).

    Отсутствие книги — не ошибка: английская поставляется не всем, а русская
    может быть ещё не скопирована в data/hbk при первом запуске.
    """
    hbk_file = resolve_hbk_file(directory, filename)
    if hbk_file is None:
        logger.info(f"Книга {filename} не найдена в {directory} — индекс {index} не строится")
        return None

    if not settings.should_reindex_on_startup:
        if await es_client.index_exists(index=index):
            docs_count = await es_client.get_documents_count(index=index)
            if docs_count > 0:
                logger.info(f"Индекс {index} уже содержит {docs_count} документов")
                return None

    return hbk_file


async def auto_index_on_startup(es_client: ElasticsearchClient):
    """
    Автоматическая индексация обеих книг в фоновом режиме при запуске.

    Русская и английская книги независимы: у каждой свой каталог, свой индекс
    и свой диалект разбора. Решение по каждой ("нужна ли индексация")
    принимается отдельно (_needs_indexing), поэтому отсутствие или готовность
    одной книги не влияет на решение по другой. Но сама индексация и
    достройка английских имён (задача 13) запускаются ОДНОЙ фоновой задачей
    на обе книги сразу — так достройка гарантированно стартует после того,
    как очередь менеджера (задача 6) опустеет целиком, а не рискует
    сработать раньше второй книги из-за двух независимых 5-секундных пауз.

    Args:
        es_client: Подключённый клиент Elasticsearch
    """
    try:
        ru_file = await _needs_indexing(
            es_client,
            settings.data.hbk_directory,
            settings.data.hbk_filename,
            index=None,  # None -> settings.elasticsearch_index, как раньше
        )
        en_file = await _needs_indexing(
            es_client,
            settings.data.hbk_directory_en,
            settings.data.hbk_filename_en,
            index=settings.elasticsearch_index_en,
        )

        if ru_file is not None or en_file is not None:
            logger.info(f"Запланирована фоновая индексация: ru={ru_file}, en={en_file}")
            asyncio.create_task(_delayed_indexing_and_backfill(es_client, ru_file, en_file))
    except Exception as e:
        logger.error(f"Ошибка при планировании автоиндексации: {e}")


async def _delayed_indexing_and_backfill(
    es_client: ElasticsearchClient,
    ru_file: Optional[Path],
    en_file: Optional[Path],
) -> None:
    """Даёт приложению 5 секунд на полный запуск, затем индексирует и достраивает имена.

    Пауза вынесена в отдельную обёртку вокруг _run_queue_then_backfill, чтобы
    тест мог проверить порядок «индексация → достройка» без реального
    ожидания (см. tests/test_startup_backfill.py).
    """
    await asyncio.sleep(5)
    await _run_queue_then_backfill(es_client, ru_file, en_file)


async def _run_queue_then_backfill(
    es_client: ElasticsearchClient,
    ru_file: Optional[Path],
    en_file: Optional[Path],
) -> None:
    """
    Индексирует обе книги (какие есть) через очередь менеджера, затем достраивает имена.

    Обе книги ставятся в очередь менеджера (задача 6) последовательными
    await в одной задаче — гарантированный порядок, а не почти-одновременные
    таймеры двух раздельных задач. Раз менеджер держит один активный слот
    (см. BackgroundIndexingManager), is_indexing() остаётся True, пока не
    готовы обе книги; поэтому достройка ждёт именно этого — цикл ниже, а не
    фиксированную паузу — и идёт последним шагом, а не гонкой с индексацией.

    Args:
        es_client: Клиент Elasticsearch
        ru_file: Файл русской книги, если её нужно (пере)индексировать
        en_file: Файл английской книги, если её нужно (пере)индексировать
    """
    manager = get_indexing_manager()

    try:
        if ru_file is not None:
            logger.info(f"Начинаем фоновую индексацию (ru): {ru_file}")
            await manager.start_indexing(str(ru_file), es_client, index=None, lang="ru")
        if en_file is not None:
            logger.info(f"Начинаем фоновую индексацию (en): {en_file}")
            await manager.start_indexing(
                str(en_file), es_client, index=settings.elasticsearch_index_en, lang="en"
            )
    except Exception as e:
        # Очередь не запущена (или запущена частично) — достройку по
        # недостроенным индексам не запускаем.
        logger.error(f"Ошибка при запуске фоновой индексации: {e}")
        return

    while manager.is_indexing():
        await asyncio.sleep(0.5)

    try:
        updated = await backfill_english_names(
            es_client, settings.elasticsearch_index, settings.elasticsearch_index_en
        )
        if updated:
            logger.info(f"Достроено английских имён при старте: {updated}")
    except Exception as e:
        logger.error(f"Ошибка при достройке английских имён: {e}")


async def index_hbk_file(
    file_path: str,
    es_client: ElasticsearchClient,
    index: Optional[str] = None,
    lang: str = "ru",
    progress_callback: Optional[ProgressCallback] = None,
) -> bool:
    """
    Индексирует .hbk файл в Elasticsearch (используется и для ручной
    индексации через API, и для фоновой индексации при запуске).

    Args:
        file_path: Путь к .hbk файлу
        es_client: Подключённый клиент Elasticsearch
        index: Индекс назначения (None — индекс из конфигурации)
        lang: Язык книги — выбирает диалект разбора HTML
        progress_callback: Callback прогресса (indexed, total) для очереди

    Returns:
        bool: True если индексация успешна, False иначе
    """
    try:
        from src.parsers.hbk_parser import HBKParser
        from src.parsers.indexer import ElasticsearchIndexer
        from src.parsers.article_books import parse_article_books

        logger.info(f"Начинаем индексацию файла: {file_path}")

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

        if _book_lost_too_many_pages(parsed_hbk):
            return False

        logger.info(f"Найдено {len(parsed_hbk.documentation)} документов для индексации")

        directory = str(Path(file_path).parent)
        articles, absent = await asyncio.to_thread(parse_article_books, directory, lang)
        if articles:
            parsed_hbk.documentation.extend(articles)
            logger.info(f"Добавлено статей к индексации: {len(articles)}")
        if absent:
            logger.info(f"Книги статей отсутствуют: {', '.join(absent)}")

        indexer = ElasticsearchIndexer(es_client, index=index)
        success = await indexer.reindex_all(parsed_hbk, progress_callback=progress_callback)

        if success:
            docs_count = await es_client.get_documents_count(index=index)
            logger.info(f"Индексация завершена. Документов в индексе: {docs_count}")

        return success

    except Exception as e:
        logger.error(f"Ошибка индексации файла {file_path}: {e}")
        return False

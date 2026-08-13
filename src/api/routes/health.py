"""Health check endpoints."""

from pathlib import Path
from typing import List, Tuple

from fastapi import APIRouter, Depends

from src.models.mcp_models import HealthResponse
from src.core.constants import ARTICLE_BOOKS
from src.core.elasticsearch import ElasticsearchClient
from src.core.metrics import get_metrics_collector
from src.core.config import settings
from src.api.dependencies import get_elasticsearch_client, get_indexing_manager
from src.infrastructure.background.indexing_manager import BackgroundIndexingManager
from src.parsers.v8_container import HelpBookArchive

router = APIRouter(tags=["health"])


def _article_book_state(directory: str, filename_attr: str) -> Tuple[List[str], List[str]]:
    """Ключи книг статей, которых нет, и тех, что лежат на месте, но не читаются."""
    missing, unreadable = [], []
    for book in ARTICLE_BOOKS:
        path = Path(directory) / getattr(book, filename_attr)
        if not path.exists():
            missing.append(book.key)
            continue
        try:
            with HelpBookArchive(path) as archive:
                archive.names()
        except Exception:
            unreadable.append(book.key)
    return missing, unreadable


@router.get("/health", response_model=HealthResponse)
async def health_check(
    es_client: ElasticsearchClient = Depends(get_elasticsearch_client),
    indexing_manager: BackgroundIndexingManager = Depends(get_indexing_manager),
    metrics=Depends(get_metrics_collector)
):
    """
    Проверка состояния системы.
    
    Возвращает информацию о:
    - Статусе приложения (всегда healthy если приложение запущено)
    - Подключении к Elasticsearch
    - Состоянии индекса
    - Статусе фоновой индексации
    """
    async with metrics.timer("health_check.duration"):
        missing_books, unreadable_books = _article_book_state(
            settings.data.hbk_directory, "ru"
        )
        missing_books_en, unreadable_books_en = _article_book_state(
            settings.data.hbk_directory_en, "en"
        )

        es_connected = await es_client.is_connected()
        index_exists = bool(await es_client.index_exists()) if es_connected else False
        docs_count = await es_client.get_documents_count() if index_exists else None

        index_en = settings.elasticsearch_index_en
        index_en_exists = bool(await es_client.index_exists(index=index_en)) if es_connected else False
        docs_count_en = await es_client.get_documents_count(index=index_en) if index_en_exists else None

        indexing_progress = await indexing_manager.get_status()

    await metrics.increment("health_check.requests")

    return HealthResponse(
        status="healthy" if es_connected else "unhealthy",
        elasticsearch=es_connected,
        index_exists=index_exists,
        documents_count=docs_count,
        indexing_status=indexing_progress.status.value,
        indexing_active=indexing_manager.is_indexing(),
        index_en_exists=index_en_exists,
        documents_count_en=docs_count_en,
        missing_article_books=missing_books,
        missing_article_books_en=missing_books_en,
        unreadable_article_books=unreadable_books,
        unreadable_article_books_en=unreadable_books_en,
    )

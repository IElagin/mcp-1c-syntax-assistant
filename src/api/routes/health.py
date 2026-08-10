"""Health check endpoints."""

from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends

from src.models.mcp_models import HealthResponse
from src.core.constants import ARTICLE_BOOKS
from src.core.elasticsearch import ElasticsearchClient
from src.core.metrics import get_metrics_collector
from src.core.config import settings
from src.api.dependencies import get_elasticsearch_client, get_indexing_manager
from src.infrastructure.background.indexing_manager import BackgroundIndexingManager

router = APIRouter(tags=["health"])


def _missing_article_books(directory: str, filename_attr: str) -> List[str]:
    """Ключи книг статей, чьего файла нет в каталоге поставки данного языка."""
    return [
        book.key for book in ARTICLE_BOOKS
        if not (Path(directory) / getattr(book, filename_attr)).exists()
    ]


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
        es_connected = await es_client.is_connected()
        index_exists = bool(await es_client.index_exists()) if es_connected else False
        docs_count = await es_client.get_documents_count() if index_exists else None

        index_en = settings.elasticsearch_index_en
        index_en_exists = bool(await es_client.index_exists(index=index_en)) if es_connected else False
        docs_count_en = await es_client.get_documents_count(index=index_en) if index_en_exists else None

        indexing_progress = await indexing_manager.get_status()

        missing_books = _missing_article_books(settings.data.hbk_directory, "ru")
        missing_books_en = _missing_article_books(settings.data.hbk_directory_en, "en")

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
    )

"""Index management endpoints."""

from fastapi import APIRouter, HTTPException, Depends

from src.core.config import settings
from src.core.elasticsearch import ElasticsearchClient
from src.core.logging import get_logger
from src.infrastructure.indexing import index_hbk_file, resolve_hbk_file
from src.api.dependencies import get_elasticsearch_client, get_indexing_manager
from src.api.indexing_messages import describe_outcome
from src.infrastructure.background.indexing_manager import BackgroundIndexingManager
from src.parsers.name_backfill import backfill_english_names

router = APIRouter(prefix="/index", tags=["index"])
logger = get_logger(__name__)


@router.get("/status")
async def index_status(
    es_client: ElasticsearchClient = Depends(get_elasticsearch_client),
    indexing_manager: BackgroundIndexingManager = Depends(get_indexing_manager)
):
    """
    Получить статус индекса и фоновой индексации.
    
    Возвращает:
    - Статус подключения к Elasticsearch
    - Информацию о существовании индекса
    - Количество документов в индексе
    - Статус фоновой индексации (если активна)
    """
    es_connected = await es_client.is_connected()
    index_exists = bool(await es_client.index_exists()) if es_connected else False
    docs_count = await es_client.get_documents_count() if index_exists else 0
    
    progress = await indexing_manager.get_status()
    reported = progress.to_dict()
    if progress.outcome is not None:
        reported["error_message"] = (
            None if progress.outcome.ok else describe_outcome(progress.outcome)
        )
        reported["message"] = describe_outcome(progress.outcome)

    return {
        "elasticsearch_connected": es_connected,
        "index_exists": index_exists,
        "documents_count": docs_count,
        "index_name": settings.elasticsearch.index_name,
        "indexing": {
            "is_active": indexing_manager.is_indexing(),
            **reported,
        }
    }


@router.post("/rebuild")
async def rebuild_index(
    es_client: ElasticsearchClient = Depends(get_elasticsearch_client)
):
    """Переиндексация документации из .hbk файла."""
    try:
        hbk_file = resolve_hbk_file(
            settings.data.hbk_directory, settings.data.hbk_filename
        )
        if hbk_file is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Книга справки {settings.data.hbk_filename} не найдена "
                    f"в {settings.data.hbk_directory}"
                )
            )

        if not await es_client.is_connected():
            raise HTTPException(
                status_code=503,
                detail="Elasticsearch недоступен"
            )

        logger.info(f"Начинаем переиндексацию файла: {hbk_file}")

        outcome = await index_hbk_file(str(hbk_file), es_client)

        if not outcome.ok:
            raise HTTPException(status_code=500, detail=describe_outcome(outcome))

        docs_count = await es_client.get_documents_count()

        try:
            updated = await backfill_english_names(
                es_client, settings.elasticsearch_index, settings.elasticsearch_index_en
            )
            if updated:
                logger.info(f"Достроено английских имён после переиндексации: {updated}")
        except Exception as e:
            logger.error(f"Ошибка достройки английских имён после переиндексации: {e}")

        return {
            "status": "success",
            "message": describe_outcome(outcome),
            "file": str(hbk_file),
            "documents_count": docs_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка переиндексации: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Внутренняя ошибка: {str(e)}"
        )

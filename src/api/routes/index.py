"""Index management endpoints."""

from enum import Enum
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Depends

from src.core.config import settings
from src.core.elasticsearch import ElasticsearchClient
from src.core.logging import get_logger
from src.core.versions import UNVERSIONED, UnknownVersionError, resolve_version
from src.infrastructure.indexing import index_hbk_file, resolve_hbk_file
from src.api.dependencies import get_elasticsearch_client, get_indexing_manager
from src.api.indexing_messages import describe_outcome
from src.infrastructure.background.indexing_manager import BackgroundIndexingManager
from src.parsers.name_backfill import backfill_english_names
from src.search.search_service import SearchService

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


class RebuildLang(str, Enum):
    """Какие книги перестраивать. Значения совпадают с Lang плюс «обе»."""

    RU = "ru"
    EN = "en"
    BOTH = "both"


def _russian_book(version: Optional[str]) -> tuple:
    resolved = resolve_version(version)
    index = None if resolved.name == UNVERSIONED else resolved.index
    return resolved.hbk_directory, settings.data.hbk_filename, index


_BOOKS = {
    "ru": _russian_book,
    "en": lambda version: (
        settings.data.hbk_directory_en,
        settings.data.hbk_filename_en,
        settings.elasticsearch_index_en,
    ),
}


def _version_or_400(version: Optional[str]):
    """Версия запроса; неизвестная — ответ 400 с перечнем версий."""
    try:
        return resolve_version(version)
    except UnknownVersionError as error:
        raise HTTPException(
            status_code=400,
            detail=f"Версии {error.version} нет. Есть: {', '.join(error.available) or 'версии не настроены'}",
        ) from None


def _requested_languages(lang: RebuildLang) -> list:
    return ["ru", "en"] if lang is RebuildLang.BOTH else [lang.value]


def _overall_status(reported: Dict[str, dict]) -> str:
    """Итог вызова целиком: собраны все запрошенные книги, часть или ни одной."""
    verdicts = {report["status"] for report in reported.values()}
    if verdicts == {"success"}:
        return "success"
    return "partial" if "success" in verdicts else "failed"


@router.post("/rebuild")
async def rebuild_index(
    lang: RebuildLang = RebuildLang.RU,
    version: Optional[str] = None,
    es_client: ElasticsearchClient = Depends(get_elasticsearch_client),
):
    """Переиндексация книг справки: русской, английской или обеих.

    Отдаёт исход по каждому запрошенному языку и итог вызова целиком —
    success, partial или failed.
    """
    russian_index = _version_or_400(version).index
    try:
        languages = _requested_languages(lang)
        reported: Dict[str, dict] = {}
        resolved: Dict[str, tuple] = {}

        for language in languages:
            directory, filename, index = _BOOKS[language](version)
            hbk_file = resolve_hbk_file(directory, filename)
            if hbk_file is None:
                reported[language] = {
                    "status": "skipped",
                    "message": f"Книга справки {filename} не найдена в {directory}",
                }
            else:
                resolved[language] = (hbk_file, index)

        if not resolved:
            detail = (
                reported[languages[0]]["message"]
                if len(languages) == 1
                else {"languages": reported}
            )
            raise HTTPException(status_code=400, detail=detail)

        if not await es_client.is_connected():
            raise HTTPException(status_code=503, detail="Elasticsearch недоступен")

        for language, (hbk_file, index) in resolved.items():
            logger.info(f"Начинаем переиндексацию ({language}): {hbk_file}")
            outcome = await index_hbk_file(str(hbk_file), es_client, index=index, lang=language)
            reported[language] = {
                "status": "success" if outcome.ok else "failed",
                "message": describe_outcome(outcome),
                "file": str(hbk_file),
            }
            if outcome.ok:
                reported[language]["documents_count"] = await es_client.get_documents_count(
                    index=index
                )

        any_success = any(report["status"] == "success" for report in reported.values())
        overall_status = _overall_status(reported)

        if any_success:
            try:
                updated = await backfill_english_names(
                    es_client, russian_index, settings.elasticsearch_index_en
                )
                if updated:
                    logger.info(f"Достроено английских имён после переиндексации: {updated}")
            except Exception as e:
                logger.error(f"Ошибка достройки английских имён после переиндексации: {e}")

        if not any_success:
            raise HTTPException(
                status_code=500,
                detail={"status": overall_status, "languages": reported},
            )

        return {"status": overall_status, "languages": reported}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка переиндексации: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Внутренняя ошибка: {str(e)}"
        )


@router.get("/names")
async def name_table(
    version: Optional[str] = None,
    es_client: ElasticsearchClient = Depends(get_elasticsearch_client),
):
    """Имена API платформы версии с доступностью — для внешних линтеров, которым нужен список целиком."""
    resolved = _version_or_400(version)
    if not await es_client.is_connected():
        raise HTTPException(status_code=503, detail="Elasticsearch недоступен")
    if not await es_client.index_exists(index=resolved.index):
        raise HTTPException(
            status_code=404,
            detail=f"Справка версии {resolved.name or 'без версии'} не проиндексирована",
        )
    names = await SearchService(es_client, index=resolved.index).name_table()
    return {"version": resolved.name, "count": len(names), "names": names}

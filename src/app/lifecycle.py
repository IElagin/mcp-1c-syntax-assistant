"""Application lifecycle management."""

import asyncio
from fastapi import FastAPI

from src.core.logging import get_logger
from src.core.elasticsearch import ElasticsearchClient
from src.core.metrics import get_metrics_collector, get_system_monitor
from src.infrastructure.indexing import auto_index_on_startup
from src.infrastructure.background.indexing_manager import setup_indexing_manager, get_indexing_manager

logger = get_logger(__name__)


async def startup(app: FastAPI):
    """
    Startup logic для приложения.
    
    Args:
        app: FastAPI application instance
    """
    logger.info("Запуск MCP сервера синтаксис-помощника 1С")
    
    metrics = get_metrics_collector()
    monitor = get_system_monitor()

    indexing_manager = setup_indexing_manager(
        shutdown_timeout=30,
        progress_log_interval=500
    )
    app.state.indexing_manager = indexing_manager
    logger.info("Менеджер фоновой индексации инициализирован")
    
    await monitor.start_monitoring(interval=60)
    
    es_client = ElasticsearchClient()
    connected = await es_client.connect()
    
    if not connected:
        logger.error("Не удалось подключиться к Elasticsearch")
        await metrics.increment("startup.elasticsearch.connection_failed")
    else:
        logger.info("Успешно подключились к Elasticsearch")
        await metrics.increment("startup.elasticsearch.connection_success")
        
        app.state.es_client = es_client
        
        await auto_index_on_startup(es_client)
    
    await metrics.increment("startup.completed")
    logger.info("✅ Приложение запущено (индексация в фоне)")



async def shutdown(app: FastAPI):
    """
    Shutdown logic для приложения с graceful завершением индексации.
    
    Args:
        app: FastAPI application instance
    """
    logger.info("Остановка MCP сервера")
    
    metrics = get_metrics_collector()
    monitor = get_system_monitor()
    
    if hasattr(app.state, 'indexing_manager'):
        manager = get_indexing_manager()
        if manager.is_indexing():
            logger.info("Обнаружена активная индексация, ожидание завершения...")
            await manager.graceful_shutdown(timeout=30)
    
    await monitor.stop_monitoring()
    
    if hasattr(app.state, 'es_client'):
        await app.state.es_client.disconnect()
    
    await metrics.increment("shutdown.completed")
    logger.info("✅ MCP сервер остановлен")

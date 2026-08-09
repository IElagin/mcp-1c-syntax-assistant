"""Клиент Elasticsearch."""

from typing import Optional, Dict, Any, List
import asyncio
from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import ConnectionError, NotFoundError, RequestError

from src.core.config import settings
from src.core.logging import get_logger
from src.core.constants import (
    ELASTICSEARCH_CONNECTION_TIMEOUT,
    ELASTICSEARCH_REQUEST_TIMEOUT,
    BATCH_SIZE
)
from src.core.retry import retry_on_connection_error, retry_on_transient_error

logger = get_logger(__name__)


class ElasticsearchError(Exception):
    """Базовое исключение для ошибок Elasticsearch."""
    pass


class ConnectionFailedError(ElasticsearchError):
    """Ошибка подключения к Elasticsearch."""
    pass


class IndexNotFoundError(ElasticsearchError):
    """Индекс не найден."""
    pass


class ElasticsearchClient:
    """Клиент для работы с Elasticsearch."""
    
    def __init__(self):
        self._client: Optional[AsyncElasticsearch] = None
        self._config = settings.elasticsearch
        self._connection_timeout = ELASTICSEARCH_CONNECTION_TIMEOUT
        self._request_timeout = ELASTICSEARCH_REQUEST_TIMEOUT

    def _index(self, index: Optional[str] = None) -> str:
        """Индекс запроса: явный аргумент важнее настройки.

        Индекс стал параметром, потому что английская справка живёт во втором
        индексе. Умолчание оставлено, чтобы существующие вызовы не менялись.
        """
        return index or self._config.index_name

    @retry_on_connection_error
    async def connect(self) -> bool:
        """Подключается к Elasticsearch с retry механизмом."""
        logger.info("Attempting to connect to Elasticsearch...")
        
        self._client = AsyncElasticsearch(
            hosts=[self._config.url],
            request_timeout=self._request_timeout,
            max_retries=0,  # Отключаем встроенный retry, используем декоратор
            retry_on_timeout=False
        )
        
        await self._client.info()
        logger.info("Successfully connected to Elasticsearch")
        return True
    
    async def disconnect(self) -> None:
        """Отключается от Elasticsearch."""
        if self._client:
            try:
                await self._client.close()
            except Exception as e:
                logger.warning(f"Ошибка при отключении от Elasticsearch: {e}")
            finally:
                self._client = None
    
    async def is_connected(self) -> bool:
        """Проверяет подключение к Elasticsearch."""
        if not self._client:
            return False
        
        try:
            await self._client.ping()
            return True
        except Exception:
            return False
    
    @retry_on_connection_error
    async def index_exists(self, index: Optional[str] = None) -> bool:
        """Проверяет существование индекса с retry."""
        if not self._client:
            raise ConnectionFailedError("No connection to Elasticsearch")

        return await self._client.indices.exists(index=self._index(index))

    @retry_on_connection_error
    async def create_index(self, index: Optional[str] = None) -> bool:
        """Создает индекс с оптимизированной схемой с retry."""
        if not self._client:
            raise ConnectionFailedError("No connection to Elasticsearch")
        
        index_config = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {
                    "analyzer": {
                        "russian": {
                            "tokenizer": "standard",
                            "filter": ["lowercase", "russian_stop", "russian_stemmer"]
                        }
                    },
                    "filter": {
                        "russian_stop": {"type": "stop", "stopwords": "_russian_"},
                        "russian_stemmer": {"type": "stemmer", "language": "russian"}
                    }
                }
            },
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "type": {"type": "keyword"}, 
                    "name": {"type": "text", "analyzer": "russian", "fields": {"keyword": {"type": "keyword"}}},
                    "name_ru": {"type": "text", "analyzer": "russian", "fields": {"keyword": {"type": "keyword"}}},
                    "name_en": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                    "object": {"type": "keyword"},
                    "element_kind": {"type": "keyword"},
                    "object_ru": {"type": "keyword"},
                    "object_en": {"type": "keyword"},
                    "call_primary": {"type": "keyword"},
                    "syntax_all": {"type": "text"},
                    "variants": {
                        "type": "object",
                        "properties": {
                            "variant": {"type": "keyword"},
                            "syntax": {"type": "text"},
                            "call": {"type": "keyword"},
                            "return_type": {"type": "keyword"},
                            "return_description": {"type": "text", "analyzer": "russian"},
                            "description": {"type": "text", "analyzer": "russian"},
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "text"},
                                    "type": {"type": "keyword"},
                                    "description": {"type": "text", "analyzer": "russian"},
                                    "required": {"type": "boolean"},
                                },
                            },
                        },
                    },
                    "value_type": {"type": "keyword"},
                    "usage": {"type": "keyword"},
                    "availability": {"type": "keyword"},
                    "note": {"type": "text", "analyzer": "russian"},
                    "description": {"type": "text", "analyzer": "russian"},
                    "version_from": {"type": "keyword"},
                    "examples": {"type": "text", "analyzer": "russian"},
                    "source_file": {"type": "keyword"},
                    "full_path": {"type": "keyword"}
                }
            }
        }
        
        resolved_index = self._index(index)
        await self._client.indices.create(index=resolved_index, body=index_config)
        logger.info(f"Index '{resolved_index}' created successfully")
        return True

    @retry_on_transient_error
    async def get_documents_count(self, index: Optional[str] = None) -> int:
        """Получает количество документов в индексе с retry."""
        if not self._client:
            raise ConnectionFailedError("No connection to Elasticsearch")

        response = await self._client.count(index=self._index(index))
        return response["count"]

    async def refresh_index(self, index: Optional[str] = None) -> bool:
        """Принудительно обновляет индекс для немедленного отражения изменений."""
        if not self._client:
            return False

        try:
            await self._client.indices.refresh(index=self._index(index))
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления индекса: {e}")
            return False

    @retry_on_connection_error
    async def delete_index(self, index: Optional[str] = None) -> bool:
        """Удаляет индекс, если он существует.

        Не бросает исключение при отсутствии индекса: reindex_all вызывает
        удаление безусловно перед пересозданием, и первый прогон
        переиндексации всегда стартует с пустой инфраструктуры.
        """
        if not self._client:
            raise ConnectionFailedError("No connection to Elasticsearch")

        resolved_index = self._index(index)
        if await self._client.indices.exists(index=resolved_index):
            await self._client.indices.delete(index=resolved_index)
        return True

    @retry_on_transient_error
    async def search(self, query: Dict[str, Any], index: Optional[str] = None) -> Dict[str, Any]:
        """Выполняет поиск в индексе с retry."""
        if not self._client:
            raise ConnectionFailedError("No connection to Elasticsearch")

        response = await self._client.search(
            index=self._index(index),
            body=query
        )
        return response


def create_elasticsearch_client() -> ElasticsearchClient:
    """Создаёт новый экземпляр ElasticsearchClient."""
    return ElasticsearchClient()


es_client = ElasticsearchClient()

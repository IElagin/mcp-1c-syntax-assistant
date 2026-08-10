"""Индексатор документации в Elasticsearch."""

from typing import List, Dict, Any, Optional, Callable, Tuple
import asyncio
import re
import time
from datetime import datetime

from src.models.doc_models import Documentation, ParsedHBK
from src.core.elasticsearch import ElasticsearchClient
from src.core.logging import get_logger

logger = get_logger(__name__)

# Справка хранит имя элемента слитно: "Добавить (Add)", "ЗначениеЗаполнено (ValueIsFilled)".
# У объектов (задача 11) английская часть бывает составной — с точками,
# плейсхолдерами и пробелами: "ExternalDataSourceCubeRecord.<External source
# name>.<Cube name>", "Global context". Однословный идентификатор
# ([A-Za-z][A-Za-z0-9._]*) такое не матчил: regex не совпадал, и вся строка
# целиком (вместе со скобкой) утекала в name_ru — карточка объекта с
# перекрывающимся object/name переставала находиться по своему full_path
# (см. tests/test_disambiguation.py ::
# test_object_card_hint_with_overlapping_path_is_executable). Поэтому правило
# другое: в скобках допустим любой текст без кириллицы, лишь бы в нём была
# хотя бы одна латинская буква — так скобка с русским пояснением (если такая
# когда-нибудь встретится) не будет принята за перевод.
_NAME_RU_EN_RE = re.compile(
    r"^(?P<ru>.+?)\s+\((?P<en>(?=[^)]*[A-Za-z])[^()Ѐ-ӿ]+)\)$"
)


def split_name_ru_en(name: Optional[str]) -> Tuple[str, Optional[str]]:
    """Раскладывает "Добавить (Add)" на русскую и английскую части.

    Имя без английской части возвращается как есть — так устроены разделы
    вида "ОбъектМетаданных: Измерение".
    """
    stripped = (name or "").strip()
    if not stripped:
        return "", None

    match = _NAME_RU_EN_RE.match(stripped)
    if match:
        return match.group("ru").strip(), match.group("en").strip()
    return stripped, None


class ElasticsearchIndexer:
    """Индексатор документации в Elasticsearch."""
    
    def __init__(self, es_client: ElasticsearchClient, index: Optional[str] = None):
        self.es_client = es_client
        # Индекс фиксируется на время жизни индексатора: один прогон
        # индексации — одна книга справки, один язык, один индекс.
        self.index = index
        self.batch_size = 100
        self.max_retries = 3
    
    async def index_documentation(
        self, 
        parsed_hbk: ParsedHBK,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> bool:
        """
        Индексирует документацию из ParsedHBK в Elasticsearch.
        
        Args:
            parsed_hbk: Распарсенные данные HBK
            progress_callback: Callback для отчёта о прогрессе (indexed, total)
        
        Returns:
            bool: True если успешно, False иначе
        """
        if not await self.es_client.is_connected():
            logger.error("Нет подключения к Elasticsearch")
            return False
        
        try:
            if not await self.es_client.index_exists(self.index):
                logger.info("Создаем индекс Elasticsearch")
                await self.es_client.create_index(self.index)
            
            total_docs = len(parsed_hbk.documentation)
            indexed_count = 0
            
            for i in range(0, total_docs, self.batch_size):
                batch = parsed_hbk.documentation[i:i + self.batch_size]
                
                success = await self._index_batch(batch)
                if success:
                    indexed_count += len(batch)
                    
                    if progress_callback:
                        progress_callback(indexed_count, total_docs)
                else:
                    logger.error(f"Ошибка индексации батча {i}-{i+len(batch)}")
            
            await self.es_client.refresh_index(self.index)
            
            return indexed_count == total_docs
            
        except Exception as e:
            logger.error(f"Ошибка индексации документации: {e}")
            return False
    
    async def _index_batch(self, documents: List[Documentation]) -> bool:
        """Индексирует батч документов."""
        if not documents:
            return True
        
        try:
            bulk_body = []
            
            for doc in documents:
                bulk_body.append({
                    "index": {
                        # bulk-запрос идёт мимо ElasticsearchClient.search и
                        # его _index() — имя индекса нужно разрешать здесь же.
                        "_index": self.index or self.es_client._config.index_name,
                        "_id": doc.id
                    }
                })
                
                bulk_body.append(self._prepare_document(doc))
            
            if self.es_client._client:
                response = await self.es_client._client.bulk(body=bulk_body)
                
                if response.get("errors"):
                    logger.warning("Есть ошибки в bulk запросе")
                    for item in response.get("items", []):
                        if "index" in item and "error" in item["index"]:
                            logger.error(f"Ошибка индексации документа: {item['index']['error']}")
                
                return not response.get("errors", True)
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка выполнения bulk запроса: {e}")
            return False
    
    def _prepare_document(self, doc: Documentation) -> Dict[str, Any]:
        """Подготавливает документ для индексации в Elasticsearch."""
        name_ru, name_en = split_name_ru_en(doc.name)

        return {
            "id": doc.id,
            "type": doc.type.value,
            "element_kind": doc.element_kind,
            "name": doc.name,
            "name_ru": name_ru,
            "name_en": name_en or "",
            "object": doc.object,
            "object_ru": doc.object_ru,
            "object_en": doc.object_en,
            "full_path": doc.full_path,
            "call_primary": doc.call_primary,
            # Поисковое поле: строки синтаксиса всех вариантов. Заменило
            # syntax_ru и syntax_en — последнее было пустым у 100% методов,
            # но участвовало в бустах.
            "syntax_all": doc.syntax_all,
            "variants": [
                {
                    "variant": v.variant,
                    "syntax": v.syntax,
                    "call": v.call,
                    "parameters": [
                        {
                            "name": p.name,
                            "type": p.type,
                            "description": p.description,
                            "required": p.required,
                        }
                        for p in v.parameters
                    ],
                    "return_type": v.return_type,
                    "return_description": v.return_description,
                    "description": v.description,
                }
                for v in doc.variants
            ],
            "value_type": doc.value_type,
            "usage": doc.usage,
            "availability": doc.availability,
            "description": doc.description,
            "note": doc.note,
            "version_from": doc.version_from,
            "examples": doc.examples,
            "source_file": doc.source_file,
            "indexed_at": datetime.now().isoformat(),
        }
    
    async def reindex_all(
        self, 
        parsed_hbk: ParsedHBK,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> bool:
        """
        Переиндексирует всю документацию (удаляет старый индекс и создает новый).
        
        Args:
            parsed_hbk: Распарсенные данные HBK
            progress_callback: Callback для отчёта о прогрессе (indexed, total)
        
        Returns:
            bool: True если успешно, False иначе
        """
        try:
            # Удаляем и создаём именно свой индекс (self.index): переиндексация
            # английской книги не должна стереть русский индекс и наоборот.
            await self.es_client.delete_index(self.index)

            await self.es_client.create_index(self.index)
            
            return await self.index_documentation(parsed_hbk, progress_callback)
            
        except Exception as e:
            logger.error(f"Ошибка переиндексации: {e}")
            return False
    
    async def get_index_stats(self) -> Optional[Dict[str, Any]]:
        """Получает статистику индекса."""
        try:
            if not await self.es_client.is_connected():
                return None

            if not await self.es_client.index_exists(self.index):
                return {"exists": False, "documents_count": 0}

            # Получаем статистику. Вызовы indices.stats/count идут мимо
            # обёрток ElasticsearchClient — имя индекса разрешаем так же, как
            # в _index_batch, а не читаем его из конфигурации напрямую.
            if self.es_client._client:
                index_name = self.index or self.es_client._config.index_name
                stats_response = await self.es_client._client.indices.stats(
                    index=index_name
                )

                count_response = await self.es_client._client.count(
                    index=index_name
                )

                return {
                    "exists": True,
                    "documents_count": count_response.get("count", 0),
                    "size_in_bytes": stats_response["indices"][index_name]["total"]["store"]["size_in_bytes"],
                    "index_name": index_name
                }

            return None

        except Exception as e:
            logger.error(f"Ошибка получения статистики индекса: {e}")
            return None

    async def search_documents(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Простой поиск документов для тестирования."""
        try:
            if not await self.es_client.is_connected():
                return []
            
            search_query = {
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": ["name^3", "full_path^2", "description", "syntax_all"],
                        "type": "best_fields"
                    }
                },
                "size": limit,
                "sort": [
                    {"_score": {"order": "desc"}}
                ]
            }
            
            response = await self.es_client.search(search_query, index=self.index)

            if response and "hits" in response:
                return [hit["_source"] for hit in response["hits"]["hits"]]
            
            return []
            
        except Exception as e:
            logger.error(f"Ошибка поиска: {e}")
            return []

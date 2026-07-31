"""Основной сервис поиска по документации 1С."""

from typing import List, Dict, Any, Optional
import time

from src.core.elasticsearch import ElasticsearchClient
from src.core.logging import get_logger
from src.search.query_builder import QueryBuilder
from src.search.ranker import SearchRanker
from src.search.formatter import SearchFormatter

logger = get_logger(__name__)

# Сколько кандидатов показать при омонимии. Перечень нужен, чтобы агент выбрал
# объект, а не чтобы прочитать все 275 — полный список он получит запросом.
KANDIDATOV_V_OTVETE = 5


def _nastoyashchiy_tip(imya_obekta) -> bool:
    """Похоже ли имя объекта на тип языка, а не на заголовок раздела справки.

    В справке под object лежат и типы («ТаблицаЗначений»), и разделы вида
    «ОбъектМетаданных: Измерение» — последние в коде не пишут.
    """
    imya = imya_obekta or ""
    return bool(imya) and " " not in imya and ":" not in imya


class SearchService:
    """Сервис поиска по документации 1С."""
    
    def __init__(self, es_client: ElasticsearchClient):
        self.es_client = es_client
        self.query_builder = QueryBuilder()
        self.ranker = SearchRanker()
        self.formatter = SearchFormatter()
    
    async def find_help_by_query(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Универсальный поиск справки по любому элементу 1С."""
        start_time = time.time()
        
        try:
            # Проверяем подключение к Elasticsearch
            if not await self.es_client.is_connected():
                return {
                    "results": [],
                    "total": 0,
                    "query": query,
                    "search_time_ms": 0,
                    "error": "Elasticsearch недоступен"
                }
            
            # Строим запрос
            es_query = self.query_builder.build_search_query(
                query=query,
                limit=limit,
                search_type="auto"
            )

            # Выполняем поиск
            response = await self.es_client.search(es_query)

            # Прежде здесь стоял повторный поиск по одному имени элемента, если
            # объект из запроса «Объект.Метод» не опознан. Он возвращал элементы
            # чужих объектов, не сообщая об этом, — агент принимал их за
            # запрошенные. Теперь пустая выдача остаётся пустой, а объяснение
            # даёт kartochka_elementa через kind="object_not_found".

            if not response:
                return {
                    "results": [],
                    "total": 0,
                    "query": query,
                    "search_time_ms": int((time.time() - start_time) * 1000),
                    "error": "Ошибка выполнения поиска"
                }
            
            # Извлекаем результаты
            hits = response.get("hits", {}).get("hits", [])
            total = response.get("hits", {}).get("total", {})
            total_count = total.get("value", 0) if isinstance(total, dict) else total
            
            # Ранжируем результаты
            ranked_results = self.ranker.rank_results(hits, query)
            
            # Форматируем для вывода
            formatted_results = self.formatter.format_search_results(ranked_results)
            
            search_time = int((time.time() - start_time) * 1000)
            
            logger.info(f"Поиск '{query}' завершен за {search_time}ms. Найдено: {len(formatted_results)}")
            
            return {
                "results": formatted_results,
                "total": total_count,
                "query": query,
                "search_time_ms": search_time
            }
            
        except Exception as e:
            search_time = int((time.time() - start_time) * 1000)
            logger.error(f"Ошибка поиска '{query}': {e}")
            
            return {
                "results": [],
                "total": 0,
                "query": query,
                "search_time_ms": search_time,
                "error": str(e)
            }
    
    async def get_detailed_syntax_info(
        self, 
        element_name: str, 
        object_name: Optional[str] = None, 
        include_examples: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Получить полную техническую информацию об элементе."""
        try:
            # Формируем запрос для точного поиска
            if object_name:
                # Для поиска метода объекта используем гибкий поиск
                elasticsearch_query = {
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"object": object_name}}
                            ],
                            "should": [
                                # Точное совпадение по полному названию (высокий приоритет)
                                {"term": {"name.keyword": {"value": element_name, "boost": 5.0}}},
                                # Поиск по частям названия (русское и английское)
                                {"match": {"name": {"query": element_name, "boost": 3.0}}},
                                # Wildcard поиск для частичных совпадений
                                {"wildcard": {"name.keyword": {"value": f"*{element_name}*", "boost": 2.0}}},
                                # Фразовый поиск
                                {"match_phrase": {"name": {"query": element_name, "boost": 2.5}}}
                            ],
                            "minimum_should_match": 1
                        }
                    },
                    "size": 1
                }
            else:
                # Для поиска без объекта используем точный запрос
                elasticsearch_query = self.query_builder.build_exact_query(element_name)
            
            response = await self.es_client.search(elasticsearch_query)
            
            if response.get('hits', {}).get('total', {}).get('value', 0) > 0:
                doc = response['hits']['hits'][0]['_source']
                
                # Фильтруем примеры если не нужны
                if not include_examples:
                    doc = doc.copy()
                    doc.pop('examples', None)
                
                return doc
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка получения детальной информации для '{element_name}': {e}")
            return None
    
    async def search_with_context_filter(
        self, 
        query: str, 
        context: str, 
        object_name: Optional[str] = None, 
        limit: int = 10
    ) -> Dict[str, Any]:
        """Поиск с фильтром по контексту (global/object/all)."""
        try:
            # Строим базовый запрос
            elasticsearch_query = self.query_builder.build_search_query(query, limit)
            
            # Фильтры по типу элемента — подходит любой из перечисленных (ИЛИ)
            type_filters = []

            if context == "global":
                type_filters.extend([
                    {"term": {"type": "global_function"}},
                    {"term": {"type": "global_procedure"}},
                    {"term": {"type": "global_event"}}
                ])
            elif context == "object":
                type_filters.extend([
                    {"term": {"type": "object_function"}},
                    {"term": {"type": "object_procedure"}},
                    {"term": {"type": "object_property"}},
                    {"term": {"type": "object_event"}},
                    {"term": {"type": "object_constructor"}}
                ])
            # Для "all" не добавляем фильтры

            # Условия соединяются через И: тип элемента И принадлежность объекту.
            # Складывать их в один should нельзя — фильтр по объекту перестаёт
            # сужать выборку, потому что условие по типу выполняется само по себе.
            filters = []

            if type_filters:
                filters.append({"bool": {"should": type_filters}})

            if object_name and context != "global":
                filters.append({"term": {"object": object_name}})

            # Применяем фильтры
            if filters:
                elasticsearch_query["query"] = {
                    "bool": {
                        "must": [elasticsearch_query["query"]],
                        "filter": filters
                    }
                }
            
            response = await self.es_client.search(elasticsearch_query)
            
            # Обрабатываем ответ
            if not response:
                return {
                    "results": [],
                    "total": 0,
                    "query": query,
                    "context": context,
                    "error": "Ошибка выполнения поиска"
                }
            
            # Извлекаем результаты
            hits = response.get("hits", {}).get("hits", [])
            total = response.get("hits", {}).get("total", {})
            total_count = total.get("value", 0) if isinstance(total, dict) else total
            
            # Ранжируем результаты
            ranked_results = self.ranker.rank_results(hits, query)
            
            # Форматируем для вывода
            formatted_results = self.formatter.format_search_results(ranked_results)
            
            return {
                "results": formatted_results,
                "total": total_count,
                "query": query,
                "context": context
            }
            
        except Exception as e:
            logger.error(f"Ошибка контекстного поиска '{query}' в контексте '{context}': {e}")
            return {
                "results": [],
                "total": 0,
                "query": query,
                "context": context,
                "error": str(e)
            }
    
    async def get_object_members_list(
        self, 
        object_name: str, 
        member_type: str = "all", 
        limit: int = 50
    ) -> Dict[str, Any]:
        """Получить список элементов объекта с фильтрацией по типу."""
        try:
            # Базовый фильтр по объекту
            query_filters = [{"term": {"object": object_name}}]
            
            # Добавляем фильтры по типу элементов
            if member_type == "methods":
                type_filters = [
                    {"term": {"type": "object_function"}},
                    {"term": {"type": "object_procedure"}},
                    {"term": {"type": "object_constructor"}}
                ]
                query_filters.append({"bool": {"should": type_filters}})
            elif member_type == "properties":
                query_filters.append({"term": {"type": "object_property"}})
            elif member_type == "events":
                query_filters.append({"term": {"type": "object_event"}})
            
            # Строим запрос
            elasticsearch_query = {
                "query": {
                    "bool": {
                        "filter": query_filters
                    }
                },
                "size": limit,
                "sort": [{"name.keyword": {"order": "asc"}}]
            }
            
            response = await self.es_client.search(elasticsearch_query)
            
            # Группируем результаты
            methods = []
            properties = []
            events = []
            
            for hit in response.get('hits', {}).get('hits', []):
                doc = hit['_source']
                doc_type = doc.get('type', '').lower()
                
                if 'function' in doc_type or 'procedure' in doc_type or 'constructor' in doc_type:
                    methods.append(doc)
                elif 'property' in doc_type:
                    properties.append(doc)
                elif 'event' in doc_type:
                    events.append(doc)
            
            # total — сколько элементов в индексе, а не сколько поместилось в
            # ответ. Раньше здесь стояла сумма вернувшихся списков, поэтому по
            # ответу нельзя было понять, что limit срезал хвост.
            vsego = response.get("hits", {}).get("total", {})
            vsego_v_indekse = (
                vsego.get("value", 0) if isinstance(vsego, dict) else (vsego or 0)
            )

            return {
                "object": object_name,
                "member_type": member_type,
                "methods": methods,
                "properties": properties,
                "events": events,
                "total": max(
                    vsego_v_indekse,
                    len(methods) + len(properties) + len(events)
                )
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения элементов объекта '{object_name}': {e}")
            return {
                "object": object_name,
                "member_type": member_type,
                "methods": [],
                "properties": [],
                "events": [],
                "total": 0,
                "error": str(e)
            }

    async def kartochka_elementa(
        self,
        name: str,
        object_name: Optional[str] = None,
        variant: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Находит элемент по точному имени, не выбирая молча при омонимии.

        Все обращения к Elasticsearch собраны под одним try/except: остальные
        публичные методы класса (find_help_by_query и другие) не дают
        исключению вылететь наружу, а превращают его в структурированный
        ответ. kind="error" отличим от пяти обычных значений — обработчик
        (Task 13) должен уметь отличить сбой связи от честного "не найдено".
        """
        try:
            if object_name:
                est_obekt = await self._obekt_sushchestvuet(object_name)
                if not est_obekt:
                    return {
                        "kind": "object_not_found",
                        "object": object_name,
                        "similar": await self.pohozhie_obekty(object_name),
                    }

            filtry = [{
                "bool": {
                    "should": [
                        {"term": {"name_ru.keyword": name}},
                        {"term": {"name_en.keyword": name}},
                    ],
                    "minimum_should_match": 1,
                }
            }]
            if object_name:
                filtry.append({"term": {"object": object_name}})

            otvet = await self.es_client.search({
                "query": {"bool": {"filter": filtry}},
                "size": 50,
            })
            hits = (otvet or {}).get("hits", {}).get("hits", [])
            vsego = (otvet or {}).get("hits", {}).get("total", {})
            vsego = vsego.get("value", 0) if isinstance(vsego, dict) else (vsego or 0)

            if not hits:
                return {
                    "kind": "not_found",
                    "name": name,
                    "similar": await self._pohozhie_elementy(name),
                }

            dokumenty = [h["_source"] for h in hits]

            if len(dokumenty) > 1:
                dokumenty.sort(
                    key=lambda d: (not _nastoyashchiy_tip(d.get("object")),
                                   d.get("object") or "")
                )
                return {
                    "kind": "ambiguous",
                    "name": name,
                    "candidates": dokumenty[:KANDIDATOV_V_OTVETE],
                    "total": vsego,
                }

            doc = dokumenty[0]

            if variant:
                imena = [v.get("variant", "") for v in (doc.get("variants") or [])]
                if variant not in imena:
                    return {"kind": "variant_not_found", "document": doc, "variants": imena}
                doc = dict(doc)
                doc["variants"] = [
                    v for v in doc["variants"] if v.get("variant") == variant
                ]

            return {"kind": "card", "document": doc}
        except Exception as e:
            logger.error(f"Ошибка дизамбигуации элемента '{name}': {e}")
            return {"kind": "error", "name": name, "error": str(e)}

    async def _obekt_sushchestvuet(self, object_name: str) -> bool:
        """Есть ли в справке объект с таким именем.

        Исключение здесь намеренно не глушится: False означает «объекта в
        справке нет», а при сбое ES мы этого не знаем — подмена сбоя на False
        выдала бы kind="object_not_found" за достоверный факт. Пусть
        исключение всплывёт к kartochka_elementa и станет честным kind="error".
        """
        otvet = await self.es_client.search({
            "query": {"bool": {"filter": [{"term": {"object": object_name}}]}},
            "size": 0,
        })
        vsego = (otvet or {}).get("hits", {}).get("total", {})
        vsego = vsego.get("value", 0) if isinstance(vsego, dict) else (vsego or 0)
        return vsego > 0

    async def pohozhie_obekty(self, object_name: str, limit: int = 5) -> List[str]:
        """Объекты с близким именем — вместо молчаливой подмены запроса.

        Искать нужно среди имён объектов, а не имён элементов: name_ru у
        элемента — это имя метода/свойства, и нечёткий поиск по нему находит
        случайное совпадение корня в чужой фразе (например, «Строка» входит в
        «Из строки» у конструктора), после чего в подсказку попадал владелец
        найденного элемента, никак не похожий на запрос. Документы объектов
        (type="object", 2506 штук) хранят имя объекта прямо в name_ru — их и
        матчим.

        Публичный метод: его вызывает и kartochka_elementa, и напрямую
        обработчик состава объекта (Task 13). Исключение ES здесь не
        перехватывается: пустой список — это ответ "похожих объектов нет",
        и подмена им сбоя связи сделала бы сбой неотличимым от честного
        отсутствия данных — ровно тот дефект, ради которого написана вся
        задача. Пусть исключение поднимется к вызывающему: kartochka_elementa
        превратит его в kind="error", а обработчик Task 13, вызывающий этот
        метод напрямую, получит то же исключение и не примет обрыв связи за
        "похожих нет, проверь написание".
        """
        otvet = await self.es_client.search({
            "query": {
                "bool": {
                    "must": [{"match": {"name_ru": {"query": object_name, "fuzziness": "AUTO"}}}],
                    "filter": [{"term": {"type": "object"}}],
                }
            },
            "size": 50,
            "_source": ["name_ru"],
        })

        vidennye = []
        for h in (otvet or {}).get("hits", {}).get("hits", []):
            imya = h["_source"].get("name_ru")
            if imya and imya not in vidennye:
                vidennye.append(imya)
            if len(vidennye) >= limit:
                break
        return vidennye

    async def _pohozhie_elementy(self, name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Элементы с близким именем для ответа «точного совпадения нет».

        Вызывается только из kartochka_elementa, внутри её try/except.
        Исключение здесь не перехватывается по той же причине, что и в
        pohozhie_obekty: пустой список — это утверждение "похожих элементов
        нет", и подменять им сбой связи значит выдавать ложь за факт. Пусть
        поднимется наверх и станет честным kind="error".
        """
        otvet = await self.es_client.search({
            "query": {"match": {"name_ru": {"query": name, "fuzziness": "AUTO"}}},
            "size": limit,
        })
        return [h["_source"] for h in (otvet or {}).get("hits", {}).get("hits", [])]

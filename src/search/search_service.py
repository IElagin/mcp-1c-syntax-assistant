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
CANDIDATES_IN_RESPONSE = 5

# Сколько совпадений упорядочивать при омонимии. Самое многозначное имя
# справки — «Количество», 275 документов, поэтому 500 покрывает индекс целиком:
# порядок строится по всем совпадениям, а не по произвольному окну. Если
# однажды имя перевалит за потолок, ответ об этом скажет (full_order).
CANDIDATES_CAP = 500

# Поля, которых хватает строке списка. Карточке нужен документ целиком, а
# перечню кандидатов — нет: тянуть 275 полных документов с параметрами всех
# вариантов ради пяти строк расточительно.
LIST_LINE_FIELDS = [
    "type", "element_kind", "name_ru", "object", "object_ru",
    "full_path", "call_primary", "description", "variants.variant",
]

# Настоящие виды членов объекта — в отличие от документа-описания самого
# объекта (type="object"), у которого поле object тоже равно имени объекта.
# Без фильтра по этому списку members="all" ловил и этот документ, выдавая
# объекту без единого метода/свойства/события total=1 вместо 0 — ветка
# "объект есть, но пуст" для all после этого не срабатывала никогда, а у
# обычных объектов (ТаблицаЗначений) счётчик был завышен на единицу.
OBJECT_MEMBER_KINDS = [
    "object_function", "object_procedure", "object_constructor",
    "object_property", "object_event",
]


def _is_real_type(object_name) -> bool:
    """Похоже ли имя объекта на тип языка, а не на заголовок раздела справки.

    В справке под object лежат и типы («ТаблицаЗначений»), и разделы вида
    «ОбъектМетаданных: Измерение» — последние в коде не пишут.
    """
    name = object_name or ""
    return bool(name) and " " not in name and ":" not in name


class SearchService:
    """Сервис поиска по документации 1С."""
    
    def __init__(self, es_client: ElasticsearchClient, index: Optional[str] = None):
        self.es_client = es_client
        # Индекс фиксируется на время жизни сервиса: один запрос агента — один
        # язык, и смешивать индексы внутри одного ответа нельзя.
        self.index = index
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
            response = await self.es_client.search(es_query, index=self.index)

            # Прежде здесь стоял повторный поиск по одному имени элемента, если
            # объект из запроса «Объект.Метод» не опознан. Он возвращал элементы
            # чужих объектов, не сообщая об этом, — агент принимал их за
            # запрошенные. Теперь пустая выдача остаётся пустой, а объяснение
            # даёт element_card через kind="object_not_found".

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
    
    async def find_help_filtered(
        self,
        query: str,
        types: list,
        object_name: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Поиск с фильтром по видам элементов и объекту.

        Заменил пару find_help_by_query и search_with_context_filter: две точки
        входа с почти одинаковым смыслом заставляли агента угадывать, какая
        нужна.
        """
        es_query = self.query_builder.build_search_query(query, limit, "auto")

        filters = []
        if types:
            filters.append({"terms": {"type": types}})
        if object_name:
            filters.append({"term": {"object": object_name}})

        if filters:
            es_query["query"] = {"bool": {"must": [es_query["query"]], "filter": filters}}

        response = await self.es_client.search(es_query, index=self.index)
        if not response:
            return {"results": [], "total": 0, "query": query,
                    "error": "Ошибка выполнения поиска"}

        hits = response.get("hits", {}).get("hits", [])
        total = response.get("hits", {}).get("total", {})
        total = total.get("value", 0) if isinstance(total, dict) else (total or 0)

        return {
            "results": self.formatter.format_search_results(
                self.ranker.rank_results(hits, query)
            ),
            "total": total,
            "query": query,
        }

    async def member_count(self, object_name: str) -> Dict[str, int]:
        """Сколько у объекта методов, свойств и событий.

        Списки methods/properties/events модели Documentation в Elasticsearch не
        переносятся, поэтому считаем документы с этим object.
        """
        groups = {
            "methods": ["object_function", "object_procedure", "object_constructor"],
            "properties": ["object_property"],
            "events": ["object_event"],
        }
        totals = {}
        for group_name, types in groups.items():
            response = await self.es_client.search({
                "query": {"bool": {"filter": [
                    {"term": {"object": object_name}},
                    {"terms": {"type": types}},
                ]}},
                "size": 0,
            }, index=self.index)
            total = (response or {}).get("hits", {}).get("total", {})
            totals[group_name] = total.get("value", 0) if isinstance(total, dict) else (total or 0)
        return totals

    async def constructor_lines(self, object_name: str) -> List[str]:
        """Строки вызова конструкторов объекта — «Новый ТаблицаЗначений».

        В документе самого объекта конструкторов нет: у справки конструктор —
        отдельная страница (type="object_constructor", 385 документов у 307
        объектов), и variants у всех 2 506 документов объектов пусты. Карточка
        читала эти пустые variants и печатала «Конструкторы: в справке не
        указано» — про 307 объектов это была неправда.

        Имя варианта добавляется, только когда конструкторов несколько: тогда
        оно и различает страницы, и годится в аргумент variant=… у
        get_1c_element.
        """
        response = await self.es_client.search({
            "query": {"bool": {"filter": [
                {"term": {"object": object_name}},
                {"term": {"type": "object_constructor"}},
            ]}},
            "size": 50,
            "sort": [{"name.keyword": {"order": "asc"}}],
            "_source": ["call_primary", "name_ru", "variants.variant"],
        }, index=self.index)

        hits = (response or {}).get("hits", {}).get("hits", [])
        lines = []
        for h in hits:
            doc = h["_source"]
            call = doc.get("call_primary") or ""
            if not call:
                continue
            variant_list = doc.get("variants") or []
            variant_name = (variant_list[0].get("variant") if variant_list else "") \
                or doc.get("name_ru") or ""
            if len(hits) > 1 and variant_name:
                lines.append(f"{call} — вариант «{variant_name}»")
            else:
                lines.append(call)
        return lines

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
            
            # Добавляем фильтры по типу элементов. "all" тоже фильтруется —
            # без ограничения по OBJECT_MEMBER_KINDS запрос ловил документ
            # самого объекта (type="object"), у которого object тоже равен
            # имени объекта.
            if member_type == "all":
                query_filters.append({"terms": {"type": OBJECT_MEMBER_KINDS}})
            elif member_type == "methods":
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
            elif member_type == "constructors":
                query_filters.append({"term": {"type": "object_constructor"}})
            
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
            
            response = await self.es_client.search(elasticsearch_query, index=self.index)
            
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
            total = response.get("hits", {}).get("total", {})
            total_in_index = (
                total.get("value", 0) if isinstance(total, dict) else (total or 0)
            )
            final_total = max(
                total_in_index,
                len(methods) + len(properties) + len(events)
            )

            result = {
                "object": object_name,
                "member_type": member_type,
                "methods": methods,
                "properties": properties,
                "events": events,
                "total": final_total,
            }

            # total=0 неоднозначен: объекта может не быть вовсе, а может — он
            # есть, просто у него нет элементов запрошенного вида (например,
            # "события" у объекта без событий, или "конструкторы" почти у
            # любого объекта, кроме считаных типов). Раньше оба случая
            # выглядели одинаково — агент слышал «не найден» про объект,
            # который есть, и тут же видел его в списке «похожих».
            if final_total == 0:
                result["object_exists"] = await self.object_exists(object_name)

            return result

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

    async def element_card(
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
        должен уметь отличить сбой связи от честного "не найдено".
        """
        try:
            if object_name:
                exists = await self.object_exists(object_name)
                if not exists:
                    return {
                        "kind": "object_not_found",
                        "object": object_name,
                        "similar": await self.similar_objects(object_name),
                    }

            filters = [{
                "bool": {
                    "should": [
                        {"term": {"name_ru.keyword": name}},
                        {"term": {"name_en.keyword": name}},
                    ],
                    "minimum_should_match": 1,
                }
            }]
            if object_name:
                filters.append({"term": {"object": object_name}})

            response = await self.es_client.search({
                "query": {"bool": {"filter": filters}},
                "size": 50,
            }, index=self.index)
            hits = (response or {}).get("hits", {}).get("hits", [])
            total = (response or {}).get("hits", {}).get("total", {})
            total = total.get("value", 0) if isinstance(total, dict) else (total or 0)

            if not hits:
                return {
                    "kind": "not_found",
                    "name": name,
                    "similar": await self._similar_members(name),
                }

            documents = [h["_source"] for h in hits]

            if len(documents) > 1:
                candidates = await self._order_candidates(filters, total)
                return {
                    "kind": "ambiguous",
                    "name": name,
                    "candidates": candidates[:CANDIDATES_IN_RESPONSE],
                    "total": total,
                    "full_order": total <= CANDIDATES_CAP,
                }

            doc = documents[0]

            if variant:
                names = [v.get("variant", "") for v in (doc.get("variants") or [])]
                if variant not in names:
                    return {"kind": "variant_not_found", "document": doc, "variants": names}
                doc = dict(doc)
                doc["variants"] = [
                    v for v in doc["variants"] if v.get("variant") == variant
                ]

            return {"kind": "card", "document": doc}
        except Exception as e:
            logger.error(f"Ошибка дизамбигуации элемента '{name}': {e}")
            return {"kind": "error", "name": name, "error": str(e)}

    async def _order_candidates(self, filters: list, total: int) -> List[Dict[str, Any]]:
        """Кандидаты при омонимии в защитимом порядке.

        Порядок: сначала настоящие типы языка, внутри — объекты, у которых в
        справке больше элементов. Прежний порядок был заявкой без покрытия:
        окно из 50 документов набиралось фильтрующим запросом, где у всех
        совпадений одинаковая оценка (то есть окно произвольно), и
        сортировалось по имени объекта — по алфавиту. Для «Количество» это
        давало АгрегатыРегистраНакопления и ВсеЭлементыФормы под заголовком
        «Наиболее вероятные», а ТаблицаЗначений, Массив и Структура не
        показывались вовсе: агент делал вывод, что у обычных коллекций
        «Количество» нет.

        Число членов объекта — дешёвый и проверяемый признак: одна агрегация на
        все объекты-владельцы сразу. Ранжирование по релевантности сюда не
        годится: запрос фильтрующий, оценки равны у всех.
        """
        response = await self.es_client.search({
            "query": {"bool": {"filter": filters}},
            "size": min(max(total, 1), CANDIDATES_CAP),
            "_source": {"includes": LIST_LINE_FIELDS},
        }, index=self.index)
        documents = [h["_source"] for h in (response or {}).get("hits", {}).get("hits", [])]

        member_counts = await self._member_count_by_object(
            [d.get("object") for d in documents]
        )
        documents.sort(key=lambda d: (
            not _is_real_type(d.get("object")),
            -member_counts.get(d.get("object") or "", 0),
            d.get("object") or "",
        ))
        return documents

    async def _member_count_by_object(self, object_names: list) -> Dict[str, int]:
        """Сколько элементов справки у каждого из перечисленных объектов.

        Одной агрегацией: пять сотен отдельных запросов ради сортировки пяти
        строк ответа не окупились бы.
        """
        names = sorted({i for i in object_names if i})
        if not names:
            return {}

        response = await self.es_client.search({
            "query": {"bool": {"filter": [
                {"terms": {"object": names}},
                {"terms": {"type": OBJECT_MEMBER_KINDS}},
            ]}},
            "size": 0,
            "aggs": {"by_object": {"terms": {"field": "object", "size": len(names)}}},
        }, index=self.index)
        buckets = (response or {}).get("aggregations", {}).get("by_object", {}).get("buckets", [])
        return {b["key"]: b["doc_count"] for b in buckets}

    async def object_exists(self, object_name: str) -> bool:
        """Есть ли в справке объект с таким именем.

        Публичный метод: его зовёт и element_card, и обработчик поиска —
        пустая выдача find_1c_help при заданном object обязана отличать «нет
        такого элемента» от «нет такого объекта».

        Исключение здесь намеренно не глушится: False означает «объекта в
        справке нет», а при сбое ES мы этого не знаем — подмена сбоя на False
        выдала бы kind="object_not_found" за достоверный факт. Пусть
        исключение всплывёт к вызывающему и станет честной ошибкой.
        """
        response = await self.es_client.search({
            "query": {"bool": {"filter": [{"term": {"object": object_name}}]}},
            "size": 0,
        }, index=self.index)
        total = (response or {}).get("hits", {}).get("total", {})
        total = total.get("value", 0) if isinstance(total, dict) else (total or 0)
        return total > 0

    async def similar_objects(self, object_name: str, limit: int = 5) -> List[str]:
        """Объекты с близким именем — вместо молчаливой подмены запроса.

        Искать нужно среди имён объектов, а не имён элементов: name_ru у
        элемента — это имя метода/свойства, и нечёткий поиск по нему находит
        случайное совпадение корня в чужой фразе (например, «Строка» входит в
        «Из строки» у конструктора), после чего в подсказку попадал владелец
        найденного элемента, никак не похожий на запрос. Документы объектов
        (type="object", 2506 штук) хранят имя объекта прямо в name_ru — их и
        матчим.

        Публичный метод: его вызывает и element_card, и напрямую обработчик
        состава объекта. Исключение ES здесь не перехватывается: пустой
        список — это ответ "похожих объектов нет", и подмена им сбоя связи
        сделала бы сбой неотличимым от честного отсутствия данных — ровно тот
        дефект, которого нужно избежать. Пусть исключение поднимется к
        вызывающему: element_card превратит его в kind="error", а обработчик
        состава объекта, вызывающий этот метод напрямую, получит то же
        исключение и не примет обрыв связи за "похожих нет, проверь
        написание".
        """
        response = await self.es_client.search({
            "query": {
                "bool": {
                    "must": [{"match": {"name_ru": {"query": object_name, "fuzziness": "AUTO"}}}],
                    "filter": [{"term": {"type": "object"}}],
                }
            },
            "size": 50,
            "_source": ["name_ru"],
        }, index=self.index)

        seen = []
        for h in (response or {}).get("hits", {}).get("hits", []):
            name = h["_source"].get("name_ru")
            if name and name not in seen:
                seen.append(name)
            if len(seen) >= limit:
                break
        return seen

    async def _similar_members(self, name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Элементы с близким именем для ответа «точного совпадения нет».

        Вызывается только из element_card, внутри её try/except.
        Исключение здесь не перехватывается по той же причине, что и в
        similar_objects: пустой список — это утверждение "похожих элементов
        нет", и подменять им сбой связи значит выдавать ложь за факт. Пусть
        поднимется наверх и станет честным kind="error".
        """
        response = await self.es_client.search({
            "query": {"match": {"name_ru": {"query": name, "fuzziness": "AUTO"}}},
            "size": limit,
        }, index=self.index)
        return [h["_source"] for h in (response or {}).get("hits", {}).get("hits", [])]

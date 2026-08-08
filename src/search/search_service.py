"""Поиск по документации 1С."""

from typing import List, Dict, Any, Optional
import time

from src.core.elasticsearch import ElasticsearchClient
from src.core.logging import get_logger
from src.handlers.ui_strings import RU_STRINGS, UiStrings
from src.search.query_builder import QueryBuilder
from src.search.ranker import SearchRanker
from src.search.formatter import SearchFormatter

logger = get_logger(__name__)

CANDIDATES_IN_RESPONSE = 5
CANDIDATES_CAP = 500

LIST_LINE_FIELDS = [
    "type", "element_kind", "name_ru", "object", "object_ru",
    "full_path", "call_primary", "description", "variants.variant",
]

OBJECT_MEMBER_KINDS = [
    "object_function", "object_procedure", "object_constructor",
    "object_property", "object_event",
]
GLOBAL_MEMBER_KINDS = ["global_function", "global_procedure", "global_event"]
MEMBER_KINDS = OBJECT_MEMBER_KINDS + GLOBAL_MEMBER_KINDS

MEMBER_KINDS_BY_GROUP = {
    "methods": [
        "object_function", "object_procedure", "object_constructor",
        "global_function", "global_procedure",
    ],
    "properties": ["object_property"],
    "events": ["object_event", "global_event"],
    "constructors": ["object_constructor"],
}

METHOD_KINDS = ("function", "procedure", "constructor")


def hits_of(response: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return (response or {}).get("hits", {}).get("hits", [])


def sources_of(response: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [hit["_source"] for hit in hits_of(response)]


def total_of(response: Optional[Dict[str, Any]]) -> int:
    total = (response or {}).get("hits", {}).get("total", {})
    return total.get("value", 0) if isinstance(total, dict) else (total or 0)


def buckets_of(response: Optional[Dict[str, Any]], aggregation: str) -> List[Dict[str, Any]]:
    aggregations = (response or {}).get("aggregations", {})
    return aggregations.get(aggregation, {}).get("buckets", [])


def _any_of(conditions: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"bool": {"should": conditions, "minimum_should_match": 1}}


def _object_filter(object_name: str) -> Dict[str, Any]:
    """Фильтр по объекту, принимающий и русское имя, и английское."""
    return _any_of([
        {"term": {"object": object_name}},
        {"term": {"object_en": object_name}},
    ])


def _name_filter(name: str) -> Dict[str, Any]:
    """Фильтр по точному имени элемента на любом из двух языков."""
    return _any_of([
        {"term": {"name_ru.keyword": name}},
        {"term": {"name_en.keyword": name}},
    ])


def _is_real_type(object_name: Optional[str]) -> bool:
    """Имя объекта — это тип языка, а не заголовок раздела справки."""
    name = object_name or ""
    return bool(name) and " " not in name and ":" not in name


def _group_of(doc_type: str) -> Optional[str]:
    lowered = (doc_type or "").lower()
    if any(kind in lowered for kind in METHOD_KINDS):
        return "methods"
    if "property" in lowered:
        return "properties"
    if "event" in lowered:
        return "events"
    return None


class SearchService:
    """Поиск по документации 1С в одном индексе — то есть на одном языке."""

    def __init__(self, es_client: ElasticsearchClient, index: Optional[str] = None):
        self.es_client = es_client
        self.index = index
        self.query_builder = QueryBuilder()
        self.ranker = SearchRanker()
        self.formatter = SearchFormatter()

    async def _search(self, body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return await self.es_client.search(body, index=self.index)

    async def _count(self, filters: List[Dict[str, Any]]) -> int:
        return total_of(await self._search({
            "query": {"bool": {"filter": filters}},
            "size": 0,
        }))

    async def find_help_by_query(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Поиск по свободному запросу."""
        start_time = time.time()

        try:
            if not await self.es_client.is_connected():
                return {"results": [], "total": 0, "query": query,
                        "search_time_ms": 0, "error": "Elasticsearch недоступен"}

            response = await self._search(
                self.query_builder.build_search_query(query, limit, "auto")
            )
            elapsed_ms = int((time.time() - start_time) * 1000)

            if not response:
                return {"results": [], "total": 0, "query": query,
                        "search_time_ms": elapsed_ms,
                        "error": "Ошибка выполнения поиска"}

            results = self.formatter.format_search_results(
                self.ranker.rank_results(hits_of(response), query)
            )
            logger.info(
                f"Поиск '{query}' завершен за {elapsed_ms}ms. Найдено: {len(results)}"
            )
            return {"results": results, "total": total_of(response),
                    "query": query, "search_time_ms": elapsed_ms}

        except Exception as e:
            logger.error(f"Ошибка поиска '{query}': {e}")
            return {"results": [], "total": 0, "query": query,
                    "search_time_ms": int((time.time() - start_time) * 1000),
                    "error": str(e)}

    async def find_help_filtered(
        self,
        query: str,
        types: list,
        object_name: Optional[str] = None,
        limit: int = 10,
        strings: UiStrings = RU_STRINGS,
    ) -> Dict[str, Any]:
        """Поиск с фильтром по видам элементов и объекту.

        `qualified_object` в ответе — объект, вычитанный из самого запроса:
        обработчик обязан назвать его, объясняя пустую выдачу.
        """
        qualified = await self._qualified_split(query)
        if qualified:
            es_query = self.query_builder.build_qualified_query(*qualified, limit=limit)
        else:
            es_query = self.query_builder.build_search_query(query, limit, "auto")

        filters = []
        if types:
            filters.append({"terms": {"type": types}})
        if object_name:
            filters.append(_object_filter(object_name))
        if filters:
            es_query["query"] = {"bool": {"must": [es_query["query"]], "filter": filters}}

        response = await self._search(es_query)
        if not response:
            return {"results": [], "total": 0, "query": query,
                    "error": strings.search_failed}

        return {
            "results": self.formatter.format_search_results(
                self.ranker.rank_results(hits_of(response), query)
            ),
            "total": total_of(response),
            "query": query,
            "qualified_object": qualified[0] if qualified else None,
        }

    async def _qualified_split(self, query: str):
        """Разрез «Объект.Элемент», проверенный по индексу, а не угаданный.

        Возвращает пару (объект, элемент) либо None. Когда ни одно левое плечо
        не опознано как объект справки, остаётся узкий синтаксический разбор —
        он сохраняет фильтр по объекту, чтобы пустая выдача назвала причину.
        """
        points = self.query_builder.split_points(query)
        if not points:
            return None

        known = await self._known_objects([obj for obj, _ in points])
        for obj, member in points:
            if obj in known:
                return obj, member

        return self.query_builder.parse_qualified_name(query)

    async def _known_objects(self, names: list) -> set:
        """Какие из имён — настоящие объекты справки, одной агрегацией."""
        names = [name for name in names if name]
        if not names:
            return set()

        response = await self._search({
            "query": {"bool": {"filter": [_any_of([
                {"terms": {"object": names}},
                {"terms": {"object_en": names}},
            ])]}},
            "size": 0,
            "aggs": {
                "ru": {"terms": {"field": "object", "size": len(names)}},
                "en": {"terms": {"field": "object_en", "size": len(names)}},
            },
        })

        # Пересечение обязательно: в бакеты попадают значения object у
        # документов, найденных по object_en.
        found = {
            bucket["key"]
            for aggregation in ("ru", "en")
            for bucket in buckets_of(response, aggregation)
        }
        return found & set(names)

    async def member_count(self, object_name: str) -> Dict[str, int]:
        """Сколько у объекта методов, свойств и событий."""
        counted_groups = {"methods", "properties", "events"}
        return {
            group: await self._count([
                _object_filter(object_name),
                {"terms": {"type": types}},
            ])
            for group, types in MEMBER_KINDS_BY_GROUP.items()
            if group in counted_groups
        }

    async def constructor_lines(
        self, object_name: str, strings: UiStrings = RU_STRINGS
    ) -> List[str]:
        """Строки вызова конструкторов объекта — «Новый ТаблицаЗначений»."""
        constructors = sources_of(await self._search({
            "query": {"bool": {"filter": [
                _object_filter(object_name),
                {"term": {"type": "object_constructor"}},
            ]}},
            "size": 50,
            "sort": [{"name.keyword": {"order": "asc"}}],
            "_source": ["call_primary", "name_ru", "variants.variant"],
        }))

        lines = []
        for doc in constructors:
            call = doc.get("call_primary") or ""
            if not call:
                continue
            variants = doc.get("variants") or []
            # Имя варианта различает страницы, только когда их несколько.
            variant_name = (variants[0].get("variant") if variants else "") \
                or doc.get("name_ru") or ""
            if len(constructors) > 1 and variant_name:
                lines.append(
                    strings.constructor_variant.format(call=call, name=variant_name)
                )
            else:
                lines.append(call)
        return lines

    async def get_object_members_list(
        self,
        object_name: str,
        member_type: str = "all",
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Состав объекта, сгруппированный по видам элементов.

        `total` — сколько элементов в индексе, а не сколько поместилось в
        ответ. `object_exists` появляется только при пустом составе: он
        отличает «объекта нет» от «объект есть, но элементов такого вида у
        него нет».
        """
        kinds = MEMBER_KINDS if member_type == "all" \
            else MEMBER_KINDS_BY_GROUP.get(member_type)

        try:
            filters = [_object_filter(object_name)]
            if kinds:
                filters.append({"terms": {"type": kinds}})

            response = await self._search({
                "query": {"bool": {"filter": filters}},
                "size": limit,
                "sort": [{"name.keyword": {"order": "asc"}}],
            })

            grouped = {"methods": [], "properties": [], "events": []}
            for doc in sources_of(response):
                group = _group_of(doc.get("type", ""))
                if group:
                    grouped[group].append(doc)

            shown = sum(len(docs) for docs in grouped.values())
            result = {
                "object": object_name,
                "member_type": member_type,
                **grouped,
                "total": max(total_of(response), shown),
            }
            if result["total"] == 0:
                result["object_exists"] = await self.object_exists(object_name)
            return result

        except Exception as e:
            logger.error(f"Ошибка получения элементов объекта '{object_name}': {e}")
            return {
                "object": object_name, "member_type": member_type,
                "methods": [], "properties": [], "events": [],
                "total": 0, "error": str(e),
            }

    async def element_card(
        self,
        name: str,
        object_name: Optional[str] = None,
        variant: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Карточка элемента по точному имени — либо причина, почему её нет.

        Возвращает `kind` из шести значений: card, ambiguous, not_in_object,
        object_not_found, variant_not_found, not_found. Седьмое, error, —
        сбой Elasticsearch: обработчик обязан отличать его от «не найдено».
        """
        try:
            if object_name and not await self.object_exists(object_name):
                return {
                    "kind": "object_not_found",
                    "object": object_name,
                    "similar": await self.similar_objects(object_name),
                }

            name_filter = _name_filter(name)
            filters = [name_filter]
            if object_name:
                filters.append(_object_filter(object_name))

            response = await self._search({
                "query": {"bool": {"filter": filters}},
                "size": 50,
            })
            documents = sources_of(response)

            if not documents:
                return await self._nothing_matched(name, object_name, name_filter)

            if len(documents) > 1:
                return await self._ambiguous(name, filters, total_of(response))

            return self._single_document(documents[0], variant)

        except Exception as e:
            logger.error(f"Ошибка дизамбигуации элемента '{name}': {e}")
            return {"kind": "error", "name": name, "error": str(e)}

    async def _nothing_matched(
        self, name: str, object_name: Optional[str], name_filter: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Почему точного совпадения нет: у объекта или во всей справке."""
        if object_name:
            total = await self._count([name_filter])
            if total:
                candidates = await self._order_candidates([name_filter], total)
                return {
                    "kind": "not_in_object",
                    "name": name,
                    "object": object_name,
                    "candidates": candidates[:CANDIDATES_IN_RESPONSE],
                    "total": total,
                    "full_order": total <= CANDIDATES_CAP,
                }

        return {
            "kind": "not_found",
            "name": name,
            "similar": await self._similar_members(name),
        }

    async def _ambiguous(
        self, name: str, filters: List[Dict[str, Any]], total: int
    ) -> Dict[str, Any]:
        candidates = await self._order_candidates(filters, total)
        return {
            "kind": "ambiguous",
            "name": name,
            "candidates": candidates[:CANDIDATES_IN_RESPONSE],
            "total": total,
            "full_order": total <= CANDIDATES_CAP,
        }

    @staticmethod
    def _single_document(doc: Dict[str, Any], variant: Optional[str]) -> Dict[str, Any]:
        if not variant:
            return {"kind": "card", "document": doc}

        names = [v.get("variant", "") for v in (doc.get("variants") or [])]
        if variant not in names:
            return {"kind": "variant_not_found", "document": doc, "variants": names}

        narrowed = dict(doc)
        narrowed["variants"] = [
            v for v in doc["variants"] if v.get("variant") == variant
        ]
        return {"kind": "card", "document": narrowed}

    async def _order_candidates(
        self, filters: list, total: int
    ) -> List[Dict[str, Any]]:
        """Кандидаты при омонимии: сначала типы языка, внутри — по числу членов."""
        documents = sources_of(await self._search({
            "query": {"bool": {"filter": filters}},
            "size": min(max(total, 1), CANDIDATES_CAP),
            "_source": {"includes": LIST_LINE_FIELDS},
        }))

        member_counts = await self._member_count_by_object(
            [doc.get("object") for doc in documents]
        )
        documents.sort(key=lambda doc: (
            not _is_real_type(doc.get("object")),
            -member_counts.get(doc.get("object") or "", 0),
            doc.get("object") or "",
        ))
        return documents

    async def _member_count_by_object(self, object_names: list) -> Dict[str, int]:
        """Число элементов справки у каждого объекта, одной агрегацией."""
        names = sorted({name for name in object_names if name})
        if not names:
            return {}

        response = await self._search({
            "query": {"bool": {"filter": [
                {"terms": {"object": names}},
                {"terms": {"type": MEMBER_KINDS}},
            ]}},
            "size": 0,
            "aggs": {"by_object": {"terms": {"field": "object", "size": len(names)}}},
        })
        return {b["key"]: b["doc_count"] for b in buckets_of(response, "by_object")}

    async def object_exists(self, object_name: str) -> bool:
        """Есть ли в справке объект с таким именем.

        Исключение Elasticsearch не глушится: False здесь означает «объекта
        нет», и подменять им сбой связи значит выдавать сбой за факт.
        """
        return await self._count([_object_filter(object_name)]) > 0

    async def similar_objects(self, object_name: str, limit: int = 5) -> List[str]:
        """Объекты с близким именем — вместо молчаливой подмены запроса.

        Ищет среди страниц объектов и матчит оба имени. Исключение
        Elasticsearch не глушится по той же причине, что в object_exists.
        """
        response = await self._search({
            "query": {
                "bool": {
                    "must": [{
                        "multi_match": {
                            "query": object_name,
                            "fields": ["name_ru", "name_en"],
                            "fuzziness": "AUTO",
                        }
                    }],
                    "filter": [{"term": {"type": "object"}}],
                }
            },
            "size": 50,
            "_source": ["name_ru"],
        })

        found = []
        for doc in sources_of(response):
            name = doc.get("name_ru")
            if name and name not in found:
                found.append(name)
            if len(found) >= limit:
                break
        return found

    async def _similar_members(self, name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Элементы с близким именем для ответа «точного совпадения нет»."""
        return sources_of(await self._search({
            "query": {"match": {"name_ru": {"query": name, "fuzziness": "AUTO"}}},
            "size": limit,
        }))

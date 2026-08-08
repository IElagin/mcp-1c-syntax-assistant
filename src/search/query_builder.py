"""Тела запросов Elasticsearch. Причины решений — docs/DESIGN.md."""

from typing import Dict, Any, List, Optional, Tuple

BY_RELEVANCE = [{"_score": {"order": "desc"}}]

SINGLE_WORD_MAX_LENGTH = 30
SEMANTIC_MIN_WORDS = 3
SEMANTIC_MIN_LENGTH = 50


def _scored(conditions: Dict[str, Any], limit: int) -> Dict[str, Any]:
    return {"query": {"bool": conditions}, "size": limit, "sort": BY_RELEVANCE}


class QueryBuilder:
    """Собирает тела запросов под вид поиска."""

    def build_search_query(
        self, query: str, limit: int = 10, search_type: str = "auto"
    ) -> Dict[str, Any]:
        """Запрос под указанный вид поиска; "auto" выбирает вид по строке."""
        if search_type == "auto":
            search_type = self._detect_search_type(query)

        if search_type == "qualified":
            parsed = self.parse_qualified_name(query)
            if parsed:
                return self.build_qualified_query(*parsed, limit=limit)
            return self._build_exact_search(query, limit)

        builders = {
            "exact": self._build_exact_search,
            "fuzzy": self._build_fuzzy_search,
            "semantic": self._build_semantic_search,
        }
        return builders.get(search_type, self._build_multi_match_search)(query, limit)

    def build_exact_query(self, function_name: str) -> Dict[str, Any]:
        """Запрос по точному имени элемента."""
        return _scored({
            "should": [
                {"term": {"name.keyword": {"value": function_name, "boost": 3.0}}},
                {"term": {"full_path": {"value": function_name, "boost": 2.0}}},
                {"match_phrase": {"name": {"query": function_name, "boost": 1.5}}},
            ]
        }, limit=5)

    @staticmethod
    def parse_qualified_name(query: str) -> Optional[Tuple[str, str]]:
        """Узкий синтаксический разрез 'ТаблицаЗначений.Добавить': одна точка, без пробелов.

        Запасной вариант для случая, когда объект в справке не найден. Широкий
        разбор — SearchService._qualified_split, он проверяет объект по индексу.
        """
        text = (query or "").strip()
        if text.count(".") != 1 or " " in text:
            return None

        obj, _, element = text.partition(".")
        obj, element = obj.strip(), element.strip()
        if not obj or not element:
            return None
        return obj, element

    @staticmethod
    def split_points(query: str) -> List[Tuple[str, str]]:
        """Все разрезы 'A.B' — от самой длинной левой части к самой короткой."""
        text = (query or "").strip()
        points = []
        for position in range(len(text) - 1, -1, -1):
            if text[position] != ".":
                continue
            obj, member = text[:position].strip(), text[position + 1:].strip()
            if obj and member:
                points.append((obj, member))
        return points

    def build_qualified_query(
        self, object_name: str, member_name: str, limit: int = 10
    ) -> Dict[str, Any]:
        """Запрос по паре объект + элемент.

        Принадлежность объекту — жёсткий filter: без него в выдачу попадают
        одноимённые методы чужих объектов («Добавить» есть у 197).
        """
        return _scored({
            "filter": [{"bool": {
                "should": [
                    {"term": {"object": object_name}},
                    {"term": {"object_en": object_name}},
                ],
                "minimum_should_match": 1,
            }}],
            "should": [
                {"term": {"name_ru.keyword": {"value": member_name, "boost": 10.0}}},
                {"term": {"name_en.keyword": {"value": member_name, "boost": 9.0}}},
                {"prefix": {"name_ru.keyword": {"value": member_name, "boost": 4.0}}},
                {"match": {"name_ru": {"query": member_name, "boost": 2.0}}},
                {"match": {"name_en": {"query": member_name, "boost": 2.0}}},
            ],
            "minimum_should_match": 1,
        }, limit)

    def _detect_search_type(self, query: str) -> str:
        words = query.split()
        if self.parse_qualified_name(query):
            return "qualified"
        if len(words) == 1 and len(query) < SINGLE_WORD_MAX_LENGTH:
            return "exact"
        if len(words) > SEMANTIC_MIN_WORDS or len(query) > SEMANTIC_MIN_LENGTH:
            return "semantic"
        return "multi_match"

    def _build_exact_search(self, query: str, limit: int) -> Dict[str, Any]:
        return _scored({
            "should": [
                {"term": {"name_ru.keyword": {"value": query, "boost": 12.0}}},
                {"term": {"name_en.keyword": {"value": query, "boost": 10.0}}},
                {"prefix": {"name_ru.keyword": {"value": query, "boost": 3.0}}},
                {"match_phrase": {"name": {"query": query, "boost": 5.0}}},
                {"match_phrase": {"syntax_all": {"query": query, "boost": 3.0}}},
                {"match": {"description": {"query": query, "boost": 2.0}}},
            ]
        }, limit)

    def _build_multi_match_search(self, query: str, limit: int) -> Dict[str, Any]:
        return _scored({
            "must": {
                "multi_match": {
                    "query": query,
                    "fields": [
                        "name^5", "full_path^4", "syntax_all^3",
                        "description^2", "examples^1",
                    ],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            },
            "should": [
                {"match_phrase": {"name": {"query": query, "boost": 2.0}}},
                {"prefix": {"name": {"value": query, "boost": 1.5}}},
            ],
        }, limit)

    def _build_fuzzy_search(self, query: str, limit: int) -> Dict[str, Any]:
        return _scored({
            "should": [
                {"multi_match": {
                    "query": query,
                    "fields": ["name^3", "full_path^2", "description^1"],
                    "fuzziness": 2,
                    "type": "best_fields",
                }},
                {"wildcard": {"name.keyword": {"value": f"*{query}*", "boost": 1.5}}},
            ]
        }, limit)

    def _build_semantic_search(self, query: str, limit: int) -> Dict[str, Any]:
        return _scored({
            "should": [
                {"multi_match": {
                    "query": query,
                    "fields": [
                        "description^3", "name^2", "full_path^2",
                        "syntax_all^1.5", "examples^1", "note^1",
                    ],
                    "type": "most_fields",
                    "minimum_should_match": "50%",
                }},
                {"match_phrase": {
                    "description": {"query": query, "boost": 2.0, "slop": 3}
                }},
            ]
        }, limit)

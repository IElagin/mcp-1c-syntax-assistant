"""Тела запросов Elasticsearch."""

from typing import Dict, Any, List, Optional, Tuple
import re

BY_RELEVANCE = [{"_score": {"order": "desc"}}]

SINGLE_WORD_MAX_LENGTH = 30
SEMANTIC_MIN_WORDS = 3
SEMANTIC_MIN_LENGTH = 50
TERM_COVERAGE_BOOST = 20.0
FUZZY_PREFIX_LENGTH = 2
FUZZY_MAX_EXPANSIONS = 10
CONVERSION_PHRASE_BOOST = 40.0
CONVERSION_PHRASE_SLOP = 1
CONVERSION_PHRASE = re.compile(
    r'\b(?:преобраз\w*|конверт\w*|convert\w*)\s+'
    r'(?P<relation>(?P<left>[^\W\d_]+)\s+(?P<direction>в|из|into|to|from)\s+'
    r'(?P<right>[^\W\d_]+))(?=[\s?!.;]*$)',
    re.IGNORECASE,
)
CONVERSION_TYPES = {
    alias: names
    for names, aliases in (
        (("Строка", "String"), ("строка", "строку", "строки", "строке", "строкой", "string")),
        (("Число", "Number"), ("число", "числа", "числу", "числом", "числе", "number")),
        (("Дата", "Date"), ("дата", "дату", "даты", "дате", "датой", "date")),
        (("Булево", "Boolean"), ("булево", "boolean", "bool")),
    )
    for alias in aliases
}


def _conversion_queries(query: str) -> List[Dict[str, Any]]:
    clauses = []
    for match in CONVERSION_PHRASE.finditer(query):
        destination = 'left' if match.group('direction').lower() in ('из', 'from') else 'right'
        types = CONVERSION_TYPES.get(match.group(destination).lower())
        if not types:
            continue
        clauses.append({"constant_score": {
            "filter": {"bool": {"filter": [
                {"terms": {"variants.return_type": list(types)}},
                {"match_phrase": {"description": {
                    "query": match.group('relation'), "slop": CONVERSION_PHRASE_SLOP,
                }}},
            ]}},
            "boost": CONVERSION_PHRASE_BOOST,
        }})
    return clauses


def _term_coverage(query: str) -> Dict[str, Any]:
    return {"constant_score": {
        "filter": {"combined_fields": {
            "query": query,
            "fields": [
                "name", "description", "note",
                "variants.description", "variants.parameters.description",
                "variants.return_description",
            ],
            "operator": "and",
        }},
        "boost": TERM_COVERAGE_BOOST,
    }}


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
                    "prefix_length": FUZZY_PREFIX_LENGTH,
                    "max_expansions": FUZZY_MAX_EXPANSIONS,
                }
            },
            "should": [
                _term_coverage(query),
                {"match_phrase": {"name": {"query": query, "boost": 2.0}}},
                *_conversion_queries(query),
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
                _term_coverage(query),
                {"multi_match": {
                    "query": query,
                    "fields": [
                        "description^3", "name^2", "full_path^2",
                        "syntax_all^1.5", "examples^1", "note^1",
                        "variants.description", "variants.parameters.description",
                        "variants.return_description",
                    ],
                    "type": "most_fields",
                    "minimum_should_match": "50%",
                    "fuzziness": "AUTO",
                    "prefix_length": FUZZY_PREFIX_LENGTH,
                    "max_expansions": FUZZY_MAX_EXPANSIONS,
                }},
                *_conversion_queries(query),
                {"match_phrase": {
                    "description": {"query": query, "boost": 2.0, "slop": 3}
                }},
            ]
        }, limit)

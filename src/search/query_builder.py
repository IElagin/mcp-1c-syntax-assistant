"""Построитель запросов для Elasticsearch."""

from typing import Dict, Any, List


class QueryBuilder:
    """Построитель Elasticsearch запросов для поиска по документации 1С."""
    
    def build_search_query(
        self,
        query: str,
        limit: int = 10,
        search_type: str = "auto"
    ) -> Dict[str, Any]:
        """
        Строит поисковый запрос.
        
        Args:
            query: Поисковый запрос
            limit: Максимальное количество результатов
            search_type: Тип поиска (auto, exact, fuzzy, semantic)
        
        Returns:
            Elasticsearch запрос
        """
        # Определяем тип поиска автоматически
        if search_type == "auto":
            search_type = self._detect_search_type(query)
        
        if search_type == "qualified":
            parsed = self.parse_qualified_name(query)
            if parsed:
                return self.build_qualified_query(*parsed, limit=limit)
            return self._build_exact_search(query, limit)
        elif search_type == "exact":
            return self._build_exact_search(query, limit)
        elif search_type == "fuzzy":
            return self._build_fuzzy_search(query, limit)
        elif search_type == "semantic":
            return self._build_semantic_search(query, limit)
        else:
            return self._build_multi_match_search(query, limit)
    
    def build_exact_query(self, function_name: str) -> Dict[str, Any]:
        """Строит точный запрос по имени функции."""
        return {
            "query": {
                "bool": {
                    "should": [
                        {"term": {"name.keyword": {"value": function_name, "boost": 3.0}}},
                        {"term": {"full_path": {"value": function_name, "boost": 2.0}}},
                        {"match_phrase": {"name": {"query": function_name, "boost": 1.5}}}
                    ]
                }
            },
            "size": 5,
            "sort": [
                {"_score": {"order": "desc"}}
            ]
        }
    
    def build_object_query(self, object_name: str, limit: int = 50) -> Dict[str, Any]:
        """Строит запрос для поиска всех элементов объекта."""
        return {
            "query": {
                "bool": {
                    "should": [
                        {"term": {"object": {"value": object_name, "boost": 3.0}}},
                        {"prefix": {"full_path": {"value": f"{object_name}.", "boost": 2.0}}},
                        {"match": {"full_path": {"query": object_name, "boost": 1.5}}}
                    ]
                }
            },
            "size": limit,
            "sort": [
                {"type": {"order": "asc"}},
                {"name.keyword": {"order": "asc"}}
            ]
        }
    
    @staticmethod
    def parse_qualified_name(query: str):
        """Разбирает 'ТаблицаЗначений.Добавить' на объект и элемент.

        Возвращает (объект, элемент) либо None, если запрос не похож на
        обращение к элементу объекта.
        """
        text = (query or "").strip()
        if text.count(".") != 1 or " " in text:
            return None

        obj, _, element = text.partition(".")
        obj, element = obj.strip(), element.strip()
        if not obj or not element:
            return None
        return obj, element

    def build_qualified_query(
        self,
        object_name: str,
        member_name: str,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Строит запрос по паре объект + элемент.

        Принадлежность объекту — жёсткий filter, иначе в выдачу попадают
        одноимённые методы чужих объектов ('Добавить' есть у десятков).
        Имя элемента ищется от точного совпадения к префиксу.
        """
        return {
            "query": {
                "bool": {
                    "filter": [{"term": {"object": object_name}}],
                    "should": [
                        {"term": {"name_ru.keyword": {"value": member_name, "boost": 10.0}}},
                        {"term": {"name_en.keyword": {"value": member_name, "boost": 9.0}}},
                        {"prefix": {"name_ru.keyword": {"value": member_name, "boost": 4.0}}},
                        {"match": {"name_ru": {"query": member_name, "boost": 2.0}}},
                        {"match": {"name_en": {"query": member_name, "boost": 2.0}}}
                    ],
                    "minimum_should_match": 1
                }
            },
            "size": limit,
            "sort": [
                {"_score": {"order": "desc"}}
            ]
        }

    def _detect_search_type(self, query: str) -> str:
        """Автоматически определяет тип поиска по запросу."""
        # Обращение к элементу объекта: 'ТаблицаЗначений.Добавить'
        if self.parse_qualified_name(query):
            return "qualified"

        # Точный поиск - если запрос короткий и не содержит пробелов
        if len(query.split()) == 1 and len(query) < 30:
            return "exact"
        
        # Семантический поиск - если запрос длинный или содержит много слов
        if len(query.split()) > 3 or len(query) > 50:
            return "semantic"
        
        # По умолчанию - обычный поиск
        return "multi_match"
    
    def _build_exact_search(self, query: str, limit: int) -> Dict[str, Any]:
        """Строит точный поиск."""
        return {
            "query": {
                "bool": {
                    "should": [
                        # Точное совпадение имени. Раньше буст вешался на
                        # name.keyword, где лежит слитное "Добавить (Add)",
                        # поэтому не срабатывал никогда.
                        {"term": {"name_ru.keyword": {"value": query, "boost": 12.0}}},
                        {"term": {"name_en.keyword": {"value": query, "boost": 10.0}}},
                        {"prefix": {"name_ru.keyword": {"value": query, "boost": 3.0}}},
                        {"match_phrase": {"name": {"query": query, "boost": 5.0}}},
                        # syntax_ru/syntax_en заменены на syntax_all: одна
                        # строка вызова вместо пары языковых полей.
                        {"match_phrase": {"syntax_all": {"query": query, "boost": 3.0}}},
                        {"match": {"description": {"query": query, "boost": 2.0}}}
                    ]
                }
            },
            "size": limit,
            "sort": [
                {"_score": {"order": "desc"}}
            ]
        }
    
    def _build_multi_match_search(self, query: str, limit: int) -> Dict[str, Any]:
        """Строит обычный multi-match поиск."""
        return {
            "query": {
                "bool": {
                    "must": {
                        "multi_match": {
                            "query": query,
                            # parameters.name был плоским match по nested-полю —
                            # 0 попаданий против 11 у настоящего nested-запроса;
                            # syntax_ru/syntax_en заменены на общее syntax_all.
                            "fields": [
                                "name^5",
                                "full_path^4",
                                "syntax_all^3",
                                "description^2",
                                "examples^1"
                            ],
                            "type": "best_fields",
                            "fuzziness": "AUTO"
                        }
                    },
                    "should": [
                        {"match_phrase": {"name": {"query": query, "boost": 2.0}}},
                        {"prefix": {"name": {"value": query, "boost": 1.5}}}
                    ]
                }
            },
            "size": limit,
            "sort": [
                {"_score": {"order": "desc"}}
            ]
        }
    
    def _build_fuzzy_search(self, query: str, limit: int) -> Dict[str, Any]:
        """Строит нечеткий поиск."""
        return {
            "query": {
                "bool": {
                    "should": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "name^3",
                                    "full_path^2",
                                    "description^1"
                                ],
                                "fuzziness": 2,
                                "type": "best_fields"
                            }
                        },
                        {
                            "wildcard": {
                                "name.keyword": {
                                    "value": f"*{query}*",
                                    "boost": 1.5
                                }
                            }
                        }
                    ]
                }
            },
            "size": limit,
            "sort": [
                {"_score": {"order": "desc"}}
            ]
        }
    
    def _build_semantic_search(self, query: str, limit: int) -> Dict[str, Any]:
        """Строит семантический поиск."""
        return {
            "query": {
                "bool": {
                    "should": [
                        {
                            "multi_match": {
                                "query": query,
                                # note добавлен осознанно: примечания справки несут
                                # оговорки, которые ищут словами ("эффективно
                                # использовать для выборки неуникальных значений").
                                "fields": [
                                    "description^3",
                                    "name^2",
                                    "full_path^2",
                                    "syntax_all^1.5",
                                    "examples^1",
                                    "note^1"
                                ],
                                "type": "most_fields",
                                "minimum_should_match": "50%"
                            }
                        },
                        {
                            "match_phrase": {
                                "description": {
                                    "query": query,
                                    "boost": 2.0,
                                    "slop": 3
                                }
                            }
                        }
                    ]
                }
            },
            "size": limit,
            "sort": [
                {"_score": {"order": "desc"}}
            ]
        }

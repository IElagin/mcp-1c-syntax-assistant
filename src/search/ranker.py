"""Ранжирование результатов поиска поверх оценки Elasticsearch."""

from typing import List, Dict, Any

FACTOR_WEIGHTS = {
    "exact_name_match": 0.4,
    "doc_type_priority": 0.2,
    "description_quality": 0.15,
    "completeness": 0.15,
    "syntax_match": 0.1,
}
DEFAULT_FACTOR_WEIGHT = 0.1

TYPE_PRIORITIES = {
    "global_function": 2.0,
    "function": 1.8,
    "method": 1.6,
    "property": 1.2,
    "event": 1.1,
    "constant": 1.0,
}

NEUTRAL = 1.0
DESCRIPTION_WELL_SIZED = (50, 500)
DESCRIPTION_SHORT = (20, 50)


class SearchRanker:
    """Досчитывает оценку документа по признакам, которых не видит Elasticsearch."""

    def rank_results(
        self, hits: List[Dict[str, Any]], query: str
    ) -> List[Dict[str, Any]]:
        """Документы с досчитанной оценкой, по убыванию."""
        ranked = []
        for hit in hits:
            doc = hit["_source"]
            factors = self._ranking_factors(doc, query)
            ranked.append({
                "document": doc,
                "score": self._apply_factors(hit["_score"], factors),
                "base_score": hit["_score"],
                "ranking_factors": factors,
            })

        ranked.sort(key=lambda result: result["score"], reverse=True)
        return ranked

    def _ranking_factors(self, doc: Dict[str, Any], query: str) -> Dict[str, float]:
        return {
            "exact_name_match": self._exact_name_match_factor(doc, query),
            "doc_type_priority": self._doc_type_priority_factor(doc),
            "description_quality": self._description_quality_factor(doc),
            "completeness": self._completeness_factor(doc),
            "syntax_match": self._syntax_match_factor(doc, query),
        }

    @staticmethod
    def _exact_name_match_factor(doc: Dict[str, Any], query: str) -> float:
        name = doc.get("name", "").lower()
        full_path = doc.get("full_path", "").lower()
        wanted = query.lower()

        if wanted in (name, full_path):
            return 3.0
        if name.startswith(wanted) or full_path.startswith(wanted):
            return 2.0
        if wanted in name or wanted in full_path:
            return 1.5
        return NEUTRAL

    @staticmethod
    def _doc_type_priority_factor(doc: Dict[str, Any]) -> float:
        doc_type = doc.get("type", "").lower()
        for type_key, priority in TYPE_PRIORITIES.items():
            if type_key in doc_type:
                return priority
        return NEUTRAL

    @staticmethod
    def _description_quality_factor(doc: Dict[str, Any]) -> float:
        description = doc.get("description", "")
        if not description:
            return 0.8

        length = len(description)
        if DESCRIPTION_WELL_SIZED[0] <= length <= DESCRIPTION_WELL_SIZED[1]:
            return 1.3
        if DESCRIPTION_SHORT[0] <= length < DESCRIPTION_SHORT[1]:
            return 1.1
        if length > DESCRIPTION_WELL_SIZED[1]:
            return 1.2
        return 0.9

    @staticmethod
    def _completeness_factor(doc: Dict[str, Any]) -> float:
        """Насколько документ полон: синтаксис, параметры, примеры, тип результата.

        Параметры и тип результата лежат внутри вариантов вызова, а не
        плоскими полями документа; у свойств тип — в value_type.
        """
        variants = doc.get("variants") or []
        parameters = [p for v in variants for p in (v.get("parameters") or [])]
        described = sum(1 for p in parameters if p.get("description"))

        score = NEUTRAL
        if doc.get("syntax_all") or doc.get("call_primary"):
            score += 0.3
        if parameters:
            score += 0.2
            score += 0.1 * (described / len(parameters))
        if doc.get("examples"):
            score += 0.2
        if any(v.get("return_type") for v in variants) or doc.get("value_type"):
            score += 0.1
        return score

    @staticmethod
    def _syntax_match_factor(doc: Dict[str, Any], query: str) -> float:
        syntax = (doc.get("syntax_all") or "").lower()
        wanted = query.lower()

        if wanted in syntax:
            return 1.4

        words = wanted.split()
        if len(words) > 1:
            matched = sum(1 for word in words if word in syntax)
            if matched:
                return NEUTRAL + (matched / len(words)) * 0.3

        return NEUTRAL

    @staticmethod
    def _apply_factors(base_score: float, factors: Dict[str, float]) -> float:
        score = base_score
        for name, value in factors.items():
            weight = FACTOR_WEIGHTS.get(name, DEFAULT_FACTOR_WEIGHT)
            score *= NEUTRAL + (value - NEUTRAL) * weight
        return score

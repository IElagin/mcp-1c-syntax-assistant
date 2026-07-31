"""Форматирование результатов поиска.

Документ отдаётся целиком: карточку собирает element_card, и любое поле,
вырезанное здесь, делает карточку неполной ещё до рендера. Прежняя версия
пересобирала документ вручную, поэтому каждое новое поле индекса приходилось
дописывать в трёх местах — и availability не дописали бы.
"""

from typing import Any, Dict, List


class SearchFormatter:
    """Форматировщик результатов поиска."""

    def format_search_results(
        self, ranked_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Документы с метаинформацией о ранжировании."""
        rezultaty = []
        for result in ranked_results:
            doc = dict(result["document"])
            doc["_score"] = round(result["score"], 3)
            doc["_relevance"] = self._uroven_relevantnosti(result["score"])
            rezultaty.append(doc)
        return rezultaty

    @staticmethod
    def _uroven_relevantnosti(score: float) -> str:
        """Словесная оценка релевантности."""
        if score >= 10.0:
            return "very_high"
        if score >= 5.0:
            return "high"
        if score >= 2.0:
            return "medium"
        if score >= 1.0:
            return "low"
        return "very_low"

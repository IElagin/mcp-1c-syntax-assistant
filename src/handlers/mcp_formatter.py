"""Форматтер ответов MCP."""

from typing import Dict, List
from src.models.mcp_models import MCPResponse


def obrezat_do_frazy(text: str, predel: int) -> str:
    """Укорачивает текст, не разрывая фразу посередине.

    Обрыв на середине фразы меняет смысл на противоположный: «Два регламентных
    задания с одинаковым значением ключа могут …» вместо «…могут быть выполнены
    только последовательно». Поэтому режем по концу фразы, а если первая же
    фраза не влезает — по границе слова.
    """
    tekst = " ".join((text or "").split())
    if len(tekst) <= predel:
        return tekst

    okno = tekst[:predel]

    granitsa = max(okno.rfind(". "), okno.rfind("! "), okno.rfind("? "))
    if granitsa >= predel // 3:
        return okno[:granitsa + 1] + " …"

    probel = okno.rfind(" ")
    if probel <= 0:
        return okno + "…"
    return okno[:probel] + " …"


class MCPResponseFormatter:
    """Класс для стандартизированного форматирования ответов MCP."""
    
    @staticmethod
    def create_error_response(message: str, details: str = None) -> MCPResponse:
        """Создаёт стандартизированный ответ с ошибкой."""
        error_text = message
        if details:
            error_text += f": {details}"
        return MCPResponse(content=[], error=error_text)
    
    @staticmethod
    def create_success_response(content: List[Dict[str, str]]) -> MCPResponse:
        """Создаёт стандартизированный успешный ответ."""
        return MCPResponse(content=content)


# Глобальный экземпляр форматтера
mcp_formatter = MCPResponseFormatter()

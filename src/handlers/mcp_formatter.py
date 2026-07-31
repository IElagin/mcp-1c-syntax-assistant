"""Форматтер ответов MCP."""

from typing import Dict, List, Any
from src.models.mcp_models import MCPResponse

# Бюджет описания в списках-превью. Замер по индексу: медиана описания 103
# знака, медиана первой фразы 65. При прежнем пределе 100 обрезалось 51.3%
# описаний — больше половины превью были неполными.
PREDEL_OPISANIYA = 200
PREDEL_OPISANIYA_KRATKO = 140


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
    def create_not_found_response(query: str, context: str = "") -> MCPResponse:
        """Ответ «не найдено» с указанием, что делать дальше.

        Голое «ничего не найдено» оставляет агента без следующего шага, и он
        либо выдумывает имя, либо сдаётся.
        """
        gde = f" в контексте '{context}'" if context else ""
        text = (
            f"По запросу '{query}'{gde} ничего не найдено.\n"
            "Что можно сделать: проверить имя по-русски и по-английски; "
            "поискать по описанию через find_1c_help; "
            "если известен объект — посмотреть его состав через "
            "list_1c_object_members."
        )
        return MCPResponse(content=[{"type": "text", "text": text}])
    
    @staticmethod
    def create_success_response(content: List[Dict[str, str]]) -> MCPResponse:
        """Создаёт стандартизированный успешный ответ."""
        return MCPResponse(content=content)

    @staticmethod
    def format_object_members_list(object_name: str, member_type: str, methods: list,
                                 properties: list, events: list, total: int) -> str:
        """Форматирует список элементов объекта.

        Выводит все переданные элементы: сколько их — решает limit вызова, а не
        форматтер. Прежние жёсткие лимиты 20/15/10 молча выбрасывали хвост, и у
        'ТабличныйДокумент' заголовок сообщал «Методы (46)» при 20 выведенных.
        """
        text = f"📦 **ОБЪЕКТ:** {object_name}\n\n"

        pokazano = len(methods) + len(properties) + len(events)

        # Методы. "constructors" тоже сюда: get_object_members_list кладёт
        # конструкторы в тот же список methods, и без constructors в этом
        # условии запрос members="constructors" молча вернул бы пустое тело —
        # ровно та неполнота, от которой этот формат уходит. Ярлык подписи при
        # этом меняем на «Конструкторы»: иначе он лжёт о виде элемента, когда
        # запрошены только конструкторы.
        if member_type in ["all", "methods", "constructors"] and methods:
            yarlyk_metodov = "Конструкторы" if member_type == "constructors" else "Методы"
            text += f"🔨 **{yarlyk_metodov} ({len(methods)}):**\n"
            for method in methods:
                name = method.get("name", "")
                syntax = method.get("syntax_ru", "")
                desc = method.get("description", "")

                text += f"   • **{name}**"
                if syntax:
                    text += f" - `{syntax}`"
                if desc:
                    text += f"\n     {obrezat_do_frazy(desc, PREDEL_OPISANIYA_KRATKO)}"
                text += "\n"
            text += "\n"

        # Свойства
        if member_type in ["all", "properties"] and properties:
            text += f"📋 **Свойства ({len(properties)}):**\n"
            for prop in properties:
                name = prop.get("name", "")
                desc = prop.get("description", "")

                text += f"   • **{name}**"
                if desc:
                    text += f" - {obrezat_do_frazy(desc, PREDEL_OPISANIYA_KRATKO)}"
                text += "\n"
            text += "\n"

        # События
        if member_type in ["all", "events"] and events:
            text += f"⚡ **События ({len(events)}):**\n"
            for event in events:
                name = event.get("name", "")
                desc = event.get("description", "")

                text += f"   • **{name}**"
                if desc:
                    text += f" - {obrezat_do_frazy(desc, PREDEL_OPISANIYA_KRATKO)}"
                text += "\n"
            text += "\n"

        # Молчаливая неполнота — худшее, что может отдать справочный инструмент:
        # агент примет урезанный список за исчерпывающий и решит, что метода нет.
        if total and total > pokazano:
            text += (
                f"⚠️ Показано {pokazano} из {total}. "
                f"Остальные не выведены — повторите вызов с limit={total}.\n"
            )

        return text


# Глобальный экземпляр форматтера
mcp_formatter = MCPResponseFormatter()

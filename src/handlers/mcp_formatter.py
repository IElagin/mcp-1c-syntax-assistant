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
    def format_search_header(count: int, query: str) -> Dict[str, str]:
        """Форматирует заголовок результатов поиска."""
        return {
            "type": "text",
            "text": f"📋 **Найдено:** {count} элементов по запросу \"{query}\"\n"
        }
    
    @staticmethod
    def format_search_result(result: Dict[str, Any], index: int) -> Dict[str, str]:
        """Форматирует отдельный результат поиска."""
        name = result.get("name", "")
        obj = result.get("object", "")
        description = result.get("description", "")
        
        text = f"{index}. **{name}**"
        if obj:
            text += f" ({obj} → Метод)" if obj != "Global context" else " (Глобальная функция)"
        
        if description:
            text += f"\n   └ {obrezat_do_frazy(description, PREDEL_OPISANIYA)}"

        return {"type": "text", "text": text + "\n"}
    
    @staticmethod
    def format_syntax_info(result: Dict[str, Any]) -> str:
        """Форматирует техническую справку."""
        text = f"🔧 **ТЕХНИЧЕСКАЯ СПРАВКА:** {result.get('name', '')}"
        
        if result.get('object'):
            text += f" ({result['object']})"
        
        text += "\n\n"
        
        if result.get('description'):
            text += f"📝 **Описание:**\n   {result['description']}\n\n"
        
        if result.get('syntax_ru'):
            text += f"🔤 **Синтаксис:**\n   `{result['syntax_ru']}`\n\n"
        
        # Параметры
        parameters = result.get('parameters')
        if parameters and isinstance(parameters, list):
            text += "⚙️ **Параметры:**\n"
            for param in parameters:
                if isinstance(param, dict):
                    required = " (обязательный)" if param.get('required') else " (необязательный)"
                    text += f"   • {param.get('name', '')} ({param.get('type', '')}){required}"
                    if param.get('description'):
                        text += f" - {param['description']}"
                    text += "\n"
            text += "\n"
        
        if result.get('return_type'):
            text += f"↩️ **Возвращает:** {result['return_type']}\n\n"
        
        return text
    
    @staticmethod
    def format_quick_reference(result: Dict[str, Any]) -> str:
        """Форматирует краткую справку."""
        name = result.get('name', '')
        syntax = result.get('syntax_ru', '')
        description = result.get('description', '')
        
        text = "⚡ **КРАТКАЯ СПРАВКА**\n\n"
        
        if syntax:
            text += f"`{syntax}`\n"
        else:
            text += f"`{name}`\n"
        
        if description:
            text += f"└ {obrezat_do_frazy(description, PREDEL_OPISANIYA_KRATKO)}"
        
        return text
    
    @staticmethod
    def format_context_search(
        search_results: List[Dict[str, Any]], 
        query: str, 
        context: str
    ) -> str:
        """Форматирует результаты контекстного поиска."""
        if context == "object":
            objects = {}
            for result in search_results:
                obj = result.get("object", "Неизвестно")
                if obj not in objects:
                    objects[obj] = []
                objects[obj].append(result)
            
            text = f"🎯 **ПОИСК В КОНТЕКСТЕ:** {context}\n\n"
            text += f"Найдено {len(search_results)} элементов по запросу \"{query}\"\n\n"
            
            # Группировку не урезаем: сколько результатов показать, задаёт limit
            # вызова. Прежние 5 объектов по 3 элемента отбрасывали остальное молча.
            for obj, items in objects.items():
                text += f"📦 **{obj}:**\n"
                for item in items:
                    name = item.get("name", "")
                    syntax = item.get("syntax_ru", "")
                    desc = item.get("description", "")

                    text += f"   • {name}"
                    if syntax:
                        text += f" - `{syntax}`"
                    if desc:
                        text += f"\n     {obrezat_do_frazy(desc, PREDEL_OPISANIYA_KRATKO)}"
                    text += "\n"
                text += "\n"
        else:
            text = f"🔍 **ПОИСК В КОНТЕКСТЕ:** {context}\n\n"
            text += f"Найдено {len(search_results)} элементов\n\n"

            for i, result in enumerate(search_results, 1):
                name = result.get("name", "")
                syntax = result.get("syntax_ru", "")
                text += f"{i}. **{name}**"
                if syntax:
                    text += f" - `{syntax}`"
                text += "\n"
        
        return text
    
    @staticmethod
    def format_quick_reference(result: dict) -> str:
        """Форматирует краткую справку."""
        name = result.get('name', '')
        syntax = result.get('syntax_ru', '')
        description = result.get('description', '')
        
        text = "⚡ **КРАТКАЯ СПРАВКА**\n\n"
        
        if syntax:
            text += f"`{syntax}`\n"
        else:
            text += f"`{name}`\n"
        
        if description:
            text += f"└ {obrezat_do_frazy(description, PREDEL_OPISANIYA_KRATKO)}"
        
        return text

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

        # Методы
        if member_type in ["all", "methods"] and methods:
            text += f"🔨 **Методы ({len(methods)}):**\n"
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

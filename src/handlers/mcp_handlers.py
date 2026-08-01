"""Обработчики MCP запросов."""

from src.api.mcp_tools import KIND_TO_TYPE, SEARCH_LIMIT_MAX, MEMBERS_LIMIT_MAX
from src.core.elasticsearch import ElasticsearchClient
from src.core.logging import get_logger
from src.handlers.element_card import (
    render_element_card, render_object_card, hint_about_remainder, member_list,
    candidate_list, list_line,
)
from src.handlers.mcp_formatter import mcp_formatter
from src.models.mcp_models import (
    Find1CHelpRequest, Get1CElementRequest, List1CObjectMembersRequest, MCPResponse,
)
from src.search.search_service import SearchService

logger = get_logger(__name__)

# Название вида элементов на русском для сообщения "у объекта нет элементов
# этого вида". "all" сюда не входит — для него сообщение формулируется иначе:
# просить попробовать members="all", когда уже запрошено all, бессмысленно.
MEMBER_KIND_RU = {
    "methods": "методов",
    "properties": "свойств",
    "events": "событий",
    "constructors": "конструкторов",
}


def _text_response(text: str) -> MCPResponse:
    return mcp_formatter.create_success_response([{"type": "text", "text": text}])


async def _why_empty(
    service: SearchService, request: Find1CHelpRequest
) -> str:
    """Почему выдача пуста: нет элемента, нет объекта или его убрал фильтр.

    Голое «по запросу ничего не найдено» сваливает три разных случая в один, и
    агент не может выбрать следующий шаг. Хуже того, прежний совет предлагал
    посмотреть состав объекта, которого в справке нет: find_1c_help(query=
    "Выполнить", object="ФоновыеЗадания") — канонический пример спеки §3.6, где
    идентификатор из кода не совпадает с именем объекта справки. get_1c_element
    этот случай уже различал, а поиск с тем же аргументом object — нет.
    """
    lines = [f"По запросу «{request.query}» ничего не найдено."]

    if request.object:
        # Исключение из object_exists и similar_objects намеренно не
        # глушится: сбой Elasticsearch долетит до внешнего except обработчика и
        # станет ошибкой, а не тихим «объекта нет».
        if await service.object_exists(request.object):
            lines.append(
                f"Объект «{request.object}» в справке есть, но подходящих "
                "элементов у него не нашлось. Весь его состав: "
                f'list_1c_object_members(object="{request.object}").'
            )
        else:
            similar = ", ".join(await service.similar_objects(request.object)) \
                or "подходящих не найдено"
            lines.append(
                f"Объект «{request.object}» в справке не найден — выдачу обнулил "
                f"фильтр по нему, а не отсутствие элемента. "
                f"Похожие объекты: {similar}."
            )
            lines.append(
                "Имя объекта в справке может отличаться от идентификатора в коде: "
                "например, менеджер фоновых заданий зовётся МенеджерФоновыхЗаданий."
            )

    if request.kind.value != "any":
        lines.append(
            f'Поиск был ограничен видом kind="{request.kind.value}" — '
            'повторите с kind="any", чтобы искать по всем видам элементов.'
        )

    if not request.object and request.kind.value == "any":
        lines.append(
            "Ни фильтра по объекту, ни фильтра по виду не было — совпадений нет "
            "во всей справке. Что можно сделать: проверить имя по-русски и "
            "по-английски; поискать по словам из описания; если известен "
            "объект — посмотреть его состав через list_1c_object_members."
        )

    return "\n".join(lines)


async def build_object_card(service: SearchService, doc: dict) -> str:
    """Карточка объекта: счётчики, конструкторы и совет — по одному ключу.

    Ключ, по которому в индексе лежат члены объекта, — его канонический путь: у
    2 286 объектов он совпадает с object, а у 220 объектов со «шаблонным» именем
    страницы («<Имя плана видов расчета>») члены хранятся под полным путём
    («БазовыеВидыРасчета.<Имя плана видов расчета>»), а не под одним object.

    Ключ считается здесь один раз и передаётся и в запросы, и в карточку.
    Раньше карточка выводила имя для совета сама, из своих полей документа, —
    два независимых вычисления одного и того же расходились молча, и ответ
    печатал состав по одному ключу, а перечень предлагал по другому.
    """
    key = doc.get("full_path") or doc.get("object") or ""
    counts = await service.member_count(key)
    constructors = await service.constructor_lines(key)
    return render_object_card(doc, counts, constructors, key)


async def handle_find_1c_help(
    request: Find1CHelpRequest, es_client: ElasticsearchClient
) -> MCPResponse:
    """Поиск кандидатов по справке."""
    logger.info(f"find_1c_help: {request.query!r} kind={request.kind.value}")
    try:
        service = SearchService(es_client)
        result = await service.find_help_filtered(
            request.query,
            KIND_TO_TYPE[request.kind.value],
            request.object,
            request.limit,
        )

        if result.get("error"):
            return mcp_formatter.create_error_response("Ошибка поиска", result["error"])

        found = result.get("results", [])
        if not found:
            return _text_response(await _why_empty(service, request))

        total = result.get("total", len(found))
        lines = [f"Найдено {total} элементов по запросу «{request.query}»."]
        if total > len(found):
            # Повтор с бо́льшим limit возвращает те же первые элементы: смещения
            # у инструмента нет. Формулировка — та же, что в карточке омонимов.
            call = f'find_1c_help(query="{request.query}"'
            if request.object:
                call += f', object="{request.object}"'
            if request.kind.value != "any":
                call += f', kind="{request.kind.value}"'
            lines.append(hint_about_remainder(
                len(found), total, SEARCH_LIMIT_MAX, call + ", limit={limit})",
            ))
        lines.append("")
        lines.extend(list_line(d) for d in found)
        lines.append("")
        lines.append("Полная карточка: get_1c_element(name=…, object=…)")

        return _text_response("\n".join(lines))
    except Exception as e:
        logger.error(f"find_1c_help: {e}")
        return mcp_formatter.create_error_response("Внутренняя ошибка поиска", str(e))


async def handle_get_1c_element(
    request: Get1CElementRequest, es_client: ElasticsearchClient
) -> MCPResponse:
    """Карточка элемента либо перечень кандидатов при неоднозначности."""
    logger.info(f"get_1c_element: {request.name!r} object={request.object!r}")
    try:
        service = SearchService(es_client)
        response = await service.element_card(
            request.name, request.object, request.variant
        )
        kind = response.get("kind")

        if kind == "card":
            doc = response["document"]
            if (doc.get("element_kind") or "") == "объект":
                return _text_response(await build_object_card(service, doc))
            return _text_response(render_element_card(doc))

        if kind == "ambiguous":
            return _text_response(candidate_list(
                response["name"], response["candidates"], response["total"],
                response.get("full_order", True),
            ))

        if kind == "object_not_found":
            similar = ", ".join(response["similar"]) or "подходящих не найдено"
            return _text_response(
                f"Объект «{response['object']}» в справке не найден, поэтому элемент "
                f"«{request.name}» у него искать негде. Похожие объекты: {similar}.\n"
                "Имя объекта в справке может отличаться от идентификатора в коде: "
                "например, менеджер фоновых заданий зовётся МенеджерФоновыхЗаданий."
            )

        if kind == "variant_not_found":
            names = ", ".join(f"«{i}»" for i in response["variants"] if i)
            return _text_response(
                f"Варианта «{request.variant}» у элемента «{request.name}» нет. "
                f"Доступные варианты: {names or 'вариант единственный и без имени'}."
            )

        if kind == "not_found":
            similar = response.get("similar") or []
            lines = [f"Элемент с точным именем «{request.name}» в справке не найден."]
            if similar:
                lines.append("Похожие по имени:")
                lines.extend(f"  {list_line(d)}" for d in similar)
            else:
                lines.append("Похожих по имени тоже нет — проверьте написание.")
            return _text_response("\n".join(lines))

        # kind == "error": element_card так помечает сбой Elasticsearch,
        # чтобы обрыв связи не выглядел как честное "не найдено".
        return mcp_formatter.create_error_response(
            "Ошибка получения карточки", response.get("error", "")
        )
    except Exception as e:
        logger.error(f"get_1c_element: {e}")
        return mcp_formatter.create_error_response("Ошибка получения карточки", str(e))


async def handle_list_1c_object_members(
    request: List1CObjectMembersRequest, es_client: ElasticsearchClient
) -> MCPResponse:
    """Состав объекта."""
    logger.info(f"list_1c_object_members: {request.object!r} members={request.members.value}")
    try:
        service = SearchService(es_client)
        result = await service.get_object_members_list(
            request.object, request.members.value, request.limit
        )

        if result.get("error"):
            return mcp_formatter.create_error_response("Ошибка", result["error"])

        if not result.get("total"):
            # total=0 неоднозначно само по себе: объекта может не быть вовсе,
            # а может — он есть, просто нет элементов запрошенного вида
            # (например, "события" у ТаблицаЗначений — событий у неё нет, а
            # объект есть). service.get_object_members_list уже отличил один
            # случай от другого запросом object_exists — раньше оба случая
            # звучали как "объект не найден", и агент слышал это про объект,
            # который тут же значился в списке "похожих" на самого себя.
            if result.get("object_exists"):
                kind = request.members.value
                if kind == "all":
                    return _text_response(
                        f"Объект «{request.object}» в справке есть, но ни методов, "
                        "ни свойств, ни событий, ни конструкторов у него не найдено."
                    )
                return _text_response(
                    f"Объект «{request.object}» в справке есть, но "
                    f"{MEMBER_KIND_RU[kind]} у него нет. "
                    'Попробуйте members="all", чтобы увидеть весь состав.'
                )

            # similar_objects вызывается здесь напрямую, вне try/except
            # element_card, поэтому сбой Elasticsearch внутри неё долетит
            # сюда как исключение — ловим его отдельно веткой ниже, а не
            # подменяем пустым списком: пустой список означал бы "похожих нет".
            similar = ", ".join(await service.similar_objects(request.object)) \
                or "подходящих не найдено"
            return _text_response(
                f"Объект «{request.object}» в справке не найден. "
                f"Похожие объекты: {similar}."
            )

        return _text_response(member_list(
            request.object,
            request.members.value,
            result["methods"],
            result["properties"],
            result["events"],
            result["total"],
            MEMBERS_LIMIT_MAX,
        ))
    except Exception as e:
        logger.error(f"list_1c_object_members: {e}")
        return mcp_formatter.create_error_response("Ошибка получения состава", str(e))

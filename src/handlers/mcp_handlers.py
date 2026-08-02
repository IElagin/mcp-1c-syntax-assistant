"""Обработчики MCP запросов."""

from src.api.mcp_tools import KIND_TO_TYPE, SEARCH_LIMIT_MAX, MEMBERS_LIMIT_MAX
from src.core.elasticsearch import ElasticsearchClient
from src.core.logging import get_logger
from src.handlers.element_card import (
    render_element_card, render_object_card, hint_about_remainder, member_list,
    candidate_list, list_line,
)
from src.handlers.mcp_formatter import mcp_formatter
from src.handlers.ui_strings import RU_STRINGS, UiStrings
from src.models.mcp_models import (
    Find1CHelpRequest, Get1CElementRequest, List1CObjectMembersRequest, MCPResponse,
)
from src.search.search_service import SearchService

logger = get_logger(__name__)


def _text_response(text: str) -> MCPResponse:
    return mcp_formatter.create_success_response([{"type": "text", "text": text}])


async def _why_empty(
    service: SearchService, request: Find1CHelpRequest, strings: UiStrings = RU_STRINGS
) -> str:
    """Почему выдача пуста: нет элемента, нет объекта или его убрал фильтр.

    Голое «по запросу ничего не найдено» сваливает три разных случая в один, и
    агент не может выбрать следующий шаг. Хуже того, прежний совет предлагал
    посмотреть состав объекта, которого в справке нет: find_1c_help(query=
    "Выполнить", object="ФоновыеЗадания") — канонический пример спеки §3.6, где
    идентификатор из кода не совпадает с именем объекта справки. get_1c_element
    этот случай уже различал, а поиск с тем же аргументом object — нет.
    """
    lines = [strings.nothing_found.format(query=request.query)]

    if request.object:
        # Исключение из object_exists и similar_objects намеренно не
        # глушится: сбой Elasticsearch долетит до внешнего except обработчика и
        # станет ошибкой, а не тихим «объекта нет».
        if await service.object_exists(request.object):
            lines.append(strings.object_exists_but_empty.format(object=request.object))
        else:
            similar = ", ".join(await service.similar_objects(request.object)) \
                or strings.no_similar_objects
            lines.append(
                strings.object_not_found.format(object=request.object, similar=similar)
            )
            lines.append(strings.object_name_differs_hint)

    if request.kind.value != "any":
        lines.append(strings.kind_filter_hint.format(kind=request.kind.value))

    if not request.object and request.kind.value == "any":
        lines.append(strings.no_filters_hint)

    return "\n".join(lines)


async def build_object_card(
    service: SearchService, doc: dict, strings: UiStrings = RU_STRINGS
) -> str:
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
    return render_object_card(doc, counts, constructors, key, strings)


async def handle_find_1c_help(
    request: Find1CHelpRequest, es_client: ElasticsearchClient, strings: UiStrings = RU_STRINGS
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
            return _text_response(await _why_empty(service, request, strings))

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
                len(found), total, SEARCH_LIMIT_MAX, call + ", limit={limit})", strings,
            ))
        lines.append("")
        lines.extend(list_line(d, strings) for d in found)
        lines.append("")
        lines.append("Полная карточка: get_1c_element(name=…, object=…)")

        return _text_response("\n".join(lines))
    except Exception as e:
        logger.error(f"find_1c_help: {e}")
        return mcp_formatter.create_error_response("Внутренняя ошибка поиска", str(e))


async def handle_get_1c_element(
    request: Get1CElementRequest, es_client: ElasticsearchClient, strings: UiStrings = RU_STRINGS
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
                return _text_response(await build_object_card(service, doc, strings))
            return _text_response(render_element_card(doc, strings))

        if kind == "ambiguous":
            return _text_response(candidate_list(
                response["name"], response["candidates"], response["total"],
                response.get("full_order", True), strings,
            ))

        if kind == "object_not_found":
            similar = ", ".join(response["similar"]) or strings.no_similar_objects
            lines = [
                strings.object_missing_for_element.format(
                    object=response["object"], name=request.name, similar=similar,
                ),
                strings.object_name_differs_hint,
            ]
            return _text_response("\n".join(lines))

        if kind == "variant_not_found":
            names = ", ".join(f"«{i}»" for i in response["variants"] if i)
            return _text_response(strings.variant_not_found.format(
                variant=request.variant, name=request.name,
                variants=names or strings.single_variant_no_name,
            ))

        if kind == "not_found":
            similar = response.get("similar") or []
            lines = [strings.element_not_found.format(name=request.name)]
            if similar:
                lines.append(strings.similar_by_name)
                lines.extend(f"  {list_line(d, strings)}" for d in similar)
            else:
                lines.append(strings.no_similar)
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
    request: List1CObjectMembersRequest, es_client: ElasticsearchClient, strings: UiStrings = RU_STRINGS
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
                        strings.no_members_at_all.format(object=request.object)
                    )
                return _text_response(strings.no_members_of_kind.format(
                    object=request.object, kind=strings.member_names_genitive[kind],
                ))

            # similar_objects вызывается здесь напрямую, вне try/except
            # element_card, поэтому сбой Elasticsearch внутри неё долетит
            # сюда как исключение — ловим его отдельно веткой ниже, а не
            # подменяем пустым списком: пустой список означал бы "похожих нет".
            similar = ", ".join(await service.similar_objects(request.object)) \
                or strings.no_similar_objects
            return _text_response(
                strings.object_missing.format(object=request.object, similar=similar)
            )

        return _text_response(member_list(
            request.object,
            request.members.value,
            result["methods"],
            result["properties"],
            result["events"],
            result["total"],
            MEMBERS_LIMIT_MAX,
            strings,
        ))
    except Exception as e:
        logger.error(f"list_1c_object_members: {e}")
        return mcp_formatter.create_error_response("Ошибка получения состава", str(e))

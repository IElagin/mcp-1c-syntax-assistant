"""Обработчики MCP запросов."""

from src.api.mcp_tools import KIND_V_TYPE
from src.core.elasticsearch import ElasticsearchClient
from src.core.logging import get_logger
from src.handlers.element_card import (
    kartochka, kartochka_obekta, spisok_kandidatov, stroka_spiska,
)
from src.handlers.mcp_formatter import mcp_formatter
from src.models.mcp_models import (
    Find1CHelpRequest, Get1CElementRequest, List1CObjectMembersRequest, MCPResponse,
)
from src.search.search_service import SearchService

logger = get_logger(__name__)


def _tekst(text: str) -> MCPResponse:
    return mcp_formatter.create_success_response([{"type": "text", "text": text}])


async def handle_find_1c_help(
    request: Find1CHelpRequest, es_client: ElasticsearchClient
) -> MCPResponse:
    """Поиск кандидатов по справке."""
    logger.info(f"find_1c_help: {request.query!r} kind={request.kind.value}")
    try:
        service = SearchService(es_client)
        rezultat = await service.find_help_by_query_s_filtrom(
            request.query,
            KIND_V_TYPE[request.kind.value],
            request.object,
            request.limit,
        )

        if rezultat.get("error"):
            return mcp_formatter.create_error_response("Ошибка поиска", rezultat["error"])

        nayden = rezultat.get("results", [])
        if not nayden:
            return mcp_formatter.create_not_found_response(request.query)

        vsego = rezultat.get("total", len(nayden))
        stroki = [f"Найдено {vsego} элементов по запросу «{request.query}»."]
        if vsego > len(nayden):
            stroki.append(
                f"Показано {len(nayden)} из {vsego} — "
                f"повторите вызов с limit={min(vsego, 200)} за остальными."
            )
        stroki.append("")
        stroki.extend(stroka_spiska(d) for d in nayden)
        stroki.append("")
        stroki.append("Полная карточка: get_1c_element(name=…, object=…)")

        return _tekst("\n".join(stroki))
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
        otvet = await service.kartochka_elementa(
            request.name, request.object, request.variant
        )
        vid = otvet.get("kind")

        if vid == "card":
            doc = otvet["document"]
            if (doc.get("element_kind") or "") == "объект":
                kolichestva = await service.kolichestvo_chlenov(doc.get("object") or "")
                return _tekst(kartochka_obekta(doc, kolichestva))
            return _tekst(kartochka(doc))

        if vid == "ambiguous":
            return _tekst(spisok_kandidatov(
                otvet["name"], otvet["candidates"], otvet["total"]
            ))

        if vid == "object_not_found":
            pohozhie = ", ".join(otvet["similar"]) or "подходящих не найдено"
            return _tekst(
                f"Объект «{otvet['object']}» в справке не найден, поэтому элемент "
                f"«{request.name}» у него искать негде. Похожие объекты: {pohozhie}.\n"
                "Имя объекта в справке может отличаться от идентификатора в коде: "
                "например, менеджер фоновых заданий зовётся МенеджерФоновыхЗаданий."
            )

        if vid == "variant_not_found":
            imena = ", ".join(f"«{i}»" for i in otvet["variants"] if i)
            return _tekst(
                f"Варианта «{request.variant}» у элемента «{request.name}» нет. "
                f"Доступные варианты: {imena or 'вариант единственный и без имени'}."
            )

        if vid == "not_found":
            pohozhie = otvet.get("similar") or []
            stroki = [f"Элемент с точным именем «{request.name}» в справке не найден."]
            if pohozhie:
                stroki.append("Похожие по имени:")
                stroki.extend(f"  {stroka_spiska(d)}" for d in pohozhie)
            else:
                stroki.append("Похожих по имени тоже нет — проверьте написание.")
            return _tekst("\n".join(stroki))

        # vid == "error": kartochka_elementa так помечает сбой Elasticsearch,
        # чтобы обрыв связи не выглядел как честное "не найдено".
        return mcp_formatter.create_error_response(
            "Ошибка получения карточки", otvet.get("error", "")
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
        rezultat = await service.get_object_members_list(
            request.object, request.members.value, request.limit
        )

        if rezultat.get("error"):
            return mcp_formatter.create_error_response("Ошибка", rezultat["error"])

        if not rezultat.get("total"):
            # pohozhie_obekty вызывается здесь напрямую, вне try/except
            # kartochka_elementa, поэтому сбой Elasticsearch внутри неё долетит
            # сюда как исключение — ловим его отдельно веткой ниже, а не
            # подменяем пустым списком: пустой список означал бы "похожих нет".
            pohozhie = ", ".join(await service.pohozhie_obekty(request.object)) \
                or "подходящих не найдено"
            return _tekst(
                f"Объект «{request.object}» в справке не найден. "
                f"Похожие объекты: {pohozhie}."
            )

        return _tekst(mcp_formatter.format_object_members_list(
            request.object,
            request.members.value,
            rezultat["methods"],
            rezultat["properties"],
            rezultat["events"],
            rezultat["total"],
        ))
    except Exception as e:
        logger.error(f"list_1c_object_members: {e}")
        return mcp_formatter.create_error_response("Ошибка получения состава", str(e))

"""Обработчики MCP запросов."""

from src.api.mcp_tools import KIND_V_TYPE, LIMIT_POISKA_MAX, LIMIT_SOSTAVA_MAX
from src.core.elasticsearch import ElasticsearchClient
from src.core.logging import get_logger
from src.handlers.element_card import (
    kartochka, kartochka_obekta, sovet_ob_ostatke, spisok_chlenov,
    spisok_kandidatov, stroka_spiska,
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
RU_VID_SOSTAVA = {
    "methods": "методов",
    "properties": "свойств",
    "events": "событий",
    "constructors": "конструкторов",
}


def _tekst(text: str) -> MCPResponse:
    return mcp_formatter.create_success_response([{"type": "text", "text": text}])


async def _pochemu_pusto(
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
    stroki = [f"По запросу «{request.query}» ничего не найдено."]

    if request.object:
        # Исключение из obekt_sushchestvuet и pohozhie_obekty намеренно не
        # глушится: сбой Elasticsearch долетит до внешнего except обработчика и
        # станет ошибкой, а не тихим «объекта нет».
        if await service.obekt_sushchestvuet(request.object):
            stroki.append(
                f"Объект «{request.object}» в справке есть, но подходящих "
                "элементов у него не нашлось. Весь его состав: "
                f'list_1c_object_members(object="{request.object}").'
            )
        else:
            pohozhie = ", ".join(await service.pohozhie_obekty(request.object)) \
                or "подходящих не найдено"
            stroki.append(
                f"Объект «{request.object}» в справке не найден — выдачу обнулил "
                f"фильтр по нему, а не отсутствие элемента. "
                f"Похожие объекты: {pohozhie}."
            )
            stroki.append(
                "Имя объекта в справке может отличаться от идентификатора в коде: "
                "например, менеджер фоновых заданий зовётся МенеджерФоновыхЗаданий."
            )

    if request.kind.value != "any":
        stroki.append(
            f'Поиск был ограничен видом kind="{request.kind.value}" — '
            'повторите с kind="any", чтобы искать по всем видам элементов.'
        )

    if not request.object and request.kind.value == "any":
        stroki.append(
            "Ни фильтра по объекту, ни фильтра по виду не было — совпадений нет "
            "во всей справке. Что можно сделать: проверить имя по-русски и "
            "по-английски; поискать по словам из описания; если известен "
            "объект — посмотреть его состав через list_1c_object_members."
        )

    return "\n".join(stroki)


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
            return _tekst(await _pochemu_pusto(service, request))

        vsego = rezultat.get("total", len(nayden))
        stroki = [f"Найдено {vsego} элементов по запросу «{request.query}»."]
        if vsego > len(nayden):
            # Повтор с бо́льшим limit возвращает те же первые элементы: смещения
            # у инструмента нет. Формулировка — та же, что в карточке омонимов.
            vyzov = f'find_1c_help(query="{request.query}"'
            if request.object:
                vyzov += f', object="{request.object}"'
            if request.kind.value != "any":
                vyzov += f', kind="{request.kind.value}"'
            stroki.append(sovet_ob_ostatke(
                len(nayden), vsego, LIMIT_POISKA_MAX, vyzov + ", limit={limit})",
            ))
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
                # Ключ, по которому в индексе лежат члены объекта, — его
                # канонический путь: у 2 286 объектов он совпадает с object, а
                # у 220 объектов со «шаблонным» именем страницы («<Имя плана
                # видов расчета>») члены хранятся под полным путём
                # («БазовыеВидыРасчета.<Имя плана видов расчета>»), а не под
                # одним object. Тот же ключ уходит в совет карточки, поэтому
                # совет исполним в обоих случаях.
                klyuch = doc.get("full_path") or doc.get("object") or ""
                kolichestva = await service.kolichestvo_chlenov(klyuch)
                konstruktory = await service.stroki_konstruktorov(klyuch)
                return _tekst(kartochka_obekta(doc, kolichestva, konstruktory))
            return _tekst(kartochka(doc))

        if vid == "ambiguous":
            return _tekst(spisok_kandidatov(
                otvet["name"], otvet["candidates"], otvet["total"],
                otvet.get("poryadok_polnyy", True),
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
            # total=0 неоднозначно само по себе: объекта может не быть вовсе,
            # а может — он есть, просто нет элементов запрошенного вида
            # (например, "события" у ТаблицаЗначений — событий у неё нет, а
            # объект есть). service.get_object_members_list уже отличил один
            # случай от другого запросом object_exists — раньше оба случая
            # звучали как "объект не найден", и агент слышал это про объект,
            # который тут же значился в списке "похожих" на самого себя.
            if rezultat.get("object_exists"):
                vid = request.members.value
                if vid == "all":
                    return _tekst(
                        f"Объект «{request.object}» в справке есть, но ни методов, "
                        "ни свойств, ни событий, ни конструкторов у него не найдено."
                    )
                return _tekst(
                    f"Объект «{request.object}» в справке есть, но "
                    f"{RU_VID_SOSTAVA[vid]} у него нет. "
                    'Попробуйте members="all", чтобы увидеть весь состав.'
                )

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

        return _tekst(spisok_chlenov(
            request.object,
            request.members.value,
            rezultat["methods"],
            rezultat["properties"],
            rezultat["events"],
            rezultat["total"],
            LIMIT_SOSTAVA_MAX,
        ))
    except Exception as e:
        logger.error(f"list_1c_object_members: {e}")
        return mcp_formatter.create_error_response("Ошибка получения состава", str(e))

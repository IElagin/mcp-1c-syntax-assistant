"""Обработчики трёх инструментов MCP."""

import re
from typing import List, Optional, Tuple

from src.core.config import settings
from src.core.constants import KIND_TO_TYPE, MEMBERS_LIMIT_MAX, SEARCH_LIMIT_MAX
from src.core.elasticsearch import ElasticsearchClient
from src.core.logging import get_logger
from src.handlers.element_card import (
    render_element_card, render_object_card, hint_about_remainder, member_list,
    candidate_list, elsewhere_list, list_line,
)
from src.handlers.mcp_formatter import mcp_formatter
from src.handlers.ui_strings import RU_STRINGS, UiStrings, strings_for
from src.models.mcp_models import (
    Find1CHelpRequest, Get1CElementRequest, List1CObjectMembersRequest, MCPResponse,
)
from src.search.search_service import SearchService

logger = get_logger(__name__)

_CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")


def index_for(lang: str) -> str:
    """Индекс по языку ответа: русская и английская книги живут раздельно."""
    return settings.elasticsearch_index_en if lang == "en" else settings.elasticsearch_index


def _text_response(text: str) -> MCPResponse:
    return mcp_formatter.create_success_response([{"type": "text", "text": text}])


def has_cyrillic(text: str) -> bool:
    """Есть ли в строке хоть одна кириллическая буква."""
    return bool(_CYRILLIC.search(text or ""))


async def _language_mismatch(
    request_lang: str, values: tuple, es_client: ElasticsearchClient, strings: UiStrings
) -> Optional[str]:
    """Почему точное совпадение по values заведомо не найти, или None.

    Только для значений, которые ищутся точным совпадением. Свободный текстовый
    query сюда не передаётся — его блокировать на входе нельзя.
    """
    if request_lang != "en":
        return None

    if any(has_cyrillic(value) for value in values if value):
        return strings.russian_name_in_english_book

    if not await es_client.index_exists(index=index_for("en")):
        return strings.english_index_missing

    return None


async def _why_empty(
    service: SearchService,
    request: Find1CHelpRequest,
    strings: UiStrings = RU_STRINGS,
    qualified_object: Optional[str] = None,
) -> str:
    """Почему выдача пуста: нет элемента, нет объекта или его убрал фильтр."""
    lines = [strings.nothing_found.format(query=request.query)]

    if strings.lang == "en" and has_cyrillic(request.query):
        lines.append(strings.russian_name_in_english_book)

    # Объект бывает не только в аргументе, но и в самом запросе:
    # find_1c_help("Массив.НетТакогоМетода") сузил выдачу фильтром по Массиву.
    filtered_by = request.object or qualified_object
    if filtered_by:
        if await service.object_exists(filtered_by):
            lines.append(strings.object_exists_but_empty.format(object=filtered_by))
        else:
            similar = ", ".join(await service.similar_objects(filtered_by)) \
                or strings.no_similar_objects
            lines.append(
                strings.object_not_found.format(object=filtered_by, similar=similar)
            )
            lines.append(strings.object_name_differs_hint)

    if request.kind.value == "article" and not await service.articles_indexed():
        lines.append(strings.articles_not_indexed)

    if request.kind.value != "any":
        lines.append(strings.kind_filter_hint.format(kind=request.kind.value))

    if not filtered_by and request.kind.value == "any":
        lines.append(strings.no_filters_hint)

    return "\n".join(lines)


def constructor_lines(
    calls: List[Tuple[str, str]], strings: UiStrings
) -> List[str]:
    """Constructor call strings; a variant name distinguishes only several calls."""
    if len(calls) < 2:
        return [call for call, _ in calls]
    return [
        strings.constructor_variant.format(call=call, name=name) if name else call
        for call, name in calls
    ]


async def build_object_card(
    service: SearchService, doc: dict, strings: UiStrings = RU_STRINGS
) -> str:
    """Карточка объекта: счётчики, конструкторы и совет — по одному ключу.

    Ключ считается здесь один раз и передаётся и в запросы, и в карточку: два
    независимых вычисления одного ключа расходились молча.
    """
    key = doc.get("full_path") or doc.get("object") or ""
    counts = await service.member_count(key)
    constructors = constructor_lines(await service.constructor_calls(key), strings)
    return render_object_card(doc, counts, constructors, key, strings)


async def handle_find_1c_help(
    request: Find1CHelpRequest, es_client: ElasticsearchClient
) -> MCPResponse:
    """Поиск кандидатов по справке."""
    logger.info(f"find_1c_help: {request.query!r} kind={request.kind.value}")
    lang = request.lang.value
    strings = strings_for(lang)
    try:
        mismatch = await _language_mismatch(lang, (request.object,), es_client, strings)
        if mismatch:
            return _text_response(mismatch)

        service = SearchService(es_client, index=index_for(lang))
        result = await service.find_help_filtered(
            request.query,
            KIND_TO_TYPE[request.kind.value],
            request.object,
            request.limit,
        )

        if result.get("search_failed"):
            return mcp_formatter.create_error_response(
                strings.search_error_title, strings.search_failed
            )

        found = result.get("results", [])
        if not found:
            return _text_response(await _why_empty(
                service, request, strings, result.get("qualified_object")
            ))

        total = result.get("total", len(found))
        lines = [strings.found_count.format(total=total, query=request.query)]
        if total > len(found):
            lines.append(hint_about_remainder(
                len(found), total, SEARCH_LIMIT_MAX,
                _search_call_template(request), strings,
            ))
        lines.append("")
        lines.extend(list_line(doc, strings) for doc in found)
        lines.append("")
        lines.append(strings.full_card_hint_generic)

        return _text_response("\n".join(lines))
    except Exception as e:
        logger.error(f"find_1c_help: {e}")
        return mcp_formatter.create_error_response(
            strings.internal_search_error_title, str(e)
        )


def _search_call_template(request: Find1CHelpRequest) -> str:
    call = f'find_1c_help(query="{request.query}"'
    if request.object:
        call += f', object="{request.object}"'
    if request.kind.value != "any":
        call += f', kind="{request.kind.value}"'
    return call + ", limit={limit})"


async def handle_get_1c_element(
    request: Get1CElementRequest, es_client: ElasticsearchClient
) -> MCPResponse:
    """Карточка элемента либо причина, почему её нет."""
    logger.info(f"get_1c_element: {request.name!r} object={request.object!r}")
    lang = request.lang.value
    strings = strings_for(lang)
    try:
        mismatch = await _language_mismatch(
            lang, (request.name, request.object), es_client, strings
        )
        if mismatch:
            return _text_response(mismatch)

        service = SearchService(es_client, index=index_for(lang))
        answer = await service.element_card(
            request.name, request.object, request.variant
        )
        kind = answer.get("kind")

        if kind == "card":
            doc = answer["document"]
            if (doc.get("element_kind") or "") == "объект":
                return _text_response(await build_object_card(service, doc, strings))
            return _text_response(render_element_card(doc, strings))

        if kind == "ambiguous":
            return _text_response(candidate_list(
                answer["name"], answer["candidates"], answer["total"],
                answer.get("full_order", True), strings,
            ))

        if kind == "not_in_object":
            return _text_response(elsewhere_list(
                answer["name"], answer["object"], answer["candidates"],
                answer["total"], answer.get("full_order", True), strings,
            ))

        if kind == "object_not_found":
            return _text_response(_object_missing_for_element(answer, request, strings))

        if kind == "variant_not_found":
            return _text_response(_variant_missing(answer, request, strings))

        if kind == "not_found":
            return _text_response(_element_missing(answer, request, strings))

        return mcp_formatter.create_error_response(
            strings.card_error_title, answer.get("error", "")
        )
    except Exception as e:
        logger.error(f"get_1c_element: {e}")
        return mcp_formatter.create_error_response(strings.card_error_title, str(e))


def _object_missing_for_element(
    answer: dict, request: Get1CElementRequest, strings: UiStrings
) -> str:
    similar = ", ".join(answer["similar"]) or strings.no_similar_objects
    return "\n".join([
        strings.object_missing_for_element.format(
            object=answer["object"], name=request.name, similar=similar,
        ),
        strings.object_name_differs_hint,
    ])


def _variant_missing(
    answer: dict, request: Get1CElementRequest, strings: UiStrings
) -> str:
    names = ", ".join(f"«{name}»" for name in answer["variants"] if name)
    return strings.variant_not_found.format(
        variant=request.variant, name=request.name,
        variants=names or strings.single_variant_no_name,
    )


def _element_missing(
    answer: dict, request: Get1CElementRequest, strings: UiStrings
) -> str:
    similar = answer.get("similar") or []
    lines = [strings.element_not_found.format(name=request.name)]
    if similar:
        lines.append(strings.similar_by_name)
        lines.extend(f"  {list_line(doc, strings)}" for doc in similar)
    else:
        lines.append(strings.no_similar)
    return "\n".join(lines)


async def handle_list_1c_object_members(
    request: List1CObjectMembersRequest, es_client: ElasticsearchClient
) -> MCPResponse:
    """Состав объекта."""
    logger.info(
        f"list_1c_object_members: {request.object!r} members={request.members.value}"
    )
    lang = request.lang.value
    strings = strings_for(lang)
    try:
        mismatch = await _language_mismatch(lang, (request.object,), es_client, strings)
        if mismatch:
            return _text_response(mismatch)

        service = SearchService(es_client, index=index_for(lang))
        result = await service.get_object_members_list(
            request.object, request.members.value, request.limit
        )

        if result.get("error"):
            return mcp_formatter.create_error_response(
                strings.generic_error_title, result["error"]
            )

        if not result.get("total"):
            return _text_response(await _why_no_members(service, request, result, strings))

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
        return mcp_formatter.create_error_response(
            strings.members_internal_error_title, str(e)
        )


async def _why_no_members(
    service: SearchService,
    request: List1CObjectMembersRequest,
    result: dict,
    strings: UiStrings,
) -> str:
    """Пустой состав: объекта нет вовсе или нет элементов запрошенного вида.

    similar_objects зовётся вне try/except сервиса, поэтому сбой Elasticsearch
    внутри неё долетит исключением до обработчика, а не станет «похожих нет».
    """
    if result.get("object_exists"):
        kind = request.members.value
        if kind == "all":
            return strings.no_members_at_all.format(object=request.object)
        return strings.no_members_of_kind.format(
            object=request.object, kind=strings.member_names_genitive[kind],
        )

    similar = ", ".join(await service.similar_objects(request.object)) \
        or strings.no_similar_objects
    return strings.object_missing.format(object=request.object, similar=similar)

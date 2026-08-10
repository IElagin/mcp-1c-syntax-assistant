"""Сборка текста ответа: карточки, перечни, строки списка.

Единственное место сборки. Набор полей карточки фиксирован, и отсутствие
данных помечается явно: пропущенное поле неотличимо от «данных нет», и модель
достраивает пробел домыслом.
"""

from typing import Any, Dict, List, Optional

from src.core.constants import SEARCH_LIMIT_MAX
from src.handlers.mcp_formatter import truncate_at_sentence
from src.handlers.ui_strings import RU_STRINGS, UiStrings
from src.models.doc_models import DocumentType

NOT_IN_HELP = RU_STRINGS.not_in_help

DESCRIPTION_LIMIT_IN_LIST = 140

GLOBAL_KINDS = ("функция", "процедура", "событие")


def _call_label(doc: Dict[str, Any], strings: UiStrings) -> str:
    """Ярлык строки вызова: по нему агент понимает, ставить ли скобки."""
    kind = doc.get("element_kind") or ""
    if kind == "свойство":
        return strings.call_property
    if kind == "объект":
        return strings.call_object
    return strings.call


def _heading(doc: Dict[str, Any], strings: UiStrings) -> str:
    """«ТаблицаЗначений.НайтиСтроки — функция объекта ТаблицаЗначений»."""
    path = doc.get("full_path") or doc.get("name_ru") or doc.get("name") or ""
    kind = doc.get("element_kind") or ""
    owner = doc.get("object_ru") or doc.get("object") or ""
    kind_display = strings.element_kind_names.get(kind, kind)

    if kind in GLOBAL_KINDS and doc.get("type", "").startswith("global"):
        part = strings.heading_global.format(kind=kind_display)
    elif kind == "объект":
        part = strings.object_word
    elif kind and owner:
        part = strings.heading_of_object.format(kind=kind_display, owner=owner)
    else:
        part = kind_display

    return f"{path} — {part}" if part else path


def _parameter(param: Dict[str, Any], strings: UiStrings) -> List[str]:
    """Две строки: сигнатура параметра и его описание."""
    param_type = param.get("type") or strings.not_in_help
    required = param.get("required")
    if required is True:
        flag = strings.required
    elif required is False:
        flag = strings.optional
    else:
        flag = strings.requiredness_unknown

    lines = [f"    {param.get('name', '')} — {param_type}, {flag}"]
    if param.get("description"):
        lines.append(f"      {param['description']}")
    return lines


def _variant(variant: Dict[str, Any], with_name: bool, strings: UiStrings) -> List[str]:
    """Один вариант вызова со своими параметрами и своим описанием."""
    lines = []
    indent = ""
    if with_name and variant.get("variant"):
        lines.append(strings.variant_named.format(name=variant["variant"]))
        indent = "  "

    call = variant.get("call") or variant.get("syntax") or strings.not_in_help
    lines.append(f"{indent}{strings.call}: {call}")

    parameters = variant.get("parameters") or []
    if parameters:
        lines.append(f"{indent}{strings.parameters}")
        for param in parameters:
            lines.extend(f"{indent}{line}" for line in _parameter(param, strings))
    else:
        lines.append(f"{indent}{strings.no_parameters}")

    if variant.get("description"):
        lines.append(
            f"{indent}{strings.variant_description.format(text=variant['description'])}"
        )
    return lines


def _return_value(doc: Dict[str, Any], strings: UiStrings) -> List[str]:
    """Что вернёт вызов. Для процедуры — прямо сказать, что ничего."""
    variants = doc.get("variants") or []
    types = [v.get("return_type") for v in variants if v.get("return_type")]

    if not types:
        if doc.get("element_kind") == "процедура":
            return [strings.returns_nothing]
        return [strings.returns.format(value=strings.not_in_help)]

    lines = [strings.returns.format(value=types[0])]
    note = next(
        (v.get("return_description") for v in variants if v.get("return_description")),
        "",
    )
    if note:
        lines.append(f"  {note}")
    return lines


def _availability(doc: Dict[str, Any], strings: UiStrings) -> str:
    items = doc.get("availability") or []
    if not items:
        return strings.availability_unknown
    return strings.availability.format(items=", ".join(items))


def _examples(doc: Dict[str, Any], strings: UiStrings) -> List[str]:
    examples = doc.get("examples") or []
    if not examples:
        return [strings.no_examples]

    lines = [strings.example]
    for code in examples:
        lines.extend(f"  {line}" for line in code.split("\n"))
    return lines


def _availability_and_description(
    doc: Dict[str, Any], strings: UiStrings
) -> List[str]:
    """Хвост, общий у карточки элемента и карточки объекта."""
    lines = [_availability(doc, strings)]
    if doc.get("version_from"):
        lines.append(strings.available_since.format(version=doc["version_from"]))
    lines.append("")
    lines.append(strings.description.format(
        text=doc.get("description") or strings.description_missing
    ))
    return lines


def _property_body(doc: Dict[str, Any], strings: UiStrings) -> List[str]:
    return [
        f"{_call_label(doc, strings)}: "
        f"{doc.get('call_primary') or strings.not_in_help}",
        strings.value_type.format(value=doc.get("value_type") or strings.not_in_help),
        strings.access.format(value=doc.get("usage") or strings.not_in_help),
    ]


def _callable_body(doc: Dict[str, Any], strings: UiStrings) -> List[str]:
    """Варианты вызова элемента. Параметры печатаются всегда, даже пустые."""
    variants = doc.get("variants") or []
    lines = []

    if len(variants) > 1:
        lines.append(strings.variant_count.format(count=len(variants)))
        lines.append("")
    for variant in variants:
        lines.extend(_variant(variant, len(variants) > 1, strings))
        lines.append("")
    if not variants:
        lines.append(f"{strings.call}: {doc.get('call_primary') or strings.not_in_help}")
        lines.append(strings.no_parameters)

    lines.extend(_return_value(doc, strings))
    return lines


def render_element_card(doc: Dict[str, Any], strings: UiStrings = RU_STRINGS) -> str:
    """Полная карточка элемента.

    Объект отдаётся render_object_card без счётчиков: их собирает обработчик
    отдельными запросами, а вызов в обход обработчика честно скажет, что
    конструкторы не проверялись.
    """
    kind = doc.get("element_kind") or ""
    if kind == "объект":
        return render_object_card(doc, {}, strings=strings)

    body = _property_body(doc, strings) if kind == "свойство" \
        else _callable_body(doc, strings)

    lines = [_heading(doc, strings), ""]
    lines.extend(body)
    lines.extend(_availability_and_description(doc, strings))
    if doc.get("note"):
        lines.append(strings.note.format(text=doc["note"]))
    lines.extend(_examples(doc, strings))
    return "\n".join(lines)


def render_object_card(
    doc: Dict[str, Any],
    counts: Dict[str, int],
    constructors: Optional[List[str]] = None,
    key: Optional[str] = None,
    strings: UiStrings = RU_STRINGS,
) -> str:
    """Карточка объекта: без списков членов, но с их числом.

    `constructors=None` означает «не проверялись» и отличимо от пустого списка
    «проверено, конструкторов нет». `key` — имя, под которым члены лежат в
    индексе; по нему же посчитаны `counts`, поэтому он приходит аргументом, а
    не выводится здесь второй раз.
    """
    name = doc.get("full_path") or doc.get("name_ru") or ""
    key = key or name
    label = _call_label(doc, strings)

    lines = [f"{name} — {strings.object_word}", ""]
    if constructors:
        lines.append(f"{label}:")
        lines.extend(f"  {line}" for line in constructors)
    elif constructors is not None:
        lines.append(f"{label}: {strings.not_in_help}")
    else:
        lines.append(f"{label}: {strings.not_checked}")

    lines.extend(_availability_and_description(doc, strings))
    lines.extend(_composition(counts, key, strings))
    return "\n".join(lines)


def _composition(counts: Dict[str, int], key: str, strings: UiStrings) -> List[str]:
    """Счётчики состава и совет — перечень либо признание, что перечислять нечего."""
    if not counts:
        return []

    genitive = strings.member_names_genitive
    by_kind = [
        (genitive[group], counts.get(group, 0))
        for group in ("methods", "properties", "events")
    ]
    parts = ", ".join(f"{name}: {count}" for name, count in by_kind)

    lines = [strings.composition.format(parts=parts)]
    if sum(count for _, count in by_kind):
        lines.append(strings.listing_hint.format(key=key))
    else:
        lines.append(strings.nothing_to_list.format(key=key))
    return lines


def article_line(doc: Dict[str, Any], strings: UiStrings = RU_STRINGS) -> str:
    """Одна строка на статью: заголовок, вид и книга."""
    parts = [doc.get("name") or doc.get("name_ru") or ""]
    kind = doc.get("element_kind") or ""
    if kind:
        parts.append(f"— {strings.element_kind_names.get(kind, kind)}")
    book = doc.get("book") or ""
    if book:
        parts.append(f"— {strings.book_names.get(book, book)}")
    description = doc.get("description") or ""
    if description:
        parts.append(f"— {truncate_at_sentence(description, DESCRIPTION_LIMIT_IN_LIST)}")
    return " ".join(parts)


def render_article(doc: Dict[str, Any], strings: UiStrings = RU_STRINGS) -> str:
    """Статья целиком: заголовок, книга, текст."""
    book = doc.get("book") or ""
    heading = doc.get("name") or doc.get("name_ru") or ""
    lines = [strings.article_heading.format(name=heading)]
    if book:
        lines.append(strings.article_book.format(book=strings.book_names.get(book, book)))
    lines.append("")
    lines.append(doc.get("description") or strings.description_missing)
    return "\n".join(lines)


def article_candidate_list(
    name: str,
    candidates: List[Dict[str, Any]],
    total: int,
    strings: UiStrings = RU_STRINGS,
) -> str:
    """Заголовок нашёлся в нескольких книгах — назвать их и показать, как уточнить."""
    lines = [strings.article_ambiguous.format(name=name, total=total), ""]
    lines.extend(f"  {article_line(doc, strings)}" for doc in candidates)
    lines.append("")
    lines.append(strings.article_book_hint.format(name=name))
    return "\n".join(lines)


def list_line(doc: Dict[str, Any], strings: UiStrings = RU_STRINGS) -> str:
    """Одна строка на элемент — для выдачи поиска и состава объекта."""
    if (doc.get("type") or "") == DocumentType.ARTICLE.value:
        return article_line(doc, strings)

    path = doc.get("full_path") or doc.get("name_ru") or ""
    kind = doc.get("element_kind") or ""
    call = doc.get("call_primary") or ""
    variants = doc.get("variants") or []
    description = doc.get("description") or ""

    parts = [path]
    if kind:
        parts.append(f"— {strings.element_kind_names.get(kind, kind)}")
    if call and call != path:
        parts.append(f"— {call}")
    if len(variants) > 1:
        parts.append(strings.variant_count_short.format(count=len(variants)))
    if description:
        parts.append(
            f"— {truncate_at_sentence(description, DESCRIPTION_LIMIT_IN_LIST)}"
        )
    return " ".join(parts)


def hint_about_remainder(
    shown: int,
    total: int,
    tool_limit: int,
    call_template: str,
    strings: UiStrings = RU_STRINGS,
) -> str:
    """«Показано N из M» и достижимый способ добрать остальное.

    `call_template` содержит `{limit}`: подставляется предел, который инструмент
    примет, а не желаемое число.
    """
    limit = min(total, tool_limit)
    call = call_template.format(limit=limit)
    if limit < total:
        return strings.shown_of_total_capped.format(
            shown=shown, total=total, limit=limit, call=call
        )
    return strings.shown_of_total.format(shown=shown, total=total, call=call)


def _candidate_lines(
    candidates: List[Dict[str, Any]], full_order: bool, strings: UiStrings
) -> List[str]:
    lines = [f"  {list_line(doc, strings)}" for doc in candidates]
    if not full_order:
        lines.append(f"  {strings.partial_order_note}")
    lines.append("")
    return lines


def candidate_list(
    name: str,
    candidates: List[Dict[str, Any]],
    total: int,
    full_order: bool = True,
    strings: UiStrings = RU_STRINGS,
) -> str:
    """Ответ при омонимии: перечень вместо молчаливого выбора одного из многих."""
    lines = [
        strings.ambiguous_header.format(name=name, total=total),
        strings.ambiguous_hint.format(name=name),
        "",
        strings.candidates_header,
    ]
    lines.extend(_candidate_lines(candidates, full_order, strings))
    lines.append(hint_about_remainder(
        len(candidates), total, SEARCH_LIMIT_MAX,
        f'find_1c_help(query="{name}", limit={{limit}})',
        strings,
    ))
    return "\n".join(lines)


def elsewhere_list(
    name: str,
    obj: str,
    candidates: List[Dict[str, Any]],
    total: int,
    full_order: bool = True,
    strings: UiStrings = RU_STRINGS,
) -> str:
    """Ответ, когда у названного объекта элемента нет, а в справке он есть."""
    lines = [
        strings.element_not_in_object.format(object=obj, name=name),
        "",
        strings.found_elsewhere_header.format(total=total),
    ]
    lines.extend(_candidate_lines(candidates, full_order, strings))
    lines.append(strings.drop_object_hint.format(name=name, object=obj))
    return "\n".join(lines)


def member_list(
    obj: str,
    kind: str,
    methods: List[Dict[str, Any]],
    properties: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    total: int,
    tool_limit: int,
    strings: UiStrings = RU_STRINGS,
) -> str:
    """Состав объекта: та же строка списка, что и в выдаче поиска."""
    methods_label = strings.constructors_word if kind == "constructors" \
        else strings.methods_word
    shown = len(methods) + len(properties) + len(events)

    lines = [strings.members_header.format(obj=obj), ""]
    for heading, elements in (
        (methods_label, methods),
        (strings.properties_word, properties),
        (strings.events_word, events),
    ):
        if not elements:
            continue
        lines.append(f"{heading} ({len(elements)}):")
        lines.extend(f"  {list_line(doc, strings)}" for doc in elements)
        lines.append("")

    if total and total > shown:
        lines.append(hint_about_remainder(
            shown, total, tool_limit,
            f'list_1c_object_members(object="{obj}", members="{kind}", '
            f'limit={{limit}})',
            strings,
        ))
    lines.append(strings.full_card_hint.format(obj=obj))
    return "\n".join(lines)

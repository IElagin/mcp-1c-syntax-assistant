"""Карточка элемента справки 1С — единственное место сборки ответа.

Карточка отвечает на два вопроса агента: что вызывать и как вызывать. Поэтому
у неё фиксированный набор полей, и отсутствие данных помечается явно: пропуск
поля неотличим от «данных нет», и модель достраивает пробел домыслом. Раньше
рендер был размазан по mcp_formatter и search/formatter, причём в первом жили
два одноимённых format_quick_reference, второй из которых перекрывал первый.
"""

from typing import Any, Dict, List, Optional

from src.api.mcp_tools import SEARCH_LIMIT_MAX
from src.handlers.mcp_formatter import truncate_at_sentence
from src.handlers.ui_strings import RU_STRINGS, UiStrings

# Оставлен для обратной совместимости: некоторые тесты сравнивают вывод с этой
# константой напрямую. Значение живёт в таблице строк — здесь только ссылка,
# чтобы не заводить второй источник истины для одного и того же текста.
NOT_IN_HELP = RU_STRINGS.not_in_help

# Бюджет описания в строке списка. Замер по индексу: медиана описания 103
# знака, медиана первой фразы 65. При прежнем пределе 100 обрезалось 51.3%
# описаний — больше половины превью были неполными.
DESCRIPTION_LIMIT_IN_LIST = 140


def _call_label(doc: Dict[str, Any], strings: UiStrings) -> str:
    """Свойство не вызывают — к нему обращаются. Разные ярлыки не украшение:

    по ярлыку агент понимает, ставить ли скобки. Ключи здесь — русские
    значения element_kind, они не переводятся (см. модуль ui_strings).
    """
    kind = doc.get("element_kind") or ""
    if kind == "свойство":
        return strings.call_property
    if kind == "объект":
        return strings.call_object
    return strings.call


def _heading(doc: Dict[str, Any], strings: UiStrings) -> str:
    """«ТаблицаЗначений.НайтиСтроки — функция объекта ТаблицаЗначений».

    Английское имя в скобки сюда не идёт — ни в карточке метода, ни в
    карточке объекта. path и owner берутся из полей документа, которые уже
    на языке ответа (full_path/object_ru — при lang="en" в них лежит
    английский текст, потому что документ пришёл из английского индекса), а
    не собираются из двух языков сразу.
    """
    path = doc.get("full_path") or doc.get("name_ru") or doc.get("name") or ""
    kind = doc.get("element_kind") or ""
    owner = doc.get("object_ru") or doc.get("object") or ""
    kind_display = strings.element_kind_names.get(kind, kind)

    if kind in ("функция", "процедура", "событие") and doc.get("type", "").startswith("global"):
        part = strings.heading_global.format(kind=kind_display)
    elif kind == "объект":
        part = strings.object_word
    elif kind:
        part = strings.heading_of_object.format(kind=kind_display, owner=owner) if owner else kind_display
    else:
        part = ""

    return f"{path} — {part}" if part else path


def _parameter(p: Dict[str, Any], strings: UiStrings) -> List[str]:
    """Две строки: сигнатура параметра и его описание."""
    param_type = p.get("type") or strings.not_in_help
    required_flag = p.get("required")
    if required_flag is True:
        flag = strings.required
    elif required_flag is False:
        flag = strings.optional
    else:
        flag = strings.requiredness_unknown

    lines = [f"    {p.get('name', '')} — {param_type}, {flag}"]
    if p.get("description"):
        lines.append(f"      {p['description']}")
    return lines


def _variant(v: Dict[str, Any], with_name: bool, strings: UiStrings) -> List[str]:
    lines = []
    if with_name and v.get("variant"):
        lines.append(strings.variant_named.format(name=v["variant"]))
        indent = "  "
    else:
        indent = ""

    lines.append(f"{indent}{strings.call}: {v.get('call') or v.get('syntax') or strings.not_in_help}")

    params = v.get("parameters") or []
    if params:
        lines.append(f"{indent}{strings.parameters}")
        for p in params:
            lines.extend(f"{indent}{s}" for s in _parameter(p, strings))
    else:
        lines.append(f"{indent}{strings.no_parameters}")

    # «Описание варианта:» относится к этому конкретному варианту вызова, а
    # не к элементу целиком — у метода с несколькими вариантами описания
    # вариантов разные. Печать здесь, внутри _variant, а не слияние в
    # Documentation.description — по той же причине, по которой задача 1
    # перестала путать «Описание:» с «Описание варианта:» при разборе: склейка
    # в одно поле стирает то, что относится не ко всем вариантам.
    if v.get("description"):
        lines.append(f"{indent}{strings.variant_description.format(text=v['description'])}")

    return lines


def _return_value(doc: Dict[str, Any], strings: UiStrings) -> List[str]:
    """Что вернёт вызов. Для процедуры — прямо сказать, что ничего."""
    variant_list = doc.get("variants") or []
    types = [v.get("return_type") for v in variant_list if v.get("return_type")]

    if not types:
        if doc.get("element_kind") == "процедура":
            return [strings.returns_nothing]
        return [strings.returns.format(value=strings.not_in_help)]

    lines = [strings.returns.format(value=types[0])]
    note = next(
        (v.get("return_description") for v in variant_list if v.get("return_description")),
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


def render_element_card(doc: Dict[str, Any], strings: UiStrings = RU_STRINGS) -> str:
    """Полная карточка элемента."""
    if (doc.get("element_kind") or "") == "объект":
        # Полная карточка объекта требует данных, которых в его документе нет:
        # числа членов и строк вызова конструкторов. Их собирает обработчик
        # отдельными запросами и зовёт render_object_card напрямую — сюда
        # попадает только вызов в обход обработчика, и он честно говорит, что
        # конструкторы не проверялись, вместо «в справке не указано».
        return render_object_card(doc, {}, strings=strings)

    lines = [_heading(doc, strings), ""]

    if (doc.get("element_kind") or "") == "свойство":
        lines.append(f"{_call_label(doc, strings)}: {doc.get('call_primary') or strings.not_in_help}")
        lines.append(strings.value_type.format(value=doc.get("value_type") or strings.not_in_help))
        lines.append(strings.access.format(value=doc.get("usage") or strings.not_in_help))
    else:
        variant_list = doc.get("variants") or []
        if len(variant_list) > 1:
            lines.append(strings.variant_count.format(count=len(variant_list)))
            lines.append("")
        for v in variant_list:
            lines.extend(_variant(v, len(variant_list) > 1, strings))
            lines.append("")
        if not variant_list:
            lines.append(f"{strings.call}: {doc.get('call_primary') or strings.not_in_help}")
            # Параметры — поле из списка «всегда печатаются»: пустые variants
            # не повод его пропускать, иначе молчание неотличимо от «данных нет».
            lines.append(strings.no_parameters)
        lines.extend(_return_value(doc, strings))

    lines.append(_availability(doc, strings))
    if doc.get("version_from"):
        lines.append(strings.available_since.format(version=doc["version_from"]))

    lines.append("")
    lines.append(strings.description.format(text=doc.get("description") or strings.description_missing))
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
    """Карточка самого объекта: без списков членов, но с их числом.

    Членов у объекта бывают сотни, и обрезанный список вернул бы ту же
    молчаливую неполноту, от которой мы уходим. Поэтому — число и прямое
    указание, чем получить перечень.

    constructors приходят отдельным аргументом, потому что в самом документе
    объекта их нет: конструктор в справке — отдельная страница
    (type="object_constructor"), и variants у всех 2 506 документов объектов
    пусты. Раньше карточка читала эти пустые variants и печатала «Конструкторы:
    в справке не указано» — у 307 объектов, конструкторы которых лежат в
    индексе, это была неправда, а неправда хуже молчания.

    None означает «не проверялись» и отличим от пустого списка «проверено,
    конструкторов нет»: утверждать второе, не спросив индекс, — ровно тот
    дефект, ради которого написана эта ветка.

    key — имя, под которым члены объекта лежат в индексе; по нему же
    посчитаны counts. Он приходит аргументом, а не выводится здесь второй
    раз из полей документа: счётчики и совет обязаны опираться на одно и то же
    значение, иначе карточка через строку противоречит сама себе — печатает
    «свойств: 0» по одному ключу и перечень по другому.
    """
    name = doc.get("full_path") or doc.get("name_ru") or ""
    key = key or name
    lines = [f"{name} — {strings.object_word}", ""]

    label = _call_label(doc, strings)
    if constructors:
        lines.append(f"{label}:")
        lines.extend(f"  {k}" for k in constructors)
    elif constructors is not None:
        lines.append(f"{label}: {strings.not_in_help}")
    else:
        # label собирается тем же _call_label, что и в двух ветках выше, а не
        # берётся готовой строкой из strings — так рендер не опирается на то,
        # что render_object_card вызывают только для element_kind="объект":
        # даже если бы это оказалось не так, все три ветки остались бы
        # согласованы между собой.
        lines.append(f"{label}: {strings.not_checked}")

    lines.append(_availability(doc, strings))
    if doc.get("version_from"):
        lines.append(strings.available_since.format(version=doc["version_from"]))

    lines.append("")
    lines.append(strings.description.format(text=doc.get("description") or strings.description_missing))

    if counts:
        genitive = strings.member_names_genitive
        by_kind = (
            (genitive["methods"], counts.get("methods", 0)),
            (genitive["properties"], counts.get("properties", 0)),
            (genitive["events"], counts.get("events", 0)),
        )
        parts = ", ".join(f"{kind_name}: {count}" for kind_name, count in by_kind)
        lines.append(strings.composition.format(parts=parts))

        if sum(count for _, count in by_kind):
            lines.append(strings.listing_hint.format(key=key))
        else:
            # Совет печатается ровно тогда, когда под тем же ключом есть что
            # перечислять. У 100 страниц справки (параметры формы вроде
            # «Расширение формы клиентского приложения для документа.Ключ»)
            # заголовок разобран как объект, но членов у него нет и само имя не
            # встречается ни в одном поле object — совет по нему отвечал
            # «объект в справке не найден». Подставить вместо него родителя
            # нельзя: его методы и свойства принадлежат не этой странице, и
            # выдать их за её состав значило бы заменить тупик на неправду.
            lines.append(strings.nothing_to_list.format(key=key))

    return "\n".join(lines)


def list_line(doc: Dict[str, Any], strings: UiStrings = RU_STRINGS) -> str:
    """Одна строка на элемент — для выдачи поиска и состава объекта."""
    path = doc.get("full_path") or doc.get("name_ru") or ""
    kind = doc.get("element_kind") or ""
    call = doc.get("call_primary") or ""

    parts = [path]
    if kind:
        parts.append(f"— {strings.element_kind_names.get(kind, kind)}")
    if call and call != path:
        parts.append(f"— {call}")

    variant_list = doc.get("variants") or []
    if len(variant_list) > 1:
        parts.append(strings.variant_count_short.format(count=len(variant_list)))

    description = doc.get("description") or ""
    if description:
        parts.append(f"— {truncate_at_sentence(description, DESCRIPTION_LIMIT_IN_LIST)}")

    return " ".join(parts)


def hint_about_remainder(
    shown: int, total: int, tool_limit: int, call_template: str, strings: UiStrings = RU_STRINGS
) -> str:
    """«Показано N из M» и выполнимый способ добрать остальное.

    Совет «повторите вызов с limit=M за остальными» обещал невозможное: у
    инструментов нет параметра смещения, поэтому повтор возвращает те же первые
    элементы заново, а сам M вдобавок мог превышать потолок схемы. Правдивая
    формулировка — сколько показано, каков предел за один вызов и какой именно
    вызов его выбирает. call_template содержит {limit}: подставляется
    достижимое число, а не желаемое.
    """
    limit = min(total, tool_limit)
    call = call_template.format(limit=limit)
    if limit < total:
        return strings.shown_of_total_capped.format(shown=shown, total=total, limit=limit, call=call)
    return strings.shown_of_total.format(shown=shown, total=total, call=call)


def candidate_list(
    name: str,
    candidates: List[Dict[str, Any]],
    total: int,
    full_order: bool = True,
    strings: UiStrings = RU_STRINGS,
) -> str:
    """Ответ при омонимии: перечень вместо молчаливого выбора одного из многих.

    Заголовок называет порядок, а не обещает вероятность. Прежние «Наиболее
    вероятные» были заявкой на ранжирование, которого не было: окно из 50
    документов набиралось фильтрующим запросом с одинаковыми оценками, то есть
    произвольно, и сортировалось по алфавиту — для «Количество» первым шёл
    АгрегатыРегистраНакопления, а ТаблицаЗначений не показывался вовсе.
    """
    lines = [
        strings.ambiguous_header.format(name=name, total=total),
        strings.ambiguous_hint.format(name=name),
        "",
        strings.candidates_header,
    ]
    lines.extend(f"  {list_line(k, strings)}" for k in candidates)
    if not full_order:
        lines.append(f"  {strings.partial_order_note}")
    lines.append("")

    # find_1c_help не примет limit больше SEARCH_LIMIT_MAX — совет с
    # limit=total при омонимах вроде «Количество» (275 совпадений) сам
    # упирался бы в validation error схемы, которую эта же задача вводит.
    lines.append(hint_about_remainder(
        len(candidates), total, SEARCH_LIMIT_MAX,
        f'find_1c_help(query="{name}", limit={{limit}})',
        strings,
    ))
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
    """Состав объекта: та же строка списка, что и в выдаче поиска.

    Раньше состав собирался вторым, независимым форматтером в mcp_formatter, и
    тот остался привязан к удалённому полю syntax_ru: строки вызова не было ни
    у одного элемента, а у конструкторов ответ сводился к голому «По
    умолчанию», из которого никак не следует, что писать надо «Новый
    ТаблицаЗначений». Спека настаивает на единственном месте сборки ответа —
    оно здесь.
    """
    methods_label = strings.constructors_word if kind == "constructors" else strings.methods_word
    shown = len(methods) + len(properties) + len(events)

    lines = [strings.members_header.format(obj=obj), ""]
    for heading, elements in (
        (methods_label, methods), (strings.properties_word, properties), (strings.events_word, events)
    ):
        if not elements:
            continue
        lines.append(f"{heading} ({len(elements)}):")
        lines.extend(f"  {list_line(d, strings)}" for d in elements)
        lines.append("")

    # Молчаливая неполнота — худшее, что может отдать справочный инструмент:
    # агент примет урезанный список за исчерпывающий и решит, что метода нет.
    if total and total > shown:
        lines.append(hint_about_remainder(
            shown, total, tool_limit,
            f'list_1c_object_members(object="{obj}", members="{kind}", '
            f'limit={{limit}})',
            strings,
        ))
    lines.append(strings.full_card_hint.format(obj=obj))
    return "\n".join(lines)

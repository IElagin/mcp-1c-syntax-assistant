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

NOT_IN_HELP = "в справке не указано"

# Бюджет описания в строке списка. Замер по индексу: медиана описания 103
# знака, медиана первой фразы 65. При прежнем пределе 100 обрезалось 51.3%
# описаний — больше половины превью были неполными.
DESCRIPTION_LIMIT_IN_LIST = 140

# Свойство не вызывают — к нему обращаются. Разные ярлыки не украшение:
# по ярлыку агент понимает, ставить ли скобки.
CALL_LABEL = {"свойство": "Обращение", "объект": "Конструкторы"}


def _call_label(doc: Dict[str, Any]) -> str:
    return CALL_LABEL.get(doc.get("element_kind") or "", "Вызов")


def _heading(doc: Dict[str, Any]) -> str:
    """«ТаблицаЗначений.НайтиСтроки (ValueTable.FindRows) — функция объекта»."""
    path = doc.get("full_path") or doc.get("name_ru") or doc.get("name") or ""
    kind = doc.get("element_kind") or ""
    owner = doc.get("object_ru") or doc.get("object") or ""

    if kind in ("функция", "процедура", "событие") and doc.get("type", "").startswith("global"):
        part = f"{kind} глобального контекста"
    elif kind == "объект":
        part = "объект"
    elif kind:
        part = f"{kind} объекта {owner}" if owner else kind
    else:
        part = ""

    return f"{path} — {part}" if part else path


def _parameter(p: Dict[str, Any]) -> List[str]:
    """Две строки: сигнатура параметра и его описание."""
    param_type = p.get("type") or NOT_IN_HELP
    required_flag = p.get("required")
    if required_flag is True:
        flag = "обязательный"
    elif required_flag is False:
        flag = "необязательный"
    else:
        flag = "обязательность в справке не указана"

    lines = [f"    {p.get('name', '')} — {param_type}, {flag}"]
    if p.get("description"):
        lines.append(f"      {p['description']}")
    return lines


def _variant(v: Dict[str, Any], with_name: bool) -> List[str]:
    lines = []
    if with_name and v.get("variant"):
        lines.append(f"Вариант «{v['variant']}»")
        indent = "  "
    else:
        indent = ""

    lines.append(f"{indent}Вызов: {v.get('call') or v.get('syntax') or NOT_IN_HELP}")

    params = v.get("parameters") or []
    if params:
        lines.append(f"{indent}Параметры:")
        for p in params:
            lines.extend(f"{indent}{s}" for s in _parameter(p))
    else:
        lines.append(f"{indent}Параметры: нет")

    # «Описание варианта метода:» относится к этому конкретному варианту
    # вызова, а не к элементу целиком — у метода с несколькими вариантами
    # описания вариантов разные. Печать здесь, внутри _variant, а не слияние
    # в Documentation.description — по той же причине, по которой задача 1
    # перестала путать «Описание:» с «Описание варианта метода:» при разборе:
    # склейка в одно поле стирает то, что относится не ко всем вариантам.
    if v.get("description"):
        lines.append(f"{indent}Описание варианта: {v['description']}")

    return lines


def _return_value(doc: Dict[str, Any]) -> List[str]:
    """Что вернёт вызов. Для процедуры — прямо сказать, что ничего."""
    variant_list = doc.get("variants") or []
    types = [v.get("return_type") for v in variant_list if v.get("return_type")]

    if not types:
        if doc.get("element_kind") == "процедура":
            return ["Возвращает: нет (процедура)"]
        return [f"Возвращает: {NOT_IN_HELP}"]

    lines = [f"Возвращает: {types[0]}"]
    note = next(
        (v.get("return_description") for v in variant_list if v.get("return_description")),
        "",
    )
    if note:
        lines.append(f"  {note}")
    return lines


def _availability(doc: Dict[str, Any]) -> str:
    items = doc.get("availability") or []
    if not items:
        return "Доступность: в справке не указана"
    return "Доступность: " + ", ".join(items)


def _examples(doc: Dict[str, Any]) -> List[str]:
    examples = doc.get("examples") or []
    if not examples:
        return ["Примеров в справке нет."]

    lines = ["Пример:"]
    for code in examples:
        lines.extend(f"  {line}" for line in code.split("\n"))
    return lines


def render_element_card(doc: Dict[str, Any]) -> str:
    """Полная карточка элемента."""
    if (doc.get("element_kind") or "") == "объект":
        # Полная карточка объекта требует данных, которых в его документе нет:
        # числа членов и строк вызова конструкторов. Их собирает обработчик
        # отдельными запросами и зовёт render_object_card напрямую — сюда
        # попадает только вызов в обход обработчика, и он честно говорит, что
        # конструкторы не проверялись, вместо «в справке не указано».
        return render_object_card(doc, {})

    lines = [_heading(doc), ""]

    if (doc.get("element_kind") or "") == "свойство":
        lines.append(f"{_call_label(doc)}: {doc.get('call_primary') or NOT_IN_HELP}")
        lines.append(f"Тип значения: {doc.get('value_type') or NOT_IN_HELP}")
        lines.append(f"Доступ: {doc.get('usage') or NOT_IN_HELP}")
    else:
        variant_list = doc.get("variants") or []
        if len(variant_list) > 1:
            lines.append(f"Вариантов вызова: {len(variant_list)}")
            lines.append("")
        for v in variant_list:
            lines.extend(_variant(v, with_name=len(variant_list) > 1))
            lines.append("")
        if not variant_list:
            lines.append(f"Вызов: {doc.get('call_primary') or NOT_IN_HELP}")
            # Параметры — поле из списка «всегда печатаются»: пустые variants
            # не повод его пропускать, иначе молчание неотличимо от «данных нет».
            lines.append("Параметры: нет")
        lines.extend(_return_value(doc))

    lines.append(_availability(doc))
    if doc.get("version_from"):
        lines.append(f"Доступно с: {doc['version_from']}")

    lines.append("")
    lines.append(f"Описание: {doc.get('description') or 'в справке отсутствует'}")
    if doc.get("note"):
        lines.append(f"Примечание: {doc['note']}")
    lines.extend(_examples(doc))

    return "\n".join(lines)


def render_object_card(
    doc: Dict[str, Any],
    counts: Dict[str, int],
    constructors: Optional[List[str]] = None,
    key: Optional[str] = None,
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
    lines = [f"{name} — объект", ""]

    label = _call_label(doc)
    if constructors:
        lines.append(f"{label}:")
        lines.extend(f"  {k}" for k in constructors)
    elif constructors is not None:
        lines.append(f"{label}: {NOT_IN_HELP}")
    else:
        lines.append(f"{label}: не проверялись")

    lines.append(_availability(doc))
    if doc.get("version_from"):
        lines.append(f"Доступно с: {doc['version_from']}")

    lines.append("")
    lines.append(f"Описание: {doc.get('description') or 'в справке отсутствует'}")

    if counts:
        by_kind = (
            ("методов", counts.get("methods", 0)),
            ("свойств", counts.get("properties", 0)),
            ("событий", counts.get("events", 0)),
        )
        parts = ", ".join(f"{kind_name}: {count}" for kind_name, count in by_kind)
        lines.append(f"Состав — {parts}.")

        if sum(count for _, count in by_kind):
            lines.append(f'Перечень: list_1c_object_members(object="{key}")')
        else:
            # Совет печатается ровно тогда, когда под тем же ключом есть что
            # перечислять. У 100 страниц справки (параметры формы вроде
            # «Расширение формы клиентского приложения для документа.Ключ»)
            # заголовок разобран как объект, но членов у него нет и само имя не
            # встречается ни в одном поле object — совет по нему отвечал
            # «объект в справке не найден». Подставить вместо него родителя
            # нельзя: его методы и свойства принадлежат не этой странице, и
            # выдать их за её состав значило бы заменить тупик на неправду.
            lines.append(
                f"Перечень: запрашивать нечего — под именем «{key}» в справке "
                "нет ни одного метода, свойства или события."
            )

    return "\n".join(lines)


def list_line(doc: Dict[str, Any]) -> str:
    """Одна строка на элемент — для выдачи поиска и состава объекта."""
    path = doc.get("full_path") or doc.get("name_ru") or ""
    kind = doc.get("element_kind") or ""
    call = doc.get("call_primary") or ""

    parts = [path]
    if kind:
        parts.append(f"— {kind}")
    if call and call != path:
        parts.append(f"— {call}")

    variant_list = doc.get("variants") or []
    if len(variant_list) > 1:
        parts.append(f"(вариантов вызова: {len(variant_list)})")

    description = doc.get("description") or ""
    if description:
        parts.append(f"— {truncate_at_sentence(description, DESCRIPTION_LIMIT_IN_LIST)}")

    return " ".join(parts)


def hint_about_remainder(
    shown: int, total: int, tool_limit: int, call_template: str
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
        return (
            f"Показано {shown} из {total}. За один вызов можно получить "
            f"не более {limit}: {call}."
        )
    return f"Показано {shown} из {total}. Полный список: {call}."


def candidate_list(
    name: str,
    candidates: List[Dict[str, Any]],
    total: int,
    full_order: bool = True,
) -> str:
    """Ответ при омонимии: перечень вместо молчаливого выбора одного из многих.

    Заголовок называет порядок, а не обещает вероятность. Прежние «Наиболее
    вероятные» были заявкой на ранжирование, которого не было: окно из 50
    документов набиралось фильтрующим запросом с одинаковыми оценками, то есть
    произвольно, и сортировалось по алфавиту — для «Количество» первым шёл
    АгрегатыРегистраНакопления, а ТаблицаЗначений не показывался вовсе.
    """
    lines = [
        f"Имя «{name}» найдено у {total} элементов — "
        f"карточка не может быть выбрана однозначно.",
        f'Уточните объект: get_1c_element(name="{name}", object="<объект>")',
        "",
        "Кандидаты (сначала типы языка, внутри — объекты с бо́льшим числом "
        "элементов в справке):",
    ]
    lines.extend(f"  {list_line(k)}" for k in candidates)
    if not full_order:
        lines.append(
            "  (порядок построен не по всем совпадениям — их слишком много "
            "для одного запроса)"
        )
    lines.append("")

    # find_1c_help не примет limit больше SEARCH_LIMIT_MAX — совет с
    # limit=total при омонимах вроде «Количество» (275 совпадений) сам
    # упирался бы в validation error схемы, которую эта же задача вводит.
    lines.append(hint_about_remainder(
        len(candidates), total, SEARCH_LIMIT_MAX,
        f'find_1c_help(query="{name}", limit={{limit}})',
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
) -> str:
    """Состав объекта: та же строка списка, что и в выдаче поиска.

    Раньше состав собирался вторым, независимым форматтером в mcp_formatter, и
    тот остался привязан к удалённому полю syntax_ru: строки вызова не было ни
    у одного элемента, а у конструкторов ответ сводился к голому «По
    умолчанию», из которого никак не следует, что писать надо «Новый
    ТаблицаЗначений». Спека настаивает на единственном месте сборки ответа —
    оно здесь.
    """
    methods_label = "Конструкторы" if kind == "constructors" else "Методы"
    shown = len(methods) + len(properties) + len(events)

    lines = [f"Состав объекта {obj}.", ""]
    for heading, elements in (
        (methods_label, methods), ("Свойства", properties), ("События", events)
    ):
        if not elements:
            continue
        lines.append(f"{heading} ({len(elements)}):")
        lines.extend(f"  {list_line(d)}" for d in elements)
        lines.append("")

    # Молчаливая неполнота — худшее, что может отдать справочный инструмент:
    # агент примет урезанный список за исчерпывающий и решит, что метода нет.
    if total and total > shown:
        lines.append(hint_about_remainder(
            shown, total, tool_limit,
            f'list_1c_object_members(object="{obj}", members="{kind}", '
            f'limit={{limit}})',
        ))
    lines.append(f'Полная карточка: get_1c_element(name=…, object="{obj}")')
    return "\n".join(lines)

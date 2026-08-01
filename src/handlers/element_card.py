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

NET_V_SPRAVKE = "в справке не указано"

# Бюджет описания в строке списка. Замер по индексу: медиана описания 103
# знака, медиана первой фразы 65. При прежнем пределе 100 обрезалось 51.3%
# описаний — больше половины превью были неполными.
PREDEL_OPISANIYA_V_SPISKE = 140

# Свойство не вызывают — к нему обращаются. Разные ярлыки не украшение:
# по ярлыку агент понимает, ставить ли скобки.
YARLYK_VYZOVA = {"свойство": "Обращение", "объект": "Конструкторы"}


def _yarlyk_vyzova(doc: Dict[str, Any]) -> str:
    return YARLYK_VYZOVA.get(doc.get("element_kind") or "", "Вызов")


def _zagolovok(doc: Dict[str, Any]) -> str:
    """«ТаблицаЗначений.НайтиСтроки (ValueTable.FindRows) — функция объекта»."""
    put = doc.get("full_path") or doc.get("name_ru") or doc.get("name") or ""
    vid = doc.get("element_kind") or ""
    vladelets = doc.get("object_ru") or doc.get("object") or ""

    if vid in ("функция", "процедура", "событие") and doc.get("type", "").startswith("global"):
        part = f"{vid} глобального контекста"
    elif vid == "объект":
        part = "объект"
    elif vid:
        part = f"{vid} объекта {vladelets}" if vladelets else vid
    else:
        part = ""

    return f"{put} — {part}" if part else put


def _parametr(p: Dict[str, Any]) -> List[str]:
    """Две строки: сигнатура параметра и его описание."""
    param_type = p.get("type") or NET_V_SPRAVKE
    obyazatelnost = p.get("required")
    if obyazatelnost is True:
        flag = "обязательный"
    elif obyazatelnost is False:
        flag = "необязательный"
    else:
        flag = "обязательность в справке не указана"

    lines = [f"    {p.get('name', '')} — {param_type}, {flag}"]
    if p.get("description"):
        lines.append(f"      {p['description']}")
    return lines


def _variant(v: Dict[str, Any], s_imenem: bool) -> List[str]:
    lines = []
    if s_imenem and v.get("variant"):
        lines.append(f"Вариант «{v['variant']}»")
        indent = "  "
    else:
        indent = ""

    lines.append(f"{indent}Вызов: {v.get('call') or v.get('syntax') or NET_V_SPRAVKE}")

    parametry = v.get("parameters") or []
    if parametry:
        lines.append(f"{indent}Параметры:")
        for p in parametry:
            lines.extend(f"{indent}{s}" for s in _parametr(p))
    else:
        lines.append(f"{indent}Параметры: нет")

    return lines


def _vozvrat(doc: Dict[str, Any]) -> List[str]:
    """Что вернёт вызов. Для процедуры — прямо сказать, что ничего."""
    variant_list = doc.get("variants") or []
    tipy = [v.get("return_type") for v in variant_list if v.get("return_type")]

    if not tipy:
        if doc.get("element_kind") == "процедура":
            return ["Возвращает: нет (процедура)"]
        return [f"Возвращает: {NET_V_SPRAVKE}"]

    lines = [f"Возвращает: {tipy[0]}"]
    note = next(
        (v.get("return_description") for v in variant_list if v.get("return_description")),
        "",
    )
    if note:
        lines.append(f"  {note}")
    return lines


def _dostupnost(doc: Dict[str, Any]) -> str:
    items = doc.get("availability") or []
    if not items:
        return "Доступность: в справке не указана"
    return "Доступность: " + ", ".join(items)


def _primery(doc: Dict[str, Any]) -> List[str]:
    primery = doc.get("examples") or []
    if not primery:
        return ["Примеров в справке нет."]

    lines = ["Пример:"]
    for kod in primery:
        lines.extend(f"  {line}" for line in kod.split("\n"))
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

    lines = [_zagolovok(doc), ""]

    if (doc.get("element_kind") or "") == "свойство":
        lines.append(f"{_yarlyk_vyzova(doc)}: {doc.get('call_primary') or NET_V_SPRAVKE}")
        lines.append(f"Тип значения: {doc.get('value_type') or NET_V_SPRAVKE}")
        lines.append(f"Доступ: {doc.get('usage') or NET_V_SPRAVKE}")
    else:
        variant_list = doc.get("variants") or []
        if len(variant_list) > 1:
            lines.append(f"Вариантов вызова: {len(variant_list)}")
            lines.append("")
        for v in variant_list:
            lines.extend(_variant(v, s_imenem=len(variant_list) > 1))
            lines.append("")
        if not variant_list:
            lines.append(f"Вызов: {doc.get('call_primary') or NET_V_SPRAVKE}")
            # Параметры — поле из списка «всегда печатаются»: пустые variants
            # не повод его пропускать, иначе молчание неотличимо от «данных нет».
            lines.append("Параметры: нет")
        lines.extend(_vozvrat(doc))

    lines.append(_dostupnost(doc))
    if doc.get("version_from"):
        lines.append(f"Доступно с: {doc['version_from']}")

    lines.append("")
    lines.append(f"Описание: {doc.get('description') or 'в справке отсутствует'}")
    if doc.get("note"):
        lines.append(f"Примечание: {doc['note']}")
    lines.extend(_primery(doc))

    return "\n".join(lines)


def render_object_card(
    doc: Dict[str, Any],
    kolichestva: Dict[str, int],
    konstruktory: Optional[List[str]] = None,
    klyuch: Optional[str] = None,
) -> str:
    """Карточка самого объекта: без списков членов, но с их числом.

    Членов у объекта бывают сотни, и обрезанный список вернул бы ту же
    молчаливую неполноту, от которой мы уходим. Поэтому — число и прямое
    указание, чем получить перечень.

    konstruktory приходят отдельным аргументом, потому что в самом документе
    объекта их нет: конструктор в справке — отдельная страница
    (type="object_constructor"), и variants у всех 2 506 документов объектов
    пусты. Раньше карточка читала эти пустые variants и печатала «Конструкторы:
    в справке не указано» — у 307 объектов, конструкторы которых лежат в
    индексе, это была неправда, а неправда хуже молчания.

    None означает «не проверялись» и отличим от пустого списка «проверено,
    конструкторов нет»: утверждать второе, не спросив индекс, — ровно тот
    дефект, ради которого написана эта ветка.

    klyuch — имя, под которым члены объекта лежат в индексе; по нему же
    посчитаны kolichestva. Он приходит аргументом, а не выводится здесь второй
    раз из полей документа: счётчики и совет обязаны опираться на одно и то же
    значение, иначе карточка через строку противоречит сама себе — печатает
    «свойств: 0» по одному ключу и перечень по другому.
    """
    name = doc.get("full_path") or doc.get("name_ru") or ""
    klyuch = klyuch or name
    lines = [f"{name} — объект", ""]

    yarlyk = _yarlyk_vyzova(doc)
    if konstruktory:
        lines.append(f"{yarlyk}:")
        lines.extend(f"  {k}" for k in konstruktory)
    elif konstruktory is not None:
        lines.append(f"{yarlyk}: {NET_V_SPRAVKE}")
    else:
        lines.append(f"{yarlyk}: не проверялись")

    lines.append(_dostupnost(doc))
    if doc.get("version_from"):
        lines.append(f"Доступно с: {doc['version_from']}")

    lines.append("")
    lines.append(f"Описание: {doc.get('description') or 'в справке отсутствует'}")

    if kolichestva:
        po_vidam = (
            ("методов", kolichestva.get("methods", 0)),
            ("свойств", kolichestva.get("properties", 0)),
            ("событий", kolichestva.get("events", 0)),
        )
        parts = ", ".join(f"{nazvanie}: {chislo}" for nazvanie, chislo in po_vidam)
        lines.append(f"Состав — {parts}.")

        if sum(chislo for _, chislo in po_vidam):
            lines.append(f'Перечень: list_1c_object_members(object="{klyuch}")')
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
                f"Перечень: запрашивать нечего — под именем «{klyuch}» в справке "
                "нет ни одного метода, свойства или события."
            )

    return "\n".join(lines)


def stroka_spiska(doc: Dict[str, Any]) -> str:
    """Одна строка на элемент — для выдачи поиска и состава объекта."""
    put = doc.get("full_path") or doc.get("name_ru") or ""
    vid = doc.get("element_kind") or ""
    vyzov = doc.get("call_primary") or ""

    parts = [put]
    if vid:
        parts.append(f"— {vid}")
    if vyzov and vyzov != put:
        parts.append(f"— {vyzov}")

    variant_list = doc.get("variants") or []
    if len(variant_list) > 1:
        parts.append(f"(вариантов вызова: {len(variant_list)})")

    opisanie = doc.get("description") or ""
    if opisanie:
        parts.append(f"— {truncate_at_sentence(opisanie, PREDEL_OPISANIYA_V_SPISKE)}")

    return " ".join(parts)


def sovet_ob_ostatke(
    pokazano: int, vsego: int, predel_instrumenta: int, shablon_vyzova: str
) -> str:
    """«Показано N из M» и выполнимый способ добрать остальное.

    Совет «повторите вызов с limit=M за остальными» обещал невозможное: у
    инструментов нет параметра смещения, поэтому повтор возвращает те же первые
    элементы заново, а сам M вдобавок мог превышать потолок схемы. Правдивая
    формулировка — сколько показано, каков предел за один вызов и какой именно
    вызов его выбирает. shablon_vyzova содержит {limit}: подставляется
    достижимое число, а не желаемое.
    """
    limit = min(vsego, predel_instrumenta)
    vyzov = shablon_vyzova.format(limit=limit)
    if limit < vsego:
        return (
            f"Показано {pokazano} из {vsego}. За один вызов можно получить "
            f"не более {limit}: {vyzov}."
        )
    return f"Показано {pokazano} из {vsego}. Полный список: {vyzov}."


def spisok_kandidatov(
    name: str,
    kandidaty: List[Dict[str, Any]],
    vsego: int,
    poryadok_polnyy: bool = True,
) -> str:
    """Ответ при омонимии: перечень вместо молчаливого выбора одного из многих.

    Заголовок называет порядок, а не обещает вероятность. Прежние «Наиболее
    вероятные» были заявкой на ранжирование, которого не было: окно из 50
    документов набиралось фильтрующим запросом с одинаковыми оценками, то есть
    произвольно, и сортировалось по алфавиту — для «Количество» первым шёл
    АгрегатыРегистраНакопления, а ТаблицаЗначений не показывался вовсе.
    """
    lines = [
        f"Имя «{name}» найдено у {vsego} элементов — "
        f"карточка не может быть выбрана однозначно.",
        f'Уточните объект: get_1c_element(name="{name}", object="<объект>")',
        "",
        "Кандидаты (сначала типы языка, внутри — объекты с бо́льшим числом "
        "элементов в справке):",
    ]
    lines.extend(f"  {stroka_spiska(k)}" for k in kandidaty)
    if not poryadok_polnyy:
        lines.append(
            "  (порядок построен не по всем совпадениям — их слишком много "
            "для одного запроса)"
        )
    lines.append("")

    # find_1c_help не примет limit больше SEARCH_LIMIT_MAX — совет с
    # limit=vsego при омонимах вроде «Количество» (275 совпадений) сам
    # упирался бы в validation error схемы, которую эта же задача вводит.
    lines.append(sovet_ob_ostatke(
        len(kandidaty), vsego, SEARCH_LIMIT_MAX,
        f'find_1c_help(query="{name}", limit={{limit}})',
    ))
    return "\n".join(lines)


def spisok_chlenov(
    obekt: str,
    vid: str,
    metody: List[Dict[str, Any]],
    svoystva: List[Dict[str, Any]],
    sobytiya: List[Dict[str, Any]],
    vsego: int,
    predel_instrumenta: int,
) -> str:
    """Состав объекта: та же строка списка, что и в выдаче поиска.

    Раньше состав собирался вторым, независимым форматтером в mcp_formatter, и
    тот остался привязан к удалённому полю syntax_ru: строки вызова не было ни
    у одного элемента, а у конструкторов ответ сводился к голому «По
    умолчанию», из которого никак не следует, что писать надо «Новый
    ТаблицаЗначений». Спека настаивает на единственном месте сборки ответа —
    оно здесь.
    """
    yarlyk_metodov = "Конструкторы" if vid == "constructors" else "Методы"
    pokazano = len(metody) + len(svoystva) + len(sobytiya)

    lines = [f"Состав объекта {obekt}.", ""]
    for heading, elementy in (
        (yarlyk_metodov, metody), ("Свойства", svoystva), ("События", sobytiya)
    ):
        if not elementy:
            continue
        lines.append(f"{heading} ({len(elementy)}):")
        lines.extend(f"  {stroka_spiska(d)}" for d in elementy)
        lines.append("")

    # Молчаливая неполнота — худшее, что может отдать справочный инструмент:
    # агент примет урезанный список за исчерпывающий и решит, что метода нет.
    if vsego and vsego > pokazano:
        lines.append(sovet_ob_ostatke(
            pokazano, vsego, predel_instrumenta,
            f'list_1c_object_members(object="{obekt}", members="{vid}", '
            f'limit={{limit}})',
        ))
    lines.append(f'Полная карточка: get_1c_element(name=…, object="{obekt}")')
    return "\n".join(lines)

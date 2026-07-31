"""Карточка элемента справки 1С — единственное место сборки ответа.

Карточка отвечает на два вопроса агента: что вызывать и как вызывать. Поэтому
у неё фиксированный набор полей, и отсутствие данных помечается явно: пропуск
поля неотличим от «данных нет», и модель достраивает пробел домыслом. Раньше
рендер был размазан по mcp_formatter и search/formatter, причём в первом жили
два одноимённых format_quick_reference, второй из которых перекрывал первый.
"""

from typing import Any, Dict, List, Optional

from src.api.mcp_tools import LIMIT_POISKA_MAX
from src.handlers.mcp_formatter import obrezat_do_frazy

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
        chast = f"{vid} глобального контекста"
    elif vid == "объект":
        chast = "объект"
    elif vid:
        chast = f"{vid} объекта {vladelets}" if vladelets else vid
    else:
        chast = ""

    return f"{put} — {chast}" if chast else put


def _parametr(p: Dict[str, Any]) -> List[str]:
    """Две строки: сигнатура параметра и его описание."""
    tip = p.get("type") or NET_V_SPRAVKE
    obyazatelnost = p.get("required")
    if obyazatelnost is True:
        priznak = "обязательный"
    elif obyazatelnost is False:
        priznak = "необязательный"
    else:
        priznak = "обязательность в справке не указана"

    stroki = [f"    {p.get('name', '')} — {tip}, {priznak}"]
    if p.get("description"):
        stroki.append(f"      {p['description']}")
    return stroki


def _variant(v: Dict[str, Any], s_imenem: bool) -> List[str]:
    stroki = []
    if s_imenem and v.get("variant"):
        stroki.append(f"Вариант «{v['variant']}»")
        otstup = "  "
    else:
        otstup = ""

    stroki.append(f"{otstup}Вызов: {v.get('call') or v.get('syntax') or NET_V_SPRAVKE}")

    parametry = v.get("parameters") or []
    if parametry:
        stroki.append(f"{otstup}Параметры:")
        for p in parametry:
            stroki.extend(f"{otstup}{s}" for s in _parametr(p))
    else:
        stroki.append(f"{otstup}Параметры: нет")

    return stroki


def _vozvrat(doc: Dict[str, Any]) -> List[str]:
    """Что вернёт вызов. Для процедуры — прямо сказать, что ничего."""
    varianty = doc.get("variants") or []
    tipy = [v.get("return_type") for v in varianty if v.get("return_type")]

    if not tipy:
        if doc.get("element_kind") == "процедура":
            return ["Возвращает: нет (процедура)"]
        return [f"Возвращает: {NET_V_SPRAVKE}"]

    stroki = [f"Возвращает: {tipy[0]}"]
    poyasnenie = next(
        (v.get("return_description") for v in varianty if v.get("return_description")),
        "",
    )
    if poyasnenie:
        stroki.append(f"  {poyasnenie}")
    return stroki


def _dostupnost(doc: Dict[str, Any]) -> str:
    spisok = doc.get("availability") or []
    if not spisok:
        return "Доступность: в справке не указана"
    return "Доступность: " + ", ".join(spisok)


def _primery(doc: Dict[str, Any]) -> List[str]:
    primery = doc.get("examples") or []
    if not primery:
        return ["Примеров в справке нет."]

    stroki = ["Пример:"]
    for kod in primery:
        stroki.extend(f"  {stroka}" for stroka in kod.split("\n"))
    return stroki


def kartochka(doc: Dict[str, Any]) -> str:
    """Полная карточка элемента."""
    if (doc.get("element_kind") or "") == "объект":
        # Полная карточка объекта требует данных, которых в его документе нет:
        # числа членов и строк вызова конструкторов. Их собирает обработчик
        # отдельными запросами и зовёт kartochka_obekta напрямую — сюда
        # попадает только вызов в обход обработчика, и он честно говорит, что
        # конструкторы не проверялись, вместо «в справке не указано».
        return kartochka_obekta(doc, {})

    stroki = [_zagolovok(doc), ""]

    if (doc.get("element_kind") or "") == "свойство":
        stroki.append(f"{_yarlyk_vyzova(doc)}: {doc.get('call_primary') or NET_V_SPRAVKE}")
        stroki.append(f"Тип значения: {doc.get('value_type') or NET_V_SPRAVKE}")
        stroki.append(f"Доступ: {doc.get('usage') or NET_V_SPRAVKE}")
    else:
        varianty = doc.get("variants") or []
        if len(varianty) > 1:
            stroki.append(f"Вариантов вызова: {len(varianty)}")
            stroki.append("")
        for v in varianty:
            stroki.extend(_variant(v, s_imenem=len(varianty) > 1))
            stroki.append("")
        if not varianty:
            stroki.append(f"Вызов: {doc.get('call_primary') or NET_V_SPRAVKE}")
            # Параметры — поле из списка «всегда печатаются»: пустые variants
            # не повод его пропускать, иначе молчание неотличимо от «данных нет».
            stroki.append("Параметры: нет")
        stroki.extend(_vozvrat(doc))

    stroki.append(_dostupnost(doc))
    if doc.get("version_from"):
        stroki.append(f"Доступно с: {doc['version_from']}")

    stroki.append("")
    stroki.append(f"Описание: {doc.get('description') or 'в справке отсутствует'}")
    if doc.get("note"):
        stroki.append(f"Примечание: {doc['note']}")
    stroki.extend(_primery(doc))

    return "\n".join(stroki)


def kartochka_obekta(
    doc: Dict[str, Any],
    kolichestva: Dict[str, int],
    konstruktory: Optional[List[str]] = None,
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
    """
    imya = doc.get("full_path") or doc.get("name_ru") or ""
    stroki = [f"{imya} — объект", ""]

    yarlyk = _yarlyk_vyzova(doc)
    if konstruktory:
        stroki.append(f"{yarlyk}:")
        stroki.extend(f"  {k}" for k in konstruktory)
    elif konstruktory is not None:
        stroki.append(f"{yarlyk}: {NET_V_SPRAVKE}")
    else:
        stroki.append(f"{yarlyk}: не проверялись")

    stroki.append(_dostupnost(doc))
    if doc.get("version_from"):
        stroki.append(f"Доступно с: {doc['version_from']}")

    stroki.append("")
    stroki.append(f"Описание: {doc.get('description') or 'в справке отсутствует'}")

    if kolichestva:
        chasti = ", ".join(
            f"{nazvanie}: {chislo}"
            for nazvanie, chislo in (
                ("методов", kolichestva.get("methods", 0)),
                ("свойств", kolichestva.get("properties", 0)),
                ("событий", kolichestva.get("events", 0)),
            )
        )
        stroki.append(f"Состав — {chasti}.")
        stroki.append(
            f'Перечень: list_1c_object_members(object="{imya}")'
        )

    return "\n".join(stroki)


def stroka_spiska(doc: Dict[str, Any]) -> str:
    """Одна строка на элемент — для выдачи поиска и состава объекта."""
    put = doc.get("full_path") or doc.get("name_ru") or ""
    vid = doc.get("element_kind") or ""
    vyzov = doc.get("call_primary") or ""

    chasti = [put]
    if vid:
        chasti.append(f"— {vid}")
    if vyzov and vyzov != put:
        chasti.append(f"— {vyzov}")

    varianty = doc.get("variants") or []
    if len(varianty) > 1:
        chasti.append(f"(вариантов вызова: {len(varianty)})")

    opisanie = doc.get("description") or ""
    if opisanie:
        chasti.append(f"— {obrezat_do_frazy(opisanie, PREDEL_OPISANIYA_V_SPISKE)}")

    return " ".join(chasti)


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
    predel = min(vsego, predel_instrumenta)
    vyzov = shablon_vyzova.format(limit=predel)
    if predel < vsego:
        return (
            f"Показано {pokazano} из {vsego}. За один вызов можно получить "
            f"не более {predel}: {vyzov}."
        )
    return f"Показано {pokazano} из {vsego}. Полный список: {vyzov}."


def spisok_kandidatov(
    imya: str,
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
    stroki = [
        f"Имя «{imya}» найдено у {vsego} элементов — "
        f"карточка не может быть выбрана однозначно.",
        f'Уточните объект: get_1c_element(name="{imya}", object="<объект>")',
        "",
        "Кандидаты (сначала типы языка, внутри — объекты с бо́льшим числом "
        "элементов в справке):",
    ]
    stroki.extend(f"  {stroka_spiska(k)}" for k in kandidaty)
    if not poryadok_polnyy:
        stroki.append(
            "  (порядок построен не по всем совпадениям — их слишком много "
            "для одного запроса)"
        )
    stroki.append("")

    # find_1c_help не примет limit больше LIMIT_POISKA_MAX — совет с
    # limit=vsego при омонимах вроде «Количество» (275 совпадений) сам
    # упирался бы в validation error схемы, которую эта же задача вводит.
    stroki.append(sovet_ob_ostatke(
        len(kandidaty), vsego, LIMIT_POISKA_MAX,
        f'find_1c_help(query="{imya}", limit={{limit}})',
    ))
    return "\n".join(stroki)


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

    stroki = [f"Состав объекта {obekt}.", ""]
    for zagolovok, elementy in (
        (yarlyk_metodov, metody), ("Свойства", svoystva), ("События", sobytiya)
    ):
        if not elementy:
            continue
        stroki.append(f"{zagolovok} ({len(elementy)}):")
        stroki.extend(f"  {stroka_spiska(d)}" for d in elementy)
        stroki.append("")

    # Молчаливая неполнота — худшее, что может отдать справочный инструмент:
    # агент примет урезанный список за исчерпывающий и решит, что метода нет.
    if vsego and vsego > pokazano:
        stroki.append(sovet_ob_ostatke(
            pokazano, vsego, predel_instrumenta,
            f'list_1c_object_members(object="{obekt}", members="{vid}", '
            f'limit={{limit}})',
        ))
    stroki.append(f'Полная карточка: get_1c_element(name=…, object="{obekt}")')
    return "\n".join(stroki)

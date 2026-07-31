"""Карточка элемента справки 1С — единственное место сборки ответа.

Карточка отвечает на два вопроса агента: что вызывать и как вызывать. Поэтому
у неё фиксированный набор полей, и отсутствие данных помечается явно: пропуск
поля неотличим от «данных нет», и модель достраивает пробел домыслом. Раньше
рендер был размазан по mcp_formatter и search/formatter, причём в первом жили
два одноимённых format_quick_reference, второй из которых перекрывал первый.
"""

from typing import Any, Dict, List

from src.handlers.mcp_formatter import obrezat_do_frazy

NET_V_SPRAVKE = "в справке не указано"
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
        return kartochka_obekta(doc, {})

    stroki = [_zagolovok(doc), ""]

    if (doc.get("element_kind") or "") == "свойство":
        stroki.append(f"Обращение: {doc.get('call_primary') or NET_V_SPRAVKE}")
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


def kartochka_obekta(doc: Dict[str, Any], kolichestva: Dict[str, int]) -> str:
    """Карточка самого объекта: без списков членов, но с их числом.

    Членов у объекта бывают сотни, и обрезанный список вернул бы ту же
    молчаливую неполноту, от которой мы уходим. Поэтому — число и прямое
    указание, чем получить перечень.
    """
    imya = doc.get("full_path") or doc.get("name_ru") or ""
    stroki = [f"{imya} — объект", ""]

    konstruktory = [v.get("call") for v in (doc.get("variants") or []) if v.get("call")]
    if konstruktory:
        stroki.append("Конструкторы:")
        stroki.extend(f"  {k}" for k in konstruktory)
    else:
        stroki.append(f"Конструкторы: {NET_V_SPRAVKE}")

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


def spisok_kandidatov(imya: str, kandidaty: List[Dict[str, Any]], vsego: int) -> str:
    """Ответ при омонимии: перечень вместо молчаливого выбора одного из многих."""
    stroki = [
        f"Имя «{imya}» найдено у {vsego} элементов — "
        f"карточка не может быть выбрана однозначно.",
        f'Уточните объект: get_1c_element(name="{imya}", object="<объект>")',
        "",
        "Наиболее вероятные:",
    ]
    stroki.extend(f"  {stroka_spiska(k)}" for k in kandidaty)
    stroki.append("")
    stroki.append(
        f"Показано {len(kandidaty)} из {vsego}. "
        f'Полный список: find_1c_help(query="{imya}", limit={vsego}).'
    )
    return "\n".join(stroki)

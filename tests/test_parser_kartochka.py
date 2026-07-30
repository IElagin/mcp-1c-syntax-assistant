"""Тесты парсера справки на реальных страницах.

Фикстуры — настоящие файлы из shcntx_ru.hbk, а не выдумка: дефекты, которые
мы правим, воспроизводятся только на настоящей разметке. Тип параметра, к
примеру, терялся именно потому, что в справке он оформлен ссылкой на страницу
объекта, а парсер узнавал только ссылки def_* на встроенные типы языка.

Путь файла обязателен и обязан быть путём ИЗ АРХИВА, а не до фикстуры:
_parse_file_path определяет вид элемента по '/methods/', '/properties/',
'/ctors/' в пути.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parsers.html_parser import HTMLParser

FIKSTURY = Path(__file__).parent / "fixtures" / "hbk"

PUTI_V_ARHIVE = {
    "valuetable_findrows.html":
        "objects/catalog234/catalog236/ValueTable/methods/FindRows646.html",
    "valuetable_columns.html":
        "objects/catalog234/catalog236/ValueTable/properties/Columns1030.html",
    "global_valueisfilled.html":
        "objects/Global context/methods/catalog1762/ValueIsFilled2886.html",
    "formdatacollection_delete.html":
        "objects/catalog1649/catalog1614/FormDataCollection/methods/Delete3481.html",
    "array_ctor_bycount.html":
        "objects/catalog234/Array/ctors/ctor13.html",
    "valuetable_ctor_auto.html":
        "objects/catalog234/catalog236/ValueTable/ctors/ctor_Auto.html",
}


def razobrat(imya_fikstury):
    """Разбирает фикстуру, подставляя её настоящий путь в архиве."""
    soderzhimoe = (FIKSTURY / imya_fikstury).read_bytes()
    return HTMLParser().parse_html_content(soderzhimoe, PUTI_V_ARHIVE[imya_fikstury])


def parametry(doc):
    """Параметры элемента.

    В Task 3 параметры переезжают внутрь вариантов вызова, и эта функция
    станет возвращать doc.variants[0].parameters. Пока — верхний уровень.
    """
    return doc.parameters


@pytest.mark.unit
@pytest.mark.parser
def test_tip_parametra_iz_ssylki_na_obekt():
    """'Тип: <a …Structure.html>Структура</a>' — это Структура, а не Произвольный."""
    doc = razobrat("valuetable_findrows.html")

    par = parametry(doc)
    assert len(par) == 1, f"ожидался один параметр, получено {len(par)}"
    assert par[0].name == "ПараметрыОтбора"
    assert par[0].type == "Структура", (
        f"тип подменён заглушкой: {par[0].type!r}"
    )


@pytest.mark.unit
@pytest.mark.parser
def test_tip_parametra_obychnym_tekstom():
    """'Тип: Произвольный.' без ссылки тоже читается."""
    doc = razobrat("global_valueisfilled.html")

    par = parametry(doc)
    assert par[0].name == "Значение"
    assert par[0].type == "Произвольный"


@pytest.mark.unit
@pytest.mark.parser
def test_neobyazatelnyy_parametr_ne_obyazatelnyy():
    """'(необязательный)' в справке даёт required=False, а не True."""
    doc = razobrat("array_ctor_bycount.html")

    par = parametry(doc)
    assert par, "у конструктора должен быть параметр"
    assert par[0].required is False, (
        "справка помечает параметр необязательным, а карточка утверждает обратное"
    )


@pytest.mark.unit
@pytest.mark.parser
def test_obyazatelnost_ne_dubliruetsya_v_opisanii():
    """Флаг обязательности не повторяется текстом в описании параметра."""
    doc = razobrat("valuetable_findrows.html")

    opisanie = parametry(doc)[0].description
    assert "(обязательный)" not in opisanie, opisanie
    assert opisanie.startswith("Задает условия поиска")

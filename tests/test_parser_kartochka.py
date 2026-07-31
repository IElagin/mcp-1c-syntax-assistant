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
    """Параметры первого варианта вызова."""
    return doc.variants[0].parameters if doc.variants else []


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
    """'(необязательный)' в справке даёт required=False, а не True.

    Разметка вариативного параметра смешивает экранированные и литеральные
    угловые скобки: "<КоличествоЭлементов1>,...,<КоличествоЭлементовN>
    (необязательный)". Имя обязано остаться чистым ("КоличествоЭлементовN"), а
    не обломком разметки с начала строки — агент подставляет это имя как имя
    аргумента в код.
    """
    doc = razobrat("array_ctor_bycount.html")

    par = parametry(doc)
    assert par, "у конструктора должен быть параметр"
    assert par[0].name == "КоличествоЭлементовN", (
        f"имя параметра испорчено обломком разметки: {par[0].name!r}"
    )
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


@pytest.mark.unit
@pytest.mark.parser
def test_oba_varianta_vyzova_izvlekayutsya():
    """У метода бывает несколько вариантов вызова с разными параметрами.

    ДанныеФормыКоллекция.Удалить вызывается и по индексу, и по элементу.
    Раньше второй вариант терялся молча: парсер брал первый «Синтаксис:» и
    резал блок до следующего заголовка V8SH_. Агент узнавал ровно половину
    способов вызвать метод и не знал, что есть вторая.
    """
    doc = razobrat("formdatacollection_delete.html")

    assert len(doc.variants) == 2, [v.variant for v in doc.variants]

    po_indeksu, po_elementu = doc.variants
    assert po_indeksu.variant == "По индексу"
    assert po_indeksu.syntax == "Удалить(<Индекс>)"
    assert [p.name for p in po_indeksu.parameters] == ["Индекс"]
    assert po_indeksu.parameters[0].type == "Число"

    assert po_elementu.variant == "По элементу"
    assert po_elementu.syntax == "Удалить(<Элемент>)"
    assert [p.name for p in po_elementu.parameters] == ["Элемент"]
    assert po_elementu.parameters[0].type == "ДанныеФормыЭлементКоллекции"


@pytest.mark.unit
@pytest.mark.parser
def test_odin_variant_bez_imeni():
    """Страница без «Вариант синтаксиса» даёт один безымянный вариант."""
    doc = razobrat("valuetable_findrows.html")

    assert len(doc.variants) == 1
    assert doc.variants[0].variant == ""
    assert doc.variants[0].syntax == "НайтиСтроки(<ПараметрыОтбора>)"


@pytest.mark.unit
@pytest.mark.parser
def test_opisanie_obshchee_dlya_variantov():
    """Описание и доступность относятся к элементу, а не к варианту."""
    doc = razobrat("formdatacollection_delete.html")

    assert doc.description.startswith("Удаляет элемент из коллекции")


@pytest.mark.unit
@pytest.mark.parser
def test_konstruktor_neset_imya_varianta():
    """У конструктора имя варианта — это имя страницы справки.

    Заголовка «Вариант синтаксиса» на страницах конструкторов нет: варианты
    разложены по отдельным страницам, и «По количеству элементов» попадало в
    имя элемента, откуда собирался бессмысленный путь
    «Массив.По количеству элементов».
    """
    doc = razobrat("array_ctor_bycount.html")

    assert len(doc.variants) == 1
    assert doc.variants[0].variant == "По количеству элементов"


@pytest.mark.unit
@pytest.mark.parser
def test_tip_vozvrata_otdelen_ot_poyasneniya():
    """Тип возврата — «Массив», а не абзац в три предложения.

    Раньше при отсутствии def_-ссылки в return_type писался весь раздел целиком,
    и у половины заполненных значений «тип» был текстом с точками внутри —
    прочитать из него тип машинно нельзя.
    """
    doc = razobrat("valuetable_findrows.html")

    variant = doc.variants[0]
    assert variant.return_type == "Массив"
    assert variant.return_description.startswith("Массив строк таблицы значений")
    assert "Замечание!" in variant.return_description


@pytest.mark.unit
@pytest.mark.parser
def test_dostupnost_izvlekaetsya():
    """Где вызов законен — главный вопрос, на который справка отвечает, а сервер молчал.

    НайтиСтроки недоступен на тонком клиенте: агент, не знающий этого,
    напишет код, который не заработает.
    """
    doc = razobrat("valuetable_findrows.html")

    assert "сервер" in doc.availability
    assert "толстый клиент" in doc.availability
    assert "тонкий клиент" not in doc.availability


@pytest.mark.unit
@pytest.mark.parser
def test_primechanie_izvlekaetsya():
    doc = razobrat("valuetable_findrows.html")

    assert doc.note.startswith("Метод эффективно использовать")


@pytest.mark.unit
@pytest.mark.parser
def test_svoystvo_tip_znacheniya_i_dostup():
    """У свойства свои два вопроса: какого типа значение и можно ли писать."""
    doc = razobrat("valuetable_columns.html")

    assert doc.value_type == "КоллекцияКолонокТаблицыЗначений"
    assert doc.usage == "только чтение"
    assert doc.description.startswith("Содержит коллекцию колонок"), doc.description


@pytest.mark.unit
@pytest.mark.parser
def test_ispolzovanie_v_versii_ne_putaetsya_s_dostupom():
    """На странице два раздела со словом «Использование» — в usage идёт нужный."""
    doc = razobrat("valuetable_columns.html")

    assert "версии" not in (doc.usage or "")


@pytest.mark.unit
@pytest.mark.parser
def test_vid_elementa_i_russkiy_vladelets():
    """Вид элемента назван по-русски, владелец глобальной функции — «Глобальный контекст»."""
    funktsiya = razobrat("global_valueisfilled.html")
    assert funktsiya.element_kind == "функция"
    assert funktsiya.object_ru == "Глобальный контекст"

    svoystvo = razobrat("valuetable_columns.html")
    assert svoystvo.element_kind == "свойство"
    assert svoystvo.object_ru == "ТаблицаЗначений"


@pytest.mark.unit
@pytest.mark.parser
def test_stroka_vyzova_metoda_s_obektom():
    """Вызов должен быть готов к копированию в код."""
    doc = razobrat("valuetable_findrows.html")

    assert doc.variants[0].call == "ТаблицаЗначений.НайтиСтроки(<ПараметрыОтбора>)"
    assert doc.call_primary == "ТаблицаЗначений.НайтиСтроки(<ПараметрыОтбора>)"


@pytest.mark.unit
@pytest.mark.parser
def test_globalnaya_funktsiya_bez_prefiksa():
    """«Global context.ЗначениеЗаполнено (ValueIsFilled)» — не строка вызова."""
    doc = razobrat("global_valueisfilled.html")

    assert doc.call_primary == "ЗначениеЗаполнено(<Значение>)"
    assert doc.full_path == "ЗначениеЗаполнено"
    assert "(" not in doc.full_path


@pytest.mark.unit
@pytest.mark.parser
def test_konstruktor_uzhe_soderzhit_novyy():
    doc = razobrat("array_ctor_bycount.html")

    assert doc.call_primary.startswith("Новый Массив(")


@pytest.mark.unit
@pytest.mark.parser
def test_konstruktor_po_umolchaniyu_dostraivaetsya():
    """У «По умолчанию» синтаксис в справке пуст, но вызов существует."""
    doc = razobrat("valuetable_ctor_auto.html")

    assert doc.call_primary == "Новый ТаблицаЗначений"


@pytest.mark.unit
@pytest.mark.parser
def test_svoystvo_obrashchenie_bez_skobok():
    doc = razobrat("valuetable_columns.html")

    assert doc.call_primary == "ТаблицаЗначений.Колонки"
    assert doc.full_path == "ТаблицаЗначений.Колонки"


@pytest.mark.unit
@pytest.mark.parser
def test_opisanie_bez_slipshihsya_fraz():
    """«не по ссылке.Не работает» — 5,3% описаний в индексе слиплись так."""
    doc = razobrat("global_valueisfilled.html")

    assert ".Не работает" not in doc.description
    assert ". Не работает" in doc.description


@pytest.mark.unit
@pytest.mark.parser
def test_primer_bez_nerazryvnyh_probelov():
    """Пример из справки должен компилироваться после копирования."""
    doc = razobrat("valuetable_findrows.html")

    assert doc.examples, "у НайтиСтроки в справке есть пример"
    assert "\xa0" not in doc.examples[0]
    assert "Новый Структура()" in doc.examples[0]

    # Отступ вложенной строки — значимое форматирование кода, а не мусор:
    # схлопывание пробелов (как делает normalizovat_probely) срезало бы его.
    assert "    ЭлементыФормы.СписокРаботников.ТекущаяСтрока = Строки[0];" in (
        doc.examples[0]
    )

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

FIXTURES = Path(__file__).parent / "fixtures" / "hbk"

ARCHIVE_PATHS = {
    # Русские двойники нужны задаче 11 (её фикстуры без RU-аналога до задачи 3
    # не существовали); тесты на них пишет она — здесь только путь в архиве.
    "array_add.html":
        "objects/catalog234/Array/methods/Add772.html",
    "array_object.html":
        "objects/catalog234/Array.html",
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
    # Доступность с прозой после перечня контекстов.
    "global_findbyref.html":
        "objects/Global context/methods/catalog570/FindByRef572.html",
    # Страница вовсе без раздела «Доступность» — единственный такой метод в справке.
    "formextension_compactmode.html":
        "objects/catalog1649/catalog1890/Client application form extension "
        "for reports/methods/method6189.html",
    # Два варианта, у каждого своё «Описание варианта метода:», общего
    # «Описание:» на странице нет вовсе.
    "global_notifychanged.html":
        "objects/Global context/methods/catalog27/NotifyChanged3763.html",
    # Второй вариант несёт «Описание варианта метода:», но на странице есть
    # и обычное «Описание:» — для элемента в целом.
    "formdatacollection_unload.html":
        "objects/catalog1649/catalog1614/FormDataCollection/methods/Unload3853.html",
}


def parse_fixture(fixture_name):
    """Разбирает фикстуру, подставляя её настоящий путь в архиве."""
    content = (FIXTURES / fixture_name).read_bytes()
    return HTMLParser().parse_html_content(content, ARCHIVE_PATHS[fixture_name])


def call_parameters(doc):
    """Параметры первого варианта вызова."""
    return doc.variants[0].parameters if doc.variants else []


@pytest.mark.unit
@pytest.mark.parser
def test_param_type_from_object_link():
    """'Тип: <a …Structure.html>Структура</a>' — это Структура, а не Произвольный."""
    doc = parse_fixture("valuetable_findrows.html")

    params = call_parameters(doc)
    assert len(params) == 1, f"ожидался один параметр, получено {len(params)}"
    assert params[0].name == "ПараметрыОтбора"
    assert params[0].type == "Структура", (
        f"тип подменён заглушкой: {params[0].type!r}"
    )


@pytest.mark.unit
@pytest.mark.parser
def test_param_type_as_plain_text():
    """'Тип: Произвольный.' без ссылки тоже читается."""
    doc = parse_fixture("global_valueisfilled.html")

    params = call_parameters(doc)
    assert params[0].name == "Значение"
    assert params[0].type == "Произвольный"


@pytest.mark.unit
@pytest.mark.parser
def test_optional_param_is_not_required():
    """'(необязательный)' в справке даёт required=False, а не True.

    Разметка вариативного параметра смешивает экранированные и литеральные
    угловые скобки: "<КоличествоЭлементов1>,...,<КоличествоЭлементовN>
    (необязательный)". Имя обязано остаться чистым ("КоличествоЭлементовN"), а
    не обломком разметки с начала строки — агент подставляет это имя как имя
    аргумента в код.
    """
    doc = parse_fixture("array_ctor_bycount.html")

    params = call_parameters(doc)
    assert params, "у конструктора должен быть параметр"
    assert params[0].name == "КоличествоЭлементовN", (
        f"имя параметра испорчено обломком разметки: {params[0].name!r}"
    )
    assert params[0].required is False, (
        "справка помечает параметр необязательным, а карточка утверждает обратное"
    )


@pytest.mark.unit
@pytest.mark.parser
def test_requiredness_is_not_duplicated_in_description():
    """Флаг обязательности не повторяется текстом в описании параметра."""
    doc = parse_fixture("valuetable_findrows.html")

    description_text = call_parameters(doc)[0].description
    assert "(обязательный)" not in description_text, description_text
    assert description_text.startswith("Задает условия поиска")


@pytest.mark.unit
@pytest.mark.parser
def test_both_call_variants_are_extracted():
    """У метода бывает несколько вариантов вызова с разными параметрами.

    ДанныеФормыКоллекция.Удалить вызывается и по индексу, и по элементу.
    Раньше второй вариант терялся молча: парсер брал первый «Синтаксис:» и
    резал блок до следующего заголовка V8SH_. Агент узнавал ровно половину
    способов вызвать метод и не знал, что есть вторая.
    """
    doc = parse_fixture("formdatacollection_delete.html")

    assert len(doc.variants) == 2, [v.variant for v in doc.variants]

    by_index, by_element = doc.variants
    assert by_index.variant == "По индексу"
    assert by_index.syntax == "Удалить(<Индекс>)"
    assert [p.name for p in by_index.parameters] == ["Индекс"]
    assert by_index.parameters[0].type == "Число"

    assert by_element.variant == "По элементу"
    assert by_element.syntax == "Удалить(<Элемент>)"
    assert [p.name for p in by_element.parameters] == ["Элемент"]
    assert by_element.parameters[0].type == "ДанныеФормыЭлементКоллекции"


@pytest.mark.unit
@pytest.mark.parser
def test_single_variant_has_no_name():
    """Страница без «Вариант синтаксиса» даёт один безымянный вариант."""
    doc = parse_fixture("valuetable_findrows.html")

    assert len(doc.variants) == 1
    assert doc.variants[0].variant == ""
    assert doc.variants[0].syntax == "НайтиСтроки(<ПараметрыОтбора>)"


@pytest.mark.unit
@pytest.mark.parser
def test_description_is_shared_by_variants():
    """Описание и доступность относятся к элементу, а не к варианту."""
    doc = parse_fixture("formdatacollection_delete.html")

    assert doc.description.startswith("Удаляет элемент из коллекции")


@pytest.mark.unit
@pytest.mark.parser
def test_constructor_carries_variant_name():
    """У конструктора имя варианта — это имя страницы справки.

    Заголовка «Вариант синтаксиса» на страницах конструкторов нет: варианты
    разложены по отдельным страницам, и «По количеству элементов» попадало в
    имя элемента, откуда собирался бессмысленный путь
    «Массив.По количеству элементов».
    """
    doc = parse_fixture("array_ctor_bycount.html")

    assert len(doc.variants) == 1
    assert doc.variants[0].variant == "По количеству элементов"


@pytest.mark.unit
@pytest.mark.parser
def test_return_type_is_separated_from_note():
    """Тип возврата — «Массив», а не абзац в три предложения.

    Раньше при отсутствии def_-ссылки в return_type писался весь раздел целиком,
    и у половины заполненных значений «тип» был текстом с точками внутри —
    прочитать из него тип машинно нельзя.
    """
    doc = parse_fixture("valuetable_findrows.html")

    variant = doc.variants[0]
    assert variant.return_type == "Массив"
    assert variant.return_description.startswith("Массив строк таблицы значений")
    assert "Замечание!" in variant.return_description


@pytest.mark.unit
@pytest.mark.parser
def test_availability_is_extracted():
    """Где вызов законен — главный вопрос, на который справка отвечает, а сервер молчал.

    НайтиСтроки недоступен на тонком клиенте: агент, не знающий этого,
    напишет код, который не заработает.
    """
    doc = parse_fixture("valuetable_findrows.html")

    assert "сервер" in doc.availability
    assert "толстый клиент" in doc.availability
    assert "тонкий клиент" not in doc.availability


@pytest.mark.unit
@pytest.mark.parser
def test_availability_does_not_absorb_prose_after_list():
    """После перечня контекстов в справке бывает проза — она не контекст.

    Настоящая страница НайтиПоСсылкам: «Сервер, толстый клиент, внешнее
    соединение, мобильное приложение (сервер), мобильный автономный
    сервер.<br>Вызов метода выполняет обращение к серверу.» Снятие одной точки
    на конце склеивало последний контекст с прозой, и агент читал «мобильный
    автономный сервер. вызов метода выполняет обращение к серверу» как место,
    где вызов законен. Замер по индексу до правки: 1 106 таких документов.
    """
    doc = parse_fixture("global_findbyref.html")

    assert doc.availability == [
        "сервер", "толстый клиент", "внешнее соединение",
        "мобильное приложение (сервер)", "мобильный автономный сервер",
    ]
    assert not any("." in context for context in doc.availability), doc.availability
    assert not any("вызов метода" in context for context in doc.availability)


@pytest.mark.unit
@pytest.mark.parser
def test_page_without_availability_section_gives_empty_list():
    """Раздела «Доступность» может не быть вовсе — тогда список пуст, а не выдуман.

    Пустой список карточка печатает как «Доступность: в справке не указана»:
    отличать «справка молчит» от «контексты такие-то» обязан сам парсер, иначе
    отличать будет нечему.
    """
    doc = parse_fixture("formextension_compactmode.html")

    assert doc.availability == []


@pytest.mark.unit
@pytest.mark.parser
def test_note_is_extracted():
    doc = parse_fixture("valuetable_findrows.html")

    assert doc.note.startswith("Метод эффективно использовать")


@pytest.mark.unit
@pytest.mark.parser
def test_property_value_type_and_access():
    """У свойства свои два вопроса: какого типа значение и можно ли писать."""
    doc = parse_fixture("valuetable_columns.html")

    assert doc.value_type == "КоллекцияКолонокТаблицыЗначений"
    assert doc.usage == "только чтение"
    assert doc.description.startswith("Содержит коллекцию колонок"), doc.description


@pytest.mark.unit
@pytest.mark.parser
def test_version_usage_is_not_confused_with_access():
    """На странице два раздела со словом «Использование» — в usage идёт нужный."""
    doc = parse_fixture("valuetable_columns.html")

    assert "версии" not in (doc.usage or "")


@pytest.mark.unit
@pytest.mark.parser
def test_element_kind_and_russian_owner():
    """Вид элемента назван по-русски, владелец глобальной функции — «Глобальный контекст»."""
    function_doc = parse_fixture("global_valueisfilled.html")
    assert function_doc.element_kind == "функция"
    assert function_doc.object_ru == "Глобальный контекст"

    property_doc = parse_fixture("valuetable_columns.html")
    assert property_doc.element_kind == "свойство"
    assert property_doc.object_ru == "ТаблицаЗначений"


@pytest.mark.unit
@pytest.mark.parser
def test_method_call_line_includes_object():
    """Вызов должен быть готов к копированию в код."""
    doc = parse_fixture("valuetable_findrows.html")

    assert doc.variants[0].call == "ТаблицаЗначений.НайтиСтроки(<ПараметрыОтбора>)"
    assert doc.call_primary == "ТаблицаЗначений.НайтиСтроки(<ПараметрыОтбора>)"


@pytest.mark.unit
@pytest.mark.parser
def test_global_function_has_no_prefix():
    """«Global context.ЗначениеЗаполнено (ValueIsFilled)» — не строка вызова."""
    doc = parse_fixture("global_valueisfilled.html")

    assert doc.call_primary == "ЗначениеЗаполнено(<Значение>)"
    assert doc.full_path == "ЗначениеЗаполнено"
    assert "(" not in doc.full_path


@pytest.mark.unit
@pytest.mark.parser
def test_constructor_already_contains_new():
    doc = parse_fixture("array_ctor_bycount.html")

    assert doc.call_primary.startswith("Новый Массив(")


@pytest.mark.unit
@pytest.mark.parser
def test_default_constructor_call_is_completed():
    """У «По умолчанию» синтаксис в справке пуст, но вызов существует."""
    doc = parse_fixture("valuetable_ctor_auto.html")

    assert doc.call_primary == "Новый ТаблицаЗначений"


@pytest.mark.unit
@pytest.mark.parser
def test_property_access_has_no_parentheses():
    doc = parse_fixture("valuetable_columns.html")

    assert doc.call_primary == "ТаблицаЗначений.Колонки"
    assert doc.full_path == "ТаблицаЗначений.Колонки"


@pytest.mark.unit
@pytest.mark.parser
def test_description_has_no_glued_sentences():
    """«не по ссылке.Не работает» — 5,3% описаний в индексе слиплись так."""
    doc = parse_fixture("global_valueisfilled.html")

    assert ".Не работает" not in doc.description
    assert ". Не работает" in doc.description


@pytest.mark.unit
@pytest.mark.parser
def test_example_has_no_non_breaking_spaces():
    """Пример из справки должен компилироваться после копирования."""
    doc = parse_fixture("valuetable_findrows.html")

    assert doc.examples, "у НайтиСтроки в справке есть пример"
    assert "\xa0" not in doc.examples[0]
    assert "Новый Структура()" in doc.examples[0]

    # Отступ вложенной строки — значимое форматирование кода, а не мусор:
    # схлопывание пробелов (как делает normalize_whitespace) срезало бы его.
    assert "    ЭлементыФормы.СписокРаботников.ТекущаяСтрока = Строки[0];" in (
        doc.examples[0]
    )


@pytest.mark.unit
@pytest.mark.parser
def test_variant_description_attaches_to_its_own_variant():
    """«Описание варианта метода:» относится к варианту, а не ко всему элементу.

    ОповеститьОбИзменении: два варианта, у каждого своё «Описание варианта
    метода:», общего «Описание:» на странице нет вовсе. Раньше подстрочный
    поиск '«описание» in header_text' находил первый такой заголовок и отдавал
    его текст в doc.description — второй вариант при этом описания не получал
    вовсе, а первый ошибочно выдавался за описание всего метода. Оба текста
    должны остаться при своих вариантах, а doc.description — пустым: справка
    элементу в целом описания не дала.
    """
    doc = parse_fixture("global_notifychanged.html")

    assert doc.description == "", doc.description
    assert len(doc.variants) == 2, [v.variant for v in doc.variants]

    one_object, many_objects = doc.variants
    assert one_object.variant == "Изменен один объект"
    assert one_object.description.startswith(
        "Уведомляет динамические списки на клиенте об изменении одного объекта"
    ), one_object.description

    assert many_objects.variant == "Изменено много объектов"
    assert many_objects.description.startswith(
        "Уведомляет динамические списки на клиенте об изменении множества объектов"
    ), many_objects.description


@pytest.mark.unit
@pytest.mark.parser
def test_element_description_is_not_replaced_by_variant_description():
    """Когда на странице есть и «Описание варианта метода:», и «Описание:» — побеждает второе.

    ДанныеФормыКоллекция.Выгрузить: у второго варианта («Выгрузить по
    отбору») есть «Описание варианта метода:», а у элемента в целом — своё
    «Описание:» дальше по странице. Раньше подстрочный поиск находил
    «Описание варианта метода:» первым (оно стоит раньше в документе) и
    доклад доставался doc.description целиком, а настоящее «Описание:» —
    про то, что метод строит таблицу значений — не читалось никогда.
    """
    doc = parse_fixture("formdatacollection_unload.html")

    assert doc.description.startswith("Создает таблицу значений"), doc.description
    assert "Если указан отбор" not in doc.description, doc.description

    assert len(doc.variants) == 2, [v.variant for v in doc.variants]
    by_columns, by_filter = doc.variants
    assert by_columns.variant == "Выгрузить колонки"
    assert by_columns.description == ""

    assert by_filter.variant == "Выгрузить по отбору"
    assert by_filter.description.startswith("Если указан отбор"), by_filter.description

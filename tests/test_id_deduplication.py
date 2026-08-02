"""Столкновения id (object+name+type) не должны стирать документы друг другом.

Книга не гарантирует, что тройка object+name+type уникальна: у части
объектов заголовок страницы совпадает с заголовком раздела-оглавления книги
в другом месте («Запрос» — полноценный объект и рядом пустая запись-раздел
«в этом разделе описываются системные перечисления запроса»), а у некоторых
пар объектов совпадает и вовсе всё отображаемое имя при разном содержании
(1С называет их одинаково). Elasticsearch индексирует документ по id — при
столкновении один документ в bulk-запросе перезаписывает другой.
"""

import pytest

from src.models.doc_models import Documentation, DocumentType
from src.parsers.hbk_parser import deduplicate_by_id


pytestmark = pytest.mark.unit


def make_object(source_file, description="", methods=None, properties=None, events=None, availability=None):
    """Документ типа object с уже вычисленным id "Запрос_Запрос_object"."""
    doc = Documentation(
        id="Запрос_Запрос_object",
        type=DocumentType.OBJECT,
        name="Запрос",
        object="Запрос",
        source_file=source_file,
        description=description,
        methods=methods or [],
        properties=properties or [],
        events=events or [],
        availability=availability or [],
    )
    return doc


def test_no_collision_leaves_documents_untouched():
    """Документы с разными id проходят без изменений."""
    a = make_object("objects/a.html", description="A")
    b = Documentation(
        id="Массив_Массив_object", type=DocumentType.OBJECT,
        name="Массив", object="Массив", source_file="objects/b.html", description="B",
    )

    result = deduplicate_by_id([a, b])

    assert {d.id for d in result} == {"Запрос_Запрос_object", "Массив_Массив_object"}
    assert len(result) == 2


def test_empty_stub_is_dropped_when_real_sibling_exists():
    """Пустая страница-заглушка выбрасывается, реальный объект держит чистый id.

    Ровно случай "Запрос": objects/catalog2/catalog259.html — раздел-оглавление
    без описания и состава, objects/catalog213/catalog393/Query.html —
    полноценный объект. Заглушка не несёт ничего, что было бы жаль потерять;
    оставлять её в индексе под тем же id, что и настоящий объект, значило бы
    рисковать: при недетерминированном порядке индексации выигрывает то
    заглушка, то объект.
    """
    stub = make_object("objects/catalog2/catalog259.html")
    real = make_object(
        "objects/catalog213/catalog393/Query.html",
        description="Предназначен для выполнения запросов к базе данных.",
        availability=["сервер", "толстый клиент"],
    )

    result = deduplicate_by_id([stub, real])

    assert len(result) == 1
    assert result[0] is real
    assert result[0].id == "Запрос_Запрос_object"
    assert result[0].description.startswith("Предназначен")


def test_multiple_stubs_all_dropped_when_real_sibling_exists():
    """Несколько заглушек рядом с одним реальным объектом — все заглушки уходят."""
    stub1 = make_object("objects/catalog2/catalog259.html")
    stub2 = make_object("objects/catalog63/catalog999.html")
    real = make_object(
        "objects/catalog213/catalog393/Query.html",
        description="Предназначен для выполнения запросов к базе данных.",
    )

    result = deduplicate_by_id([stub1, real, stub2])

    assert len(result) == 1
    assert result[0] is real


def test_two_real_documents_both_kept_with_distinct_ids():
    """Два разных, но одинаково названных объекта — оба остаются, но с разными id.

    Ровно случай «ЭлементыФормы»: FormItems и Controls — разные объекты,
    у обоих есть содержимое. Терять любой из них нельзя, поэтому оба
    сохраняются: первый (по сортировке source_file) держит чистый id, второй
    получает "#2".
    """
    form_items = make_object(
        "objects/catalog1649/catalog1890/FormItems.html",
        description="Содержит коллекцию подчиненных элементов формы клиентского приложения.",
        methods=[{"name": "Найти"}],
    )
    controls = make_object(
        "objects/catalog56/catalog246/Controls.html",
        description="Используется для доступа к элементам управления формы.",
        methods=[{"name": "Найти"}, {"name": "Получить"}],
    )

    result = deduplicate_by_id([controls, form_items])

    assert len(result) == 2
    ids = sorted(d.id for d in result)
    assert ids == ["Запрос_Запрос_object", "Запрос_Запрос_object#2"]

    # source_file "catalog1649/..." < "catalog56/..." лексикографически —
    # значит FormItems держит чистый id, Controls получает "#2".
    by_id = {d.id: d for d in result}
    assert by_id["Запрос_Запрос_object"].source_file == "objects/catalog1649/catalog1890/FormItems.html"
    assert by_id["Запрос_Запрос_object#2"].source_file == "objects/catalog56/catalog246/Controls.html"


def test_all_stubs_collision_keeps_both_with_distinct_ids():
    """Две одинаково пустые страницы-раздела — не источник данных, но и не теряются.

    Оба документа пусты (ни описания, ни состава) — предпочесть один другому
    нечем, поэтому оба остаются, просто с разными id: молча выбрасывать
    архивные страницы, когда неясно, какая из них лишняя, этот проект
    считает худшим выбором, чем оставить малополезный дубль.
    """
    stub_a = make_object("objects/catalog63/catalog1.html")
    stub_b = make_object("objects/catalog2/catalog2.html")

    result = deduplicate_by_id([stub_a, stub_b])

    assert len(result) == 2
    assert {d.id for d in result} == {"Запрос_Запрос_object", "Запрос_Запрос_object#2"}


def test_disambiguation_is_deterministic_regardless_of_input_order():
    """Порядок документов на входе не должен менять итоговое распределение id.

    Разбор идёт батчами, и порядок обработки страниц зависит от того, как
    7zip перечислил архив — сортировка по source_file внутри столкнувшейся
    группы не зависит от этого порядка, поэтому переиндексация той же книги
    даёт те же id каждый раз.
    """
    form_items = make_object("objects/catalog1649/catalog1890/FormItems.html", description="A")
    controls = make_object("objects/catalog56/catalog246/Controls.html", description="B")

    result_1 = deduplicate_by_id([form_items, controls])
    result_2 = deduplicate_by_id([controls, form_items])

    by_source_1 = {d.source_file: d.id for d in result_1}
    by_source_2 = {d.source_file: d.id for d in result_2}
    assert by_source_1 == by_source_2


def test_real_collision_among_three_documents():
    """Тройное столкновение реальных документов — держатели '#2' и '#3' по source_file."""
    a = make_object("objects/z_last.html", description="Z")
    b = make_object("objects/a_first.html", description="A")
    c = make_object("objects/m_middle.html", description="M")

    result = deduplicate_by_id([a, b, c])

    assert len(result) == 3
    by_source = {d.source_file: d.id for d in result}
    assert by_source["objects/a_first.html"] == "Запрос_Запрос_object"
    assert by_source["objects/m_middle.html"] == "Запрос_Запрос_object#2"
    assert by_source["objects/z_last.html"] == "Запрос_Запрос_object#3"


def test_non_object_type_collision_is_never_treated_as_stub():
    """Столкновение у методов/свойств не подчиняется правилу про заглушки объектов.

    _is_empty_object_stub применим только к type == OBJECT — у методов и
    свойств отсутствие описания не означает «страница-заглушка», это может
    быть просто скудно документированный, но настоящий, адресуемый элемент
    (например, конструктор «По умолчанию» без общего абзаца описания).
    Оба документа в этом случае сохраняются с различителем, а не
    отбрасываются.
    """
    poor = Documentation(
        id="Объект_Метод_object_function", type=DocumentType.OBJECT_FUNCTION,
        name="Метод", object="Объект", source_file="objects/b.html", description="",
    )
    rich = Documentation(
        id="Объект_Метод_object_function", type=DocumentType.OBJECT_FUNCTION,
        name="Метод", object="Объект", source_file="objects/a.html", description="Описание метода",
    )

    result = deduplicate_by_id([poor, rich])

    assert len(result) == 2
    ids = {d.id for d in result}
    assert ids == {"Объект_Метод_object_function", "Объект_Метод_object_function#2"}

"""Unit тесты для парсера .hbk файлов."""

import pytest
from pathlib import Path
from bs4 import BeautifulSoup

from src.models.doc_models import Documentation, DocumentType
from src.parsers.html_parser import HTMLParser


@pytest.mark.unit
@pytest.mark.parser
def test_parsed_hbk_structure(mock_parsed_hbk):
    """Тест структуры распарсенных данных."""
    assert mock_parsed_hbk is not None
    assert mock_parsed_hbk.documentation is not None
    assert len(mock_parsed_hbk.documentation) > 0
    assert mock_parsed_hbk.file_info is not None
    assert mock_parsed_hbk.categories is not None
    assert mock_parsed_hbk.stats is not None


@pytest.mark.unit
@pytest.mark.parser
def test_parsed_hbk_documentation_types(mock_parsed_hbk):
    """Тест типов документации в распарсенных данных."""
    docs = mock_parsed_hbk.documentation
    
    # Проверяем наличие разных типов
    types_found = {doc.type for doc in docs}
    
    assert DocumentType.GLOBAL_FUNCTION in types_found
    assert DocumentType.GLOBAL_EVENT in types_found
    assert DocumentType.OBJECT_PROPERTY in types_found
    assert DocumentType.OBJECT_PROCEDURE in types_found


@pytest.mark.unit
@pytest.mark.parser
def test_parsed_hbk_global_functions(mock_parsed_hbk):
    """Тест глобальных функций."""
    global_funcs = [
        doc for doc in mock_parsed_hbk.documentation 
        if doc.type == DocumentType.GLOBAL_FUNCTION
    ]
    
    assert len(global_funcs) >= 2
    
    # Проверяем структуру первой функции
    func = global_funcs[0]
    assert func.name is not None
    assert func.variants[0].syntax is not None
    assert func.description is not None
    assert func.object is None  # Глобальная функция


@pytest.mark.unit
@pytest.mark.parser
def test_parsed_hbk_object_members(mock_parsed_hbk):
    """Тест членов объектов."""
    object_members = [
        doc for doc in mock_parsed_hbk.documentation 
        if doc.object is not None
    ]
    
    assert len(object_members) >= 2
    
    # Проверяем что у членов есть объект
    for member in object_members:
        assert member.object is not None
        assert member.name is not None


@pytest.mark.unit
@pytest.mark.parser
def test_parsed_hbk_parameters(mock_parsed_hbk):
    """Тест параметров функций."""
    funcs_with_params = [
        doc for doc in mock_parsed_hbk.documentation
        if doc.variants and doc.variants[0].parameters
    ]

    assert len(funcs_with_params) > 0

    # Проверяем структуру параметров
    func = funcs_with_params[0]
    param = func.variants[0].parameters[0]

    assert param.name is not None
    assert param.type is not None
    assert param.description is not None
    assert param.required is not None


@pytest.mark.unit
@pytest.mark.parser
def test_parsed_hbk_stats(mock_parsed_hbk):
    """Тест статистики парсинга."""
    stats = mock_parsed_hbk.stats
    
    assert 'html_files' in stats
    assert 'processed_html' in stats
    
    # Проверяем что статистика не пустая
    assert stats['html_files'] > 0
    assert stats['processed_html'] > 0
    assert isinstance(stats, dict)


@pytest.mark.unit
@pytest.mark.parser
def test_parsed_hbk_categories(mock_parsed_hbk):
    """Тест категорий документации."""
    categories = mock_parsed_hbk.categories
    
    assert len(categories) > 0
    assert 'Глобальный контекст' in categories or 'Массив' in categories


@pytest.mark.unit
@pytest.mark.parser
def test_parsed_hbk_no_errors(mock_parsed_hbk):
    """Тест отсутствия ошибок парсинга."""
    errors = mock_parsed_hbk.errors
    
    # В mock данных не должно быть ошибок
    assert len(errors) == 0


@pytest.mark.unit
@pytest.mark.parser
def test_documentation_full_path(mock_parsed_hbk):
    """Тест полных путей документов."""
    docs = mock_parsed_hbk.documentation
    
    for doc in docs:
        assert doc.full_path is not None
        assert len(doc.full_path) > 0
        
        # Глобальные функции должны содержать "Глобальный контекст"
        if doc.type == DocumentType.GLOBAL_FUNCTION:
            assert "Глобальный контекст" in doc.full_path or doc.name in doc.full_path


@pytest.mark.unit
@pytest.mark.parser
def test_documentation_examples(mock_parsed_hbk):
    """Тест наличия примеров кода."""
    docs_with_examples = [
        doc for doc in mock_parsed_hbk.documentation 
        if doc.examples
    ]
    
    # Хотя бы у некоторых документов должны быть примеры
    assert len(docs_with_examples) > 0
    
    # Проверяем что примеры не пустые
    for doc in docs_with_examples:
        assert len(doc.examples) > 0


@pytest.mark.unit
@pytest.mark.parser
def test_canonical_object_path_does_not_double_the_name():
    """У документа самого объекта object равен его имени — склеивать нельзя.

    Склейка object + "." + имя давала «ТаблицаЗначений.ТаблицаЗначений» у 2 286
    из 2 506 объектов, и карточка советовала
    list_1c_object_members(object="ТаблицаЗначений.ТаблицаЗначений") — вызов,
    который отвечает «объект в справке не найден».
    """
    from src.models.doc_models import Documentation

    doc = Documentation(id="", type=DocumentType.OBJECT, name="ТаблицаЗначений",
                        object="ТаблицаЗначений")
    doc.build_call_strings()

    assert doc.full_path == "ТаблицаЗначений"


@pytest.mark.unit
@pytest.mark.parser
def test_canonical_object_path_with_placeholder_name_keeps_the_type():
    """У 220 объектов имя страницы — заполнитель, а тип лежит в object.

    Там склейка и есть канонический путь заголовка справки, и по нему же лежат
    члены таких объектов: под ключом «БазовыеВидыРасчета.<Имя плана видов
    расчета>» 17 документов против одного под голым «БазовыеВидыРасчета».
    """
    from src.models.doc_models import Documentation

    doc = Documentation(id="", type=DocumentType.OBJECT,
                        name="<Имя плана видов расчета>",
                        object="БазовыеВидыРасчета")
    doc.build_call_strings()

    assert doc.full_path == "БазовыеВидыРасчета.<Имя плана видов расчета>"


@pytest.mark.unit
@pytest.mark.parser
def test_get_content_after_chapter_does_not_match_by_substring():
    """«Общие методы:» — не то же самое, что «Методы:», хотя и содержит его как подстроку.

    _get_content_after_chapter раньше искал секцию подстрочным сравнением
    ('методы' in header_text), и заголовок вроде «Общие методы:» ловился бы
    точно так же, как «Методы:» — агент получил бы либо не ту секцию, либо
    объединение обеих. На реальном корпусе такого заголовка нет, поэтому
    проверка — на синтетической, но правдоподобной странице объекта.
    """
    html = (
        '<html><body>'
        '<p class="V8SH_chapter">Общие методы:</p>'
        '<a href="decoy.html">Ловушка (Decoy)</a><br>'
        '<p class="V8SH_chapter">Методы:</p>'
        '<a href="real.html">Настоящий (Real)</a><br>'
        '<p class="V8SH_chapter">Свойства:</p>'
        '<a href="prop.html">Свойство (Prop)</a><br>'
        '</body></html>'
    )
    soup = BeautifulSoup(html, 'html.parser')
    doc = Documentation(id="", type=DocumentType.OBJECT, name="Тест")

    HTMLParser()._extract_object_methods(soup, doc)

    assert [m.name for m in doc.methods] == ["Настоящий"], doc.methods


@pytest.mark.unit
@pytest.mark.parser
def test_parser_takes_no_argument_it_does_not_honour():
    """Ручка, которую никто не читает, обещает работу, которой не будет."""
    import inspect

    from src.parsers.hbk_parser import HBKParser

    accepted = set(inspect.signature(HBKParser.__init__).parameters)

    assert "max_files_per_type" not in accepted, accepted
    assert "max_total_files" not in accepted, accepted


def test_fixture_archive_holds_every_page_at_its_archive_path(hbk_fixture_archive):
    """Путь внутри архива — это то, по чему парсер узнаёт вид элемента."""
    import zipfile

    from tests.conftest import ARCHIVE_PATHS_RU

    with zipfile.ZipFile(hbk_fixture_archive) as archive:
        stored = set(archive.namelist())

    assert stored == set(ARCHIVE_PATHS_RU.values())

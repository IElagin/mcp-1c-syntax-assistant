"""
Конфигурация pytest для тестов проекта.
"""

import pytest
import asyncio
import sys
import io
import struct
import zipfile
from pathlib import Path

# Добавляем корневую директорию проекта в sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Включаем режим asyncio для pytest
pytest_asyncio_mode = "auto"


@pytest.fixture(scope="session")
def event_loop():
    """Создает event loop для асинхронных тестов."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_hbk_path():
    """Путь к тестовому .hbk файлу."""
    from src.core.config import settings
    hbk_dir = Path(settings.data.hbk_directory)
    hbk_files = list(hbk_dir.glob("*.hbk"))
    
    if hbk_files:
        return str(hbk_files[0])
    else:
        pytest.skip("Нет доступных .hbk файлов для тестирования")


@pytest.fixture
def es_client_without_en_index():
    """Мок клиента ES, у которого нет английского индекса.

    Реальный help1c_docs_en сейчас существует и заполнен (23 104 документа) —
    удалять его ради теста нельзя, поэтому ветку «индекса нет» имитирует мок:
    index_exists(index="help1c_docs_en") возвращает False, как при первом
    запуске без английской книги (задача 8).
    """
    from unittest.mock import AsyncMock

    client = AsyncMock()
    client.index_exists = AsyncMock(return_value=False)
    return client


@pytest.fixture
def es_client_with_en_index():
    """Мок клиента ES, у которого английский индекс существует и отвечает.

    Раунд правок 1 (ревью задачи 10) нашёл регрессию ровно там, где
    единственная прежде фикстура (`es_client_without_en_index`) не могла её
    заметить: под индексом, которого «нет», find_1c_help с любым запросом
    обрывается раньше поиска, и неважно, режет ли _language_mismatch заодно и
    query — до реального search() дело не доходит вовсе. Здесь индекс есть,
    и search() возвращает настоящий (пусть и один) документ, так что видно,
    дошёл ли вызов до Elasticsearch или его подавили раньше срока.
    """
    from unittest.mock import AsyncMock

    client = AsyncMock()
    client.index_exists = AsyncMock(return_value=True)
    client.search = AsyncMock(return_value={
        "hits": {
            "hits": [{
                "_score": 12.5,
                "_source": {
                    "type": "object_function",
                    "element_kind": "function",
                    "name_ru": "Add",
                    "name_en": "",
                    "object": "FormDataCollection",
                    "full_path": "FormDataCollection.Add",
                    "call_primary": "FormDataCollection.Add(<Item>)",
                    "description": "Adds an item to the collection.",
                },
            }],
            "total": {"value": 1},
        },
    })
    return client


@pytest.fixture
def mock_elasticsearch():
    """Мок для Elasticsearch клиента."""
    from unittest.mock import Mock
    
    mock_client = Mock()
    mock_client.is_connected.return_value = True
    mock_client.index_exists.return_value = True
    mock_client.get_documents_count.return_value = 100
    
    return mock_client


@pytest.fixture
def mock_parsed_hbk():
    """Mock данных распарсенного .hbk файла для unit тестов."""
    from src.models.doc_models import (
        ParsedHBK, Documentation, DocumentType,
        HBKFile, Parameter, SyntaxVariant
    )
    from datetime import datetime

    # Создаём тестовые документы. Синтаксис, параметры и тип возврата лежат
    # внутри variants — у модели больше нет отдельных полей для них
    # на самом документе. Полей name_en/object_en (Documentation), name_en
    # (Parameter), name_en/count (CategoryInfo) в моделях нет и не было —
    # раньше pydantic молча их игнорировал, фикстура не должна делать вид,
    # что они существуют.
    docs = [
        Documentation(
            id="global_func_add",
            name="Добавить",
            type=DocumentType.GLOBAL_FUNCTION,
            object=None,
            element_kind="функция",
            description="Добавляет значение в массив",
            variants=[
                SyntaxVariant(
                    syntax="Добавить(<Значение>)",
                    parameters=[
                        Parameter(
                            name="Значение",
                            type="Произвольный",
                            description="Добавляемое значение",
                            required=True
                        )
                    ],
                    return_type="Булево",
                )
            ],
            version_from="8.3.5",
            examples=["Массив.Добавить(10);"],
            source_file="GlobalContext/Add.html",
        ),
        Documentation(
            id="global_func_delete",
            name="Удалить",
            type=DocumentType.GLOBAL_FUNCTION,
            object=None,
            element_kind="функция",
            description="Удаляет элемент из массива",
            variants=[
                SyntaxVariant(
                    syntax="Удалить(<Индекс>)",
                    parameters=[
                        Parameter(
                            name="Индекс",
                            type="Число",
                            description="Индекс удаляемого элемента",
                            required=True
                        )
                    ],
                )
            ],
            version_from="8.3.5",
            examples=["Массив.Удалить(0);"],
            source_file="GlobalContext/Delete.html",
        ),
        Documentation(
            id="object_array_count",
            name="Количество",
            type=DocumentType.OBJECT_PROPERTY,
            object="Массив",
            element_kind="свойство",
            description="Возвращает количество элементов в массиве",
            variants=[
                SyntaxVariant(
                    syntax="Массив.Количество()",
                    return_type="Число",
                )
            ],
            version_from="8.0",
            examples=["КоличествоЭлементов = Массив.Количество();"],
            source_file="Objects/Array/Count.html",
        ),
        Documentation(
            id="object_array_clear",
            name="Очистить",
            type=DocumentType.OBJECT_PROCEDURE,
            object="Массив",
            element_kind="процедура",
            description="Очищает массив",
            variants=[
                SyntaxVariant(syntax="Массив.Очистить()")
            ],
            version_from="8.0",
            examples=["Массив.Очистить();"],
            source_file="Objects/Array/Clear.html",
        ),
        Documentation(
            id="event_before_write",
            name="ПередЗаписью",
            type=DocumentType.GLOBAL_EVENT,
            object=None,
            element_kind="событие",
            description="Событие перед записью объекта",
            variants=[
                SyntaxVariant(
                    syntax="Процедура ПередЗаписью(Отказ)",
                    parameters=[
                        Parameter(
                            name="Отказ",
                            type="Булево",
                            description="Признак отказа от записи",
                            required=True
                        )
                    ],
                )
            ],
            version_from="8.0",
            examples=["Процедура ПередЗаписью(Отказ)\n  // Код обработчика\nКонецПроцедуры"],
            source_file="Events/BeforeWrite.html",
        )
    ]

    # full_path, call_primary, variants[].call и id собирает build_call_strings() —
    # фикстура не должна дублировать эту логику вручную.
    for d in docs:
        d.build_call_strings()

    # Создаём информацию о файле
    file_info = HBKFile(
        path="data/hbk/test.hbk",
        size=1024 * 1024,  # 1 MB
        modified=1234567890.0,
        entries_count=5
    )

    # Создаём статистику
    stats = {
        'html_files': 5,
        'processed_html': 5,
        'total_docs': 5,
        'by_type': 5
    }

    # Создаём категории
    from src.models.doc_models import CategoryInfo
    categories = {
        'Глобальный контекст': CategoryInfo(name='Глобальный контекст'),
        'Массив': CategoryInfo(name='Массив'),
        'События': CategoryInfo(name='События')
    }

    return ParsedHBK(
        file_info=file_info,
        documentation=docs,
        categories=categories,
        stats=stats,
        errors=[],
        pages_attempted=5,
        pages_parsed=5,
    )


@pytest.fixture
async def mock_elasticsearch_indexer():
    """Mock ElasticsearchIndexer для unit тестов."""
    from unittest.mock import AsyncMock, Mock
    
    indexer = Mock()
    indexer.reindex_all = AsyncMock(return_value=True)
    indexer.index_documentation = AsyncMock(return_value=100)
    
    return indexer


NO_PAGE = 0x7FFFFFFF
BLOCK_HEADER_SIZE = 31
ELEMENT_NAME_OFFSET = 20


def _pages(body: bytes, page_size: int, start: int) -> bytes:
    """Тело элемента как цепочка страниц, начинающаяся по адресу start."""
    pages = [body[i:i + page_size] for i in range(0, len(body), page_size)] or [b""]
    out = bytearray()
    position = start
    for number, page in enumerate(pages):
        position += BLOCK_HEADER_SIZE + page_size
        following = position if number + 1 < len(pages) else NO_PAGE
        declared = len(body) if number == 0 else page_size
        out += b"\r\n%08x %08x %08x \r\n" % (declared, page_size, following)
        out += page.ljust(page_size, b"\x00")
    return bytes(out)


def build_container(elements: dict, page_size: int = 512) -> bytes:
    """Контейнер V8 из именованных элементов."""
    table_page = max(page_size, 12 * len(elements))
    cursor = 16 + BLOCK_HEADER_SIZE + table_page
    table, body = bytearray(), bytearray()

    for name, content in elements.items():
        header = b"\x00" * ELEMENT_NAME_OFFSET + name.encode("utf-16-le") + b"\x00\x00"
        header_block = _pages(header, page_size, cursor)
        body += header_block
        table_entry = [cursor]
        cursor += len(header_block)
        if content is not None:
            data_block = _pages(content, page_size, cursor)
            table_entry.append(cursor)
            body += data_block
            cursor += len(data_block)
        else:
            table_entry.append(NO_PAGE)
        table_entry.append(NO_PAGE)
        table += struct.pack("<III", *table_entry)

    file_header = struct.pack("<IIII", NO_PAGE, page_size, 1, 0)
    table_block = (
        b"\r\n%08x %08x %08x \r\n" % (len(table), table_page, NO_PAGE)
        + bytes(table).ljust(table_page, b"\x00")
    )
    return file_header + table_block + bytes(body)


def zip_of(files: dict) -> bytes:
    """Zip в памяти — содержимое элемента FileStorage книги справки."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def write_book(path: Path, files: dict, page_size: int = 512, extra: dict = None) -> Path:
    """Книга справки из готовых файлов, для тестов без настоящей поставки 1С."""
    elements = {"Book": b'{7,"Test"}', "FileStorage": zip_of(files)}
    elements.update(extra or {})
    path.write_bytes(build_container(elements, page_size=page_size))
    return path


FIXTURES_RU = Path(__file__).parent / "fixtures" / "hbk"

ARCHIVE_PATHS_RU = {
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
    # Третий параметр называется по-английски («AddInName») внутри в остальном
    # кириллической страницы — регрессия на _serialize_for_reparsing, см. тест
    # test_latin_placeholder_survives_reparsing_in_russian_page в
    # tests/test_parser_element_card.py.
    "serveragentconnection_unregsecurityprofileaddin.html":
        "objects/catalog1369/catalog1384/catalog1386/IServerAgentConnection/"
        "methods/UnregSecurityProfileAddIn4409.html",
    # У этого метода V8SH_pagetitle — «Прочитать (Read)», без имени
    # объекта-владельца вовсе (страница не повторяет длинное имя расширения).
    "extdatasource_record_read.html":
        "objects/catalog1649/catalog1890/Client application form extension "
        "for external data source table record/methods/Read4577.html",
    # «СправочникМенеджер.<Имя справочника> (CatalogManager.<Catalog name>)» —
    # точка есть и в русской, и в английской половине заголовка.
    "catalogmanager_object.html":
        "objects/catalog125/catalog126/object128.html",
}


@pytest.fixture
def hbk_fixture_archive(tmp_path):
    """Маленькая книга справки из фикстурных страниц, по их путям в книге."""
    pages = {
        archive_path_inside: (FIXTURES_RU / fixture_name).read_bytes()
        for fixture_name, archive_path_inside in ARCHIVE_PATHS_RU.items()
    }
    return write_book(tmp_path / "fixture_book.hbk", pages)


FIXTURES_ARTICLES = Path(__file__).parent / "fixtures" / "articles"

ARTICLE_PAGES_RU = {
    "shlang": ("struct_for.html", "array_article.html"),
    "shquery": ("union_section.html", "overall_totals.html"),
    "dcsui": ("functions_group.html", "saving_settings.html"),
}


@pytest.fixture
def article_books_directory(tmp_path):
    """Каталог книг статей из фикстурных страниц; книги shclang в нём нет."""
    from src.core.constants import ARTICLE_BOOKS

    directory = tmp_path / "hbk"
    directory.mkdir()
    for book in ARTICLE_BOOKS:
        pages = ARTICLE_PAGES_RU.get(book.key)
        if pages:
            write_book(directory / book.ru, {
                page: (FIXTURES_ARTICLES / page).read_bytes() for page in pages
            })
    return directory


@pytest.fixture
async def isolated_index():
    """Имя индекса, который тест вправе перестраивать, и уборка за ним."""
    from src.core.elasticsearch import ElasticsearchClient

    index = "help1c_docs_test"
    client = ElasticsearchClient()
    await client.connect()
    try:
        yield index
    finally:
        await client.delete_index(index=index)
        await client.disconnect()


@pytest.fixture(autouse=True)
def refuse_writes_to_the_production_index(monkeypatch):
    """Читать боевой индекс тест вправе, перестраивать — нет."""
    from src.core.config import settings
    from src.parsers.indexer import ElasticsearchIndexer

    original = ElasticsearchIndexer.reindex_all

    async def guarded(self, *args, **kwargs):
        if self.index in (None, settings.elasticsearch_index, settings.elasticsearch_index_en):
            pytest.fail(
                f"тест перестраивает боевой индекс "
                f"{self.index or settings.elasticsearch_index}; "
                f"возьмите свой через фикстуру isolated_index",
                pytrace=False,
            )
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(ElasticsearchIndexer, "reindex_all", guarded)

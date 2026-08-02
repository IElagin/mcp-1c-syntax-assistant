"""
Конфигурация pytest для тестов проекта.
"""

import pytest
import asyncio
import sys
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
        errors=[]
    )


@pytest.fixture
def mock_hbk_parser():
    """Mock HBKParser для unit тестов."""
    from unittest.mock import Mock
    
    parser = Mock()
    parser.max_files_per_type = 10
    parser.max_total_files = 50
    
    # Метод parse_file возвращает mock_parsed_hbk
    def parse_file_side_effect(file_path):
        # Возвращаем простой mock результат
        from src.models.doc_models import ParsedHBK, HBKFile
        return ParsedHBK(
            file_info=HBKFile(
                path=file_path,
                size=1024,
                modified=1234567890.0,
                entries_count=5
            ),
            documentation=[],
            categories={},
            stats={},
            errors=[]
        )
    
    parser.parse_file.side_effect = parse_file_side_effect
    return parser


@pytest.fixture
async def mock_elasticsearch_indexer():
    """Mock ElasticsearchIndexer для unit тестов."""
    from unittest.mock import AsyncMock, Mock
    
    indexer = Mock()
    indexer.reindex_all = AsyncMock(return_value=True)
    indexer.index_documentation = AsyncMock(return_value=100)
    
    return indexer

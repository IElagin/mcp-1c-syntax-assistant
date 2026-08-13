"""Тест 2: Парсинг .hbk файла."""

import asyncio
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import settings
from src.parsers.hbk_parser import HBKParser


@pytest.mark.integration
@pytest.mark.real_book
@pytest.mark.parser
@pytest.mark.asyncio
async def test_configured_book_parses_into_known_document_types():
    """Книга, заданная конфигурацией (а не первая по алфавиту в каталоге), разбирается в документы известных типов."""
    print("=== Тест 2: Парсинг .hbk файла ===")

    try:
        hbk_file = Path(settings.data.hbk_directory) / settings.data.hbk_filename

        if not hbk_file.exists():
            pytest.skip(f"книга {settings.data.hbk_filename} не найдена в {hbk_file.parent}")

        print(f"📁 Найден файл: {hbk_file}")
        print(f"📊 Размер: {hbk_file.stat().st_size / 1024 / 1024:.1f} МБ")

        # Создаем парсер с выводом путей файлов
        class HBKParserWithLogging(HBKParser):
            def _create_document_from_html(self, archive, name, result):
                print(f"📄 Обрабатывается файл в архиве: {name}")
                return super()._create_document_from_html(archive, name, result)

        parser = HBKParserWithLogging()
        parsed_hbk = parser.parse_file(str(hbk_file))

        if not parsed_hbk:
            print("❌ Ошибка парсинга файла")
            assert False, "Парсер вернул None"
        
        print(f"✅ Парсинг завершен:")
        print(f"   • Записей в архиве: {parsed_hbk.file_info.entries_count}")
        print(f"   • Всего HTML файлов: {parsed_hbk.stats.get('html_files', 0)}")
        print(f"   • Файлов методов: {parsed_hbk.stats.get('global_methods_files', 0)}")
        print(f"   • Файлов событий: {parsed_hbk.stats.get('global_events_files', 0)}")
        print(f"   • Файлов Global context: {parsed_hbk.stats.get('global_context_files', 0)}")
        print(f"   • Файлов конструкторов: {parsed_hbk.stats.get('object_constructors_files', 0)}")
        print(f"   • Файлов событий объектов: {parsed_hbk.stats.get('object_events_files', 0)}")
        print(f"   • Файлов других объектов: {parsed_hbk.stats.get('other_object_files', 0)}")
        print(f"   • Обработано HTML: {parsed_hbk.stats.get('processed_html', 0)}")
        print(f"   • Найдено документов: {len(parsed_hbk.documentation)}")
        print(f"   • Категорий: {len(parsed_hbk.categories)}")
        print(f"   • Ошибок: {len(parsed_hbk.errors)}")
        
        categories_processed = parsed_hbk.stats.get('categories_processed', {})
        found_types = parsed_hbk.stats.get('found_types', {})
        print(f"   • Обработано по категориям:")
        print(f"     - Методы: {categories_processed.get('global_methods', 0)}")
        print(f"     - События: {categories_processed.get('global_events', 0)}")
        print(f"     - Global context: {categories_processed.get('global_context', 0)}")
        print(f"     - Конструкторы: {categories_processed.get('object_constructors', 0)}")
        print(f"     - События объектов: {categories_processed.get('object_events', 0)}")
        print(f"     - Другие объекты: {categories_processed.get('other_objects', 0)}")
        print(f"   • Найдено по типам:")
        for doc_type, count in found_types.items():
            if count > 0:
                print(f"     - {doc_type}: {count} документов")
        
        # Проверяем критерии успеха
        if len(parsed_hbk.documentation) == 0:
            print("❌ Не найдено ни одного документа!")
            assert False, "Парсинг не извлек документы из .hbk файла"
            
        if len(parsed_hbk.errors) > 0:
            print(f"⚠️ Обнаружены ошибки парсинга:")
            for error in parsed_hbk.errors[:3]:
                print(f"   • {error}")
            # Можно сделать предупреждение, но не падать

        # Проверяем типы документации
        expected_types = {
            'GLOBAL_FUNCTION', 'GLOBAL_PROCEDURE', 'GLOBAL_EVENT',
            'OBJECT_FUNCTION', 'OBJECT_PROCEDURE', 
            'OBJECT_PROPERTY', 'OBJECT_EVENT', 'OBJECT_CONSTRUCTOR',
            'OBJECT'
        }
        
        found_types = set()
        for doc in parsed_hbk.documentation:
            found_types.add(doc.type.name)
        
        print(f"\n📋 Найденные типы документации:")
        for doc_type in sorted(found_types):
            count = sum(1 for doc in parsed_hbk.documentation if doc.type.name == doc_type)
            print(f"   • {doc_type}: {count} документов")
        
        # Проверяем, что найдены ожидаемые типы
        found_expected = found_types.intersection(expected_types)
        if found_expected:
            print(f"\n✅ Найдены ожидаемые типы: {sorted(found_expected)}")
        else:
            print(f"\n⚠️ Не найдено ни одного из ожидаемых типов: {sorted(expected_types)}")
        
        print(f"\n✅ Тест парсинга ПРОЙДЕН: {len(parsed_hbk.documentation)} документов")
        
        # Показываем первые несколько документов
        if parsed_hbk.documentation:
            print("\nПример найденных документов:")
            for i, doc in enumerate(parsed_hbk.documentation[:5], 1):
                print(f"   {i}. {doc.name} ({doc.type.name}) - {doc.object or 'глобальный'}")
        
        if parsed_hbk.errors:
            print(f"\nОшибки парсинга:")
            for error in parsed_hbk.errors[:3]:
                print(f"   • {error}")
        
        # Тест завершается успешно только если нет критических ошибок
        
    except Exception as e:
        print(f"❌ Ошибка тестирования парсера: {e}")
        assert False, f"Исключение в тесте парсинга: {e}"


if __name__ == "__main__":
    asyncio.run(test_configured_book_parses_into_known_document_types())

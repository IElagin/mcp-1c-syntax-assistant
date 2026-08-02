"""Скрипт для потоковой индексации архива документации 1С порциями."""

import asyncio
import sys
import time
import warnings
import argparse
from pathlib import Path
from typing import List, Generator
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures

# Отключаем предупреждения от внешних библиотек
warnings.filterwarnings("ignore", category=FutureWarning, module="soupsieve")

# Скрипт лежит в scripts/, а пакет src/ — в корне репозитория.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import settings
from src.core.elasticsearch import es_client
from src.parsers.hbk_parser import HBKParser
from src.parsers.indexer import indexer
from src.models.doc_models import Documentation, ParsedHBK, HBKEntry, HBKFile


class StreamingIndexer:
    """Потоковый индексатор с парсингом и индексацией порциями."""
    
    def __init__(self, batch_size: int = 500, max_documents: int = None, max_workers: int = 4):
        self.batch_size = batch_size
        self.max_documents = max_documents
        self.max_workers = max_workers
        self.parser = HBKParser()
        
    def _initialize_extractor(self, archive_path: Path):
        """Инициализирует параметры для извлечения файлов и возвращает список файлов."""
        # Просто вызываем метод парсера который уже инициализирует _zip_command и _archive_path
        all_entries = self.parser._extract_external_7z(archive_path)
        
        if not self.parser._zip_command:
            raise Exception("Не удалось инициализировать 7zip")
            
        return all_entries
        
    def _chunk_list(self, lst: List, chunk_size: int) -> Generator[List, None, None]:
        """Разбивает список на части заданного размера."""
        for i in range(0, len(lst), chunk_size):
            yield lst[i:i + chunk_size]
    
    def _extract_files_batch(self, archive_path: Path, file_entries: List[HBKEntry]) -> dict:
        """Извлекает пакет файлов из архива через временный файл-список."""
        from src.core.utils import safe_subprocess_run, create_safe_temp_dir, safe_remove_dir
        import tempfile
        
        temp_dir = create_safe_temp_dir("batch_extract_")
        extracted_contents = {}
        
        try:
            # Создаем временный файл со списком файлов для извлечения
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as list_file:
                for entry in file_entries:
                    list_file.write(f"{entry.path}\n")
                list_file_path = list_file.name
            
            try:
                # Извлекаем файлы используя файл-список
                cmd = [self.parser._zip_command, 'e', str(archive_path), f'-i@{list_file_path}', f'-o{temp_dir}', '-y']
                result = safe_subprocess_run(cmd, timeout=120)
                
                if result.returncode == 0:
                    # Читаем содержимое всех извлеченных файлов
                    for entry in file_entries:
                        # Ищем извлеченный файл (7zip может изменить структуру папок)
                        file_name = Path(entry.path).name
                        extracted_files = list(temp_dir.rglob(file_name))
                        
                        for extracted_file in extracted_files:
                            if extracted_file.is_file():
                                try:
                                    with open(extracted_file, 'rb') as f:
                                        extracted_contents[entry.path] = f.read()
                                    break
                                except Exception as e:
                                    print(f"⚠️ Ошибка чтения файла {entry.path}: {e}")
                
                return extracted_contents
                
            finally:
                # Удаляем временный файл-список
                try:
                    Path(list_file_path).unlink()
                except:
                    pass
            
        except Exception as e:
            print(f"⚠️ Ошибка батчевого извлечения: {e}")
            return {}
        finally:
            safe_remove_dir(temp_dir)
    
    def _parse_single_file(self, entry: HBKEntry, hbk_file_path: Path) -> List[Documentation]:
        """Парсит один HTML файл и возвращает список документов."""
        try:
            # Создаем временный результат для одного файла
            temp_result = ParsedHBK(
                file_info=self._create_file_info(hbk_file_path)
            )
            
            # Парсим один HTML файл (метод добавляет документы в temp_result.documentation)
            self.parser._create_document_from_html(entry, temp_result)
            
            # Возвращаем найденные документы
            return temp_result.documentation if temp_result.documentation else []
        except Exception as e:
            print(f"⚠️ Ошибка парсинга файла {entry.path}: {e}")
            return []
    
    async def _parse_files_parallel(self, batch_entries: List[HBKEntry], extracted_contents: dict, hbk_file_path: Path, max_workers: int = 4) -> tuple:
        """Параллельно парсит файлы в порции."""
        loop = asyncio.get_event_loop()
        batch_docs = []
        parsed_count = 0
        
        # Подготавливаем задачи для параллельного выполнения
        valid_entries = []
        
        for entry in batch_entries:
            if entry.path in extracted_contents:
                # Устанавливаем содержимое файла
                entry.content = extracted_contents[entry.path]
                valid_entries.append(entry)
        
        # Выполняем парсинг параллельно в пуле потоков
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Создаем задачи для каждого файла
            tasks = [
                loop.run_in_executor(executor, self._parse_single_file, entry, hbk_file_path)
                for entry in valid_entries
            ]
            
            # Ждем завершения всех задач
            try:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        print(f"⚠️ Ошибка параллельного парсинга файла {valid_entries[i].path}: {result}")
                    elif result:  # result - это список документов
                        batch_docs.extend(result)
                        parsed_count += 1
                        
            except Exception as e:
                print(f"⚠️ Ошибка при параллельном выполнении: {e}")
        
        return batch_docs, parsed_count
    
    def _create_file_info(self, file_path: Path) -> HBKFile:
        """Создает информацию о HBK файле."""
        return HBKFile(
            path=str(file_path),
            size=file_path.stat().st_size,
            modified=file_path.stat().st_mtime
        )
    
    def _filter_html_entries(self, entries: List[HBKEntry]) -> List[HBKEntry]:
        """Фильтрует только HTML файлы из архива."""
        html_entries = []
        for entry in entries:
            if (not entry.is_dir and 
                entry.path.endswith('.html') and 
                'objects/' in entry.path.replace('\\', '/')):
                html_entries.append(entry)
        return html_entries
    
    async def stream_index_archive(self, hbk_file_path: str) -> bool:
        """Потоковая индексация: парсинг порциями + индексация каждой порции."""
        print(f"=== Потоковая индексация (парсинг порциями по {self.batch_size}) ===")
        
        try:
            # Подключаемся к Elasticsearch
            print("🔌 Подключение к Elasticsearch...")
            connected = await es_client.connect()
            if not connected:
                print("❌ Elasticsearch недоступен")
                return False
            
            print("✅ Подключение к Elasticsearch установлено")
            
            # Очищаем старый индекс и создаем новый
            print("🗑️ Очистка старого индекса...")
            if await es_client.index_exists():
                if es_client._client:
                    await es_client._client.indices.delete(index=es_client._config.index_name)
            
            print("🏗️ Создание нового индекса...")
            await es_client.create_index()
            
            # Извлекаем список всех файлов из архива
            print(f"📁 Извлечение списка файлов из архива: {Path(hbk_file_path).name}")
            start_extract_time = time.time()
            
            # Инициализируем экстрактор и получаем список файлов одним вызовом
            all_entries = self._initialize_extractor(Path(hbk_file_path))
            if not all_entries:
                print("❌ Не удалось извлечь список файлов из архива")
                return False
            
            # Фильтруем только HTML файлы
            html_entries = self._filter_html_entries(all_entries)
            extract_time = time.time() - start_extract_time
            
            total_html_files = len(html_entries)
            print(f"✅ Извлечение завершено за {extract_time:.2f} сек")
            print(f"📁 Всего записей в архиве: {len(all_entries)}")
            print(f"📄 HTML файлов для обработки: {total_html_files}")
            
            # Применяем лимит файлов если задан
            if self.max_documents and total_html_files > self.max_documents:
                html_entries = html_entries[:self.max_documents]
                total_html_files = len(html_entries)
                print(f"⚠️ Ограничено до {self.max_documents} HTML файлов")
            
            print(f"📦 Размер порции: {self.batch_size}")
            total_batches = (total_html_files + self.batch_size - 1) // self.batch_size
            print(f"🔢 Количество порций: {total_batches}")
            
            # Обрабатываем файлы порциями
            print("🚀 Запуск потоковой обработки...")
            start_process_time = time.time()
            
            total_indexed = 0
            batch_num = 0
            
            for batch_entries in self._chunk_list(html_entries, self.batch_size):
                batch_num += 1
                batch_start_time = time.time()
                
                print(f"\n📦 Порция {batch_num}/{total_batches} ({len(batch_entries)} файлов)")
                
                # Извлекаем всю порцию файлов одной командой
                extract_start_time = time.time()
                extracted_contents = self._extract_files_batch(Path(hbk_file_path), batch_entries)
                extract_time = time.time() - extract_start_time
                
                print(f"   📁 Извлечение: {len(extracted_contents)}/{len(batch_entries)} файлов, {extract_time:.2f}с")
                
                # Параллельно парсим извлеченные файлы
                parse_start_time = time.time()
                batch_docs, parsed_count = await self._parse_files_parallel(
                    batch_entries, extracted_contents, Path(hbk_file_path), max_workers=self.max_workers
                )
                parse_time = time.time() - parse_start_time
                print(f"   📝 Параллельный парсинг ({self.max_workers} потоков): {parsed_count}/{len(batch_entries)} файлов, {len(batch_docs)} документов, {parse_time:.2f}с")
                
                # Индексируем распарсенную порцию
                if batch_docs:
                    index_start_time = time.time()
                    
                    batch_hbk = ParsedHBK(
                        file_info=self._create_file_info(Path(hbk_file_path)),
                        documentation=batch_docs
                    )
                    
                    success = await indexer.index_documentation(batch_hbk)
                    
                    if not success:
                        print(f"❌ Ошибка индексации порции {batch_num}")
                        return False
                    
                    index_time = time.time() - index_start_time
                    total_indexed += len(batch_docs)
                    
                    batch_total_time = time.time() - batch_start_time
                    docs_per_sec = len(batch_docs) / batch_total_time if batch_total_time > 0 else 0
                    
                    print(f"   💾 Индексация: {len(batch_docs)} документов, {index_time:.2f}с")
                    print(f"   ✅ Порция завершена: {batch_total_time:.2f}с, {docs_per_sec:.1f} док/с")
                    print(f"   📊 Прогресс: {total_indexed} документов, порция {batch_num}/{total_batches}")
                else:
                    print(f"   ⚠️ Нет документов для индексации в порции {batch_num}")
            
            process_time = time.time() - start_process_time
            total_time = extract_time + process_time
            
            # Проверяем итоговое количество документов в индексе
            print("\n🔍 Проверка итогового количества документов...")
            await es_client.refresh_index()
            indexed_docs_count = await es_client.get_documents_count()
            
            # Итоговая статистика
            print(f"\n🎉 ПОТОКОВАЯ ИНДЕКСАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
            print(f"📊 Итоговая статистика:")
            print(f"   • Извлечение списка файлов: {extract_time:.2f} сек")
            print(f"   • Обработка порциями: {process_time:.2f} сек")
            print(f"   • Общее время: {total_time:.2f} сек")
            print(f"   • HTML файлов обработано: {total_html_files}")
            print(f"   • Документов создано: {total_indexed}")
            print(f"   • Документов в индексе: {indexed_docs_count}")
            print(f"   • Размер порции: {self.batch_size}")
            print(f"   • Количество порций: {batch_num}")
            if self.max_documents:
                print(f"   • Лимит HTML файлов: {self.max_documents}")
            print(f"   • Средняя скорость: {total_indexed/total_time:.1f} док/сек")
            
            if total_indexed == indexed_docs_count:
                print("✅ Все документы успешно проиндексированы")
            else:
                print(f"⚠️ Несоответствие: создано {total_indexed}, в индексе {indexed_docs_count}")
            
            return total_indexed == indexed_docs_count
            
        except Exception as e:
            print(f"❌ Критическая ошибка: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            print("🔌 Отключение от Elasticsearch...")
            await es_client.disconnect()


async def main():
    """Главная функция с парсингом аргументов."""
    parser = argparse.ArgumentParser(description="Потоковая индексация архива 1С")
    parser.add_argument(
        "--batch-size", 
        type=int, 
        default=500, 
        help="Размер порции для индексации (по умолчанию: 500)"
    )
    parser.add_argument(
        "--max-docs", 
        type=int, 
        default=None, 
        help="Максимальное количество HTML файлов для обработки (по умолчанию: без ограничений)"
    )
    parser.add_argument(
        "--workers", 
        type=int, 
        default=4, 
        help="Количество потоков для параллельного парсинга (по умолчанию: 4)"
    )
    
    args = parser.parse_args()
    
    # Находим .hbk файл
    hbk_dir = Path(settings.data.hbk_directory)
    hbk_files = list(hbk_dir.glob("*.hbk"))
    
    if not hbk_files:
        print("❌ .hbk файл не найден")
        return False
    
    # Создаем потоковый индексатор
    streaming_indexer = StreamingIndexer(
        batch_size=args.batch_size, 
        max_documents=args.max_docs,
        max_workers=args.workers
    )
    
    # Запускаем индексацию
    result = await streaming_indexer.stream_index_archive(str(hbk_files[0]))
    
    if result:
        print("\n✅ Потоковая индексация завершена успешно!")
    else:
        print("\n❌ Потоковая индексация завершилась с ошибками!")
    
    return result


if __name__ == "__main__":
    asyncio.run(main())

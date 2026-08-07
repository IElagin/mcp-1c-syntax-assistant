
"""Парсер .hbk файлов (архивы документации 1С)."""

import os
import tempfile
import re
from collections import defaultdict
from typing import Optional, List, Dict, Any
from pathlib import Path

from src.models.doc_models import HBKFile, HBKEntry, ParsedHBK, CategoryInfo, Documentation, DocumentType
from src.core.logging import get_logger
from src.parsers.html_parser import HTMLParser
from src.parsers.dialects import HelpDialect, RU_DIALECT
from src.core.utils import (
    safe_subprocess_run,
    SafeSubprocessError,
    create_safe_temp_dir,
    safe_remove_dir,
    validate_file_path
)
from src.core.constants import MAX_FILE_SIZE_MB, SUPPORTED_ENCODINGS, BATCH_SIZE

logger = get_logger(__name__)


class HBKParserError(Exception):
    """Исключение для ошибок парсера HBK."""
    pass


def _is_empty_object_stub(doc: Documentation) -> bool:
    """Страница-раздел книги без адресуемого содержимого, а не настоящий объект.

    У части каталожных «оглавлений» V8SH_pagetitle совпадает с именем
    настоящего объекта (пример — «Запрос»: настоящий объект и рядом отдельная
    служебная запись «в этом разделе описываются системные перечисления
    запроса»). Такая запись не даёт парсеру разобрать ни описания (проза
    оглавления не оформлена разделом «Описание:»), ни состава — zero content
    надёжнее эвристики по имени файла или пути.
    """
    return (
        doc.type == DocumentType.OBJECT
        and not doc.description
        and not doc.methods
        and not doc.properties
        and not doc.events
    )


def deduplicate_by_id(documents: List[Documentation]) -> List[Documentation]:
    """Устраняет столкновения id — иначе один документ в Elasticsearch стирает другой.

    id собирается из object+name+type (Documentation.build_call_strings), а
    книга не гарантирует, что эта тройка уникальна: у части объектов
    заголовок страницы совпадает с заголовком не связанного с ним раздела
    книги, а у некоторых пар объектов и вовсе одинаковое отображаемое имя при
    разном содержании — 1С называет их одинаково, и различить эти случаи
    можно только по source_file, который в архиве уникален по построению.

    Правило:
    - Если среди столкнувшихся документов есть хотя бы одна пустая
      страница-заглушка (см. _is_empty_object_stub) и хотя бы один документ с
      реальным содержимым — заглушки выбрасываются целиком: они не несут
      ничего, что жаль было бы потерять, а оставлять их значило бы отдавать
      «чистый» id по недетерминированному принципу (в зависимости от порядка
      батчей то заглушке, то настоящему объекту).
    - Иначе (все документы группы содержательны, либо все пусты) столкновение
      решается добавлением различителя "#2", "#3"... — группа сортируется по
      source_file (единственное, что гарантированно уникально и не зависит
      от порядка разбора), поэтому распределение различителей одно и то же
      при каждой переиндексации той же книги.

    Args:
        documents: Документы одной книги за один проход разбора.

    Returns:
        Документы с уникальными id, в исходном порядке; часть пустых
        страниц-заглушек может отсутствовать.
    """
    by_id: Dict[str, List[Documentation]] = defaultdict(list)
    for doc in documents:
        by_id[doc.id].append(doc)

    dropped_object_ids = set()
    for doc_id, group in by_id.items():
        if len(group) == 1:
            continue

        stubs = [d for d in group if _is_empty_object_stub(d)]
        non_stubs = [d for d in group if not _is_empty_object_stub(d)]
        survivors = non_stubs if (stubs and non_stubs) else group

        for d in stubs:
            if d in survivors:
                continue
            dropped_object_ids.add(id(d))

        if len(survivors) <= 1:
            continue

        # source_file уникален и не зависит от порядка разбора — сортировка
        # по нему делает распределение "#2"/"#3" стабильным между запусками.
        ordered = sorted(survivors, key=lambda d: d.source_file or "")
        for n, doc in enumerate(ordered[1:], start=2):
            doc.id = f"{doc_id}#{n}"

    return [d for d in documents if id(d) not in dropped_object_ids]


class HBKParser:
    """Парсер .hbk архивов с документацией 1С."""
    
    def __init__(
        self,
        max_files_per_type: Optional[int] = None,
        max_total_files: Optional[int] = None,
        dialect: HelpDialect = RU_DIALECT,
    ):
        self.supported_extensions = ['.hbk', '.zip', '.7z']
        self._zip_command = None
        self._archive_path = None
        self._max_file_size = MAX_FILE_SIZE_MB * 1024 * 1024  # MB в байты
        self.dialect = dialect
        # Диалект прокидывается в HTMLParser: разбор английской книги
        # отличается от русской только текстом заголовков разделов, а не
        # структурой кода, поэтому HBKParser не ветвится по языку сам.
        self.html_parser = HTMLParser(dialect=dialect)
        
        # Параметры ограничений для тестирования
        self.max_files_per_type = max_files_per_type  # None = без ограничений
        self.max_total_files = max_total_files        # None = парсить все файлы
    
    def parse_file(self, file_path: str) -> Optional[ParsedHBK]:
        """Парсит .hbk файл и извлекает содержимое."""
        file_path = Path(file_path)
        
        # Валидация входного файла
        try:
            validate_file_path(file_path, self.supported_extensions)
        except SafeSubprocessError as e:
            logger.error(f"Валидация файла не прошла: {e}")
            return None
        
        # Проверка размера файла
        if file_path.stat().st_size > self._max_file_size:
            logger.error(f"Файл слишком большой: {file_path.stat().st_size / 1024 / 1024:.1f}MB")
            return None
        
        # Создаем объект результата
        result = ParsedHBK(
            file_info=HBKFile(
                path=str(file_path),
                size=file_path.stat().st_size,
                modified=file_path.stat().st_mtime
            )
        )
        
        try:
            # Пробуем разные методы извлечения
            entries = self._extract_archive(file_path)
            if not entries:
                result.errors.append("Не удалось извлечь файлы из архива")
                return result
            
            result.file_info.entries_count = len(entries)
            
            # Анализируем структуру и извлекаем документацию
            self._analyze_structure(entries, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка парсинга файла {file_path}: {e}")
            result.errors.append(f"Ошибка парсинга: {str(e)}")
            return result
    
    def _extract_archive(self, file_path: Path) -> List[HBKEntry]:
        """Извлекает содержимое архива через внешний 7zip."""
        try:
            entries = self._extract_external_7z(file_path)
            if entries:
                return entries
            else:
                logger.error(f"Не удалось извлечь файлы из архива: {file_path}")
                return []
        except Exception as e:
            logger.error(f"Ошибка обработки архива через 7zip: {e}")
            return []
    
    def _analyze_structure(self, entries: List[HBKEntry], result: ParsedHBK):
        """Анализирует структуру архива и извлекает документацию."""
        
        # Статистика
        html_files = 0
        st_files = 0
        category_files = 0
        
        # Собираем все HTML файлы
        html_entries = []
        
        for entry in entries:
            if entry.is_dir:
                continue
                
            path_parts = entry.path.replace('\\', '/').split('/')
            
            # Анализируем файлы __categories__
            if path_parts[-1] == '__categories__':
                category_files += 1
                self._parse_categories_file(entry, result)
                continue
            
            # Собираем .html файлы
            if entry.path.endswith('.html'):
                html_files += 1
                if 'objects/' in entry.path or 'objects\\' in entry.path:
                    html_entries.append(entry)
                continue
            
            # Анализируем .st файлы (шаблоны)
            if entry.path.endswith('.st'):
                st_files += 1
                continue
        
        logger.info(f"Найдено HTML файлов для парсинга: {len(html_entries)}")
        
        # Обрабатываем файлы батчами
        batch_size = BATCH_SIZE
        processed_html = 0
        
        for i in range(0, len(html_entries), batch_size):
            batch = html_entries[i:i + batch_size]
            
            # Батчевое извлечение
            filenames = [entry.path for entry in batch]
            extracted_files = self.extract_batch_files(filenames)
            
            # Парсим извлеченные файлы
            for entry in batch:
                if entry.path in extracted_files:
                    entry.content = extracted_files[entry.path]
                    self._create_document_from_html(entry, result)
                    processed_html += 1
                else:
                    logger.warning(f"Файл не извлечен: {entry.path}")
        
        logger.info(f"Обработано всего: {processed_html} HTML файлов")

        # Устраняет столкновения id (object+name+type не всегда уникальны в
        # книге) до того, как документы уйдут в индексатор: коллизия,
        # обнаруженная только на стороне Elasticsearch, — это уже одна из
        # двух страниц, молча стёршая другую.
        before = len(result.documentation)
        result.documentation = deduplicate_by_id(result.documentation)
        removed = before - len(result.documentation)
        if removed:
            logger.info(f"Устранены столкновения id: удалено страниц-заглушек — {removed}")

        # Обновляем статистику
        result.stats = {
            'html_files': html_files,
            'processed_html': processed_html,
            'st_files': st_files,
            'category_files': category_files,
            'total_entries': len(entries)
        }
    
    def _create_document_from_html(self, entry: HBKEntry, result: ParsedHBK):
        """Создает документ из HTML файла, используя HTMLParser для извлечения содержимого."""
        from src.models.doc_models import Documentation, DocumentType
        
        try:
            # Определяем имя документа из пути
            path_parts = entry.path.replace('\\', '/').split('/')
            doc_name = path_parts[-1].replace('.html', '')
            
            # Определяем категорию из пути
            category = path_parts[-2] if len(path_parts) > 1 else "common"
            
            # Извлекаем содержимое HTML файла из архива
            html_content = None
            if entry.content:
                # Если содержимое уже загружено
                html_content = entry.content
            else:
                # Извлекаем содержимое по требованию
                html_content = self.extract_file_content(entry.path)
            
            if not html_content:
                logger.warning(f"Не удалось извлечь содержимое файла {entry.path}")
                return
            
            # Парсим HTML используя HTMLParser
            documentation = self.html_parser.parse_html_content(
                content=html_content,
                file_path=entry.path
            )
            
            if documentation:
                # Добавляем обработанную документацию напрямую
                result.documentation.append(documentation)
                logger.debug(f"Создан документ: {documentation.name} из файла {entry.path}")
            else:
                logger.warning(f"HTMLParser не смог обработать файл {entry.path}")
            
        except Exception as e:
            logger.warning(f"Ошибка создания документа из {entry.path}: {e}")
    
    def _parse_categories_file(self, entry: HBKEntry, result: ParsedHBK):
        """Парсит файл __categories__ для извлечения метаинформации."""
        if not entry.content:
            return
        
        try:
            # Пробуем разные кодировки
            content = None
            for encoding in SUPPORTED_ENCODINGS:
                try:
                    content = entry.content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if not content:
                logger.warning(f"Не удалось декодировать файл категорий {entry.path}")
                return
            
            # Создаем категорию
            path_parts = entry.path.replace('\\', '/').split('/')
            section_name = path_parts[-2] if len(path_parts) > 1 else "unknown"
            
            category = CategoryInfo(
                name=section_name,
                section=section_name,
                description=f"Раздел документации: {section_name}"
            )
            
            # Простой парсинг версии из содержимого
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if 'version' in line.lower() or 'версия' in line.lower():
                    # Ищем версию типа 8.3.24
                    version_match = re.search(r'8\.\d+\.\d+', line)
                    if version_match:
                        category.version_from = version_match.group(0)
                        break
            
            result.categories[section_name] = category
            logger.debug(f"Обработана категория: {section_name}")
            
        except Exception as e:
            logger.warning(f"Ошибка парсинга файла категорий {entry.path}: {e}")
    
    def _find_7zip_command(self) -> Optional[str]:
        """Первая работающая команда 7zip — в PATH или в стандартных местах.

        Отдельным методом, а не строчками внутри разбора архива: команду ищет и
        parse_single_file_from_archive, и раньше он звал несуществующий
        _get_7zip_command — то есть падал с AttributeError на первом же вызове.
        """
        zip_commands = [
            '7z',           # В PATH
            '7z.exe',       # В PATH
            '7za',          # В PATH (standalone версия)
            '7za.exe',      # В PATH (standalone версия)
            # Стандартные пути Windows
            'C:\\Program Files\\7-Zip\\7z.exe',
            'C:\\Program Files (x86)\\7-Zip\\7z.exe',
            # Переносная версия
            '7-Zip\\7z.exe',
            '7zip\\7z.exe'
        ]

        for cmd in zip_commands:
            try:
                logger.debug(f"Проверяем команду: {cmd}")
                result = safe_subprocess_run([cmd], timeout=5)
                # 7zip возвращает код 0 при показе help или содержит информацию о версии
                if result.returncode == 0 or 'Igor Pavlov' in result.stdout or '7-Zip' in result.stdout:
                    return cmd
            except SafeSubprocessError as e:
                logger.debug(f"Команда {cmd} не найдена: {e}")
                continue

        return None

    def _extract_external_7z(self, file_path: Path) -> List[HBKEntry]:
        """Извлекает список файлов из архива через внешний 7zip."""
        entries = []

        working_7z = self._find_7zip_command()
        if not working_7z:
            logger.error("7zip не найден в системе. Проверьте установку 7-Zip")
            raise HBKParserError("7zip не найден в системе. Проверьте установку 7-Zip")

        # Получаем список файлов (без извлечения)
        try:
            result = safe_subprocess_run([working_7z, 'l', str(file_path)], timeout=60)
        except SafeSubprocessError as e:
            logger.error(f"Ошибка выполнения команды 7zip: {e}")
            raise HBKParserError(f"Ошибка чтения архива: {e}")
        
        if result.returncode != 0:
            logger.error(f"7zip вернул код ошибки {result.returncode}: {result.stderr}")
            raise HBKParserError(f"Ошибка чтения архива: {result.stderr}")
        
        logger.debug(f"Вывод 7zip: {result.stdout[:500]}...")  # Первые 500 символов для отладки
        
        # Парсим вывод 7zip
        lines = result.stdout.split('\n')
        in_files_section = False
        
        for line in lines:
            if '---------------' in line:
                in_files_section = not in_files_section
                continue
            
            if in_files_section and line.strip():
                # Парсим строку файла: дата время атрибуты размер сжатый_размер имя
                parts = line.split()
                if len(parts) >= 6:
                    filename = ' '.join(parts[5:])
                    if filename and not filename.startswith('Date'):
                        # Определяем размер и тип
                        try:
                            size = int(parts[3]) if parts[3].isdigit() else 0
                        except (ValueError, IndexError):
                            size = 0
                        
                        is_dir = parts[2] == 'D' if len(parts) > 2 and len(parts[2]) == 1 else False
                        
                        entry = HBKEntry(
                            path=filename,
                            size=size,
                            is_dir=is_dir,
                            content=None  # Не извлекаем содержимое сразу
                        )
                        
                        entries.append(entry)
        
        # Сохраняем команду 7zip для дальнейшего использования
        self._zip_command = working_7z
        self._archive_path = file_path
        
        return entries
    
    def extract_file_content(self, filename: str) -> Optional[bytes]:
        """Извлекает содержимое конкретного файла по требованию."""
        if not self._zip_command or not self._archive_path:
            logger.error("Архив не был проинициализирован")
            return None
        
        try:
            return self._extract_single_file(self._archive_path, filename, self._zip_command)
        except Exception as e:
            logger.error(f"Ошибка извлечения файла {filename}: {e}")
            return None
    
    def _extract_single_file(self, archive_path: Path, filename: str, zip_cmd: str) -> Optional[bytes]:
        """Извлекает один файл из архива."""
        temp_dir = create_safe_temp_dir("hbk_extract_")
        
        try:
            # Безопасное извлечение файла
            result = safe_subprocess_run([
                zip_cmd, 'e', str(archive_path), filename, 
                f'-o{temp_dir}', '-y'
            ], timeout=30)
            
            if result.returncode == 0:
                # Ищем извлеченный файл
                extracted_files = list(temp_dir.rglob("*"))
                for extracted_file in extracted_files:
                    if extracted_file.is_file():
                        with open(extracted_file, 'rb') as f:
                            return f.read()
            
            return None
            
        except SafeSubprocessError as e:
            logger.error(f"Ошибка извлечения файла {filename}: {e}")
            return None
        finally:
            safe_remove_dir(temp_dir)
    
    def extract_batch_files(self, filenames: List[str]) -> Dict[str, bytes]:
        """
        Извлекает несколько файлов из архива за одну операцию.
        
        Args:
            filenames: Список имен файлов для извлечения
            
        Returns:
            Словарь {filename: content} с содержимым извлеченных файлов
        """
        if not self._zip_command or not self._archive_path:
            logger.error("Архив не был проинициализирован")
            return {}
        
        if not filenames:
            return {}
        
        temp_dir = create_safe_temp_dir("hbk_batch_extract_")
        extracted_files = {}
        
        try:
            # Подготавливаем команду для извлечения всех файлов
            cmd = [self._zip_command, 'x', str(self._archive_path), f'-o{temp_dir}', '-y']
            cmd.extend(filenames)
            
            # Извлекаем все файлы одной командой
            result = safe_subprocess_run(cmd, timeout=120)
            
            if result.returncode == 0:
                # Читаем все извлеченные файлы
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        file_path = Path(root) / file
                        # Вычисляем относительный путь от temp_dir
                        try:
                            relative_path = file_path.relative_to(temp_dir)
                            # Нормализуем путь (заменяем / на \)
                            normalized_path = str(relative_path).replace('/', '\\')
                            
                            # Ищем соответствие в списке запрошенных файлов
                            for original_filename in filenames:
                                # Нормализуем оригинальное имя
                                normalized_original = original_filename.replace('/', '\\')
                                if normalized_path == normalized_original:
                                    with open(file_path, 'rb') as f:
                                        extracted_files[original_filename] = f.read()
                                    break
                        except Exception as e:
                            logger.warning(f"Ошибка чтения файла {file_path}: {e}")
            else:
                logger.error(f"7zip вернул код ошибки {result.returncode}")
        
        except SafeSubprocessError as e:
            logger.error(f"Ошибка батчевого извлечения: {e}")
        except Exception as e:
            logger.error(f"Неожиданная ошибка при батчевом извлечении: {e}")
        finally:
            safe_remove_dir(temp_dir)
        
        return extracted_files
    
    def get_supported_files(self, directory: str) -> List[str]:
        """Возвращает список поддерживаемых файлов в директории."""
        supported_files = []
        
        if not os.path.exists(directory):
            return supported_files
        
        for file_name in os.listdir(directory):
            file_path = os.path.join(directory, file_name)
            if os.path.isfile(file_path):
                file_ext = os.path.splitext(file_name)[1].lower()
                if file_ext in self.supported_extensions:
                    supported_files.append(file_path)
        
        return supported_files

    def parse_single_file_from_archive(self, archive_path: str, target_file_path: str) -> Optional[ParsedHBK]:
        """
        Извлекает и парсит один конкретный файл из архива.
        
        Args:
            archive_path: Путь к архиву .hbk
            target_file_path: Путь к файлу внутри архива (например: "Global context/methods/catalog4838/StrLen912.html")
        
        Returns:
            ParsedHBK объект с одним файлом или None при ошибке
        """
        archive_path = Path(archive_path)
        
        try:
            # Валидация входного файла
            validate_file_path(archive_path, self.supported_extensions)
        except SafeSubprocessError as e:
            logger.error(f"Валидация архива не прошла: {e}")
            return None
        
        # Создаем объект результата
        result = ParsedHBK(
            file_info=HBKFile(
                path=str(archive_path),
                size=archive_path.stat().st_size,
                modified=archive_path.stat().st_mtime
            )
        )
        
        try:
            # Определяем команду для 7zip
            zip_cmd = self._find_7zip_command()
            if not zip_cmd:
                result.errors.append("7zip не найден")
                return result
            
            # Сохраняем параметры для использования в extract_file_content
            self._zip_command = zip_cmd
            self._archive_path = archive_path
            
            logger.info(f"Извлекаение одного файла: {target_file_path}")
            
            # Извлекаем содержимое конкретного файла
            content = self.extract_file_content(target_file_path)
            if not content:
                result.errors.append(f"Не удалось извлечь файл: {target_file_path}")
                return result
            
            logger.info(f"Файл извлечен: {len(content)} байт")
            
            # Парсим HTML содержимое если это HTML файл
            if target_file_path.lower().endswith('.html'):
                try:
                    # Байты, а не str: parse_html_content сам подбирает кодировку
                    # (_decode_content перебирает utf-8, windows-1251, cp1251).
                    # Декодирование здесь отдавало ему готовую строку, разбор
                    # кодировки на ней возвращал None, и метод отвечал «не
                    # удалось распарсить HTML» на странице, которая при обычной
                    # индексации разбирается без единого замечания.
                    parsed_doc = self.html_parser.parse_html_content(content, target_file_path)

                    if parsed_doc:
                        # documentation — то же поле, что заполняет полный
                        # разбор архива. Прежнее result.documents не существует
                        # в модели ParsedHBK: присваивание падало AttributeError,
                        # его ловил внешний except, и вызывающий получал
                        # «Ошибка извлечения» вместо разобранной страницы.
                        parsed_doc.build_call_strings()
                        result.documentation.append(parsed_doc)
                        result.file_info.entries_count = 1
                        logger.info(f"Документ успешно распарсен: {parsed_doc.name}")
                    else:
                        result.errors.append(f"Не удалось распарсить HTML: {target_file_path}")
                        
                except Exception as e:
                    logger.error(f"Ошибка парсинга HTML {target_file_path}: {e}")
                    result.errors.append(f"Ошибка парсинга HTML: {str(e)}")
            else:
                result.errors.append(f"Файл не является HTML: {target_file_path}")
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка извлечения файла {target_file_path} из {archive_path}: {e}")
            result.errors.append(f"Ошибка извлечения: {str(e)}")
            return result

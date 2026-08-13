
"""Парсер .hbk файлов (архивы документации 1С)."""

from collections import defaultdict
from typing import Optional, List, Dict, Any
from pathlib import Path

from src.models.doc_models import HBKFile, ParsedHBK, Documentation, DocumentType
from src.core.logging import get_logger
from src.parsers.html_parser import HTMLParser
from src.parsers.dialects import HelpDialect, RU_DIALECT
from src.core.errors import FilePathError
from src.core.utils import validate_file_path
from src.core.constants import MAX_FILE_SIZE_MB
from src.parsers.v8_container import HelpBookArchive, HelpBookArchiveError

logger = get_logger(__name__)


class HBKParserError(Exception):
    """Исключение для ошибок парсера HBK."""
    pass


def _is_empty_object_stub(doc: Documentation) -> bool:
    """Страница-раздел книги без адресуемого содержимого, а не настоящий объект."""
    return (
        doc.type == DocumentType.OBJECT
        and not doc.description
        and not doc.methods
        and not doc.properties
        and not doc.events
    )


def deduplicate_by_id(documents: List[Documentation]) -> List[Documentation]:
    """Делает id уникальными до индексации.

    Пустые страницы-заглушки уступают содержательным документам и
    выбрасываются; равные между собой получают различители «#2», «#3» в
    порядке source_file.
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
            doc.disambiguate_id(n)

    return [d for d in documents if id(d) not in dropped_object_ids]


class HBKParser:
    """Парсер .hbk архивов с документацией 1С."""
    
    def __init__(self, dialect: HelpDialect = RU_DIALECT):
        self._max_file_size = MAX_FILE_SIZE_MB * 1024 * 1024
        self.dialect = dialect
        # Диалект прокидывается в HTMLParser: разбор английской книги
        # отличается от русской только текстом заголовков разделов, а не
        # структурой кода, поэтому HBKParser не ветвится по языку сам.
        self.html_parser = HTMLParser(dialect=dialect)

    def _open_archive(self, file_path: Path) -> HelpBookArchive:
        """Книга, открытая для чтения по именам файлов."""
        return HelpBookArchive(file_path)

    def parse_file(self, file_path: str) -> Optional[ParsedHBK]:
        """Разбирает книгу справки .hbk и извлекает документацию."""
        file_path = Path(file_path)

        try:
            validate_file_path(file_path)
        except FilePathError as e:
            logger.error(f"Валидация файла не прошла: {e}")
            return None

        if file_path.stat().st_size > self._max_file_size:
            logger.error(f"Файл слишком большой: {file_path.stat().st_size / 1024 / 1024:.1f}MB")
            return None

        result = ParsedHBK(
            file_info=HBKFile(
                path=str(file_path),
                size=file_path.stat().st_size,
                modified=file_path.stat().st_mtime,
            )
        )

        try:
            with self._open_archive(file_path) as archive:
                names = archive.names()
                if not names:
                    result.errors.append("Книга не содержит файлов")
                    return result
                result.file_info.entries_count = len(names)
                self._analyze_structure(archive, names, result)
            return result
        except HelpBookArchiveError as e:
            logger.error(f"Не удалось прочитать книгу {file_path}: {e}")
            result.errors.append(f"Не удалось прочитать книгу: {e}")
            return result
        except Exception as e:
            logger.error(f"Ошибка парсинга файла {file_path}: {e}")
            result.errors.append(f"Ошибка парсинга: {str(e)}")
            return result

    def _analyze_structure(
        self, archive: HelpBookArchive, names: List[str], result: ParsedHBK
    ) -> None:
        """Раскладывает файлы книги на категории, шаблоны и страницы объектов."""
        category_files = 0
        st_files = 0
        object_pages = []

        for name in names:
            if name.rsplit("/", 1)[-1] == "__categories__":
                category_files += 1
            elif name.endswith(".st"):
                st_files += 1
            elif name.endswith(".html") and name.startswith("objects/"):
                object_pages.append(name)

        logger.info(f"Найдено HTML файлов для парсинга: {len(object_pages)}")

        processed = 0
        for name in object_pages:
            if self._create_document_from_html(archive, name, result):
                processed += 1

        logger.info(f"Обработано всего: {processed} HTML файлов")

        # Устраняет столкновения id (object+name+type не всегда уникальны в
        # книге) до того, как документы уйдут в индексатор: коллизия,
        # обнаруженная только на стороне Elasticsearch, — это уже одна из
        # двух страниц, молча стёршая другую.
        before = len(result.documentation)
        result.documentation = deduplicate_by_id(result.documentation)
        removed = before - len(result.documentation)
        if removed:
            logger.info(f"Устранены столкновения id: удалено страниц-заглушек — {removed}")

        result.pages_attempted = len(object_pages)
        result.pages_parsed = processed
        result.stats = {
            "object_pages": result.pages_attempted,
            "processed_html": result.pages_parsed,
            "st_files": st_files,
            "category_files": category_files,
            "total_entries": len(names),
        }

    def _create_document_from_html(
        self, archive: HelpBookArchive, name: str, result: ParsedHBK
    ) -> bool:
        """Создаёт документ из страницы книги; False — страницу разобрать не удалось."""
        try:
            content = archive.read(name)
        except Exception as e:
            message = f"Не удалось прочитать файл {name}: {e}"
            logger.warning(message)
            result.errors.append(message)
            return False

        try:
            documentation = self.html_parser.parse_html_content(content=content, file_path=name)
        except Exception as e:
            logger.warning(f"Ошибка создания документа из {name}: {e}")
            return False

        if not documentation:
            logger.warning(f"HTMLParser не смог обработать файл {name}")
            return False

        result.documentation.append(documentation)
        return True

"""Парсер HTML документации 1С."""

import html
import re
from typing import Optional
from bs4 import BeautifulSoup, NavigableString

from src.models.doc_models import (
    Documentation, Parameter, SyntaxVariant, DocumentType,
    ObjectMethod, ObjectProperty, ObjectEvent,
)
from src.core.logging import get_logger
from src.parsers.dialects import Chapter, HelpDialect, RU_DIALECT
from src.parsers.text_utils import (
    split_type_and_note, normalize_whitespace, clean_description, text_from_html,
)

logger = get_logger(__name__)


def nodes_until_boundary(start, boundary_classes) -> list:
    """Соседние узлы после start — до первой границы.

    Границей считается узел одного из классов boundary_classes или <HR>: этим
    тегом справка отделяет подвал страницы («Методическая информация») от
    содержимого, и без него сбор последней главы дотягивался до конца
    документа.

    Обход соседей был скопирован в четыре места файла, и границу по <HR>
    приходилось добавлять в каждую копию отдельно — в двух она так и не
    появилась. Поэтому обход живёт здесь один.
    """
    nodes = []
    elem = getattr(start, "next_sibling", None)
    while elem is not None:
        if getattr(elem, 'name', None) == 'hr':
            break
        css_classes = elem.get('class') or [] if hasattr(elem, 'get') else []
        if any(css_class in css_classes for css_class in boundary_classes):
            break
        nodes.append(elem)
        elem = elem.next_sibling
    return nodes


def _serialize_for_reparsing(node) -> str:
    """Строка узла, годная к повторному разбору как HTML.

    Tag.__str__ сам экранирует текст своих потомков — обычный self-round-trip
    BeautifulSoup. А NavigableString — подкласс str, и str() на ней возвращает
    уже раскодированный текст как есть, без обратного экранирования. Плейсхолдер
    «<Value>» (после декодирования &lt;Value&gt; при исходном разборе страницы)
    в таком виде неотличим от настоящего тега: при повторном разборе html.parser
    молча вырезает его как неизвестный тег, и текст пропадает. Кириллическое имя
    («<ПараметрыОтбора>») тегом не распознаётся — в имени тега нет ASCII-букв —
    и потому уцелевает случайно. Отсюда была разница между русской и английской
    книгой на одном и том же месте разметки: дело в форме плейсхолдера, а не в
    языке справки.
    """
    if isinstance(node, NavigableString):
        return html.escape(str(node), quote=False)
    return str(node)


# Вид элемента по-русски: агент читает карточку, а не enum индекса.
ELEMENT_KIND_BY_TYPE = {
    DocumentType.GLOBAL_FUNCTION: "функция",
    DocumentType.GLOBAL_PROCEDURE: "процедура",
    DocumentType.GLOBAL_EVENT: "событие",
    DocumentType.OBJECT_FUNCTION: "функция",
    DocumentType.OBJECT_PROCEDURE: "процедура",
    DocumentType.OBJECT_PROPERTY: "свойство",
    DocumentType.OBJECT_EVENT: "событие",
    DocumentType.OBJECT_CONSTRUCTOR: "конструктор",
    DocumentType.OBJECT: "объект",
}


class HTMLParser:
    """Парсер HTML документации 1С."""

    def __init__(self, dialect: HelpDialect = RU_DIALECT):
        self.dialect = dialect
        # Флаги обязательности параметра — часть текста справки на языке
        # диалекта, поэтому регэксп собирается из него, а не фиксируется на
        # русских словах: на другом языке справка пишет флаг иначе.
        self._parameter_heading_re = re.compile(
            r'<\s*(?P<name>[^<>]*)\s*>\s*(?:\((?P<flag>'
            + '|'.join((dialect.required_flag, dialect.optional_flag))
            + r')\))?\s*\Z'
        )

    def parse_html_content(self, content: bytes, file_path: str) -> Optional[Documentation]:
        """Парсит HTML содержимое и извлекает документацию."""
        try:
            # Декодируем содержимое
            html_content = self._decode_content(content)
            if not html_content:
                return None
            
            # Парсим HTML
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Определяем тип документации из пути файла
            doc_type, object_name, item_name = self._parse_file_path(file_path)
            
            # Для методов определяем точный тип (функция/процедура) по содержимому
            if doc_type in [DocumentType.GLOBAL_FUNCTION, DocumentType.OBJECT_FUNCTION]:
                is_function = self._is_function_not_procedure(soup)
                if not is_function:
                    if doc_type == DocumentType.GLOBAL_FUNCTION:
                        doc_type = DocumentType.GLOBAL_PROCEDURE
                    else:
                        doc_type = DocumentType.OBJECT_PROCEDURE
            
            # Создаем базовый объект документации
            doc = Documentation(
                id="",  # Будет заполнен в build_call_strings
                type=doc_type,
                name=item_name,
                object=object_name,
                source_file=file_path
            )
            
            # Извлекаем основную информацию
            self._extract_title_and_description(soup, doc)
            
            # Для всех типов кроме глобальных переопределяем object из заголовка
            if doc.type not in (DocumentType.GLOBAL_FUNCTION, DocumentType.GLOBAL_PROCEDURE, DocumentType.GLOBAL_EVENT):
                doc.object = self._extract_object_name_from_title(soup)

            doc.element_kind = ELEMENT_KIND_BY_TYPE.get(doc.type, "")
            doc.object_ru = self._extract_russian_object_name(soup) or doc.object
            self._extract_element_sections(soup, doc)

            if doc.type == DocumentType.OBJECT_PROPERTY:
                self._extract_property_type(soup, doc)

            # Для объектов извлекаем методы, свойства и события
            if doc.type == DocumentType.OBJECT:
                self._extract_object_methods(soup, doc)
                self._extract_object_properties(soup, doc)
                self._extract_object_events(soup, doc)
            else:
                # Для функций/методов/событий извлекаем варианты вызова и примеры
                self._extract_variants(soup, doc)
                self._extract_examples(soup, doc)
            
            self._extract_version(soup, doc)
            
            # Автоматически заполняем служебные поля
            doc.build_call_strings()
            
            logger.debug(f"Обработан HTML файл: {file_path} -> {doc.name}")
            return doc
            
        except Exception as e:
            logger.error(f"Ошибка парсинга HTML файла {file_path}: {e}")
            return None
    
    def _decode_content(self, content: bytes) -> Optional[str]:
        """Декодирует содержимое файла в строку."""
        encodings = ['utf-8', 'windows-1251', 'cp1251', 'iso-8859-1']
        
        for encoding in encodings:
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        
        logger.warning("Не удалось декодировать содержимое файла")
        return None
    
    def _parse_file_path(self, file_path: str) -> tuple[DocumentType, Optional[str], str]:
        """Определяет тип документации из пути файла."""
        # Нормализуем путь
        path_str = file_path.replace('\\', '/')
        path_parts = path_str.split('/')
        
        # Убираем расширение из имени файла
        file_name = path_parts[-1]
        if file_name.endswith('.html'):
            file_name = file_name[:-5]
        
        # Ищем ключевые слова в пути
        path_lower = path_str.lower()
        
        if '/methods/' in path_lower:
            # Это метод (функция/процедура) - определяем тип по содержимому
            object_name = self._extract_object_name(path_str, 'methods')
            if object_name and object_name.lower() == 'global context':
                return DocumentType.GLOBAL_FUNCTION, object_name, file_name
            else:
                return DocumentType.OBJECT_FUNCTION, object_name, file_name
            
        elif '/properties/' in path_lower:
            # Это свойство объекта (глобальных свойств в 1С нет)
            object_name = self._extract_object_name(path_str, 'properties')
            return DocumentType.OBJECT_PROPERTY, object_name, file_name
            
        elif '/events/' in path_lower:
            # Это событие - может быть глобальным или объектным
            object_name = self._extract_object_name(path_str, 'events')
            if object_name and object_name.lower() == 'global context':
                return DocumentType.GLOBAL_EVENT, object_name, file_name
            else:
                return DocumentType.OBJECT_EVENT, object_name, file_name
            
        elif '/ctors/' in path_lower or '/ctor/' in path_lower:
            # Это конструктор объекта
            object_name = self._extract_object_name(path_str, 'ctors')
            if not object_name:
                object_name = self._extract_object_name(path_str, 'ctor')
            return DocumentType.OBJECT_CONSTRUCTOR, object_name, file_name
            
        elif 'globalfunctions/' in path_lower or '/functions/' in path_lower:
            # Глобальная функция
            return DocumentType.GLOBAL_FUNCTION, None, file_name
            
        elif '/objects/' in path_lower or path_lower.startswith('objects/'):
            # Это объект
            object_name = self._extract_main_object_name(path_str)
            return DocumentType.OBJECT, object_name, file_name
        
        # По умолчанию считаем объектом
        return DocumentType.OBJECT, None, file_name
        
    def _extract_object_name(self, path_str: str, member_type: str) -> Optional[str]:
        """Извлекает имя объекта из пути для методов/свойств/событий."""
        parts = path_str.split('/')
        
        # Ищем индекс папки с типом (methods/properties/events)
        member_idx = None
        for i, part in enumerate(parts):
            if part.lower() == member_type:
                member_idx = i
                break
                
        if member_idx is None:
            return None
            
        # Объект находится перед папкой типа
        if member_idx > 0:
            object_part = parts[member_idx - 1]
            
            # Если это специальные объекты как "Global context"
            if object_part == "Global context":
                return "Global context"
            
            # Если это каталожная структура catalog123, извлекаем имя
            if object_part.startswith('catalog'):
                # Попробуем найти более читаемое имя объекта
                # Ищем в предыдущих частях пути
                for j in range(member_idx - 1, -1, -1):
                    if not parts[j].startswith('catalog') and parts[j] != 'objects':
                        return parts[j]
                        
            return object_part
            
        return None
        
    def _extract_main_object_name(self, path_str: str) -> Optional[str]:
        """Извлекает имя основного объекта из пути."""
        parts = path_str.split('/')
        
        # Ищем индекс папки objects
        objects_idx = None
        for i, part in enumerate(parts):
            if part.lower() == 'objects':
                objects_idx = i
                break
                
        if objects_idx is None:
            return None
            
        # Для пути objects/catalog125/catalog462/object464.html
        # нужно взять последний каталог перед HTML файлом
        if objects_idx + 1 < len(parts):
            # Ищем последний каталог перед HTML файлом
            for i in range(len(parts) - 2, objects_idx, -1):  # Идем от конца к началу
                part = parts[i]
                if not part.endswith('.html') and part.startswith('catalog'):
                    return part
            
            # Если не найден каталог, берем первый элемент после objects
            object_part = parts[objects_idx + 1]
            if not object_part.endswith('.html'):
                return object_part
                
        return None
    
    def _is_function_not_procedure(self, soup: BeautifulSoup) -> bool:
        """Определяет, является ли метод функцией (возвращает значение) или процедурой."""
        # Ищем заголовок "Возвращаемое значение" в V8SH_chapter
        chapter_headers = soup.find_all('p', class_='V8SH_chapter')
        for header in chapter_headers:
            if self.dialect.chapter_of(header.get_text(strip=True)) is Chapter.RETURN_VALUE:
                return True

        # По умолчанию считаем процедурой
        return False
    
    def _extract_object_name_from_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Извлекает имя объекта из заголовка для объектов."""
        # Ищем заголовок в V8SH_pagetitle или V8SH_heading
        title_tag = soup.find('h1', class_='V8SH_pagetitle') or soup.find('p', class_='V8SH_heading')
        if not title_tag:
            return None
            
        title_text = title_tag.get_text(strip=True)
        if not title_text:
            return None
            
        # Убираем английскую часть в скобках
        if ' (' in title_text:
            title_text = title_text.split(' (')[0]
        
        # Для объектов: "РегистрБухгалтерииМенеджер.<Имя регистра бухгалтерии>"
        # Для событий: "КритерийОтбораМенеджер.<Имя критерия>.ОбработкаПолученияФормы"
        
        if '.' in title_text:
            parts = title_text.split('.')
            if len(parts) == 2:
                # Обычный объект: "РегистрБухгалтерииМенеджер.<Имя регистра бухгалтерии>"
                return parts[0].strip()
            elif len(parts) > 2:
                # Событие/метод: "КритерийОтбораМенеджер.<Имя критерия>.ОбработкаПолученияФормы"
                # Объектом является все кроме последней части
                return '.'.join(parts[:-1]).strip()
            else:
                return parts[0].strip()
            
        return title_text.strip()
    
    def _get_content_after_chapter(self, soup: BeautifulSoup, chapter: Chapter) -> str:
        """
        Универсальный метод для получения HTML контента после заголовка V8SH_chapter.

        Args:
            soup: Объект BeautifulSoup
            chapter: Раздел, который нужно найти

        Returns:
            HTML строка с контентом после найденного заголовка до следующего заголовка

        Сравнение идёт через self.dialect.chapter_of, а не подстрокой: подстрочное
        сравнение по «методы» матчило бы и заголовок «Общие методы:» — на реальном
        корпусе такого раздела нет, но сама проверка не должна на это полагаться.
        """
        chapter_headers = soup.find_all('p', class_='V8SH_chapter')

        for header in chapter_headers:
            if self.dialect.chapter_of(header.get_text(strip=True)) is chapter:
                parent = header.parent
                if parent:
                    header_html = str(header)
                    parent_html = str(parent)
                    
                    # Ищем позицию заголовка в родительском элементе
                    header_pos = parent_html.find(header_html)
                    if header_pos != -1:
                        # Берем HTML после заголовка
                        remaining_html = parent_html[header_pos + len(header_html):]
                        
                        # Ограничиваем до следующего заголовка V8SH_chapter
                        next_chapter_pos = remaining_html.find('class="V8SH_chapter"')
                        if next_chapter_pos != -1:
                            remaining_html = remaining_html[:next_chapter_pos]
                        
                        return remaining_html
                break
        
        return ""
    
    def _extract_title_and_description(self, soup: BeautifulSoup, doc: Documentation):
        """Извлекает заголовок и описание."""
        # Ищем заголовок в V8SH_pagetitle или V8SH_heading
        title_tag = soup.find('h1', class_='V8SH_pagetitle') or soup.find('p', class_='V8SH_heading')
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            if title_text:
                if doc.type == DocumentType.OBJECT:
                    # Для объектов берем часть после точки как имя
                    # Убираем английскую часть в скобках
                    if ' (' in title_text:
                        title_text = title_text.split(' (')[0].strip()
                    
                    if '.' in title_text:
                        # Извлекаем часть после точки как имя объекта
                        doc.name = title_text.split('.', 1)[1].strip()
                    else:
                        doc.name = title_text
                else:
                    # Для функций/методов/событий
                    if '.' in title_text:
                        # Разделяем русскую и английскую части
                        russian_part = title_text.split(' (')[0] if ' (' in title_text else title_text
                        english_part = title_text.split(' (')[1] if ' (' in title_text else ''
                        
                        # Берем последнюю часть русского названия
                        russian_parts = russian_part.split('.')
                        russian_name = russian_parts[-1] if len(russian_parts) > 1 else russian_part
                        
                        # Берем последнюю часть английского названия
                        if english_part:
                            english_parts = english_part.replace(')', '').split('.')
                            english_name = english_parts[-1] if len(english_parts) > 1 else english_part.replace(')', '')
                            doc.name = f"{russian_name} ({english_name})"
                        else:
                            doc.name = russian_name
                    else:
                        doc.name = title_text

        # Ищем описание в разделе "Описание:"
        desc_headers = soup.find_all('p', class_='V8SH_chapter')
        
        for header in desc_headers:
            if self.dialect.chapter_of(header.get_text(strip=True)) is Chapter.DESCRIPTION:
                # Ищем в тексте после заголовка до следующего V8SH_chapter
                description_parts = []

                for elem in nodes_until_boundary(header, ('V8SH_chapter',)):
                    if hasattr(elem, 'get_text'):
                        text = elem.get_text().strip()  # Сохраняем внутренние пробелы
                        if text and len(text) > 3:  # Игнорируем короткие фрагменты
                            description_parts.append(text)
                    elif isinstance(elem, str):
                        text = elem.strip()
                        if text and len(text) > 3:
                            description_parts.append(text)

                if description_parts:
                    doc.description = clean_description(' '.join(description_parts))
                    break
    
    def _chapters(self, soup: BeautifulSoup):
        """Главы страницы: [(заголовок, html после заголовка), …].

        Идём по узлам-соседям, а не поиском подстроки в HTML родителя: на
        странице с вариантами заголовки «Синтаксис:» текстуально одинаковы, и
        поиск подстроки возвращал бы для каждого позицию первого.
        """
        chapters = []
        for header in soup.find_all('p', class_='V8SH_chapter'):
            parts = [
                _serialize_for_reparsing(u)
                for u in nodes_until_boundary(header, ('V8SH_chapter',))
            ]
            chapters.append((header.get_text(strip=True), "".join(parts)))
        return chapters

    def _extract_element_sections(self, soup: BeautifulSoup, doc: Documentation):
        """Разделы, относящиеся к элементу целиком, а не к варианту вызова."""
        for heading, html in self._chapters(soup):
            chapter = self.dialect.chapter_of(heading)

            if chapter is Chapter.AVAILABILITY:
                doc.availability = self._parse_availability(html)
            elif chapter is Chapter.NOTE:
                doc.note = clean_description(text_from_html(html))
            elif chapter is Chapter.USAGE:
                # USAGE, а не VERSION: «Использование в версии:» говорит о
                # версии платформы и в доступ к свойству не годится.
                doc.usage = normalize_whitespace(text_from_html(html)).rstrip('.').lower()

    @staticmethod
    def _parse_availability(html: str):
        """«Сервер, толстый клиент, внешнее соединение.» → список контекстов.

        Перечень контекстов — всегда первое предложение раздела, поэтому текст
        обрезается по его границе ДО разбиения по запятым. Снятия одной точки
        на конце (rstrip) не хватало: если после перечня стоит проза («Вызов
        метода выполняет обращение к серверу», «Данный объект может быть
        сериализован в/из XML»), она вливалась в последний контекст, и агент
        читал «мобильный автономный сервер. вызов метода выполняет обращение к
        серверу» как место, где вызов законен. Замер по индексу: так было у
        1 106 из 19 156 документов с непустой доступностью.
        """
        text = normalize_whitespace(text_from_html(html))
        boundary = text.find('. ')
        if boundary != -1:
            text = text[:boundary]
        text = text.rstrip('.')
        return [part.strip().lower() for part in text.split(',') if part.strip()]

    def _extract_property_type(self, soup: BeautifulSoup, doc: Documentation):
        """Вынимает «Тип: X.» из начала описания свойства в отдельное поле.

        В справке тип значения свойства стоит первой фразой раздела «Описание:»,
        причём в HTML это россыпь узлов (текст, ссылка, <br>) без общего
        родителя-<p>. Общий сборщик _extract_title_and_description отбрасывает
        короткие текстовые фрагменты (в т.ч. точку после ссылки на тип) и рвёт
        границу между типом и пояснением, поэтому раздел разбирается заново из
        собственного HTML, а не из уже собранного doc.description.
        """
        for heading, html in self._chapters(soup):
            if self.dialect.chapter_of(heading) is not Chapter.DESCRIPTION:
                continue

            text = text_from_html(html).strip()
            if text.startswith(self.dialect.type_label):
                doc.value_type, doc.description = split_type_and_note(html, self.dialect.type_label)
            break

    def _extract_russian_object_name(self, soup: BeautifulSoup) -> Optional[str]:
        """«ТаблицаЗначений (ValueTable)» → «ТаблицаЗначений»."""
        title = soup.find('p', class_='V8SH_title')
        if not title:
            return None
        text = title.get_text(strip=True)
        return text.split(' (')[0].strip() or None

    # Обязательность параметра справка пишет в скобке после имени:
    # "<Индекс> (обязательный)". У вариативных параметров конструкторов
    # разметка бита: "<КоличествоЭлементов1>,...,<КоличествоЭлементовN>" — часть
    # угловых скобок экранирована как &lt;/&gt;, часть — нет, и после разбора
    # BeautifulSoup внутри текста рубрики остаются лишние литеральные '<' и '>'.
    # Имя не должно пересекать эти внутренние скобки (иначе в него попадает
    # обломок разметки вроде "КоличествоЭлементов1>,...,<КоличествоЭлементовN"),
    # но искать его надо от пары <...>, что стоит прямо перед концом строки
    # (или перед флагом) — то есть от последней настоящей пары скобок, а не от
    # первой встречной: иначе на этом же случае теряется флаг обязательности.
    # Сами слова флага — часть текста справки, поэтому регэксп собран в
    # __init__ из self.dialect, а не зафиксирован здесь константой класса.

    def _parse_parameter_header(self, text: str):
        """Возвращает (имя, обязательность) из '<Индекс> (обязательный)'.

        BeautifulSoup уже превратил &lt; в <, поэтому имя ищется в угловых
        скобках. Обязательность None — справка о ней молчит.
        """
        match = self._parameter_heading_re.search(text.replace('\xa0', ' '))
        if not match:
            return "", None

        name = match.group('name').strip()
        required = self.dialect.required_from_flag(match.group('flag') or "")
        return name, required

    def _parse_parameters(self, html: str):
        """Параметры одной главы «Параметры:»."""
        from bs4 import BeautifulSoup as BS

        sup = BS(html or "", 'html.parser')
        params = []
        for rubric in sup.find_all('div', class_='V8SH_rubric'):
            name, is_required = self._parse_parameter_header(
                rubric.get_text(' ', strip=True)
            )
            if not name:
                continue

            parts = [
                _serialize_for_reparsing(u)
                for u in nodes_until_boundary(rubric, ('V8SH_rubric',))
            ]
            param_type, description = split_type_and_note("".join(parts), self.dialect.type_label)
            params.append(
                Parameter(name=name, type=param_type, description=description,
                          required=is_required)
            )
        return params

    def _extract_variants(self, soup: BeautifulSoup, doc: Documentation):
        """Собирает варианты вызова.

        «Синтаксис», «Параметры» и «Возвращаемое значение» принадлежат текущему
        варианту — последнему встреченному «Вариант синтаксиса». Всё остальное
        относится к элементу целиком.
        """
        parsed_variants = []
        current = None

        def take_current():
            nonlocal current
            if current is None:
                current = SyntaxVariant()
                parsed_variants.append(current)
            return current

        for heading, html in self._chapters(soup):
            chapter = self.dialect.chapter_of(heading)

            if chapter is Chapter.SYNTAX_VARIANT:
                current = SyntaxVariant(variant=self.dialect.variant_name(heading))
                parsed_variants.append(current)
            elif chapter is Chapter.SYNTAX:
                take_current().syntax = normalize_whitespace(text_from_html(html))
            elif chapter is Chapter.PARAMETERS:
                take_current().parameters = self._parse_parameters(html)
            elif chapter is Chapter.RETURN_VALUE:
                variant = take_current()
                variant.return_type, variant.return_description = \
                    split_type_and_note(html, self.dialect.type_label)
            elif chapter is Chapter.VARIANT_DESCRIPTION:
                take_current().description = clean_description(text_from_html(html))

        if doc.type == DocumentType.OBJECT_CONSTRUCTOR:
            # У конструкторов варианты разложены по отдельным страницам справки,
            # и заголовка «Вариант синтаксиса» на них нет: имя варианта («По
            # количеству элементов») — это имя самой страницы. Раньше оно
            # выдавалось за имя элемента, и путь получался бессмысленный:
            # «Массив.По количеству элементов» вместо «Новый Массив(...)».
            if not parsed_variants:
                parsed_variants.append(SyntaxVariant())
            for v in parsed_variants:
                if not v.variant:
                    v.variant = doc.name_ru()

        doc.variants = parsed_variants
        doc.syntax_all = " | ".join(v.syntax for v in parsed_variants if v.syntax)

    def _extract_examples(self, soup: BeautifulSoup, doc: Documentation):
        """Извлекает примеры кода."""
        # Ищем заголовок "Пример:" с классом V8SH_chapter
        example_headers = soup.find_all('p', class_='V8SH_chapter')
        
        for header in example_headers:
            if self.dialect.chapter_of(header.get_text(strip=True)) is not Chapter.EXAMPLE:
                continue

            # Ищем таблицы с кодом после заголовка
            for elem in nodes_until_boundary(header, ('V8SH_chapter',)):
                # Пропускаем текстовые узлы и элементы без методов find
                if not (hasattr(elem, 'name') and elem.name and hasattr(elem, 'find')):
                    continue

                tables = elem.find_all('table') if elem.name != 'table' else [elem]
                for table in tables:
                    # Ищем ячейки с кодом (обычно с моноширинным шрифтом)
                    code_cells = table.find_all('td')
                    for cell in code_cells:
                        fonts = cell.find_all('font', face='Courier New')
                        if not fonts:
                            continue
                            
                        # Получаем весь HTML внутри ячейки для корректного извлечения
                        cell_html = str(cell)
                        
                        # Извлекаем код, сохраняя структуру и переносы строк
                        from bs4 import BeautifulSoup as BS
                        cell_soup = BS(cell_html, 'html.parser')
                        
                        # Получаем текст, заменяя <BR> на переносы строк
                        for br in cell_soup.find_all('br'):
                            br.replace_with('\n')
                        
                        code_text = cell_soup.get_text()
                        
                        if code_text.strip() and len(code_text.strip()) > 5:
                            # Очищаем лишние пробелы, но сохраняем структуру
                            lines = code_text.split('\n')
                            clean_lines = [line.rstrip() for line in lines if line.strip()]
                            full_code = '\n'.join(clean_lines)
                            
                            if full_code.strip():
                                # Неразрывные пробелы в коде 1С — синтаксическая
                                # ошибка: агент скопирует пример и получит отказ
                                # компиляции. normalize_whitespace тут не годится:
                                # она схлопывает пробельные последовательности через
                                # .split() и срезает ведущий отступ — а отступ вложенных
                                # строк примера значим и должен остаться дословным.
                                example_lines = [
                                    example_line.replace('\xa0', ' ').rstrip()
                                    for example_line in full_code.strip().split('\n')
                                ]
                                doc.examples.append('\n'.join(example_lines))
                
                elem = elem.next_sibling
            break
    
    def _extract_version(self, soup: BeautifulSoup, doc: Documentation):
        """Извлекает информацию о версии."""
        # Ищем элементы с классом V8SH_versionInfo
        version_elements = soup.find_all('p', class_='V8SH_versionInfo')
        
        for elem in version_elements:
            version_text = elem.get_text(strip=True)
            
            # Ищем версию типа "8.3.24" или "8.0"
            version_match = re.search(r'8\.\d+(?:\.\d+)?', version_text)
            if version_match:
                version = version_match.group(0)
                
                # Определяем тип версии по контексту
                if self.dialect.is_version_available(version_text):
                    doc.version_from = version
                elif self.dialect.is_version_changed(version_text):
                    # Это версия изменения, можно сохранить как дополнительную информацию
                    if not doc.version_from:
                        doc.version_from = version
    
    def _extract_object_methods(self, soup: BeautifulSoup, doc: Documentation):
        """Извлекает методы объекта."""
        # Ищем секцию "Методы:"
        methods_section = self._get_content_after_chapter(soup, Chapter.METHODS)
        if not methods_section:
            return
            
        # Ищем все ссылки на методы
        method_links = re.findall(r'<a href="([^"]+)">([^<]+)</a>', methods_section)
        for href, name in method_links:
            # Парсим название (может быть "Выбрать (Select)")
            if '(' in name and ')' in name:
                match = re.match(r'([^(]+)\s*\(([^)]+)\)', name)
                if match:
                    name_ru = match.group(1).strip()
                    name_en = match.group(2).strip()
                else:
                    name_ru = name
                    name_en = ""
            else:
                name_ru = name
                name_en = ""
            
            method = ObjectMethod(
                name=name_ru,
                name_en=name_en,
                href=href
            )
            doc.methods.append(method)
    
    def _extract_object_properties(self, soup: BeautifulSoup, doc: Documentation):
        """Извлекает свойства объекта."""
        # Ищем секцию "Свойства:"
        properties_section = self._get_content_after_chapter(soup, Chapter.PROPERTIES)
        if not properties_section:
            return
            
        # Ищем все ссылки на свойства
        prop_links = re.findall(r'<a href="([^"]+)">([^<]+)</a>', properties_section)
        for href, name in prop_links:
            # Парсим название
            if '(' in name and ')' in name:
                match = re.match(r'([^(]+)\s*\(([^)]+)\)', name)
                if match:
                    name_ru = match.group(1).strip()
                    name_en = match.group(2).strip()
                else:
                    name_ru = name
                    name_en = ""
            else:
                name_ru = name
                name_en = ""
            
            prop = ObjectProperty(
                name=name_ru,
                name_en=name_en,
                href=href
            )
            doc.properties.append(prop)
    
    def _extract_object_events(self, soup: BeautifulSoup, doc: Documentation):
        """Извлекает события объекта."""
        # Ищем секцию "События:"
        events_section = self._get_content_after_chapter(soup, Chapter.EVENTS)
        if not events_section:
            return
            
        # Ищем все ссылки на события
        event_links = re.findall(r'<a href="([^"]+)">([^<]+)</a>', events_section)
        for href, name in event_links:
            # Парсим название
            if '(' in name and ')' in name:
                match = re.match(r'([^(]+)\s*\(([^)]+)\)', name)
                if match:
                    name_ru = match.group(1).strip()
                    name_en = match.group(2).strip()
                else:
                    name_ru = name
                    name_en = ""
            else:
                name_ru = name
                name_en = ""
            
            event = ObjectEvent(
                name=name_ru,
                name_en=name_en,
                href=href
            )
            doc.events.append(event)
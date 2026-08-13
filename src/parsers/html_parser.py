"""Разбор страницы справки 1С."""

import html
import re
from typing import Optional, Tuple
from bs4 import BeautifulSoup, NavigableString

from src.models.doc_models import (
    Documentation, Parameter, SyntaxVariant, DocumentType,
    ObjectMethod, ObjectProperty, ObjectEvent,
)
from src.core.logging import get_logger
from src.parsers.dialects import Chapter, HelpDialect, RU_DIALECT
from src.parsers.indexer import split_name_ru_en
from src.parsers.text_utils import (
    split_type_and_note, normalize_whitespace, clean_prose, text_from_html,
)

logger = get_logger(__name__)


def nodes_until_boundary(start, boundary_classes) -> list:
    """Соседние узлы после start — до узла из boundary_classes или до <hr>.

    <hr> отделяет подвал страницы («Методическая информация») от содержимого.
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


_HTML_TAG_NAMES = frozenset("""
a abbr acronym address applet area article aside audio b base basefont bdi bdo
big blockquote body br button canvas caption center cite code col colgroup data
datalist dd del details dfn dialog dir div dl dt em embed fieldset figcaption
figure font footer form frame frameset h1 h2 h3 h4 h5 h6 head header hgroup hr
html i iframe img input ins kbd label legend li link main map mark marquee menu
meta meter nav noframes noscript object ol optgroup option output p param
picture pre progress q rp rt ruby s samp script search section select slot small
source span strike strong style sub summary sup table tbody td template textarea
tfoot th thead time title tr track tt u ul var video wbr
""".split())

# «<», необязательный слеш закрывающего тега, имя из ASCII-букв, всё до «>».
_TAG_LIKE_RE = re.compile(r'<\s*/?\s*(?P<name>[A-Za-z][^\s<>/]*)[^<>]*>')


def escape_pseudo_tags(html_content: str) -> str:
    """Экранирует плейсхолдеры справки, записанные сырыми угловыми скобками.

    Настоящая разметка книги проходит нетронутой: её имена есть в закрытом
    списке HTML-элементов, а «Value1», «size0», «AddInName» — нет. Экранируются
    ровно «<» и «>» самого совпадения: html.escape тронул бы ещё и «&», а
    внутри разметки амперсанды уже бывают сущностями.
    """
    def escape_match(match: re.Match) -> str:
        if match.group('name').lower() in _HTML_TAG_NAMES:
            return match.group(0)
        return match.group(0).replace('<', '&lt;').replace('>', '&gt;')

    return _TAG_LIKE_RE.sub(escape_match, html_content)


def _serialize_for_reparsing(node) -> str:
    """Строка узла, годная к повторному разбору как HTML.

    Tag.__str__ экранирует потомков сам, а NavigableString — подкласс str и
    возвращает раскодированный текст как есть, из-за чего плейсхолдер
    «<Value>» становится неотличим от тега и пропадает при повторном разборе.
    """
    if isinstance(node, NavigableString):
        return html.escape(str(node), quote=False)
    return str(node)


MEMBER_TYPES = (
    DocumentType.OBJECT_FUNCTION, DocumentType.OBJECT_PROCEDURE,
    DocumentType.OBJECT_PROPERTY, DocumentType.OBJECT_EVENT,
    DocumentType.OBJECT_CONSTRUCTOR,
)
GLOBAL_TYPES = (
    DocumentType.GLOBAL_FUNCTION, DocumentType.GLOBAL_PROCEDURE,
    DocumentType.GLOBAL_EVENT,
)

GLOBAL_CONTEXT_PATH_SEGMENT = "Global context"

PROCEDURE_BY_FUNCTION = {
    DocumentType.GLOBAL_FUNCTION: DocumentType.GLOBAL_PROCEDURE,
    DocumentType.OBJECT_FUNCTION: DocumentType.OBJECT_PROCEDURE,
}

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
        # Флаг обязательности справка пишет на своём языке, поэтому регэксп
        # собирается из диалекта.
        self._parameter_heading_re = re.compile(
            r'<\s*(?P<name>[^<>]*)\s*>\s*(?:\((?P<flag>'
            + '|'.join((dialect.required_flag, dialect.optional_flag))
            + r')\))?\s*\Z'
        )

    def parse_html_content(self, content: bytes, file_path: str) -> Optional[Documentation]:
        """Разбирает страницу справки в документ индекса."""
        try:
            html_content = self._decode_content(content)
            if not html_content:
                return None

            # До первого BeautifulSoup: сырой «<Value1>» открывает настоящий
            # тег уже на этом разборе и съедает остаток страницы.
            soup = BeautifulSoup(escape_pseudo_tags(html_content), 'html.parser')

            doc_type, object_name, item_name = self._parse_file_path(file_path)
            doc_type = self._narrow_callable_type(doc_type, soup)

            doc = Documentation(
                id="",
                type=doc_type,
                name=item_name,
                object=object_name,
                source_file=file_path,
            )

            self._extract_title_and_description(soup, doc)

            object_name_ru, object_name_en = self._extract_object_names(soup)
            doc.object = self._owner_of(doc, soup, object_name_ru)
            doc.element_kind = ELEMENT_KIND_BY_TYPE.get(doc.type, "")
            doc.object_ru = object_name_ru or doc.object
            doc.object_en = object_name_en
            self._extract_element_sections(soup, doc)

            if doc.type == DocumentType.OBJECT_PROPERTY:
                self._extract_property_type(soup, doc)

            if doc.type == DocumentType.OBJECT:
                self._extract_object_methods(soup, doc)
                self._extract_object_properties(soup, doc)
                self._extract_object_events(soup, doc)
            else:
                self._extract_variants(soup, doc)
                self._extract_examples(soup, doc)

            self._extract_version(soup, doc)
            doc.build_call_strings()

            logger.debug(f"Обработан HTML файл: {file_path} -> {doc.name}")
            return doc

        except Exception as e:
            logger.error(f"Ошибка парсинга HTML файла {file_path}: {e}")
            return None
    
    def _narrow_callable_type(
        self, doc_type: DocumentType, soup: BeautifulSoup
    ) -> DocumentType:
        """Функция или процедура — видно по наличию раздела о результате."""
        if doc_type not in PROCEDURE_BY_FUNCTION:
            return doc_type
        if self._is_function_not_procedure(soup):
            return doc_type
        return PROCEDURE_BY_FUNCTION[doc_type]

    def _owner_of(
        self, doc: Documentation, soup: BeautifulSoup, object_name_ru: Optional[str]
    ) -> Optional[str]:
        """Имя объекта-владельца страницы.

        Член объекта берёт его из V8SH_title: собственный заголовок страницы
        имя владельца не обязан повторять. Глобальные берут имя из диалекта —
        путь страницы английский в обеих книгах. Страница самого объекта
        разбирает свой заголовок.
        """
        if doc.type in MEMBER_TYPES:
            return (
                object_name_ru
                or self._extract_object_name_from_title(soup)
                or doc.object
            )
        if doc.type in GLOBAL_TYPES:
            return self.dialect.global_context_name
        return self._extract_object_name_from_title(soup)

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
        """Вид элемента, имя владельца и имя страницы — по пути внутри книги.

        Глобальных свойств в 1С нет, поэтому у папки properties владелец всегда
        объектный. Владелец «Global context» переводит метод и событие в
        глобальный вид.
        """
        path = file_path or ""
        file_name = path.rsplit('/', 1)[-1]
        if file_name.endswith('.html'):
            file_name = file_name[:-5]
        lowered = path.lower()

        if '/methods/' in lowered:
            owner = self._extract_object_name(path, 'methods')
            return self._global_or_object(
                owner, DocumentType.GLOBAL_FUNCTION, DocumentType.OBJECT_FUNCTION
            ), owner, file_name

        if '/properties/' in lowered:
            owner = self._extract_object_name(path, 'properties')
            return DocumentType.OBJECT_PROPERTY, owner, file_name

        if '/events/' in lowered:
            owner = self._extract_object_name(path, 'events')
            return self._global_or_object(
                owner, DocumentType.GLOBAL_EVENT, DocumentType.OBJECT_EVENT
            ), owner, file_name

        if '/ctors/' in lowered or '/ctor/' in lowered:
            owner = self._extract_object_name(path, 'ctors') \
                or self._extract_object_name(path, 'ctor')
            return DocumentType.OBJECT_CONSTRUCTOR, owner, file_name

        if 'globalfunctions/' in lowered or '/functions/' in lowered:
            return DocumentType.GLOBAL_FUNCTION, None, file_name

        if '/objects/' in lowered or lowered.startswith('objects/'):
            return DocumentType.OBJECT, self._extract_main_object_name(path), file_name

        return DocumentType.OBJECT, None, file_name

    @staticmethod
    def _global_or_object(
        owner: Optional[str], global_type: DocumentType, object_type: DocumentType
    ) -> DocumentType:
        is_global = bool(owner) and owner.lower() == GLOBAL_CONTEXT_PATH_SEGMENT.lower()
        return global_type if is_global else object_type

    @staticmethod
    def _index_of_segment(parts: list, segment: str) -> Optional[int]:
        for position, part in enumerate(parts):
            if part.lower() == segment:
                return position
        return None

    def _extract_object_name(self, path_str: str, member_type: str) -> Optional[str]:
        """Имя владельца — сегмент пути перед папкой methods/properties/events.

        Служебный сегмент вида «catalog123» именем не является: за настоящим
        именем поднимаемся вверх по пути.
        """
        parts = path_str.split('/')
        member_idx = self._index_of_segment(parts, member_type)
        if not member_idx:
            return None

        owner = parts[member_idx - 1]
        if owner == GLOBAL_CONTEXT_PATH_SEGMENT:
            return GLOBAL_CONTEXT_PATH_SEGMENT

        if owner.startswith('catalog'):
            for position in range(member_idx - 1, -1, -1):
                part = parts[position]
                if not part.startswith('catalog') and part != 'objects':
                    return part

        return owner

    def _extract_main_object_name(self, path_str: str) -> Optional[str]:
        """Имя объекта из пути его собственной страницы.

        «objects/catalog125/catalog462/object464.html» → «catalog462»:
        последний каталог перед файлом, иначе первый сегмент после objects.
        """
        parts = path_str.split('/')
        objects_idx = self._index_of_segment(parts, 'objects')
        if objects_idx is None or objects_idx + 1 >= len(parts):
            return None

        for position in range(len(parts) - 2, objects_idx, -1):
            part = parts[position]
            if not part.endswith('.html') and part.startswith('catalog'):
                return part

        first_after_objects = parts[objects_idx + 1]
        return None if first_after_objects.endswith('.html') else first_after_objects

    def _is_function_not_procedure(self, soup: BeautifulSoup) -> bool:
        """У функции есть раздел о возвращаемом значении, у процедуры — нет."""
        return any(
            self.dialect.chapter_of(header.get_text(strip=True)) is Chapter.RETURN_VALUE
            for header in soup.find_all('p', class_='V8SH_chapter')
        )

    def _extract_object_name_from_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Имя объекта из заголовка страницы — всё, кроме последнего сегмента.

        «РегистрБухгалтерииМенеджер.<Имя регистра>» → «РегистрБухгалтерииМенеджер»,
        «КритерийОтбораМенеджер.<Имя критерия>.ОбработкаПолученияФормы» →
        «КритерийОтбораМенеджер.<Имя критерия>».
        """
        title_tag = soup.find('h1', class_='V8SH_pagetitle') \
            or soup.find('p', class_='V8SH_heading')
        if not title_tag:
            return None

        title_text = title_tag.get_text(strip=True)
        if not title_text:
            return None

        russian_part = title_text.split(' (')[0]
        return russian_part.rsplit('.', 1)[0].strip()

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
    
    @staticmethod
    def _object_name_from_title(title_text: str) -> str:
        """Имя объекта из заголовка страницы объекта.

        Английская часть остаётся в имени: индексатор разложит её в name_en, а
        name_ru() отрежет для путей. Точка ищется в русской части — у
        «СправочникМенеджер.<Имя справочника> (CatalogManager.<Catalog name>)»
        она есть в обеих половинах, и разрез по первой точке всей строки
        оставляет английский хвост целым.
        """
        if '.' in title_text.split(' (')[0]:
            return title_text.split('.', 1)[1].strip()
        return title_text

    @staticmethod
    def _element_name_from_title(title_text: str) -> str:
        """Имя элемента из заголовка: последний сегмент каждой половины."""
        if '.' not in title_text:
            return title_text

        russian_part, _, english_part = title_text.partition(' (')
        russian_name = russian_part.split('.')[-1]
        if not english_part:
            return russian_name

        english_name = english_part.replace(')', '').split('.')[-1]
        return f"{russian_name} ({english_name})"

    def _extract_title_and_description(self, soup: BeautifulSoup, doc: Documentation):
        """Извлекает заголовок и описание."""
        title_tag = soup.find('h1', class_='V8SH_pagetitle') \
            or soup.find('p', class_='V8SH_heading')
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            if title_text:
                doc.name = self._object_name_from_title(title_text) \
                    if doc.type == DocumentType.OBJECT \
                    else self._element_name_from_title(title_text)

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
                    doc.description = clean_prose(' '.join(description_parts))
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
                doc.note = clean_prose(text_from_html(html))
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

    def _extract_object_names(self, soup: BeautifulSoup) -> Tuple[Optional[str], Optional[str]]:
        """«ТаблицаЗначений (ValueTable)» → («ТаблицаЗначений», «ValueTable»).

        V8SH_title есть на каждой странице метода, свойства и конструктора, и
        английское имя объекта лежит именно там — брать его больше неоткуда.
        Расщепление то же, что и для doc.name (split_name_ru_en): владелец
        глобальных функций назван двумя словами — «Глобальный контекст
        (Global context)», а не однословным идентификатором, поэтому regex
        принимает в скобках любой текст без кириллицы, а не только вид
        "Identifier".
        """
        title = soup.find('p', class_='V8SH_title')
        if not title:
            return None, None
        name_ru, name_en = split_name_ru_en(title.get_text(strip=True))
        return name_ru or None, name_en

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
                take_current().description = clean_prose(text_from_html(html))

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
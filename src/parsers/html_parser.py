"""Парсер HTML документации 1С."""

import re
from typing import Optional
from bs4 import BeautifulSoup

from src.models.doc_models import (
    Documentation, Parameter, SyntaxVariant, DocumentType,
    ObjectMethod, ObjectProperty, ObjectEvent,
)
from src.core.logging import get_logger
from src.parsers.tekst import (
    izvlech_tip_i_poyasnenie, normalizovat_probely, pochistit_opisanie, tekst_iz_html,
)

logger = get_logger(__name__)

# Вид элемента по-русски: агент читает карточку, а не enum индекса.
VID_ELEMENTA = {
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
                id="",  # Будет заполнен в sobrat_vyzovy
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

            doc.element_kind = VID_ELEMENTA.get(doc.type, "")
            doc.object_ru = self._izvlech_russkoe_imya_obekta(soup) or doc.object
            self._izvlech_razdely_elementa(soup, doc)

            if doc.type == DocumentType.OBJECT_PROPERTY:
                self._izvlech_tip_svoystva(soup, doc)

            # Для объектов извлекаем методы, свойства и события
            if doc.type == DocumentType.OBJECT:
                self._extract_object_methods(soup, doc)
                self._extract_object_properties(soup, doc)
                self._extract_object_events(soup, doc)
            else:
                # Для функций/методов/событий извлекаем варианты вызова и примеры
                self._izvlech_varianty(soup, doc)
                self._extract_examples(soup, doc)
            
            self._extract_version(soup, doc)
            
            # Автоматически заполняем служебные поля
            doc.sobrat_vyzovy()
            
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
            header_text = header.get_text(strip=True).lower()
            if 'возвращаемое' in header_text or 'return' in header_text:
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
    
    def _get_content_after_chapter(self, soup: BeautifulSoup, chapter_keywords: list) -> str:
        """
        Универсальный метод для получения HTML контента после заголовка V8SH_chapter.
        
        Args:
            soup: Объект BeautifulSoup
            chapter_keywords: Список ключевых слов для поиска заголовка (в нижнем регистре)
            
        Returns:
            HTML строка с контентом после найденного заголовка до следующего заголовка
        """
        chapter_headers = soup.find_all('p', class_='V8SH_chapter')
        
        for header in chapter_headers:
            header_text = header.get_text(strip=True).lower()
            if any(keyword in header_text for keyword in chapter_keywords):
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
            header_text = header.get_text(strip=True).lower()
            if 'описание' in header_text or 'description' in header_text:
                # Ищем в тексте после заголовка до следующего V8SH_chapter
                description_parts = []
                elem = header.next_sibling
                
                while elem:
                    # Если нашли следующий заголовок - прерываем
                    if (hasattr(elem, 'get') and hasattr(elem, 'get_text') and 
                        elem.get('class') == ['V8SH_chapter']):
                        break
                    
                    if hasattr(elem, 'get_text'):
                        text = elem.get_text().strip()  # Сохраняем внутренние пробелы
                        if text and len(text) > 3:  # Игнорируем короткие фрагменты
                            description_parts.append(text)
                    elif isinstance(elem, str):
                        text = elem.strip()
                        if text and len(text) > 3:
                            description_parts.append(text)
                    
                    elem = elem.next_sibling
                
                if description_parts:
                    doc.description = ' '.join(description_parts)
                    break
    
    def _glavy(self, soup: BeautifulSoup):
        """Главы страницы: [(заголовок, html после заголовка), …].

        Идём по узлам-соседям, а не поиском подстроки в HTML родителя: на
        странице с вариантами заголовки «Синтаксис:» текстуально одинаковы, и
        поиск подстроки возвращал бы для каждого позицию первого.
        """
        glavy = []
        for header in soup.find_all('p', class_='V8SH_chapter'):
            chasti = []
            elem = header.next_sibling
            while elem is not None:
                if getattr(elem, 'name', None) == 'hr':
                    # <HR> отделяет подвал страницы («Методическая информация»)
                    # от содержимого. Если глава последняя на странице, следующего
                    # заголовка V8SH_chapter нет, и без этой границы сбор дошёл
                    # бы до конца документа, затянув подвал в текст главы.
                    break
                klassy = elem.get('class') or [] if hasattr(elem, 'get') else []
                if 'V8SH_chapter' in klassy:
                    break
                chasti.append(str(elem))
                elem = elem.next_sibling
            glavy.append((header.get_text(strip=True), "".join(chasti)))
        return glavy

    def _izvlech_razdely_elementa(self, soup: BeautifulSoup, doc: Documentation):
        """Разделы, относящиеся к элементу целиком, а не к варианту вызова."""
        for zagolovok, html in self._glavy(soup):
            nizhniy = zagolovok.lower().rstrip(':').strip()

            if nizhniy == 'доступность':
                doc.availability = self._razobrat_dostupnost(html)
            elif nizhniy == 'примечание':
                doc.note = pochistit_opisanie(tekst_iz_html(html))
            elif nizhniy == 'использование':
                # Ровно «Использование:». Заголовок «Использование в версии:»
                # говорит о версии платформы и в доступ к свойству не годится.
                doc.usage = normalizovat_probely(tekst_iz_html(html)).rstrip('.').lower()

    @staticmethod
    def _razobrat_dostupnost(html: str):
        """«Сервер, толстый клиент, внешнее соединение.» → список контекстов."""
        tekst = normalizovat_probely(tekst_iz_html(html)).rstrip('.')
        return [chast.strip().lower() for chast in tekst.split(',') if chast.strip()]

    def _izvlech_tip_svoystva(self, soup: BeautifulSoup, doc: Documentation):
        """Вынимает «Тип: X.» из начала описания свойства в отдельное поле.

        В справке тип значения свойства стоит первой фразой раздела «Описание:»,
        причём в HTML это россыпь узлов (текст, ссылка, <br>) без общего
        родителя-<p>. Общий сборщик _extract_title_and_description отбрасывает
        короткие текстовые фрагменты (в т.ч. точку после ссылки на тип) и рвёт
        границу между типом и пояснением, поэтому раздел разбирается заново из
        собственного HTML, а не из уже собранного doc.description.
        """
        for zagolovok, html in self._glavy(soup):
            if zagolovok.lower().rstrip(':').strip() != 'описание':
                continue

            tekst = tekst_iz_html(html).strip()
            if tekst.startswith('Тип:'):
                doc.value_type, doc.description = izvlech_tip_i_poyasnenie(html)
            break

    def _izvlech_russkoe_imya_obekta(self, soup: BeautifulSoup) -> Optional[str]:
        """«ТаблицаЗначений (ValueTable)» → «ТаблицаЗначений»."""
        title = soup.find('p', class_='V8SH_title')
        if not title:
            return None
        tekst = title.get_text(strip=True)
        return tekst.split(' (')[0].strip() or None

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
    _ZAGOLOVOK_PARAMETRA = re.compile(
        r'<\s*(?P<imya>[^<>]*)\s*>\s*(?:\((?P<flag>обязательный|необязательный)\))?\s*\Z'
    )

    def _razobrat_zagolovok_parametra(self, tekst: str):
        """Возвращает (имя, обязательность) из '<Индекс> (обязательный)'.

        BeautifulSoup уже превратил &lt; в <, поэтому имя ищется в угловых
        скобках. Обязательность None — справка о ней молчит.
        """
        sovpadenie = self._ZAGOLOVOK_PARAMETRA.search(tekst.replace('\xa0', ' '))
        if not sovpadenie:
            return "", None

        imya = sovpadenie.group('imya').strip()
        flag = sovpadenie.group('flag')
        if flag == 'обязательный':
            return imya, True
        if flag == 'необязательный':
            return imya, False
        return imya, None

    def _razobrat_parametry(self, html: str):
        """Параметры одной главы «Параметры:»."""
        from bs4 import BeautifulSoup as BS

        sup = BS(html or "", 'html.parser')
        parametry = []
        for rubric in sup.find_all('div', class_='V8SH_rubric'):
            imya, obyazatelnyy = self._razobrat_zagolovok_parametra(
                rubric.get_text(' ', strip=True)
            )
            if not imya:
                continue

            chasti = []
            elem = rubric.next_sibling
            while elem is not None:
                klassy = elem.get('class') or [] if hasattr(elem, 'get') else []
                if 'V8SH_rubric' in klassy:
                    break
                chasti.append(str(elem))
                elem = elem.next_sibling

            tip, opisanie = izvlech_tip_i_poyasnenie("".join(chasti))
            parametry.append(
                Parameter(name=imya, type=tip, description=opisanie,
                          required=obyazatelnyy)
            )
        return parametry

    def _izvlech_varianty(self, soup: BeautifulSoup, doc: Documentation):
        """Собирает варианты вызова.

        «Синтаксис», «Параметры» и «Возвращаемое значение» принадлежат текущему
        варианту — последнему встреченному «Вариант синтаксиса». Всё остальное
        относится к элементу целиком.
        """
        varianty = []
        tekushchiy = None

        def vzyat_tekushchiy():
            nonlocal tekushchiy
            if tekushchiy is None:
                tekushchiy = SyntaxVariant()
                varianty.append(tekushchiy)
            return tekushchiy

        for zagolovok, html in self._glavy(soup):
            nizhniy = zagolovok.lower().rstrip(':').strip()

            if nizhniy.startswith('вариант синтаксиса'):
                imya = zagolovok.split(':', 1)[1].strip() if ':' in zagolovok else ""
                tekushchiy = SyntaxVariant(variant=imya)
                varianty.append(tekushchiy)
            elif nizhniy == 'синтаксис':
                vzyat_tekushchiy().syntax = normalizovat_probely(tekst_iz_html(html))
            elif nizhniy.startswith('параметр'):
                vzyat_tekushchiy().parameters = self._razobrat_parametry(html)
            elif nizhniy.startswith('возвращаемое значение'):
                variant = vzyat_tekushchiy()
                variant.return_type, variant.return_description = \
                    izvlech_tip_i_poyasnenie(html)

        if doc.type == DocumentType.OBJECT_CONSTRUCTOR:
            # У конструкторов варианты разложены по отдельным страницам справки,
            # и заголовка «Вариант синтаксиса» на них нет: имя варианта («По
            # количеству элементов») — это имя самой страницы. Раньше оно
            # выдавалось за имя элемента, и путь получался бессмысленный:
            # «Массив.По количеству элементов» вместо «Новый Массив(...)».
            if not varianty:
                varianty.append(SyntaxVariant())
            for v in varianty:
                if not v.variant:
                    v.variant = doc.imya_ru()

        doc.variants = varianty
        doc.syntax_all = " | ".join(v.syntax for v in varianty if v.syntax)

    def _extract_examples(self, soup: BeautifulSoup, doc: Documentation):
        """Извлекает примеры кода."""
        # Ищем заголовок "Пример:" с классом V8SH_chapter
        example_headers = soup.find_all('p', class_='V8SH_chapter')
        
        for header in example_headers:
            header_text = header.get_text(strip=True).lower()
            if 'пример' not in header_text and 'example' not in header_text:
                continue
                
            # Ищем таблицы с кодом после заголовка
            elem = header.next_sibling
            while elem:
                # Если нашли следующий заголовок - прерываем
                if (hasattr(elem, 'get') and hasattr(elem, 'get_text') and 
                    elem.get('class') == ['V8SH_chapter']):
                    break
                
                # Пропускаем текстовые узлы и элементы без методов find
                if not (hasattr(elem, 'name') and elem.name and hasattr(elem, 'find')):
                    elem = elem.next_sibling
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
                                doc.examples.append(full_code.strip())
                
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
                if 'доступен' in version_text.lower() or 'начиная' in version_text.lower():
                    doc.version_from = version
                elif 'изменен' in version_text.lower() or 'описание' in version_text.lower():
                    # Это версия изменения, можно сохранить как дополнительную информацию
                    if not doc.version_from:
                        doc.version_from = version
    
    def _extract_object_methods(self, soup: BeautifulSoup, doc: Documentation):
        """Извлекает методы объекта."""
        # Ищем секцию "Методы:"
        methods_section = self._get_content_after_chapter(soup, ['методы'])
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
        properties_section = self._get_content_after_chapter(soup, ['свойства'])
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
        events_section = self._get_content_after_chapter(soup, ['события'])
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
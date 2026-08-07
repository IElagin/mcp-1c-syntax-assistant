"""Языковые диалекты справки 1С.

Русская и английская книги устроены одинаково: те же внутренние пути, те же
CSS-классы, тот же порядок глав. Различается только текст заголовков. Поэтому
парсер не ветвится по языку, а спрашивает диалект — таблицу строк.

Ветвление по языку в двенадцати местах разбора дало бы двенадцать мест, где
можно забыть вторую ветку, и терять раздел молча: карточка недосчиталась бы
поля, а тест на неё об этом бы не узнал.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple


class Chapter(str, Enum):
    """Разделы страницы справки, независимые от языка."""

    SYNTAX = "syntax"
    SYNTAX_VARIANT = "syntax_variant"
    PARAMETERS = "parameters"
    RETURN_VALUE = "return_value"
    DESCRIPTION = "description"
    VARIANT_DESCRIPTION = "variant_description"
    AVAILABILITY = "availability"
    NOTE = "note"
    EXAMPLE = "example"
    VERSION = "version"
    USAGE = "usage"
    METHODS = "methods"
    PROPERTIES = "properties"
    EVENTS = "events"
    CONSTRUCTORS = "constructors"
    COLLECTION_ELEMENTS = "collection_elements"
    SEE_ALSO = "see_also"
    FORM_PARAMETERS = "form_parameters"
    # Раздел страниц-каталогов встроенных именованных наборов (StyleColors,
    # StyleFonts, PictureLib, Chars и т.п.) — перечень значений набора, а не
    # элементов коллекции произвольного типа. Обнаружен сверкой словаря с
    # реальной книгой (замер по всем 23 125 парным страницам objects/ каждой
    # книги: 623 вхождения что в русской, что в английской, без варианта
    # написания с двоеточием ни в одной).
    VALUES = "values"


def _normalize(heading: str) -> str:
    """Заголовок в сравнимом виде: без хвостового двоеточия и лишних пробелов."""
    return " ".join((heading or "").replace("\xa0", " ").split()).rstrip(":").strip().lower()


@dataclass(frozen=True)
class HelpDialect:
    """Как звучат разделы и метки справки на одном языке."""

    lang: str
    chapters: Dict[Chapter, str]
    type_label: str
    required_flag: str
    optional_flag: str
    version_available_markers: Tuple[str, ...]
    version_changed_markers: Tuple[str, ...]
    # Как книга зовёт глобальный контекст. Путь страницы этого не говорит: он
    # английский в обеих книгах (objects/Global context/...), и разбор пути
    # оставлял русским глобальным функциям владельца «Global context» — имя,
    # которого в русской справке нет ни на одной странице. Из-за этого 479
    # процедур и функций глобального контекста не находились по имени
    # владельца, под которым книга их и печатает.
    global_context_name: str

    def chapter_of(self, heading: str) -> Optional[Chapter]:
        """Раздел по тексту заголовка; None — раздел диалекту неизвестен.

        Заголовок варианта вызова несёт хвост («Вариант синтаксиса: По
        индексу»), поэтому проверяется первым и по префиксу. Все остальные
        сравниваются на точное равенство: «Использование:» и «Использование в
        версии:» — разные разделы, и префиксное сравнение их бы склеило.
        """
        normalized = _normalize(heading)
        if not normalized:
            return None

        variant_prefix = _normalize(self.chapters[Chapter.SYNTAX_VARIANT])
        if normalized.startswith(variant_prefix):
            return Chapter.SYNTAX_VARIANT

        for chapter, title in self.chapters.items():
            if chapter is Chapter.SYNTAX_VARIANT:
                continue
            if normalized == _normalize(title):
                return chapter
        return None

    def variant_name(self, heading: str) -> str:
        """«Вариант синтаксиса: По индексу» → «По индексу»."""
        _, _, tail = (heading or "").partition(":")
        return tail.strip()

    def required_from_flag(self, flag: str) -> Optional[bool]:
        """Обязательность параметра по флагу в скобке; None — справка молчит."""
        normalized = (flag or "").strip().lower()
        if normalized == self.required_flag:
            return True
        if normalized == self.optional_flag:
            return False
        return None

    def is_version_available(self, text: str) -> bool:
        lowered = (text or "").lower()
        return any(marker in lowered for marker in self.version_available_markers)

    def is_version_changed(self, text: str) -> bool:
        lowered = (text or "").lower()
        return any(marker in lowered for marker in self.version_changed_markers)


RU_DIALECT = HelpDialect(
    lang="ru",
    chapters={
        Chapter.SYNTAX: "Синтаксис:",
        Chapter.SYNTAX_VARIANT: "Вариант синтаксиса:",
        Chapter.PARAMETERS: "Параметры:",
        Chapter.RETURN_VALUE: "Возвращаемое значение:",
        Chapter.DESCRIPTION: "Описание:",
        Chapter.VARIANT_DESCRIPTION: "Описание варианта метода:",
        Chapter.AVAILABILITY: "Доступность:",
        Chapter.NOTE: "Примечание:",
        Chapter.EXAMPLE: "Пример:",
        Chapter.VERSION: "Использование в версии:",
        Chapter.USAGE: "Использование:",
        Chapter.METHODS: "Методы:",
        Chapter.PROPERTIES: "Свойства:",
        Chapter.EVENTS: "События:",
        Chapter.CONSTRUCTORS: "Конструкторы:",
        Chapter.COLLECTION_ELEMENTS: "Элементы коллекции:",
        Chapter.SEE_ALSO: "См. также:",
        Chapter.FORM_PARAMETERS: "Параметры формы:",
        Chapter.VALUES: "Значения",
    },
    type_label="Тип:",
    required_flag="обязательный",
    optional_flag="необязательный",
    version_available_markers=("доступен", "начиная"),
    version_changed_markers=("изменен", "описание"),
    global_context_name="Глобальный контекст",
)

# Значения измерены на книгах 8.3.20.1914: 3 975 парных страниц, счётчики
# разделов совпали в обеих книгах до единицы. «Returned value:» — именно так,
# а не «Return value:», как подсказывает интуиция.
EN_DIALECT = HelpDialect(
    lang="en",
    chapters={
        Chapter.SYNTAX: "Syntax:",
        Chapter.SYNTAX_VARIANT: "Syntax variant:",
        Chapter.PARAMETERS: "Parameters:",
        Chapter.RETURN_VALUE: "Returned value:",
        Chapter.DESCRIPTION: "Description:",
        Chapter.VARIANT_DESCRIPTION: "Description of method variant:",
        Chapter.AVAILABILITY: "Availability:",
        Chapter.NOTE: "Note:",
        Chapter.EXAMPLE: "Example:",
        Chapter.VERSION: "Available since:",
        Chapter.USAGE: "Usage:",
        Chapter.METHODS: "Methods:",
        Chapter.PROPERTIES: "Properties:",
        Chapter.EVENTS: "Events:",
        Chapter.CONSTRUCTORS: "Constructors:",
        Chapter.COLLECTION_ELEMENTS: "Collection elements:",
        Chapter.SEE_ALSO: "See also:",
        Chapter.FORM_PARAMETERS: "Form parameters:",
        Chapter.VALUES: "Values",
    },
    type_label="Type:",
    required_flag="required",
    optional_flag="optional",
    # «since version» покрывает и «Available since version», и «It is not
    # recommended to use since version» — ровно как русское «начиная» покрывает
    # оба соответствующих случая.
    version_available_markers=("since version",),
    version_changed_markers=("changed in version",),
    global_context_name="Global context",
)

_DIALECTS = {d.lang: d for d in (RU_DIALECT, EN_DIALECT)}


def dialect_for(lang: str) -> HelpDialect:
    """Диалект по коду языка. Неизвестный язык — ошибка, а не молчаливый русский."""
    try:
        return _DIALECTS[lang]
    except KeyError:
        raise ValueError(
            f"Неизвестный язык справки: {lang!r}. Доступны: "
            + ", ".join(sorted(_DIALECTS))
        ) from None

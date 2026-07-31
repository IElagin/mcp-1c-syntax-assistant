"""Модели для документации 1С."""

from typing import ClassVar, List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field
from enum import Enum


class DocumentType(str, Enum):
    """Типы документации 1С."""
    GLOBAL_FUNCTION = "global_function"
    GLOBAL_PROCEDURE = "global_procedure"
    GLOBAL_EVENT = "global_event"
    OBJECT_FUNCTION = "object_function"
    OBJECT_PROCEDURE = "object_procedure"
    OBJECT_PROPERTY = "object_property"
    OBJECT_EVENT = "object_event"
    OBJECT_CONSTRUCTOR = "object_constructor"
    OBJECT = "object"


class ObjectMethod(BaseModel):
    """Метод объекта."""
    name: str
    name_en: str = ""
    href: str = ""
    
    
class ObjectProperty(BaseModel):
    """Свойство объекта."""
    name: str
    name_en: str = ""
    href: str = ""


class ObjectEvent(BaseModel):
    """Событие объекта."""
    name: str
    name_en: str = ""
    href: str = ""


class Parameter(BaseModel):
    """Параметр функции/метода."""
    name: str
    type: str = ""
    description: str = ""
    # None — справка об обязательности молчит. Раньше здесь стояло True по
    # умолчанию, и карточка объявляла обязательными 2 677 параметров, которые
    # справка помечает необязательными. Ложь хуже отсутствия данных: агент
    # передаёт лишний аргумент и получает отказ платформы.
    required: Optional[bool] = None


class SyntaxVariant(BaseModel):
    """Вариант вызова элемента.

    У 247 методов справки несколько вариантов вызова с разными параметрами
    («Удалить(<Индекс>)» и «Удалить(<Элемент>)»), а у конструкторов вариант
    приходит отдельной страницей. Один вариант — один способ вызвать.
    """
    variant: str = ""
    syntax: str = ""
    call: str = ""
    parameters: List[Parameter] = []
    return_type: str = ""
    return_description: str = ""


class Documentation(BaseModel):
    """Базовая модель документации."""
    id: str = Field(..., description="Уникальный идентификатор")
    type: DocumentType
    name: str
    object: Optional[str] = None  # Для методов/свойств/событий объектов
    description: str = ""
    variants: List[SyntaxVariant] = []
    call_primary: str = ""
    syntax_all: str = ""
    usage: Optional[str] = None  # Для свойств - "чтение и запись", "только чтение" и т.д.
    element_kind: str = ""          # функция / процедура / свойство / событие / конструктор / объект
    object_ru: Optional[str] = None  # «Глобальный контекст» вместо технического Global context
    value_type: str = ""            # тип значения свойства
    availability: List[str] = []    # контексты исполнения в нижнем регистре
    note: str = ""                  # раздел «Примечание»
    version_from: Optional[str] = None
    examples: List[str] = []
    source_file: str = ""
    full_path: str = ""  # Полный путь типа "ТаблицаЗначений.Добавить"

    # Для объектов - списки методов, свойств и событий
    methods: List[ObjectMethod] = []
    properties: List[ObjectProperty] = []
    events: List[ObjectEvent] = []

    def imya_ru(self) -> str:
        """Русская часть имени: из «Добавить (Add)» — «Добавить»."""
        imya = (self.name or "").strip()
        if imya.endswith(')') and ' (' in imya:
            return imya.rsplit(' (', 1)[0].strip()
        return imya

    # ClassVar — иначе pydantic 2 примет присвоение без аннотации типа за
    # попытку объявить поле модели и упадёт с PydanticUserError.
    GLOBALNYE: ClassVar[Tuple[DocumentType, ...]] = (
        DocumentType.GLOBAL_FUNCTION,
        DocumentType.GLOBAL_PROCEDURE,
        DocumentType.GLOBAL_EVENT,
    )

    def sobrat_vyzovy(self):
        """Заполняет строки вызова и канонический путь.

        Раньше full_path собирался как «Global context.ЗначениеЗаполнено
        (ValueIsFilled)» — агент мог принять это за код вызова. Канонический
        путь не содержит ни английского имени, ни технического Global context.
        """
        imya = self.imya_ru()

        if self.type in self.GLOBALNYE:
            self.full_path = imya
        elif self.object:
            self.full_path = f"{self.object}.{imya}"
        else:
            self.full_path = imya

        for variant in self.variants:
            if self.type == DocumentType.OBJECT_CONSTRUCTOR:
                variant.call = variant.syntax or f"Новый {self.object or imya}"
            elif self.type in self.GLOBALNYE:
                variant.call = variant.syntax
            elif self.object and variant.syntax:
                variant.call = f"{self.object}.{variant.syntax}"
            else:
                variant.call = variant.syntax

        if self.variants:
            self.call_primary = self.variants[0].call
        elif self.type == DocumentType.OBJECT_PROPERTY:
            # У свойства раздела «Синтаксис» нет: обращение — это путь.
            self.call_primary = self.full_path
        else:
            self.call_primary = ""

        # Обычно syntax_all уже выставлен парсером (_izvlech_varianty), но
        # пересчитываем и здесь: sobrat_vyzovy вызывается и на документах,
        # собранных напрямую (тесты, фикстуры) — без парсера поле осталось
        # бы пустым по умолчанию.
        self.syntax_all = " | ".join(v.syntax for v in self.variants if v.syntax)

        self.id = f"{self.object}_{self.name}_{self.type.value}" if self.object \
            else f"{self.name}_{self.type.value}"


class HBKFile(BaseModel):
    """Информация о .hbk файле."""
    path: str
    size: int
    modified: float
    entries_count: int = 0


class HBKEntry(BaseModel):
    """Запись в .hbk архиве."""
    path: str
    size: int
    is_dir: bool
    content: Optional[bytes] = None


class CategoryInfo(BaseModel):
    """Информация из файла __categories__."""
    name: str = ""
    description: str = ""
    version_from: Optional[str] = None
    section: str = ""


class ParsedHBK(BaseModel):
    """Результат парсинга .hbk файла."""
    file_info: HBKFile
    categories: Dict[str, CategoryInfo] = {}
    documentation: List[Documentation] = []
    errors: List[str] = []
    stats: Dict[str, int] = {}

"""Модели для MCP Protocol."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field
from enum import Enum

from src import __version__
from src.api.mcp_tools import SEARCH_LIMIT_MAX
from src.core.config import settings


class MCPToolType(str, Enum):
    """Типы MCP инструментов."""
    FIND_1C_HELP = "find_1c_help"
    GET_1C_ELEMENT = "get_1c_element"
    LIST_1C_OBJECT_MEMBERS = "list_1c_object_members"


class SearchKind(str, Enum):
    """Чем ограничить поиск."""
    ANY = "any"
    GLOBAL = "global"
    METHOD = "method"
    PROPERTY = "property"
    EVENT = "event"
    CONSTRUCTOR = "constructor"


class MemberType(str, Enum):
    """Какие элементы объекта перечислить."""
    ALL = "all"
    METHODS = "methods"
    PROPERTIES = "properties"
    EVENTS = "events"
    CONSTRUCTORS = "constructors"


class Lang(str, Enum):
    """Язык ответа. Не язык запроса: искать можно по-русски, а получать по-английски."""
    RU = "ru"
    EN = "en"


class MCPRequest(BaseModel):
    """Базовая модель MCP запроса."""
    tool: MCPToolType
    arguments: Dict[str, Any]


class Find1CHelpRequest(BaseModel):
    """Запрос поиска по справке."""
    # extra="forbid" — схема обещает additionalProperties: false; без этого
    # pydantic по умолчанию молча отбрасывает лишние поля вместо ошибки, и
    # опечатка вроде старого object_name (упразднённое имя параметра) тихо
    # превращалась в поиск без фильтра по объекту — агент получал не тот
    # ответ, о котором просил, и не узнавал об этом.
    model_config = ConfigDict(extra="forbid")

    # min_length=1 у всех имён и запросов — не косметика контракта. Пустая
    # строка не «ничего не задано», а полноценный фильтр: term по
    # name_en.keyword == "" совпадает со всеми 23 104 документами английского
    # индекса (английские заголовки скобок не несут, поле пустое почти везде), а
    # term по object == "" — с документами без объекта-владельца. Агент,
    # приславший пустое имя по ошибке, получал в ответ «имя принадлежит 10 000
    # элементов» вместо отказа, то есть узнавал о своей ошибке не от сервера.
    # Отказ валидации доезжает до клиента как isError с текстом pydantic.
    query: str = Field(..., min_length=1, description="Поисковый запрос")
    kind: SearchKind = Field(SearchKind.ANY, description="Чем ограничить поиск")
    object: Optional[str] = Field(None, min_length=1, description="Искать только у этого объекта")
    # le=SEARCH_LIMIT_MAX, а не число: тот же потолок используют клемпы советов
    # в mcp_handlers и element_card. Рассинхронизация трёх хардкодов 200
    # приводила к тому, что карточка советовала вызов, отвергаемый тем же
    # лимитом.
    limit: int = Field(10, ge=1, le=SEARCH_LIMIT_MAX, description="Сколько кандидатов вернуть")
    lang: Lang = Field(
        default_factory=lambda: Lang(settings.default_help_lang),
        description="Язык ответа",
    )


class Get1CElementRequest(BaseModel):
    """Запрос карточки элемента."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, description="Точное имя элемента")
    object: Optional[str] = Field(None, min_length=1, description="Объект справки")
    variant: Optional[str] = Field(None, min_length=1, description="Имя варианта вызова")
    lang: Lang = Field(
        default_factory=lambda: Lang(settings.default_help_lang),
        description="Язык ответа",
    )


class List1CObjectMembersRequest(BaseModel):
    """Запрос состава объекта."""
    model_config = ConfigDict(extra="forbid")

    object: str = Field(..., min_length=1, description="Имя объекта справки")
    members: MemberType = Field(MemberType.ALL, description="Какие элементы перечислить")
    limit: int = Field(100, ge=1, le=1000, description="Сколько элементов вернуть")
    lang: Lang = Field(
        default_factory=lambda: Lang(settings.default_help_lang),
        description="Язык ответа",
    )


class MCPResponse(BaseModel):
    """Базовая модель MCP ответа."""
    content: List[Dict[str, str]]
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """Модель ответа health check."""
    status: str
    elasticsearch: bool
    index_exists: bool
    documents_count: Optional[int] = None
    indexing_status: Optional[str] = None
    indexing_active: Optional[bool] = None
    # Отсутствие английского индекса — не болезнь сервера: книга необязательна.
    # Поле присутствует всегда, чтобы клиент отличал «нет индекса» от «сервер
    # не умеет английский».
    index_en_exists: Optional[bool] = None
    documents_count_en: Optional[int] = None
    # Версия — из src/__init__.py, единственного источника истины.
    version: str = __version__

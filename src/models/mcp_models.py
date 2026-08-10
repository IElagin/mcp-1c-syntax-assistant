"""Модели для MCP Protocol."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field
from enum import Enum

from src import __version__
from src.core.config import settings
from src.core.constants import (
    MEMBERS_LIMIT_DEFAULT,
    MEMBERS_LIMIT_MAX,
    SEARCH_LIMIT_DEFAULT,
    SEARCH_LIMIT_MAX,
)


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
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, description="Поисковый запрос")
    kind: SearchKind = Field(SearchKind.ANY, description="Чем ограничить поиск")
    object: Optional[str] = Field(None, min_length=1, description="Искать только у этого объекта")
    limit: int = Field(
        SEARCH_LIMIT_DEFAULT, ge=1, le=SEARCH_LIMIT_MAX,
        description="Сколько кандидатов вернуть",
    )
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
    limit: int = Field(
        MEMBERS_LIMIT_DEFAULT, ge=1, le=MEMBERS_LIMIT_MAX,
        description="Сколько элементов вернуть",
    )
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
    index_en_exists: Optional[bool] = None
    documents_count_en: Optional[int] = None
    missing_article_books: List[str] = []
    missing_article_books_en: List[str] = []
    version: str = __version__

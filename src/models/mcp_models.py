"""Модели для MCP Protocol."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


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


class MCPRequest(BaseModel):
    """Базовая модель MCP запроса."""
    tool: MCPToolType
    arguments: Dict[str, Any]


class Find1CHelpRequest(BaseModel):
    """Запрос поиска по справке."""
    query: str = Field(..., description="Поисковый запрос")
    kind: SearchKind = Field(SearchKind.ANY, description="Чем ограничить поиск")
    object: Optional[str] = Field(None, description="Искать только у этого объекта")
    limit: int = Field(10, ge=1, le=200, description="Сколько кандидатов вернуть")


class Get1CElementRequest(BaseModel):
    """Запрос карточки элемента."""
    name: str = Field(..., description="Точное имя элемента")
    object: Optional[str] = Field(None, description="Объект справки")
    variant: Optional[str] = Field(None, description="Имя варианта вызова")


class List1CObjectMembersRequest(BaseModel):
    """Запрос состава объекта."""
    object: str = Field(..., description="Имя объекта справки")
    members: MemberType = Field(MemberType.ALL, description="Какие элементы перечислить")
    limit: int = Field(100, ge=1, le=1000, description="Сколько элементов вернуть")


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
    version: str = "1.0.0"

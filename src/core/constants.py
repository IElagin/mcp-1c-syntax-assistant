"""Константы проекта."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ArticleBook:
    """Книга статей справки и имена её файлов в обеих поставках."""
    key: str
    ru: str
    en: str


ARTICLE_BOOKS = (
    ArticleBook(key="shlang", ru="shlang_ru.hbk", en="shlang_root.hbk"),
    ArticleBook(key="shquery", ru="shquery_ru.hbk", en="shquery_root.hbk"),
    ArticleBook(key="shclang", ru="shclang_ru.hbk", en="shclang_root.hbk"),
    ArticleBook(key="dcsui", ru="dcsui_ru.hbk", en="dcsui_root.hbk"),
)

ELASTICSEARCH_CONNECTION_TIMEOUT = 30
ELASTICSEARCH_REQUEST_TIMEOUT = 60

BATCH_SIZE = 100
MAX_FILE_SIZE_MB = 50

REQUESTS_PER_MINUTE = 60
REQUESTS_PER_HOUR = 1000

SEARCH_LIMIT_DEFAULT = 10
SEARCH_LIMIT_MAX = 200
MEMBERS_LIMIT_DEFAULT = 100
MEMBERS_LIMIT_MAX = 1000
MIN_NAME_LENGTH = 1

SUPPORTED_ENCODINGS = ["utf-8", "cp1251"]

MAX_TOLERATED_PAGE_LOSS_SHARE = 0.05

KIND_TO_TYPE = {
    "any": [],
    "global": ["global_function", "global_procedure", "global_event"],
    "method": ["object_function", "object_procedure"],
    "property": ["object_property"],
    "event": ["object_event"],
    "constructor": ["object_constructor"],
    "article": ["article"],
}

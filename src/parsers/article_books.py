"""Сбор статей всех книг одного языка."""

from pathlib import Path
from typing import List, Tuple

from src.core.constants import ARTICLE_BOOKS
from src.core.logging import get_logger
from src.models.doc_models import Documentation
from src.parsers.article_parser import ArticleDecodingError, decode_article, is_article_file, parse_article_file
from src.parsers.v8_container import HelpBookArchive

logger = get_logger(__name__)


def parse_article_books(directory: str, lang: str) -> Tuple[List[Documentation], List[str]]:
    """Статьи найденных книг и ключи тех, что прочитать не удалось."""
    articles: List[Documentation] = []
    absent: List[str] = []

    for book in ARTICLE_BOOKS:
        path = Path(directory) / (book.en if lang == "en" else book.ru)
        if not path.exists():
            logger.info(f"Книга статей {path.name} не найдена — статьи {book.key} не индексируются")
            absent.append(book.key)
            continue
        try:
            with HelpBookArchive(path) as archive:
                articles.extend(_book_articles(archive, book.key, path.name))
        except Exception as error:
            logger.error(f"Книга статей {path.name} не читается: {error}")
            absent.append(book.key)

    logger.info(f"Собрано статей: {len(articles)}, книг не хватает: {absent or 'нет'}")
    return articles, absent


def _book_articles(archive: HelpBookArchive, book_key: str, book_name: str) -> List[Documentation]:
    """Статьи всех файлов книги; файл, который не читается, не декодируется или не разбирается, теряет только себя."""
    articles: List[Documentation] = []
    for name in archive.names():
        if not is_article_file(book_key, name):
            continue
        try:
            raw = archive.read(name)
        except Exception as error:
            logger.error(f"Файл {name} книги {book_name} не читается: {error}")
            continue
        try:
            html = decode_article(raw)
        except ArticleDecodingError as error:
            logger.error(f"Файл {name} книги {book_name} не декодируется: {error}")
            continue
        try:
            articles.extend(parse_article_file(book_key, name, html))
        except Exception as error:
            logger.error(f"Файл {name} книги {book_name} не разбирается: {error}")
    return articles

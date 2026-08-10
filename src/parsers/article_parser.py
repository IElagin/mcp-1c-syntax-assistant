"""Разбор статей книг справки: язык, запросы, общий синтаксис, выражения СКД."""

from typing import List, Optional

from bs4 import BeautifulSoup, NavigableString, Tag

from src.core.constants import SUPPORTED_ENCODINGS
from src.models.doc_models import Documentation, DocumentType
from src.parsers.text_utils import clean_description

ARTICLE_KIND = "статья"
LEAD_MIN_LENGTH = 40
SECTION_HEADINGS = ("h2", "h3", "h4", "h5", "h6")

SKIPPED_SUFFIXES = (".st", ".gif", ".png", ".jpg", ".jpeg")
SKIPPED_NAMES = ("__categories__",)
SKIPPED_PREFIX = "_CONTENTS_NODE_"
DIALOG_HELP_BOOK = "dcsui"
DIALOG_HELP_PREFIX = "form_"


def is_article_file(book: str, name: str) -> bool:
    """Файл книги несёт статью, а не шаблон, картинку или служебные данные."""
    if name.lower().endswith(SKIPPED_SUFFIXES):
        return False
    if name in SKIPPED_NAMES or name.startswith(SKIPPED_PREFIX):
        return False
    return not (book == DIALOG_HELP_BOOK and name.startswith(DIALOG_HELP_PREFIX))


class ArticleDecodingError(Exception):
    """Файл книги не читается ни в одной из поддерживаемых кодировок."""


def decode_article(raw: bytes) -> str:
    """Текст файла книги; кодировка книг — UTF-8 с BOM."""
    for encoding in ("utf-8-sig", *SUPPORTED_ENCODINGS):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    tried = ["utf-8-sig", *SUPPORTED_ENCODINGS]
    raise ArticleDecodingError(
        f"файл не читается ни в одной из кодировок {tried}: первые байты {raw[:16]!r}"
    )


def parse_article_file(book: str, file_name: str, html: str) -> List[Documentation]:
    """Статьи одного файла книги: целиком или по заголовочным якорям."""
    soup = BeautifulSoup(html or "", "html.parser")
    title = _text_of(soup.find("h1")) or file_name
    sections = _anchored_headings(soup)

    if not sections:
        text = clean_description(soup.get_text(" "))
        return [_article(book, file_name, None, title, text)] if text else []

    articles = []
    lead = _lead_text(soup, sections[0][0], title)
    if len(lead) > LEAD_MIN_LENGTH:
        articles.append(_article(book, file_name, None, title, lead))

    for position, (heading, anchor) in enumerate(sections):
        following = sections[position + 1][0] if position + 1 < len(sections) else None
        articles.append(
            _article(book, file_name, anchor, _text_of(heading), _section_text(heading, following))
        )
    return articles


def _anchored_headings(soup: BeautifulSoup) -> List[tuple]:
    """Заголовки 2–6 уровня, внутри которых стоит якорь с непустым именем."""
    found = []
    for heading in soup.find_all(SECTION_HEADINGS):
        anchor = heading.find("a", attrs={"name": True})
        name = anchor["name"] if anchor else ""
        if name:
            found.append((heading, name))
    return found


def _text_of(node: Optional[Tag]) -> str:
    return clean_description(node.get_text(" ")) if node else ""


def _strings_until(start, stop) -> str:
    collected = []
    for node in start.next_elements:
        if stop is not None and node is stop:
            break
        if isinstance(node, NavigableString):
            collected.append(str(node))
    return clean_description(" ".join(collected))


def _section_text(heading: Tag, following: Optional[Tag]) -> str:
    return _strings_until(heading, following)


def _lead_text(soup: BeautifulSoup, first_heading: Tag, title: str) -> str:
    """Текст файла до первого заголовочного якоря, без самого названия статьи."""
    root = soup.body or soup
    collected = []
    for node in root.descendants:
        if node is first_heading:
            break
        if isinstance(node, NavigableString):
            collected.append(str(node))
    text = clean_description(" ".join(collected))
    return text.replace(title, "", 1).strip() if title else text


def _article(
    book: str, file_name: str, anchor: Optional[str], title: str, text: str
) -> Documentation:
    key = f"{book}/{file_name}" + (f"#{anchor}" if anchor else "")
    return Documentation(
        id=key,
        type=DocumentType.ARTICLE,
        name=title,
        description=text,
        source_file=key,
        full_path=key,
        book=book,
        element_kind=ARTICLE_KIND,
    )

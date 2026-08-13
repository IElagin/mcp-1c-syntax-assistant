"""Разбор статей книг справки: язык, запросы, общий синтаксис, выражения СКД."""

from typing import Iterable, Iterator, List, Optional

from bs4 import BeautifulSoup, NavigableString, Tag
from bs4.element import PreformattedString

from src.core.constants import SUPPORTED_ENCODINGS
from src.models.doc_models import Documentation, DocumentType
from src.parsers.text_utils import (
    clean_description, normalize_lines, restore_space_after_period,
)

ARTICLE_KIND = "статья"
LEAD_MIN_LENGTH = 40
SECTION_HEADINGS = ("h2", "h3", "h4", "h5", "h6")
PAGE_TITLE_HEADING = "h1"
PAGE_HEADER_CLASS = "V8SH_title"
FOOTER_SEPARATOR = "hr"
LINE_BREAK_TAGS = frozenset({
    "br", "p", "div", "li", "tr", "table", "pre", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6",
})
CELL_TAGS = frozenset({"td", "th"})
MONOSPACE_TAGS = frozenset({"pre", "code", "tt", "samp"})
MONOSPACE_FONT = "Courier"
PREFORMATTED_TAGS = frozenset({"pre"})

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
    _drop_page_footer(soup)
    page_title = _text_of(soup.find(PAGE_TITLE_HEADING))
    _drop_page_header(soup)

    title = page_title or file_name
    sections = _anchored_headings(soup)
    root = soup.body or soup

    if not sections:
        text = _text_of_nodes(root.descendants)
        return [_article(book, file_name, None, title, text)] if text else []

    articles = []
    lead = _text_of_nodes(root.descendants, sections[0][0])
    if len(lead) > LEAD_MIN_LENGTH:
        articles.append(_article(book, file_name, None, title, lead))

    for position, (heading, anchor) in enumerate(sections):
        following = sections[position + 1][0] if position + 1 < len(sections) else None
        articles.append(_article(
            book, file_name, anchor, _text_of(heading),
            _text_of_nodes(_after_subtree(heading), following),
        ))
    return articles


def _drop_page_footer(soup: BeautifulSoup) -> None:
    """Подвал страницы отделён горизонтальной чертой и в статью не входит."""
    separator = soup.find(FOOTER_SEPARATOR)
    if separator is None:
        return
    for node in list(separator.next_elements):
        node.extract()
    separator.extract()


def _drop_page_header(soup: BeautifulSoup) -> None:
    """Шапка повторяет заголовок страницы, а он печатается отдельной строкой.

    Шапку книга помечает классом сама, и сверять её текст с <h1> нельзя: на
    двух страницах она написана другими словами — «Для каждого» под
    заголовком «Для Каждого (For Each)», — но остаётся шапкой.
    """
    for node in soup.find_all(PAGE_TITLE_HEADING):
        node.decompose()
    for node in soup.find_all(class_=PAGE_HEADER_CLASS):
        node.decompose()


def _after_subtree(node: Tag) -> Iterator:
    """Документ после поддерева узла: заголовок в текст своего раздела не входит."""
    inside = {id(child) for child in node.descendants}
    return (following for following in node.next_elements if id(following) not in inside)


def _has_ancestor(node, names: frozenset) -> bool:
    return any(parent.name in names for parent in node.parents)


def _is_code(text: NavigableString) -> bool:
    """Код в книге размечен моноширинным шрифтом: точка в нём — часть имени."""
    if _has_ancestor(text, MONOSPACE_TAGS):
        return True
    return any(
        parent.name == "font" and MONOSPACE_FONT in (parent.get("face") or "")
        for parent in text.parents
    )


def _text_fragment(text: NavigableString) -> str:
    """Перевод строки в разметке — обычный пробел; значим он только в <pre>."""
    if _has_ancestor(text, PREFORMATTED_TAGS):
        return str(text)
    flat = str(text).replace("\n", " ")
    return flat if _is_code(text) else restore_space_after_period(flat)


def _text_of_nodes(nodes: Iterable, stop: Optional[Tag] = None) -> str:
    """Текст узлов до stop; абзацы, строки таблиц и <br> дают перевод строки.

    Куски склеиваются без разделителя: собственные пробелы у разметки уже есть,
    а добавленный разбивает «<Описание запроса>» на «< Описание запроса >».
    Пробел после точки восстанавливается только в прозе — в коде точка
    разделяет части составного имени, и «Документ.РасхНакл» ею не кончается.
    """
    collected = []
    for node in nodes:
        if node is stop:
            break
        if isinstance(node, PreformattedString):
            continue
        if isinstance(node, NavigableString):
            collected.append(_text_fragment(node))
        elif node.name in LINE_BREAK_TAGS:
            collected.append(" " if _has_ancestor(node, CELL_TAGS) else "\n")
        elif node.name in CELL_TAGS:
            collected.append(" ")
    return normalize_lines("".join(collected))


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

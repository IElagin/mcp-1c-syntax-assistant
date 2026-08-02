"""Диалект справки: таблица строк вместо захардкоженных литералов."""

from pathlib import Path
import re

import pytest

from src.parsers.dialects import RU_DIALECT, EN_DIALECT, Chapter, dialect_for


pytestmark = pytest.mark.parser


def test_chapter_recognized_by_exact_heading():
    assert RU_DIALECT.chapter_of("Доступность:") is Chapter.AVAILABILITY
    assert RU_DIALECT.chapter_of("Примечание:") is Chapter.NOTE
    assert RU_DIALECT.chapter_of("Синтаксис:") is Chapter.SYNTAX


def test_usage_and_version_headings_are_different_chapters():
    """«Использование:» — доступ к свойству, «Использование в версии:» — версия.

    Прежний код различал их сравнением на точное равенство, и потеря этого
    различия дала бы свойству доступ вида «доступен, начиная с версии 8.0».
    """
    assert RU_DIALECT.chapter_of("Использование:") is Chapter.USAGE
    assert RU_DIALECT.chapter_of("Использование в версии:") is Chapter.VERSION


def test_syntax_variant_heading_carries_its_name():
    heading = "Вариант синтаксиса: По индексу"
    assert RU_DIALECT.chapter_of(heading) is Chapter.SYNTAX_VARIANT
    assert RU_DIALECT.variant_name(heading) == "По индексу"


def test_syntax_variant_does_not_swallow_plain_syntax():
    """«Синтаксис:» не должен опознаваться как вариант, и наоборот."""
    assert RU_DIALECT.chapter_of("Синтаксис:") is not Chapter.SYNTAX_VARIANT


def test_unknown_heading_gives_none():
    assert RU_DIALECT.chapter_of("Методическая информация") is None


def test_parameter_flag_maps_to_requiredness():
    assert RU_DIALECT.required_from_flag("обязательный") is True
    assert RU_DIALECT.required_from_flag("необязательный") is False
    assert RU_DIALECT.required_from_flag("") is None


def test_version_markers():
    assert RU_DIALECT.is_version_available("Доступен, начиная с версии 8.0.")
    assert RU_DIALECT.is_version_changed("Описание изменено в версии 8.3.20.")


def test_dialect_for_rejects_unknown_language():
    with pytest.raises(ValueError):
        dialect_for("de")


def test_english_chapters_recognized():
    assert EN_DIALECT.chapter_of("Availability:") is Chapter.AVAILABILITY
    assert EN_DIALECT.chapter_of("Returned value:") is Chapter.RETURN_VALUE
    assert EN_DIALECT.chapter_of("Available since:") is Chapter.VERSION
    assert EN_DIALECT.chapter_of("Usage:") is Chapter.USAGE


def test_english_syntax_variant_carries_its_name():
    heading = "Syntax variant: By index"
    assert EN_DIALECT.chapter_of(heading) is Chapter.SYNTAX_VARIANT
    assert EN_DIALECT.variant_name(heading) == "By index"


def test_english_parameter_flags():
    assert EN_DIALECT.required_from_flag("required") is True
    assert EN_DIALECT.required_from_flag("optional") is False


def test_english_version_markers():
    assert EN_DIALECT.is_version_available("Available since version 8.0.")
    assert EN_DIALECT.is_version_available(
        "It is not recommended to use since version 8.3.10."
    )
    assert EN_DIALECT.is_version_changed("Description changed in version 8.3.20.")


def test_values_chapter_recognized_in_both_dialects():
    """«Значения»/«Values» — реальный раздел, а не разделитель или опечатка.

    Найден сверкой словаря с книгой на страницах-каталогах встроенных
    именованных наборов (StyleColors, StyleFonts, PictureLib, Chars и т.п.):
    623 вхождения что в русской, что в английской книге, и ни разу — с
    двоеточием. Без этой пары раздел не терялся бы (в карточку он и так не
    попадает — html_parser его не разбирает), но тест полноты словаря падал бы
    на каждой такой странице.
    """
    assert RU_DIALECT.chapter_of("Значения") is Chapter.VALUES
    assert EN_DIALECT.chapter_of("Values") is Chapter.VALUES


def test_dialects_describe_the_same_chapters():
    """Диалекты обязаны покрывать один и тот же набор разделов.

    Раздел, описанный только в русском диалекте, потеряется на английской
    странице молча: карточка недосчитается поля, и ни один тест на русскую
    книгу этого не заметит.
    """
    assert set(RU_DIALECT.chapters) == set(EN_DIALECT.chapters)


ENGLISH_BOOK = Path("/app/data/hbk-en/shcntx_root.hbk")

# Одиночные буквы — алфавитные разделители на страницах каталогов, а не главы.
# Парсер их не разбирает ни на одном языке.
_ALPHABET_HEADING = re.compile(r"^\W*\w\W*$")


@pytest.mark.hbk_en
@pytest.mark.slow
@pytest.mark.skipif(not ENGLISH_BOOK.exists(), reason="английской книги нет")
def test_every_chapter_of_the_english_book_is_known_to_the_dialect():
    """Нераспознанная глава теряется молча — это и ловит тест.

    Без него добавленный в новой версии платформы раздел просто не попадёт в
    карточку, и ни один тест на фикстурах об этом не узнает: фикстуры сняты со
    страниц, которые мы уже умеем разбирать.
    """
    from src.parsers.hbk_parser import HBKParser

    parser = HBKParser(max_total_files=400)
    entries = parser._extract_archive(ENGLISH_BOOK)
    unknown = set()

    for entry in entries[:400]:
        if not entry.path.endswith(".html"):
            continue
        content = parser.extract_file_content(entry.path)
        if not content:
            continue
        html = content.decode("utf-8", errors="replace")
        for heading in re.findall(r'<p class="V8SH_chapter">(.*?)</p>', html):
            if _ALPHABET_HEADING.match(heading.strip()):
                continue
            if EN_DIALECT.chapter_of(heading) is None:
                unknown.add(heading.strip())

    assert not unknown, f"диалект не знает разделов: {sorted(unknown)}"

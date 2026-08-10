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


ENGLISH_BOOK = (
    Path(__file__).parent.parent / "data" / "hbk-en" / "shcntx_root.hbk"
)

# Одиночные буквы — алфавитные разделители на страницах каталогов, а не главы.
# Парсер их не разбирает ни на одном языке.
_ALPHABET_HEADING = re.compile(r"^\W*\w\W*$")

# Раздел «Values», из-за которого переписан этот тест, живёт именно здесь —
# записью №44280 из 48 682, за пределами любого среза вроде entries[:400].
# Если выборка снова сузится до первых записей архива, это же имя выпадет из
# unknown-проверки, и assert ниже по коду упадёт раньше, чем тест научится
# молчать о своей слепоте.
_KNOWN_VALUES_PAGE = "objects/catalog274/StyleColors.html"


@pytest.mark.hbk_en
@pytest.mark.slow
@pytest.mark.skipif(not ENGLISH_BOOK.exists(), reason="английской книги нет")
def test_every_chapter_of_the_english_book_is_known_to_the_dialect():
    """Нераспознанная глава теряется молча — это и ловит тест.

    Первая версия брала entries[:400] — первые 400 записей архива целиком
    лежат в одной ветке objects/ (formparams/events одного каталога), а раздел
    «Values» нашёлся записью №44280: тест был бы зелёным и не проверял бы ровно
    тот класс дефектов, ради которого написан. Теперь просматриваются все
    страницы objects/ — то же подмножество, что реально становится карточками
    (HBKParser._analyze_structure берёт в работу только пути с 'objects/',
    tables/ не разбирает вовсе — то же условие продублировано здесь, а не
    выведено из HBKParser, чтобы тест не зависел от приватностей парсера).
    """
    from src.parsers.v8_container import HelpBookArchive

    with HelpBookArchive(ENGLISH_BOOK) as archive:
        object_pages = [
            name for name in archive.names()
            if name.endswith(".html") and name.startswith("objects/")
        ]

        assert _KNOWN_VALUES_PAGE in object_pages, (
            f"{_KNOWN_VALUES_PAGE} выпала из выборки — тест снова ничего не проверяет"
        )

        unknown = set()
        for name in object_pages:
            html = archive.read(name).decode("utf-8", errors="replace")
            for heading in re.findall(r'<p class="V8SH_chapter">(.*?)</p>', html):
                if _ALPHABET_HEADING.match(heading.strip()):
                    continue
                if EN_DIALECT.chapter_of(heading) is None:
                    unknown.add(heading.strip())

    assert not unknown, f"диалект не знает разделов: {sorted(unknown)}"


@pytest.mark.unit
def test_every_dialect_names_the_global_context():
    """Имя глобального контекста — часть диалекта, а не константа парсера.

    Путь страницы английский в обеих книгах, поэтому владельца глобальных
    функций может назвать только язык книги. Пустое значение вернуло бы разбор
    к сегменту пути — тому самому «Global context» в русском индексе.
    """
    assert RU_DIALECT.global_context_name == "Глобальный контекст"
    assert EN_DIALECT.global_context_name == "Global context"
    for dialect in (RU_DIALECT, EN_DIALECT):
        assert dialect.global_context_name.strip()

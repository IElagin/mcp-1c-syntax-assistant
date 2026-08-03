"""Сырой плейсхолдер вида <Value1> не должен открывать настоящий тег.

Асимметрия между книгами была не в языке справки, а в форме плейсхолдера: имя
HTML-тега по HTML5 обязано начинаться с ASCII-буквы, поэтому «<Значение1>»
токенизатор оставляет текстом, а «<Value1>» на том же самом месте разметки
открывает тег, который не закрывается и поглощает остаток страницы. В индекс
попадала строка вызова длиной со страницу — то самое поле, ради которого агент
и зовёт инструмент.

Страницы здесь синтетические, а не выдержки из книги: воспроизводится структура
разметки (классы V8SH_*), которой достаточно для дефекта, а текст свой — книга
справки проприетарна, и лишний её фрагмент в публичном репозитории не нужен.
Сама правка при этом проверена на настоящих книгах: 342 файла английской книги
меняют разбор, 38 склеенных страниц становятся нулём, русская книга не меняется
ни в одном файле из 23 848.
"""

import pytest

from src.parsers import html_parser as hp
from src.parsers.dialects import EN_DIALECT, RU_DIALECT
from src.parsers.html_parser import HTMLParser, escape_pseudo_tags


pytestmark = [pytest.mark.unit, pytest.mark.parser]

ARCHIVE_PATH = "objects/Global context/methods/catalog1762/DoSomething1.html"

EN_PAGE = """<html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8"></head><body>
<h1 class="V8SH_pagetitle">Global context.DoSomething</h1>
<p class="V8SH_title">Global context</p>
<p class="V8SH_heading">DoSomething</p>
<p class="V8SH_chapter">Syntax:</p>DoSomething(&lt;<Value1>,...,<ValueN>&gt;)
<p class="V8SH_chapter">Parameters:</p><div class="V8SH_rubric"><p>&lt;<Value1>,...,<ValueN>&gt; (optional)</div>Type: Arbitrary. <br>Any set of values.
<p class="V8SH_chapter">Returned value:</p>Type: Boolean. <br>Whether it worked.
<p class="V8SH_chapter">Description:</p><p>Does something to every value passed in.</p>
<p class="V8SH_chapter">Availability: </p><p>Thin client, server.</p>
<p class="V8SH_chapter">Available since:</p><p class="V8SH_versionInfo">Available since version 8.3.9.</p>
</body></html>""".encode("utf-8")

RU_PAGE = """<html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8"></head><body>
<h1 class="V8SH_pagetitle">Глобальный контекст.СделатьЧтоТо (Global context.DoSomething)</h1>
<p class="V8SH_title">Глобальный контекст (Global context)</p>
<p class="V8SH_heading">СделатьЧтоТо (DoSomething)</p>
<p class="V8SH_chapter">Синтаксис:</p>СделатьЧтоТо(&lt;<Значение1>,...,<ЗначениеN>&gt;)
<p class="V8SH_chapter">Параметры:</p><div class="V8SH_rubric"><p>&lt;<Значение1>,...,<ЗначениеN>&gt; (необязательный)</div>Тип: Произвольный. <br>Любой набор значений.
<p class="V8SH_chapter">Возвращаемое значение:</p>Тип: Булево. <br>Получилось ли.
<p class="V8SH_chapter">Описание:</p><p>Делает что-то с каждым переданным значением.</p>
<p class="V8SH_chapter">Доступность:</p><p>Тонкий клиент, сервер.</p>
<p class="V8SH_chapter">Доступен, начиная с версии:</p><p class="V8SH_versionInfo">Доступен, начиная с версии 8.3.9.</p>
</body></html>""".encode("utf-8")

# Заголовки соседних разделов: их появление в строке вызова и означает, что
# страница склеилась в одно поле.
CHAPTER_MARKERS = ("Parameters:", "Description:", "Returned value:",
                   "Availability:", "Available since:")


def test_real_markup_is_left_alone():
    """Настоящая разметка книги обязана пройти нетронутой.

    Регистр имён в книге смешанный («<TABLE>» рядом с «<p>»), поэтому сверка
    идёт по имени без учёта регистра.
    """
    markup = (
        '<html><head><meta http-equiv="Content-Type"></head><body>'
        '<h1 class="V8SH_pagetitle">X</h1><TABLE width="100%"><TBODY><TR><TD>'
        '<font face="Courier New">code<BR></font></TD></TR></TBODY></TABLE>'
        '<HR><a href="http://example.invalid/?a=1&amp;b=2">link</a></body></html>'
    )

    assert escape_pseudo_tags(markup) == markup


@pytest.mark.parametrize("placeholder", ["<Value1>", "<size0>", "<sizeN-1>",
                                         "<AddInName>", "<MethodName>"])
def test_placeholders_are_escaped(placeholder):
    escaped = placeholder.replace("<", "&lt;").replace(">", "&gt;")

    assert escape_pseudo_tags(f"Call({placeholder})") == f"Call({escaped})"


def test_cyrillic_placeholder_needs_no_escaping():
    """Кириллическое имя тегом не считается — трогать его нечем и незачем."""
    assert escape_pseudo_tags("Вызов(<Значение1>)") == "Вызов(<Значение1>)"


def test_english_page_keeps_its_call_string_short():
    """Строка вызова — это сигнатура, а не вся страница.

    До правки в call_primary у ProceedWithCall лежало 1195 знаков: параметры,
    описание, доступность, примеры и подвал подряд. Агент, скопировавший такую
    строку, получает мусор вместо кода.
    """
    doc = HTMLParser(dialect=EN_DIALECT).parse_html_content(EN_PAGE, ARCHIVE_PATH)

    assert doc is not None
    call = doc.call_primary
    for marker in CHAPTER_MARKERS:
        assert marker not in call, call
    assert len(call) < 60, call
    assert call.startswith("DoSomething(")


def test_english_page_keeps_the_chapters_that_the_tag_used_to_swallow():
    """Поглощённый тегом текст пропадал не только из синтаксиса.

    Из 38 склеенных страниц у пяти терялось ещё и описание: раздел уезжал
    внутрь незакрытого тега вместе со всем остальным.
    """
    doc = HTMLParser(dialect=EN_DIALECT).parse_html_content(EN_PAGE, ARCHIVE_PATH)

    assert doc.description == "Does something to every value passed in."
    assert doc.availability == ["thin client", "server"]
    assert doc.version_from == "8.3.9"
    assert doc.variants[0].return_type == "Boolean"


def test_both_books_read_the_same_page_the_same_way():
    """Форма плейсхолдера больше не решает, что попадёт в индекс.

    Это и есть корень дефекта: та же самая разметка на русской странице
    разбиралась правильно, а на английской — нет, потому что «<Значение1>» не
    похоже на имя тега, а «<Value1>» похоже.
    """
    en = HTMLParser(dialect=EN_DIALECT).parse_html_content(EN_PAGE, ARCHIVE_PATH)
    ru = HTMLParser(dialect=RU_DIALECT).parse_html_content(RU_PAGE, ARCHIVE_PATH)

    assert len(en.variants) == len(ru.variants) == 1
    assert en.variants[0].return_type == "Boolean"
    assert ru.variants[0].return_type == "Булево"
    assert en.availability == ["thin client", "server"]
    assert ru.availability == ["тонкий клиент", "сервер"]
    # Число знаков в синтаксисе отличается только длиной самих слов — ни одна
    # из страниц не тащит в него соседние разделы.
    assert len(en.variants[0].syntax) < 60
    assert len(ru.variants[0].syntax) < 60


def test_without_the_fix_the_english_page_swallows_itself():
    """Фиксирует сам дефект, а не только его отсутствие.

    Без экранирования на входе английская страница склеивается в одно поле —
    тест перестанет проходить, если книга или разбор изменятся так, что этот
    класс дефектов исчезнет сам собой, и тогда правку можно будет пересмотреть
    осознанно, а не унаследовать молча.
    """
    original = hp.escape_pseudo_tags
    hp.escape_pseudo_tags = lambda text: text
    try:
        doc = HTMLParser(dialect=EN_DIALECT).parse_html_content(EN_PAGE, ARCHIVE_PATH)
    finally:
        hp.escape_pseudo_tags = original

    assert any(marker in doc.call_primary for marker in CHAPTER_MARKERS), \
        doc.call_primary

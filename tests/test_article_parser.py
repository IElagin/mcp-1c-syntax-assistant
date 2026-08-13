"""Разбор статей книг справки."""

import pytest

from src.models.doc_models import DocumentType
from src.parsers.article_parser import (
    ARTICLE_KIND, decode_article, is_article_file, parse_article_file,
)

WHOLE_FILE = """<html><head><meta charset="utf-8"></head><body>
<h1 class="V8SH_pagetitle">Для&nbsp;(For)</h1>
<div class="V8SH_title">Для&nbsp;(For)</div>
<p class="Usual"><b>Синтаксис:<br></b>Для &lt;Имя переменной&gt; = &lt;Выражение 1&gt; По &lt;Выражение 2&gt; Цикл<br>// Операторы<br>[Прервать;]<br>КонецЦикла;</p>
<p class="Usual"><b>Описание:<br></b>Оператор цикла Для предназначен для циклического повторения операторов.</p>
<hr>
<p>&nbsp;<a href="http://www.1centerprise.com/devlinks">Методическая информация</a></p>
</body></html>"""

TABLE_LAYOUT = """<HTML><BODY>
<H1 class="">Секция ОБЪЕДИНИТЬ</H1>
<P>Объединение запросов описывается по следующему правилу:</P>
<TABLE class=SimplyTable><TBODY>
<TR><TD><P class=Usual>&lt;Объединение запросов&gt;</P></TD></TR>
<TR><TD><P class=Usual>ОБЪЕДИНИТЬ [ВСЕ]</P></TD><TD><P class=Usual>&lt;Описание запроса&gt;</P></TD></TR>
</TBODY></TABLE>
</BODY></HTML>"""

CODE_EXAMPLE = """<HTML><BODY>
<H1 class="">Расчет общих итогов</H1>
<P>Для расчета итогов по всей таблице указывается ключевое слово.В этом случае считаются все записи.</P>
<H4 class="">Пример:</H4>
<BLOCKQUOTE><P><FONT face="Courier New">ВЫБРАТЬ Док.Товар, Док.Ссылка.Номер<BR>ИЗ Документ.РасхНакл.Состав КАК Док</FONT></P></BLOCKQUOTE>
</BODY></HTML>"""

CODE_EXAMPLE_IN_CELL = """<HTML><BODY>
<H1 class="">Расчет общих итогов</H1>
<TABLE width="100%" bgColor="#f7f7f7"><TBODY><TR><TD><FONT face="Courier New">ВЫБРАТЬ<BR>&nbsp;&nbsp;&nbsp;&nbsp;Состав.Номенклатура<BR>ИЗ<BR>&nbsp;&nbsp;&nbsp;&nbsp;Документ.РасхНакл.Состав КАК Состав</FONT></TD></TR></TBODY></TABLE>
</BODY></HTML>"""

ANCHORED = """<html><body>
<h1>Работа с выражениями</h1>
<blockquote><a href="#calculate">Вычислить</a> <br><a href="#EvalExpression">ВычислитьВыражение</a></blockquote>
<h2 valign="bottom"><a name="calculate"></a>Вычислить (Eval)</h2>
<p>Функция Вычислить предназначена для вычисления выражения в контексте некоторой группировки.</p>
<h2 valign="bottom"><a name="EvalExpression"></a>ВычислитьВыражение (EvalExpression)</h2>
<p>Функция предназначена для вычисления выражения в контексте некоторой группировки.</p>
</body></html>"""

ANCHOR_WRAPS_TITLE = """<HTML><BODY>
<H1 class="">Виды программных модулей</H1>
<P>В системе существует несколько видов программных модулей.</P>
<H3><A name=ManagedApplicationModule>Модуль приложения</A></H3>
<P>Модуль приложения располагается в корневом разделе конфигурации.</P>
</BODY></HTML>"""

ANCHOR_IN_PROSE = """<HTML><BODY>
<H1 class="">Логические выражения</H1>
<P>Текст с точкой перехода <A name=Common></A> посреди абзаца, а не заголовком.</P>
</BODY></HTML>"""

ANCHOR_NAME_EMPTY = """<HTML><BODY>
<H1 class="">Работа со строками</H1>
<P>Общие сведения о работе со строковыми значениями и их преобразовании в системе.</P>
<H3><A name="">Технический подраздел без якоря</A></H3>
<P>Текст технического подраздела, который не должен стать отдельной статьёй.</P>
</BODY></HTML>"""

LEAD_IS_ONLY_LINKS = """<html><body>
<h1>Функции работы со строками</h1>
<blockquote><a href="#Left">Лев</a><br><a href="#Right">Прав</a></blockquote>
<h2><a name="Left"></a>Лев (Left)</h2>
<p>Функция выделяет левую часть строки указанной длины и возвращает её значение.</p>
</body></html>"""


def test_whole_file_without_heading_anchors_is_one_article():
    articles = parse_article_file("shlang", "struct_For", WHOLE_FILE)
    assert len(articles) == 1
    assert articles[0].name == "Для (For)"
    assert articles[0].type == DocumentType.ARTICLE
    assert articles[0].book == "shlang"
    assert articles[0].element_kind == ARTICLE_KIND
    assert articles[0].source_file == "shlang/struct_For"
    assert articles[0].id == "shlang/struct_For"
    assert articles[0].full_path == "shlang/struct_For"
    assert "циклического повторения" in articles[0].description


def test_heading_anchors_split_the_file_into_named_articles():
    articles = parse_article_file("dcsui", "SKD_Functions_Expressions", ANCHORED)
    assert [a.name for a in articles] == [
        "Вычислить (Eval)",
        "ВычислитьВыражение (EvalExpression)",
    ]
    assert articles[0].source_file == "dcsui/SKD_Functions_Expressions#calculate"
    assert articles[0].full_path == "dcsui/SKD_Functions_Expressions#calculate"
    assert articles[1].id == "dcsui/SKD_Functions_Expressions#EvalExpression"
    assert articles[1].full_path == "dcsui/SKD_Functions_Expressions#EvalExpression"


def test_anchor_wrapping_the_heading_text_also_splits():
    articles = parse_article_file("shclang", "source_wasistdas_kind.html", ANCHOR_WRAPS_TITLE)
    assert [a.name for a in articles] == [
        "Виды программных модулей",
        "Модуль приложения",
    ]
    assert articles[0].source_file == "shclang/source_wasistdas_kind.html"
    assert articles[1].source_file == "shclang/source_wasistdas_kind.html#ManagedApplicationModule"


def test_lead_article_text_does_not_repeat_its_own_heading():
    articles = parse_article_file("shclang", "source_wasistdas_kind.html", ANCHOR_WRAPS_TITLE)
    lead = articles[0]
    assert lead.name == "Виды программных модулей"
    assert lead.description == "В системе существует несколько видов программных модулей."
    assert not lead.description.startswith(lead.name)


def test_anchor_outside_a_heading_does_not_split_the_file():
    articles = parse_article_file("shlang", "expressions_logical.html", ANCHOR_IN_PROSE)
    assert len(articles) == 1
    assert articles[0].name == "Логические выражения"


def test_heading_with_empty_anchor_name_does_not_split_the_file():
    articles = parse_article_file("shlang", "string_functions.html", ANCHOR_NAME_EMPTY)
    assert len(articles) == 1
    assert articles[0].name == "Работа со строками"


def test_lead_that_is_only_a_link_list_produces_no_article():
    articles = parse_article_file("shquery", "builtin_functions.html", LEAD_IS_ONLY_LINKS)
    assert [a.name for a in articles] == ["Лев (Left)"]


def test_article_text_does_not_repeat_its_own_heading():
    articles = parse_article_file("dcsui", "SKD_Functions_Expressions", ANCHORED)
    assert articles[0].name == "Вычислить (Eval)"
    assert articles[0].description == (
        "Функция Вычислить предназначена для вычисления выражения в контексте "
        "некоторой группировки."
    )


def test_article_text_does_not_repeat_the_page_title():
    article = parse_article_file("shlang", "struct_For", WHOLE_FILE)[0]
    assert article.name == "Для (For)"
    assert "Для (For)" not in article.description
    assert article.description.startswith("Синтаксис:")


def test_line_breaks_of_the_syntax_block_survive():
    article = parse_article_file("shlang", "struct_For", WHOLE_FILE)[0]
    assert article.description.splitlines()[:5] == [
        "Синтаксис:",
        "Для <Имя переменной> = <Выражение 1> По <Выражение 2> Цикл",
        "// Операторы",
        "[Прервать;]",
        "КонецЦикла;",
    ]


def test_page_footer_after_the_horizontal_rule_is_dropped():
    article = parse_article_file("shlang", "struct_For", WHOLE_FILE)[0]
    assert "Методическая информация" not in article.description


def test_each_table_row_is_its_own_line():
    """Строку таблицы разбивает строка, а не абзацы внутри её ячеек."""
    article = parse_article_file("shquery", "UNIONSection", TABLE_LAYOUT)[0]
    assert "<Объединение запросов>" in article.description.splitlines()
    assert "ОБЪЕДИНИТЬ [ВСЕ] <Описание запроса>" in article.description.splitlines()


def test_a_line_break_inside_a_table_cell_still_breaks_the_line():
    """Пример кода книга кладёт в ячейку таблицы, и <BR> в нём — перевод строки.

    Прежнее правило считало ячейку поводом склеить строку: пример статьи
    shlang/root_New печатал два оператора в одной строке.
    """
    article = parse_article_file("shquery", "overall_totals.html", CODE_EXAMPLE_IN_CELL)[0]

    assert article.description.splitlines() == [
        "ВЫБРАТЬ",
        "Состав.Номенклатура",
        "ИЗ",
        "Документ.РасхНакл.Состав КАК Состав",
    ]


def test_dotted_names_inside_a_code_example_keep_their_dots():
    """«Документ. РасхНакл. Состав» — синтаксическая ошибка, а не запрос."""
    article = parse_article_file("shquery", "overall_totals.html", CODE_EXAMPLE)[0]
    assert "ВЫБРАТЬ Док.Товар, Док.Ссылка.Номер" in article.description
    assert "ИЗ Документ.РасхНакл.Состав КАК Док" in article.description


def test_the_missing_space_is_still_restored_in_prose():
    article = parse_article_file("shquery", "overall_totals.html", CODE_EXAMPLE)[0]
    assert "ключевое слово. В этом случае" in article.description


def test_article_leaves_card_only_fields_empty():
    """У оператора нет ни владельца, ни варианта вызова, ни типа возврата."""
    article = parse_article_file("shlang", "struct_For", WHOLE_FILE)[0]
    assert article.variants == []
    assert article.object is None
    assert article.availability == []
    assert article.call_primary == ""


@pytest.mark.parametrize("book,name,expected", [
    ("shlang", "struct_For", True),
    ("shlang", "struct_For.st", False),
    ("shclang", "Analiz1.gif", False),
    ("shclang", "__categories__", False),
    ("shclang", "_CONTENTS_NODE_fileConf", False),
    ("dcsui", "SKD_Functions", True),
    ("dcsui", "form_RoleDlg", False),
    ("shquery", "form_something", True),
])
def test_only_article_files_are_taken_from_a_book(book, name, expected):
    assert is_article_file(book, name) is expected


def test_article_text_survives_the_utf8_bom():
    assert decode_article("\ufeff<h1>Для</h1>".encode("utf-8")) == "\ufeff<h1>Для</h1>".lstrip("\ufeff")


INLINE_MARKUP = """<HTML><BODY>
<H1 class="">Секция ОБЪЕДИНИТЬ</H1>
<P>Правило: <STRONG>ОБЪЕДИНИТЬ [ВСЕ]</STRONG> &lt;<A href="v8help://q/SELECT">Описание запроса</A>&gt; — далее ключевое слово <STRONG>ВСЕ</STRONG>.</P>
</BODY></HTML>"""


def test_inline_markup_does_not_add_spaces_inside_a_placeholder():
    """«< Описание запроса >» — не то, что агент может вставить в запрос."""
    article = parse_article_file("shquery", "UNIONSection", INLINE_MARKUP)[0]
    assert "<Описание запроса>" in article.description
    assert article.description.endswith("ключевое слово ВСЕ.")


COMMENTED_OUT_MARKUP = """<HTML><BODY>
<H1 class="">Сохранение настроек</H1>
<P>Настройки печати для веб-клиента по умолчанию.</P>
<!-- <tr><td class="WideColumn"><p class="Usual">Черновик строки</p></td></tr> -->
</BODY></HTML>"""


def test_commented_out_markup_does_not_leak_into_the_article():
    """Комментарий — не текст страницы: его разметка попадала в ответ как есть."""
    article = parse_article_file("shlang", "SavingSettings", COMMENTED_OUT_MARKUP)[0]
    assert "WideColumn" not in article.description
    assert "Черновик строки" not in article.description
    assert article.description == "Настройки печати для веб-клиента по умолчанию."


HEADER_WORDED_DIFFERENTLY = """<html><body>
<h1 class="V8SH_pagetitle">Для&nbsp;Каждого&nbsp;(For Each)</h1>
<div class="V8SH_title">Для каждого</div>
<p class="Usual"><b>Синтаксис:<br></b>Для Каждого &lt;Имя&gt; Из &lt;Коллекция&gt; Цикл</p>
</body></html>"""


def test_page_header_is_dropped_even_when_worded_differently():
    """Шапку помечает класс книги, а не совпадение её текста с заголовком."""
    article = parse_article_file("shlang", "struct_ForEach", HEADER_WORDED_DIFFERENTLY)[0]
    assert article.name == "Для Каждого (For Each)"
    assert article.description.startswith("Синтаксис:")

"""Разбор статей книг справки."""

import pytest

from src.models.doc_models import DocumentType
from src.parsers.article_parser import (
    ARTICLE_KIND, decode_article, is_article_file, parse_article_file,
)

WHOLE_FILE = """<html><head><meta charset="utf-8"></head><body>
<h1 class="V8SH_pagetitle">Для&nbsp;(For)</h1>
<div class="V8SH_title">Для&nbsp;(For)</div>
<p class="Usual"><b>Синтаксис:<br></b>Для &lt;Имя переменной&gt; = &lt;Выражение 1&gt; По &lt;Выражение 2&gt; Цикл</p>
<p class="Usual"><b>Описание:<br></b>Оператор цикла Для предназначен для циклического повторения операторов.</p>
</body></html>"""

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
    assert "циклического повторения" in articles[0].description


def test_heading_anchors_split_the_file_into_named_articles():
    articles = parse_article_file("dcsui", "SKD_Functions_Expressions", ANCHORED)
    assert [a.name for a in articles] == [
        "Вычислить (Eval)",
        "ВычислитьВыражение (EvalExpression)",
    ]
    assert articles[0].source_file == "dcsui/SKD_Functions_Expressions#calculate"
    assert articles[1].id == "dcsui/SKD_Functions_Expressions#EvalExpression"


def test_anchor_wrapping_the_heading_text_also_splits():
    articles = parse_article_file("shclang", "source_wasistdas_kind.html", ANCHOR_WRAPS_TITLE)
    assert [a.name for a in articles] == [
        "Виды программных модулей",
        "Модуль приложения",
    ]
    assert articles[0].source_file == "shclang/source_wasistdas_kind.html"
    assert articles[1].source_file == "shclang/source_wasistdas_kind.html#ManagedApplicationModule"


def test_anchor_outside_a_heading_does_not_split_the_file():
    articles = parse_article_file("shlang", "expressions_logical.html", ANCHOR_IN_PROSE)
    assert len(articles) == 1
    assert articles[0].name == "Логические выражения"


def test_lead_that_is_only_a_link_list_produces_no_article():
    articles = parse_article_file("shquery", "builtin_functions.html", LEAD_IS_ONLY_LINKS)
    assert [a.name for a in articles] == ["Лев (Left)"]


def test_article_text_carries_its_own_heading():
    articles = parse_article_file("dcsui", "SKD_Functions_Expressions", ANCHORED)
    assert articles[0].description.startswith("Вычислить (Eval)")


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

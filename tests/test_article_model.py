"""Статья как документ индекса."""

from src.core.elasticsearch import ElasticsearchClient
from src.handlers.ui_strings import EN_STRINGS, RU_STRINGS
from src.models.doc_models import Documentation, DocumentType
from src.parsers.indexer import ElasticsearchIndexer


def test_article_type_has_its_own_value():
    assert DocumentType.ARTICLE.value == "article"


def test_article_document_carries_its_book():
    doc = Documentation(
        id="shquery/MONTH", type=DocumentType.ARTICLE, name="Функция МЕСЯЦ", book="shquery"
    )
    assert doc.book == "shquery"


def test_indexed_article_keeps_book_and_splits_its_name():
    doc = Documentation(
        id="dcsui/SKD_Functions_Expressions#calculate",
        type=DocumentType.ARTICLE,
        name="Вычислить (Eval)",
        book="dcsui",
        element_kind="статья",
    )
    prepared = ElasticsearchIndexer(ElasticsearchClient())._prepare_document(doc)
    assert prepared["book"] == "dcsui"
    assert prepared["type"] == "article"
    assert prepared["name_ru"] == "Вычислить"
    assert prepared["name_en"] == "Eval"


def test_article_kind_is_translated_for_the_english_answer():
    assert RU_STRINGS.element_kind_names["статья"] == "статья"
    assert EN_STRINGS.element_kind_names["статья"] == "article"

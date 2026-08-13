"""Достройка английских имён из английского индекса по общему пути страницы.

Плановая цифра брифа (158 страниц из 3063) устарела — индекс менялся трижды
с задачи 11. На деле кандидатов 707: 674 с пустым name_en, 304 без object_en,
271 из них пересекаются (не хватает обоих полей). Часть этой выборки (33
документа) уже имеет разобранное задачей 11 name_en и ждёт только object_en —
именно этот случай проверяет test_already_parsed_name_en_is_not_overwritten:
достройка обязана трогать только недостающее поле, а не оба разом.
"""

from unittest.mock import AsyncMock

import pytest

from src.parsers.name_backfill import _fields_to_fill, _both_separators, backfill_english_names


@pytest.fixture
async def own_index_pair(isolated_index):
    """Пара индексов под достройку имён: русский и английский, оба свои."""
    from src.core.elasticsearch import ElasticsearchClient

    ru_index, en_index = isolated_index, f"{isolated_index}_en"
    client = ElasticsearchClient()
    assert await client.connect(), "Elasticsearch недоступен"
    await client.create_index(index=ru_index)
    await client.create_index(index=en_index)
    try:
        yield client, ru_index, en_index
    finally:
        await client.delete_index(index=en_index)
        await client.disconnect()


def _page_query(source_file: str) -> dict:
    """Запрос страницы по пути в обеих записях — со слэшем и с обратным.

    Тест не вправе требовать одной записи там, где её не требует код:
    индексатор пишет source_file канонически (через «/»), но уже собранные
    индексы этим не переписываются, а собраны они бывают на разных платформах
    — 7-Zip под Windows печатает пути через «\\», p7zip под Linux через «/».
    Прежний term по одной записи падал IndexError'ом на индексе, собранном на
    хосте, — и это было не «страницы нет», а «тест смотрит не туда».
    """
    forward, backward = _both_separators(source_file)
    return {"terms": {"source_file": [forward, backward]}}


@pytest.mark.integration
@pytest.mark.elasticsearch
async def test_global_context_gets_its_english_name(own_index_pair):
    """У «Глобальный контекст» в норме нет ни name_en, ни object_en.

    Ключ склейки — внутрикнижный путь страницы: он одинаков в обеих книгах,
    но не его запись — разделитель зависит от платформы, на которой собирали
    индекс, — поэтому и код, и этот тест приводят путь к канонической форме,
    а не сравнивают строки как есть.
    """
    client, ru_index, en_index = own_index_pair
    source_file = "objects/Global context.html"

    await client.index_document(
        {"name_en": "", "object_en": None, "source_file": source_file}, index=ru_index
    )
    await client.index_document(
        {"name": "Global context", "source_file": source_file}, index=en_index
    )
    await client.refresh_index(index=ru_index)
    await client.refresh_index(index=en_index)

    updated = await backfill_english_names(client, ru_index, en_index)
    assert updated > 0

    response = await client.search(
        {"query": _page_query(source_file)},
        index=ru_index,
    )
    source = response["hits"]["hits"][0]["_source"]
    assert source["name_en"] == "Global context"


@pytest.mark.integration
@pytest.mark.elasticsearch
async def test_backfill_is_exhaustive_in_one_pass_and_idempotent_after(own_index_pair):
    """Один вызов обязан достроить всё достижимое, второй — ничего не менять."""
    client, ru_index, en_index = own_index_pair
    source_file = "objects/Global context.html"

    await client.index_document(
        {"name_en": "", "object_en": None, "source_file": source_file}, index=ru_index
    )
    await client.index_document(
        {"name": "Global context", "source_file": source_file}, index=en_index
    )
    await client.refresh_index(index=ru_index)
    await client.refresh_index(index=en_index)

    first = await backfill_english_names(client, ru_index, en_index)
    assert first > 0, "первому проходу было что достроить — он обязан это сделать"

    second = await backfill_english_names(client, ru_index, en_index)
    assert second == 0, (
        "всё достижимое достраивается за один вызов; второму проходу "
        "работы не остаётся"
    )


@pytest.mark.integration
@pytest.mark.elasticsearch
async def test_already_parsed_name_en_is_not_overwritten(own_index_pair):
    """Достройка object_en не переписывает уже заполненный name_en."""
    client, ru_index, en_index = own_index_pair
    source_file = "test/name_backfill_probe.html"

    await client.index_document(
        {
            "type": "object_property",
            "name_en": "AlreadyParsedName",
            "object_en": None,
            "source_file": source_file,
        },
        index=ru_index,
    )
    await client.index_document(
        {
            "name": "RawEnglishTitle",
            "object": "SomeObject",
            "source_file": source_file,
        },
        index=en_index,
    )
    await client.refresh_index(index=ru_index)
    await client.refresh_index(index=en_index)

    await backfill_english_names(client, ru_index, en_index)

    after = await client.search(
        {"query": {"term": {"source_file": source_file}}},
        index=ru_index,
    )
    source = after["hits"]["hits"][0]["_source"]
    assert source["name_en"] == "AlreadyParsedName"
    assert source["object_en"] == "SomeObject"


@pytest.mark.unit
def test_backfill_matches_a_page_indexed_with_windows_separators():
    """Индекс, построенный старой версией, ещё содержит objects\\…"""
    assert _both_separators("objects/Global context.html") == (
        "objects/Global context.html",
        "objects\\Global context.html",
    )


@pytest.mark.unit
def test_both_separators_normalizes_backslash_input():
    """_both_separators должна обрабатывать пути из старых индексов с обратными слэшами."""
    assert _both_separators("objects\\Global context.html") == (
        "objects/Global context.html",
        "objects\\Global context.html",
    )


@pytest.mark.unit
async def test_join_survives_books_indexed_on_different_platforms():
    """Русская книга собрана под Windows, английская — в контейнере.

    Ровно это и было на живом стенде: 23 125 русских путей записаны через
    «\\», 23 104 английских — через «/». Склейка шла term'ом по строке как
    есть, совпадений давала ноль из 23 104 возможных, и 653 документа
    оставались без английского имени при живой парной странице у каждого.
    Хуже отказа была его форма: достройка возвращала 0 и выглядела
    работающей — «кандидатов нет» и «ключ не сходится» с её стороны
    неотличимы, поэтому регрессию сюда обязан ловить тест, а не следующий
    аудит корпуса.
    """
    mock_client = AsyncMock()
    mock_client.index_exists = AsyncMock(return_value=True)
    mock_client.search = AsyncMock(
        side_effect=[
            {"hits": {"hits": [{
                "_id": "ru1",
                "_source": {"source_file": "objects\\Array\\methods\\Add.html",
                            "name_en": "", "object_en": None},
            }]}},
            {"hits": {"hits": [{
                "_source": {"source_file": "objects/Array/methods/Add.html",
                            "name": "Add", "object": "Array"},
            }]}},
        ]
    )
    mock_client._client.bulk = AsyncMock(
        return_value={"errors": False, "items": [{"update": {"_id": "ru1", "result": "updated"}}]}
    )
    mock_client.refresh_index = AsyncMock(return_value=True)

    updated = await backfill_english_names(mock_client, "help1c_docs", "help1c_docs_en")

    assert updated == 1, "пути одной и той же страницы обязаны сойтись"
    written = mock_client._client.bulk.await_args.kwargs["body"][1]["doc"]
    assert written == {"name_en": "Add", "object_en": "Array"}

    # В terms уходят обе записи пути: индекс мог быть собран любой из платформ,
    # и требовать от него одной — то же условие, из-за которого склейка молчала.
    lookup = mock_client.search.await_args_list[1].args[0]["query"]["terms"]["source_file"]
    assert "objects/Array/methods/Add.html" in lookup
    assert "objects\\Array\\methods\\Add.html" in lookup


@pytest.mark.integration
async def test_missing_english_index_is_silently_skipped():
    """Английская книга необязательна — без индекса достройка тихо не делает ничего.

    es_client — мок (не реальный ES): index_exists всегда отвечает False,
    как при первом запуске без английской книги (задача 8). Это не
    интеграционный тест — реального подключения не требуется.
    """
    mock_client = AsyncMock()
    mock_client.index_exists = AsyncMock(return_value=False)

    updated = await backfill_english_names(mock_client, "help1c_docs", "help1c_docs_en")

    assert updated == 0
    mock_client.index_exists.assert_awaited_once_with(index="help1c_docs_en")


@pytest.mark.unit
async def test_bulk_partial_failure_is_not_reported_as_success():
    """Счётчик обновлённых должен верить bulk, а не своим намерениям.

    Elasticsearch может частично отказать в bulk-запросе (конфликт версии,
    временная недоступность шарда) — часть операций проходит, часть нет.
    Если считать «обновлено» по числу подготовленных операций, а не по
    результату bulk, вызывающий получит «685 обновлено», хотя часть не
    записалась. Здесь два документа-кандидата, у второго update в bulk
    возвращает error — счётчик обязан посчитать только первый.
    """
    mock_client = AsyncMock()
    mock_client.index_exists = AsyncMock(return_value=True)
    mock_client.search = AsyncMock(
        side_effect=[
            {
                "hits": {
                    "hits": [
                        {"_id": "a1", "_source": {"source_file": "a.html", "name_en": "", "object_en": None}},
                        {"_id": "b1", "_source": {"source_file": "b.html", "name_en": "", "object_en": None}},
                    ]
                }
            },
            {
                "hits": {
                    "hits": [
                        {"_source": {"source_file": "a.html", "name": "NameA", "object": "ObjA"}},
                        {"_source": {"source_file": "b.html", "name": "NameB", "object": "ObjB"}},
                    ]
                }
            },
        ]
    )
    mock_client._client.bulk = AsyncMock(
        return_value={
            "errors": True,
            "items": [
                {"update": {"_id": "a1", "result": "updated"}},
                {"update": {"_id": "b1", "error": {"type": "version_conflict_engine_exception"}}},
            ],
        }
    )
    mock_client.refresh_index = AsyncMock(return_value=True)

    updated = await backfill_english_names(mock_client, "help1c_docs", "help1c_docs_en")

    assert updated == 1, "успешна только первая операция — счётчик обязан отразить именно это"
    mock_client.refresh_index.assert_awaited_once()


@pytest.mark.unit
class TestFieldsToFill:
    """_fields_to_fill — чистая функция: что можно дописать документу, а что нет."""

    def test_fills_empty_name_en(self):
        fields = _fields_to_fill({"name_en": "", "object_en": "X"}, {"name": "Add", "object": "Y"})
        assert fields == {"name_en": "Add"}

    def test_does_not_touch_already_parsed_name_en(self):
        fields = _fields_to_fill(
            {"name_en": "Array", "object_en": None}, {"name": "ArrayObject", "object": "Array"}
        )
        assert "name_en" not in fields
        assert fields == {"object_en": "Array"}

    def test_fills_missing_object_en(self):
        fields = _fields_to_fill({"name_en": "Add", "object_en": None}, {"name": "Add", "object": "FormDataCollection"})
        assert fields == {"object_en": "FormDataCollection"}

    def test_does_not_touch_already_filled_object_en(self):
        fields = _fields_to_fill(
            {"name_en": "", "object_en": "FormDataCollection"}, {"name": "Add", "object": "OtherObject"}
        )
        assert fields == {"name_en": "Add"}
        assert "object_en" not in fields

    def test_nothing_to_fill_when_english_side_is_blank(self):
        """Пустая заглушка английской страницы не должна превращать
        отсутствие поля в бессмысленную пустую строку — это сломало бы
        идемпотентность: пустая строка снова считалась бы «нужна достройка».
        """
        fields = _fields_to_fill({"name_en": "", "object_en": None}, {"name": "", "object": None})
        assert fields == {}

    def test_nothing_to_fill_when_both_already_present(self):
        fields = _fields_to_fill(
            {"name_en": "Add", "object_en": "FormDataCollection"}, {"name": "Add", "object": "FormDataCollection"}
        )
        assert fields == {}

    def test_page_identifier_is_not_a_name(self):
        """«catalog2627» — имя файла страницы, а не английское имя элемента.

        Английская страница objects/catalog2/catalog2627.html не имеет
        заголовка, и парсер оставляет в name то, что вывел из пути. Достройка
        записала это русскому документу «РешениеСЛУ», после чего
        get_1c_element(name="catalog2627") отдавал его карточку, а README
        считал документ обеспеченным английским именем.
        """
        fields = _fields_to_fill(
            {"name_en": "", "object_en": "X"},
            {"name": "catalog2627", "object": "X",
             "source_file": "objects/catalog2/catalog2627.html"},
        )

        assert fields == {}

    def test_page_identifier_is_not_an_object_name_either(self):
        fields = _fields_to_fill(
            {"name_en": "Add", "object_en": None},
            {"name": "Add", "object": "catalog63",
             "source_file": "objects/catalog63.html"},
        )

        assert fields == {}

    def test_real_name_that_matches_its_file_name_is_kept(self):
        """Совпадения с именем файла мало: у части страниц файл честно назван
        по элементу («Array.html» → «Array»), и отвергать такое имя не за что.
        """
        fields = _fields_to_fill(
            {"name_en": "", "object_en": "X"},
            {"name": "Array", "object": "X",
             "source_file": "objects/catalog234/Array.html"},
        )

        assert fields == {"name_en": "Array"}

    def test_article_takes_its_english_title_not_its_file_name(self):
        """«Ключевое слово ВЫБРАТЬ» получает name_en «SELECT keyword»."""
        russian = {"source_file": "shquery/KeyWordsSELECT", "name_en": "", "object_en": None}
        english = {"source_file": "shquery/KeyWordsSELECT", "name": "SELECT keyword"}
        assert _fields_to_fill(russian, english) == {"name_en": "SELECT keyword"}

    def test_anchored_article_joins_on_the_same_key_in_both_books(self):
        russian = {"source_file": "dcsui/SKD_Functions_Date#Year", "name_en": "", "object_en": None}
        english = {"source_file": "dcsui/SKD_Functions_Date#Year", "name": "Year"}
        assert _fields_to_fill(russian, english)["name_en"] == "Year"

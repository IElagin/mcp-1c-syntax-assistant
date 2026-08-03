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

from src.core.config import settings
from src.core.elasticsearch import es_client
from src.parsers.name_backfill import _fields_to_fill, backfill_english_names


@pytest.mark.integration
@pytest.mark.elasticsearch
async def test_global_context_gets_its_english_name():
    """У «Глобальный контекст» в норме нет ни name_en, ни object_en.

    source_file одинаков в обеих книгах символ в символ — это и есть ключ
    склейки, измеренный на всём корпусе (48 682 файла, обе книги).

    Индекс персистентный: на живом индексе, где предыдущий прогон уже
    достроил этот документ, «updated > 0» стало бы ложным без вины кода —
    достраивать уже нечего. Тест сам откатывает документ в состояние «имени
    не хватает» перед прогоном, поэтому проходит одинаково на свежем индексе
    и на уже достроенном, локально и в CI, при первом запуске и при сотом.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    ru_index = settings.elasticsearch_index
    try:
        found = await es_client.search(
            {"query": {"term": {"source_file": "objects/Global context.html"}}},
            index=ru_index,
        )
        doc_id = found["hits"]["hits"][0]["_id"]

        await es_client._client.update(
            index=ru_index, id=doc_id, doc={"name_en": "", "object_en": None}, refresh=True
        )

        updated = await backfill_english_names(
            es_client, ru_index, settings.elasticsearch_index_en
        )
        assert updated > 0

        response = await es_client.search(
            {"query": {"term": {"source_file": "objects/Global context.html"}}},
            index=ru_index,
        )
        source = response["hits"]["hits"][0]["_source"]
        assert source["name_en"] == "Global context"
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
async def test_backfill_is_idempotent():
    """Второй прогон не должен ничего менять — иначе он затирает разбор."""
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        await backfill_english_names(
            es_client, settings.elasticsearch_index, settings.elasticsearch_index_en
        )
        second = await backfill_english_names(
            es_client, settings.elasticsearch_index, settings.elasticsearch_index_en
        )
        assert second == 0
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
async def test_already_parsed_name_en_is_not_overwritten():
    """object_en бывает пуст у страниц, чьё name_en уже разобрано задачей 11.

    В русской книге составной заголовок вида «Массив (Array)» разбирается
    точнее, чем сырой заголовок английской страницы. Если достройка при
    случае докладки object_en заодно перепишет и name_en значением из
    английского индекса — она отменит результат задачи 11 молча. Документ
    заводится и удаляется тестом, чтобы не зависеть от того, какие именно
    707 страниц сейчас пусты в живом индексе (это меняется от прогона к
    прогону).
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    ru_index = settings.elasticsearch_index
    en_index = settings.elasticsearch_index_en
    doc_id = "test_name_backfill_probe_ru"
    en_doc_id = "test_name_backfill_probe_en"
    source_file = "test/name_backfill_probe.html"
    try:
        await es_client._client.index(
            index=ru_index,
            id=doc_id,
            document={
                "id": doc_id,
                "type": "object_property",
                "name_en": "AlreadyParsedName",
                "object_en": None,
                "source_file": source_file,
            },
            refresh=True,
        )
        await es_client._client.index(
            index=en_index,
            id=en_doc_id,
            document={
                "name": "RawEnglishTitle",
                "object": "SomeObject",
                "source_file": source_file,
            },
            refresh=True,
        )

        await backfill_english_names(es_client, ru_index, en_index)

        after = await es_client._client.get(index=ru_index, id=doc_id)
        assert after["_source"]["name_en"] == "AlreadyParsedName"
        assert after["_source"]["object_en"] == "SomeObject"
    finally:
        from elasticsearch.exceptions import NotFoundError

        for index, _id in ((ru_index, doc_id), (en_index, en_doc_id)):
            try:
                await es_client._client.delete(index=index, id=_id, refresh=True)
            except NotFoundError:
                pass
        await es_client.disconnect()


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

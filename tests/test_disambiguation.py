"""Тесты однозначности выбора элемента.

69,1% документов индекса имеют неуникальное имя: «Количество» встречается у 275
элементов, «Добавить» — у 197. Прежний get_syntax_info выполнял запрос с size:1
и возвращал один документ из 275, ничем не сообщая о выборе. Агент принимал
чужую карточку за единственную.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.elasticsearch import es_client
from src.handlers.mcp_handlers import build_object_card
from src.search.search_service import SearchService


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_homonym_is_not_chosen_silently():
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        answer = await SearchService(es_client).element_card("Количество")

        assert answer["kind"] == "ambiguous", answer.get("kind")
        assert answer["total"] > 100
        assert answer["candidates"], "перечень кандидатов пуст"
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_qualified_object_yields_card():
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        answer = await SearchService(es_client).element_card(
            "НайтиСтроки", "ТаблицаЗначений"
        )

        assert answer["kind"] == "card"
        assert answer["document"]["object"] == "ТаблицаЗначений"
        assert answer["document"]["name_ru"] == "НайтиСтроки"
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_nonexistent_object_is_not_substituted_silently():
    """«ФоновыеЗадания» — идентификатор из кода, в справке объект зовётся иначе.

    Прежде сервис молча искал по одному имени метода и отдавал элементы чужих
    объектов, не сообщая о подмене.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        answer = await SearchService(es_client).element_card(
            "Выполнить", "ФоновыеЗадания"
        )

        assert answer["kind"] == "object_not_found"
        assert answer["object"] == "ФоновыеЗадания"
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_candidates_start_with_real_types():
    """Настоящие типы важнее заголовков разделов справки вида «ОбъектМетаданных: Х»."""
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        answer = await SearchService(es_client).element_card("Количество")

        first_object = answer["candidates"][0]["object"] or ""
        assert " " not in first_object and ":" not in first_object, first_object
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_candidate_order_is_built_over_all_matches():
    """Порядок не должен зависеть от произвольного окна выдачи.

    Прежде кандидаты брались запросом size:50 с одинаковыми оценками у всех
    совпадений (то есть окно произвольно) и сортировались по алфавиту: для
    «Количество» ответ начинался с АгрегатыРегистраНакопления, а
    ТаблицаЗначений и СписокЗначений — коллекции, ради которых имя и
    спрашивают, — в пятёрку не попадали вовсе.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        answer = await SearchService(es_client).element_card("Количество")

        assert answer["full_order"] is True, (
            "275 совпадений обязаны упорядочиваться целиком, а не окном"
        )
        objects = [k.get("object") for k in answer["candidates"]]
        assert "ТаблицаЗначений" in objects, objects
        assert "СписокЗначений" in objects, objects
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_constructors_come_from_separate_documents():
    """У документа объекта variants пуст — конструкторы лежат отдельно.

    Карточка объекта читала пустые variants и заявляла «Конструкторы: в справке
    не указано». В индексе при этом 385 документов-конструкторов у 307
    объектов, и у ТаблицаЗначений там «Новый ТаблицаЗначений».
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)

        assert await service.constructor_lines("ТаблицаЗначений") == [
            "Новый ТаблицаЗначений"
        ]
        assert await service.constructor_lines("ТаблицаЗначенийБезКонструкторов") == []
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_canonical_object_path_does_not_double_the_name():
    """full_path объекта — его имя, а не «ТаблицаЗначений.ТаблицаЗначений».

    Удвоенное имя текло в совет карточки и в строки списков, а вызов с ним не
    находил ничего: члены объекта лежат под ключом «ТаблицаЗначений».
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        answer = await service.element_card("ТаблицаЗначений")

        assert answer["kind"] == "card", answer.get("kind")
        path = answer["document"]["full_path"]
        assert path == "ТаблицаЗначений", path

        # Совет карточки строится из этого же пути — проверяем, что по нему
        # действительно находится состав объекта.
        members = await service.get_object_members_list(path, "all", limit=1)
        assert members["total"] > 0, members
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_object_card_hint_with_overlapping_path_is_executable():
    """У 16 объектов хвост object повторял начало имени страницы.

    Склейка давала «…КубЗапись.<Имя внешнего источника>.<Имя внешнего
    источника>.<Имя куба>» — такого значения object в индексе нет. Карточка
    советовала по нему перечень (ответ: «объект в справке не найден») и по нему
    же считала состав, печатая «свойств: 0» о двух свойствах индекса.

    Совет из карточки выполняем как есть: проверять его пересобранной строкой
    значило бы проверять сам тест.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        answer = await service.element_card(
            "<Имя внешнего источника>.<Имя куба>",
            "ВнешнийИсточникДанныхКубЗапись.<Имя внешнего источника>",
        )
        assert answer["kind"] == "card", answer.get("kind")

        text = await build_object_card(service, answer["document"])

        hint = re.search(r'list_1c_object_members\(object="(.+?)"\)', text)
        assert hint, text
        members = await service.get_object_members_list(hint.group(1), "all", 50)
        assert members["total"] == 2, members["total"]
        assert "свойств: 2" in text, text
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_unknown_name_gives_not_found_not_an_empty_card():
    """Точного совпадения по имени нет вообще — сервис называет это прямо."""
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        name = "ЗаведомоНесуществующееИмяЭлементаXYZ123Qwerty"
        answer = await SearchService(es_client).element_card(name)

        assert answer["kind"] == "not_found"
        assert answer["name"] == name
        assert isinstance(answer["similar"], list)
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_unknown_variant_lists_existing_ones_instead_of_choosing_silently():
    """У 'ДанныеФормыКоллекция.Выгрузить' два варианта вызова.

    Несуществующее имя варианта не выбирает один из них молча, а называет оба
    существующих; настоящее имя, наоборот, сужает document.variants до одного
    — обе стороны контракта variant проверены в одном тесте.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)

        unknown_variant = await service.element_card(
            "Выгрузить", "ДанныеФормыКоллекция", variant="НесуществующийВариант"
        )
        assert unknown_variant["kind"] == "variant_not_found"
        assert unknown_variant["variants"] == ["Выгрузить колонки", "Выгрузить по отбору"]

        known_variant = await service.element_card(
            "Выгрузить", "ДанныеФормыКоллекция", variant="Выгрузить колонки"
        )
        assert known_variant["kind"] == "card"
        narrowed_variants = known_variant["document"]["variants"]
        assert len(narrowed_variants) == 1
        assert narrowed_variants[0]["variant"] == "Выгрузить колонки"
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_similar_objects_searches_object_names_not_element_names():
    """Подсказка о похожих объектах ищет среди имён объектов, а не элементов.

    Прежде нечёткий поиск шёл по имени элемента (name_ru метода/свойства) и
    отдавал случайного владельца найденного элемента — 'Строка' совпадала
    корнем с 'Из строки' у чужого конструктора, и в подсказке оказывались
    объекты, не похожие на запрос ни по одной букве смысла.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)

        assert await service.similar_objects("ТаблицыЗначений") == ["ТаблицаЗначений"]
        assert await service.similar_objects("МенеджерФоновыхЗадания") == [
            "МенеджерФоновыхЗаданий"
        ]
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_object_filter_accepts_english_name():
    """object= принимает английское имя объекта — задача 11 заполнила object_en.

    До правки фильтр по объекту смотрел только в object (техническое русское
    имя), и list_1c_object_members(object="ValueTable") отвечал «объект не
    найден», хотя английское имя уже лежало в индексе у 22 821 документа.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)

        assert await service.object_exists("ValueTable")
        counts = await service.member_count("ValueTable")
        assert counts["methods"] > 0
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_dotted_english_path_is_found():
    """'ValueTable.Add' находит элемент через ту же точечную запись, что и по-русски.

    find_1c_help("ValueTable.Add") строит запрос через build_qualified_query,
    чей filter по object тоже смотрел только в русское техническое имя.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        result = await service.find_help_filtered("ValueTable.Add", [], None, 10)

        assert result["results"]
    finally:
        await es_client.disconnect()

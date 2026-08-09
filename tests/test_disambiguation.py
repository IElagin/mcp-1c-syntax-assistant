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
from src.handlers.mcp_handlers import (
    build_object_card, handle_find_1c_help, handle_get_1c_element,
)
from src.models.mcp_models import Find1CHelpRequest, Get1CElementRequest
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

        calls = await service.constructor_calls("ТаблицаЗначений")
        assert [call for call, _ in calls] == ["Новый ТаблицаЗначений"]
        assert await service.constructor_calls("ТаблицаЗначенийБезКонструкторов") == []
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
async def test_element_absent_at_the_object_is_not_declared_absent_from_the_book():
    """object сужает поиск — отрицание обязано сужаться вместе с ним.

    get_1c_element(name="XMLТипЗнч", object="ФабрикаXDTO") отвечал «Элемент с
    точным именем «XMLТипЗнч» в справке не найден», а следующей строкой
    печатал этот самый «XMLТипЗнч» среди похожих: точное совпадение искалось
    у одного объекта, а перечень похожих — по всей книге, и ответ опровергал
    сам себя. Элемент в справке есть, просто не у ФабрикаXDTO.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        answer = await SearchService(es_client).element_card(
            "XMLТипЗнч", "ФабрикаXDTO"
        )

        assert answer["kind"] == "not_in_object", answer.get("kind")
        assert answer["object"] == "ФабрикаXDTO"
        assert answer["total"] == 2
        paths = [k.get("full_path") for k in answer["candidates"]]
        assert "XMLТипЗнч" in paths, paths
        assert "СериализаторXDTO.XMLТипЗнч" in paths, paths
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_answer_does_not_deny_the_name_it_then_lists():
    """Тот же дефект на уровне текста ответа — его читает агент, а не kind."""
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        response = await handle_get_1c_element(
            Get1CElementRequest(name="XMLТипЗнч", object="ФабрикаXDTO"), es_client
        )

        text = response.content[0]["text"]
        assert "ФабрикаXDTO" in text, text
        assert "в справке не найден" not in text, text
        assert 'get_1c_element(name="XMLТипЗнч")' in text, text
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_name_absent_everywhere_still_says_absent_from_the_book():
    """Обратная сторона: если имени нет нигде, сужать отрицание нечем.

    Ветка not_in_object не должна подменять собой честное «такого имени в
    справке нет» — иначе исчезнет единственный ответ, из которого агент
    поймёт, что дело в написании имени, а не в выборе объекта.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        answer = await SearchService(es_client).element_card(
            "ЗаведомоНесуществующееИмяЭлементаXYZ123Qwerty", "ФабрикаXDTO"
        )

        assert answer["kind"] == "not_found", answer.get("kind")
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
async def test_similar_objects_helps_after_a_typo_in_the_english_name():
    """Опечатка в английском имени объекта тоже обязана давать подсказку.

    Живая асимметрия до правки: object="ТаблицаЗначенй" → «ТаблицаЗначений»,
    object="ValuTable" → «подходящих не найдено». Английское имя объекта уже
    полноправный вход (задачи 11 и 12), и молчание подсказки агент читает как
    «объекта в справке нет».
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)

        assert "ТаблицаЗначений" in await service.similar_objects("ValuTable")
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


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_global_context_members_are_listable_under_its_russian_name():
    """Перечень глобального контекста обязан включать его процедуры и функции.

    До правки объект существовал в индексе под двумя именами сразу: 510
    процедур, функций и событий лежали под английским «Global context» (имя
    приходило из пути страницы, английского в обеих книгах), а 87 свойств — под
    русским «Глобальный контекст». Вдобавок глобальные виды не входили в фильтр
    состава. Итог: list_1c_object_members("Глобальный контекст") отдавал 87
    свойств и ни одного метода — ни Сообщить, ни СтрШаблон, ни
    ЗначениеЗаполнено нельзя было перечислить ничем.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)

        members = await service.get_object_members_list("Глобальный контекст", "all", 5)
        assert members["total"] > 500, members["total"]

        methods = await service.get_object_members_list("Глобальный контекст", "methods", 5)
        assert methods["total"] > 400, methods["total"]

        counts = await service.member_count("Глобальный контекст")
        assert counts["methods"] > 400 and counts["properties"] > 80, counts

        # Английское имя объекта продолжает работать: object_en у этих страниц
        # заполнен, и агент, знающий тип по английскому имени, не теряет доступ.
        assert await service.object_exists("Global context")

        for name in ("Сообщить", "СтрШаблон"):
            answer = await service.element_card(name, "Глобальный контекст")
            assert answer["kind"] == "card", (name, answer.get("kind"))
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_empty_result_names_the_object_the_query_itself_narrowed_to():
    """Фильтр, вычитанный из запроса, обязан быть назван в объяснении пустоты.

    find_1c_help("Массив.НетТакогоМетода") сужает выдачу по Массиву и не
    находит ничего. Прежний ответ говорил «Ни фильтра по объекту, ни фильтра по
    виду не было — совпадений нет во всей справке»: оба утверждения неверны,
    фильтр был, и искали у одного объекта.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        response = await handle_find_1c_help(
            Find1CHelpRequest(query="Массив.НетТакогоМетодаXYZ"), es_client
        )

        text = response.content[0]["text"]
        assert "Массив" in text, text
        assert "Ни фильтра по объекту" not in text, text
    finally:
        await es_client.disconnect()

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
from src.handlers.mcp_handlers import sobrat_kartochku_obekta
from src.search.search_service import SearchService


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_omonim_ne_vybiraetsya_molcha():
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        otvet = await SearchService(es_client).kartochka_elementa("Количество")

        assert otvet["kind"] == "ambiguous", otvet.get("kind")
        assert otvet["total"] > 100
        assert otvet["candidates"], "перечень кандидатов пуст"
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_utochnennyy_obekt_daet_kartochku():
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        otvet = await SearchService(es_client).kartochka_elementa(
            "НайтиСтроки", "ТаблицаЗначений"
        )

        assert otvet["kind"] == "card"
        assert otvet["document"]["object"] == "ТаблицаЗначений"
        assert otvet["document"]["name_ru"] == "НайтиСтроки"
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_nesushchestvuyushchiy_obekt_ne_podmenyaetsya_molcha():
    """«ФоновыеЗадания» — идентификатор из кода, в справке объект зовётся иначе.

    Прежде сервис молча искал по одному имени метода и отдавал элементы чужих
    объектов, не сообщая о подмене.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        otvet = await SearchService(es_client).kartochka_elementa(
            "Выполнить", "ФоновыеЗадания"
        )

        assert otvet["kind"] == "object_not_found"
        assert otvet["object"] == "ФоновыеЗадания"
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_kandidaty_nachinayutsya_s_nastoyashchih_tipov():
    """Настоящие типы важнее заголовков разделов справки вида «ОбъектМетаданных: Х»."""
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        otvet = await SearchService(es_client).kartochka_elementa("Количество")

        pervyy = otvet["candidates"][0]["object"] or ""
        assert " " not in pervyy and ":" not in pervyy, pervyy
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_poryadok_kandidatov_stroitsya_po_vsem_sovpadeniyam():
    """Порядок не должен зависеть от произвольного окна выдачи.

    Прежде кандидаты брались запросом size:50 с одинаковыми оценками у всех
    совпадений (то есть окно произвольно) и сортировались по алфавиту: для
    «Количество» ответ начинался с АгрегатыРегистраНакопления, а
    ТаблицаЗначений и СписокЗначений — коллекции, ради которых имя и
    спрашивают, — в пятёрку не попадали вовсе.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        otvet = await SearchService(es_client).kartochka_elementa("Количество")

        assert otvet["poryadok_polnyy"] is True, (
            "275 совпадений обязаны упорядочиваться целиком, а не окном"
        )
        obekty = [k.get("object") for k in otvet["candidates"]]
        assert "ТаблицаЗначений" in obekty, obekty
        assert "СписокЗначений" in obekty, obekty
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_konstruktory_berutsya_iz_otdelnyh_dokumentov():
    """У документа объекта variants пуст — конструкторы лежат отдельно.

    Карточка объекта читала пустые variants и заявляла «Конструкторы: в справке
    не указано». В индексе при этом 385 документов-конструкторов у 307
    объектов, и у ТаблицаЗначений там «Новый ТаблицаЗначений».
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)

        assert await service.stroki_konstruktorov("ТаблицаЗначений") == [
            "Новый ТаблицаЗначений"
        ]
        assert await service.stroki_konstruktorov("ТаблицаЗначенийБезКонструкторов") == []
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_kanonicheskiy_put_obekta_ne_udvaivaet_imya():
    """full_path объекта — его имя, а не «ТаблицаЗначений.ТаблицаЗначений».

    Удвоенное имя текло в совет карточки и в строки списков, а вызов с ним не
    находил ничего: члены объекта лежат под ключом «ТаблицаЗначений».
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        otvet = await service.kartochka_elementa("ТаблицаЗначений")

        assert otvet["kind"] == "card", otvet.get("kind")
        put = otvet["document"]["full_path"]
        assert put == "ТаблицаЗначений", put

        # Совет карточки строится из этого же пути — проверяем, что по нему
        # действительно находится состав объекта.
        sostav = await service.get_object_members_list(put, "all", limit=1)
        assert sostav["total"] > 0, sostav
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_sovet_kartochki_obekta_s_perekrytiem_ispolnim():
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
        otvet = await service.kartochka_elementa(
            "<Имя внешнего источника>.<Имя куба>",
            "ВнешнийИсточникДанныхКубЗапись.<Имя внешнего источника>",
        )
        assert otvet["kind"] == "card", otvet.get("kind")

        tekst = await sobrat_kartochku_obekta(service, otvet["document"])

        sovet = re.search(r'list_1c_object_members\(object="(.+?)"\)', tekst)
        assert sovet, tekst
        sostav = await service.get_object_members_list(sovet.group(1), "all", 50)
        assert sostav["total"] == 2, sostav["total"]
        assert "свойств: 2" in tekst, tekst
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_neizvestnoe_imya_daet_not_found_a_ne_pustuyu_kartochku():
    """Точного совпадения по имени нет вообще — сервис называет это прямо."""
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        imya = "ЗаведомоНесуществующееИмяЭлементаXYZ123Qwerty"
        otvet = await SearchService(es_client).kartochka_elementa(imya)

        assert otvet["kind"] == "not_found"
        assert otvet["name"] == imya
        assert isinstance(otvet["similar"], list)
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_neizvestnyy_variant_nazyvaet_sushchestvuyushchie_a_ne_vybiraet_molcha():
    """У 'ДанныеФормыКоллекция.Выгрузить' два варианта вызова.

    Несуществующее имя варианта не выбирает один из них молча, а называет оба
    существующих; настоящее имя, наоборот, сужает document.variants до одного
    — обе стороны контракта variant проверены в одном тесте.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)

        ne_naiden = await service.kartochka_elementa(
            "Выгрузить", "ДанныеФормыКоллекция", variant="НесуществующийВариант"
        )
        assert ne_naiden["kind"] == "variant_not_found"
        assert ne_naiden["variants"] == ["Выгрузить колонки", "Выгрузить по отбору"]

        naiden = await service.kartochka_elementa(
            "Выгрузить", "ДанныеФормыКоллекция", variant="Выгрузить колонки"
        )
        assert naiden["kind"] == "card"
        varianty = naiden["document"]["variants"]
        assert len(varianty) == 1
        assert varianty[0]["variant"] == "Выгрузить колонки"
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_pohozhie_obekty_ishchet_sredi_imen_obektov_a_ne_elementov():
    """Подсказка о похожих объектах ищет среди имён объектов, а не элементов.

    Прежде нечёткий поиск шёл по имени элемента (name_ru метода/свойства) и
    отдавал случайного владельца найденного элемента — 'Строка' совпадала
    корнем с 'Из строки' у чужого конструктора, и в подсказке оказывались
    объекты, не похожие на запрос ни по одной букве смысла.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)

        assert await service.pohozhie_obekty("ТаблицыЗначений") == ["ТаблицаЗначений"]
        assert await service.pohozhie_obekty("МенеджерФоновыхЗадания") == [
            "МенеджерФоновыхЗаданий"
        ]
    finally:
        await es_client.disconnect()

"""Тесты полноты вывода: списки не режутся молча, фразы не рвутся посередине.

Найдено на реальном примере. Справка по 'ОбъектМетаданных: РегламентноеЗадание.Ключ'
в выдаче find_1c_help обрывалась на слове «могут»:

  "Два регламентных задания с одинаковым значением ключа могут ..."

тогда как полный текст — "...могут быть выполнены только последовательно".
Обрыв посередине фразы переворачивает смысл на противоположный.

Замер по индексу: при пределе 100 знаков обрезалось 51.3% описаний (2052 из
3999), медиана описания — 103 знака, медиана первой фразы — 65.

Второй дефект того же класса: format_object_members_list печатал в заголовке
настоящее число элементов, а список обрезал на 20/15/10 без всякой пометки.
У 'ТабличныйДокумент' заголовок сообщал «Методы (46)», выводилось ровно 20, и
всё от «О» до «Я» (Прочитать, Показать, Сохранить) было невидимо.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.elasticsearch import es_client
from src.handlers.mcp_formatter import mcp_formatter, obrezat_do_frazy
from src.search.search_service import SearchService

KLYUCH_POLNYY = (
    "Тип: Строка Ключ регламентного задания. Два регламентных задания с "
    "одинаковым значением ключа могут быть выполнены только последовательно."
)


@pytest.mark.unit
def test_korotkoe_opisanie_ne_trogaem():
    assert obrezat_do_frazy("Добавляет строку.", 200) == "Добавляет строку."


@pytest.mark.unit
def test_obrez_ne_rvet_frazu_poseredine():
    """Показанный текст всегда заканчивается целой фразой.

    Именно это защищает от инверсии смысла: лучше показать меньше фраз,
    чем половину фразы.
    """
    rezultat = obrezat_do_frazy(KLYUCH_POLNYY, 60)

    assert "могут" not in rezultat or "последовательно" in rezultat, (
        f"Фраза оборвана посередине: {rezultat!r}"
    )
    assert rezultat.startswith("Тип: Строка Ключ регламентного задания.")


@pytest.mark.unit
def test_obrez_pometchaetsya():
    """Укороченный текст помечен, чтобы не выглядел полным."""
    rezultat = obrezat_do_frazy(KLYUCH_POLNYY, 60)
    assert rezultat.endswith("…"), rezultat


@pytest.mark.unit
def test_klyuch_reglamentnogo_zadaniya_vlezaet_polnostyu():
    """Тот самый случай из отчёта: 135 знаков влезают в бюджет превью."""
    assert obrezat_do_frazy(KLYUCH_POLNYY, 200) == KLYUCH_POLNYY


@pytest.mark.unit
def test_spisok_elementov_ne_rezhetsya_molcha():
    """Все переданные элементы попадают в вывод.

    Раньше форматтер жёстко обрезал на 20 методах, игнорируя limit вызова.
    """
    metody = [
        {"name": f"Метод{i:02d}", "syntax_ru": f"Метод{i:02d}()", "description": "Описание."}
        for i in range(46)
    ]

    text = mcp_formatter.format_object_members_list(
        "ТабличныйДокумент", "methods", metody, [], [], total=46
    )

    poteryany = [m["name"] for m in metody if m["name"] not in text]
    assert not poteryany, f"Не попали в вывод: {poteryany}"


@pytest.mark.unit
def test_soobshchaem_kogda_pokazano_ne_vse():
    """Если в индексе элементов больше, чем показано — это сказано прямо."""
    metody = [
        {"name": f"Метод{i:02d}", "syntax_ru": "", "description": ""}
        for i in range(20)
    ]

    text = mcp_formatter.format_object_members_list(
        "ТабличныйДокумент", "methods", metody, [], [], total=46
    )

    assert "20" in text and "46" in text, (
        f"Нет пометки о неполноте выдачи:\n{text[:300]}"
    )


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_nastoyashchiy_total_kogda_limit_rezhet():
    """total отражает число элементов в индексе, а не размер вернувшегося куска."""
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        rezultat = await service.get_object_members_list("ТабличныйДокумент", "methods", limit=5)

        assert len(rezultat["methods"]) == 5
        assert rezultat["total"] > 5, (
            f"total={rezultat['total']} повторяет размер куска вместо числа в индексе"
        )
    finally:
        await es_client.disconnect()


@pytest.mark.unit
def test_konstruktory_pechatayutsya_pod_svoim_yarlykom():
    """members="constructors" не должен подписываться "Методы".

    get_object_members_list кладёт конструкторы в тот же список methods, что и
    обычные методы (см. test_spisok_elementov_ne_rezhetsya_molcha) — иначе для
    этого вида запроса вывод был бы пуст. Но ярлык в заголовке должен называть
    вещи своими именами: конструктор — не то же самое, что метод.
    """
    konstruktory = [
        {"name": "На основании фиксированного массива", "syntax_ru": "", "description": ""},
        {"name": "По количеству элементов", "syntax_ru": "", "description": ""},
    ]

    text = mcp_formatter.format_object_members_list(
        "Массив", "constructors", konstruktory, [], [], total=2
    )

    assert "Конструкторы (2)" in text
    assert "Методы" not in text


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_sushchestvuyushchii_obekt_bez_nuzhnogo_vida_ne_schitaetsya_nenaidennym():
    """total=0 при members="events" у ТаблицаЗначений — но объект есть.

    Разграничение "объекта нет" от "объект есть, но не того вида" делает
    get_object_members_list через отдельный ключ object_exists — раньше оба
    случая одинаково звучали как "объект не найден", и агент слышал это про
    объект, который тут же значился в списке "похожих" на самого себя.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        rezultat = await service.get_object_members_list("ТаблицаЗначений", "events", limit=10)

        assert rezultat["total"] == 0
        assert rezultat.get("object_exists") is True, (
            "ТаблицаЗначений существует, даже если событий у неё нет"
        )
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_nesushchestvuyushchii_obekt_deistvitelno_ne_naiden():
    """Настоящее отсутствие объекта по-прежнему отличимо от «нет элементов
    этого вида» — object_exists=False только тогда, когда объекта нет вовсе.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        rezultat = await service.get_object_members_list(
            "НесуществующийОбъект123", "all", limit=10
        )

        assert rezultat["total"] == 0
        assert rezultat.get("object_exists") is False
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_metody_za_dvadtsatym_vidny():
    """Методы из хвоста алфавита доходят до вывода."""
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        rezultat = await service.get_object_members_list("ТабличныйДокумент", "methods", limit=100)

        text = mcp_formatter.format_object_members_list(
            "ТабличныйДокумент", "methods",
            rezultat["methods"], rezultat["properties"], rezultat["events"],
            rezultat["total"],
        )

        for imya in ("Прочитать", "Показать"):
            assert imya in text, f"'{imya}' потерян в выводе"
    finally:
        await es_client.disconnect()

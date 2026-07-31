"""Тесты качества поиска: точечная запись и точное совпадение имени.

Замер до правок (150 элементов эталона из индекса):
  - запрос 'Объект.Метод'  — 2.0% попаданий в топ-5, 60.7% пустых ответов;
  - голое имя метода       — 26.7% на первом месте.

Причины:
  - full_path имеет тип keyword, а запрашивался через match/match_phrase,
    которые для keyword требуют совпадения строки целиком;
  - name хранит русское и английское имя слитно ("Добавить (Add)"), поэтому
    term по name.keyword со значением "Добавить" не срабатывал никогда —
    буст на точное совпадение был мёртвым.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.elasticsearch import es_client
from src.search.search_service import SearchService


def imena(rezultaty):
    return [(r.get("object"), r.get("name")) for r in rezultaty]


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.search
@pytest.mark.asyncio
async def test_tochechnaya_zapis_nahodit_imenno_etot_metod():
    """'ТаблицаЗначений.Добавить' возвращает нужный элемент первым.

    Так разработчик пишет запрос естественнее всего — копирует выражение
    из кода. До правки такой запрос возвращал мусор или пустоту.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        res = await service.find_help_by_query("ТаблицаЗначений.Добавить", limit=5)

        assert not res.get("error"), res.get("error")
        rezultaty = res.get("results", [])
        assert rezultaty, "Пустой ответ на точечную запись"

        pervyy = rezultaty[0]
        assert pervyy.get("object") == "ТаблицаЗначений", imena(rezultaty)
        assert pervyy.get("name", "").startswith("Добавить"), imena(rezultaty)
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.search
@pytest.mark.asyncio
async def test_tochechnaya_zapis_ne_puskaet_chuzhie_obekty():
    """В выдаче по 'Объект.Метод' нет элементов других объектов."""
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        res = await service.find_help_by_query("МенеджерФоновыхЗаданий.ПолучитьФоновыеЗадания", limit=5)

        rezultaty = res.get("results", [])
        assert rezultaty, "Пустой ответ на точечную запись"

        chuzhie = sorted({
            r.get("object") for r in rezultaty
            if r.get("object") != "МенеджерФоновыхЗаданий"
        })
        assert not chuzhie, f"Просочились чужие объекты: {chuzhie}"
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.search
@pytest.mark.asyncio
async def test_tochnoe_imya_vyshe_chastichnogo():
    """Точное совпадение имени ранжируется выше частичного.

    'Записать' — точное имя метода у многих объектов; 'ЗаписатьАтрибут',
    'ЗаписатьТекст' и подобные не должны обгонять его.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        res = await service.find_help_by_query("Записать", limit=5)

        rezultaty = res.get("results", [])
        assert rezultaty, "Пустой ответ"

        pervoe_imya = rezultaty[0].get("name", "")
        # name хранится как "Записать (Write)" — сравниваем русскую часть
        assert pervoe_imya.split(" (")[0] == "Записать", (
            f"Первым пришло частичное совпадение: {imena(rezultaty)}"
        )
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.search
@pytest.mark.asyncio
async def test_poisk_po_angliyskomu_imeni_tochnyy():
    """Английское имя находит тот же элемент: ValueIsFilled."""
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        res = await service.find_help_by_query("ValueIsFilled", limit=5)

        rezultaty = res.get("results", [])
        assert rezultaty, "Пустой ответ"
        assert any(
            "ЗначениеЗаполнено" in (r.get("name") or "") for r in rezultaty[:3]
        ), imena(rezultaty)
    finally:
        await es_client.disconnect()


@pytest.mark.unit
@pytest.mark.search
def test_zaprosy_ne_ssylayutsya_na_udalennye_polya():
    """Буст по несуществующему полю — тихий ноль, а не ошибка.

    syntax_en был пуст у 100% методов и всё равно стоял в бустах; parameters.*
    в плоском match по nested-полю не находил ничего (0 попаданий против 11 у
    nested-запроса). Такие бусты создают ложное чувство настроенного поиска.
    """
    import json

    from src.search.query_builder import QueryBuilder

    builder = QueryBuilder()
    zaprosy = [
        builder.build_search_query("ЗначениеЗаполнено", 10, "exact"),
        builder.build_search_query("как получить количество строк", 10, "semantic"),
        builder.build_search_query("ТаблицаЗначений.Добавить", 10, "auto"),
        builder.build_search_query("найти строки", 10, "multi_match"),
        builder.build_search_query("НайтиСтроки", 10, "fuzzy"),
        builder.build_exact_query("Добавить"),
    ]

    tekst = json.dumps(zaprosy, ensure_ascii=False)
    for pole in ("syntax_ru", "syntax_en", "parameters.name", "parameters.description"):
        assert pole not in tekst, f"запрос ссылается на удалённое поле {pole}"

    assert "syntax_all" in tekst, "поисковое поле синтаксиса не используется"

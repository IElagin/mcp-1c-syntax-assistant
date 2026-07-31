"""Тесты полноты вывода: списки не режутся молча, фразы не рвутся посередине.

Найдено на реальном примере. Справка по 'ОбъектМетаданных: РегламентноеЗадание.Ключ'
в выдаче find_1c_help обрывалась на слове «могут»:

  "Два регламентных задания с одинаковым значением ключа могут ..."

тогда как полный текст — "...могут быть выполнены только последовательно".
Обрыв посередине фразы переворачивает смысл на противоположный.

Замер по индексу: при пределе 100 знаков обрезалось 51.3% описаний (2052 из
3999), медиана описания — 103 знака, медиана первой фразы — 65.

Второй дефект того же класса: список состава объекта печатал в заголовке
настоящее число элементов, а сам список обрезал на 20/15/10 без всякой пометки.
У 'ТабличныйДокумент' заголовок сообщал «Методы (46)», выводилось ровно 20, и
всё от «О» до «Я» (Прочитать, Показать, Сохранить) было невидимо.

Третий — и он пережил прошлое ревью именно из-за здешних фикстур. Форматтер
состава читал поле syntax_ru, удалённое из модели и из документа индекса, а
фикстуры теста это поле подставляли руками и проверяли только присутствие имён.
Тест не мог упасть за то поведение, которое покрывал: он одинаково проходил и
до, и после удаления поля, пока живой ответ не содержал ни одной строки вызова.
Поэтому фикстуры ниже — настоящие документы индекса help1c_docs, а утверждения
касаются строки вызова.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.mcp_tools import LIMIT_SOSTAVA_MAX
from src.core.elasticsearch import es_client
from src.handlers.element_card import spisok_chlenov
from src.handlers.mcp_formatter import obrezat_do_frazy
from src.search.search_service import SearchService

KLYUCH_POLNYY = (
    "Тип: Строка Ключ регламентного задания. Два регламентных задания с "
    "одинаковым значением ключа могут быть выполнены только последовательно."
)

# Документы индекса help1c_docs как есть (параметры вариантов опущены — строке
# списка они не нужны). Ни у одного нет поля syntax_ru: его нет в индексе.
VSTAVIT = {
    "type": "object_function",
    "element_kind": "функция",
    "name": "Вставить (Insert)",
    "name_ru": "Вставить",
    "object": "ТаблицаЗначений",
    "full_path": "ТаблицаЗначений.Вставить",
    "call_primary": "ТаблицаЗначений.Вставить(<Индекс>)",
    "variants": [{
        "variant": "", "syntax": "Вставить(<Индекс>)",
        "call": "ТаблицаЗначений.Вставить(<Индекс>)",
        "return_type": "СтрокаТаблицыЗначений",
        "return_description": "Вставленная строка.",
    }],
    "description": "Вставляет строку на позицию в таблице значений, "
                   "соответствующую указанному индексу.",
}

KOLONKI = {
    "type": "object_property",
    "element_kind": "свойство",
    "name": "Колонки (Columns)",
    "name_ru": "Колонки",
    "object": "ТаблицаЗначений",
    "full_path": "ТаблицаЗначений.Колонки",
    "call_primary": "ТаблицаЗначений.Колонки",
    "variants": [],
    "description": "Содержит коллекцию колонок таблицы значений.",
}

KONSTRUKTOR_TZ = {
    "type": "object_constructor",
    "element_kind": "конструктор",
    "name": "По умолчанию",
    "name_ru": "По умолчанию",
    "object": "ТаблицаЗначений",
    "full_path": "ТаблицаЗначений.По умолчанию",
    "call_primary": "Новый ТаблицаЗначений",
    "variants": [{
        "variant": "По умолчанию", "syntax": "Новый ТаблицаЗначений",
        "call": "Новый ТаблицаЗначений", "return_type": "", "return_description": "",
    }],
    "description": "",
}


def sostav(vid, metody=(), svoystva=(), sobytiya=(), vsego=None):
    """Состав объекта ТаблицаЗначений с явным total."""
    elementy = list(metody), list(svoystva), list(sobytiya)
    if vsego is None:
        vsego = sum(len(s) for s in elementy)
    return spisok_chlenov(
        "ТаблицаЗначений", vid, *elementy, vsego=vsego,
        predel_instrumenta=LIMIT_SOSTAVA_MAX,
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
def test_kazhdyy_metod_sostava_neset_stroku_vyzova():
    """Состав объекта обязан отвечать на вопрос «как вызывать», а не только «что».

    Прежний форматтер читал удалённое поле syntax_ru, и живой ответ состоял из
    имени и описания: «Вставить (Insert)» — по такой строке агент не напишет
    ни скобок, ни имени объекта.
    """
    text = sostav("methods", metody=[VSTAVIT])

    assert "ТаблицаЗначений.Вставить(<Индекс>)" in text, text
    assert "функция" in text, "вид элемента не назван: " + text


@pytest.mark.unit
def test_konstruktor_v_sostave_pokazyvaet_novyy():
    """members="constructors" у ТаблицаЗначений давал голое «По умолчанию».

    Из такого ответа никак не следует, что вызов пишется как
    «Новый ТаблицаЗначений» — а это единственное, ради чего конструктор
    спрашивают.
    """
    text = sostav("constructors", metody=[KONSTRUKTOR_TZ])

    assert "Новый ТаблицаЗначений" in text, text
    assert "Конструкторы (1)" in text
    assert "Методы" not in text, "конструктор — не метод: " + text


@pytest.mark.unit
def test_svoystvo_v_sostave_neset_obrashchenie():
    """У свойства строка вызова — обращение через точку, без скобок."""
    text = sostav("properties", svoystva=[KOLONKI])

    assert "ТаблицаЗначений.Колонки" in text
    assert "свойство" in text


@pytest.mark.unit
def test_spisok_elementov_ne_rezhetsya_molcha():
    """Все переданные элементы попадают в вывод.

    Раньше форматтер жёстко обрезал на 20 методах, игнорируя limit вызова.
    """
    metody = [
        dict(VSTAVIT, name_ru=f"Метод{i:02d}",
             full_path=f"ТаблицаЗначений.Метод{i:02d}",
             call_primary=f"ТаблицаЗначений.Метод{i:02d}()")
        for i in range(46)
    ]

    text = sostav("methods", metody=metody, vsego=46)

    poteryany = [m["full_path"] for m in metody if m["full_path"] not in text]
    assert not poteryany, f"Не попали в вывод: {poteryany}"


@pytest.mark.unit
def test_soobshchaem_kogda_pokazano_ne_vse():
    """Если в индексе элементов больше, чем показано — это сказано прямо."""
    metody = [
        dict(VSTAVIT, name_ru=f"Метод{i:02d}",
             full_path=f"ТаблицаЗначений.Метод{i:02d}")
        for i in range(20)
    ]

    text = sostav("methods", metody=metody, vsego=46)

    assert "Показано 20 из 46" in text, (
        f"Нет пометки о неполноте выдачи:\n{text[:300]}"
    )


@pytest.mark.unit
def test_sovet_o_dobore_ne_obeshchaet_nevozmozhnogo():
    """Совет обязан быть выполнимым: смещения у инструмента нет.

    «Повторите вызов с limit=N за остальными» — обещание, которого инструмент
    не выполняет: повтор вернёт те же первые N элементов. Годится только
    «за один вызов не более N» либо «полный список — вот такой вызов».
    """
    metody = [
        dict(VSTAVIT, full_path=f"ТаблицаЗначений.Метод{i:02d}") for i in range(5)
    ]

    text = sostav("methods", metody=metody, vsego=46)

    assert "за остальными" not in text, text
    assert 'list_1c_object_members(object="ТаблицаЗначений", members="methods", ' \
           'limit=46)' in text, text


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
async def test_obekt_bez_nastoyashchih_chlenov_pri_all_ne_lovit_sam_sebya():
    """members="all" раньше фильтровал только по object, без ограничения по
    видам, и ловил документ самого объекта (type="object" — у него поле
    object тоже равно собственному имени). У объекта без единого настоящего
    метода/свойства/события/конструктора (JSON, DOM, HTML, XDTO и другие — 359
    из 2506) total выходил 1 вместо 0, и ветка "объект есть, но пуст" для all
    не срабатывала никогда: агенту обещался элемент, которого нет.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        rezultat = await service.get_object_members_list("JSON", "all", limit=10)

        assert rezultat["total"] == 0, (
            f"Документ самого объекта JSON попал в выборку: total={rezultat['total']}"
        )
        assert rezultat.get("object_exists") is True, "JSON как объект в справке есть"
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_schetchik_all_ravna_summe_po_vidam_bez_lishnego_dokumenta():
    """total для all обязан равняться сумме total по methods+properties+events,
    без лишней единицы за документ-описание самого объекта.

    Раньше у ТаблицаЗначений all выдавал 23 при 22 настоящих членах.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)

        vse = await service.get_object_members_list("ТаблицаЗначений", "all", limit=1)
        metody = await service.get_object_members_list("ТаблицаЗначений", "methods", limit=1)
        svoystva = await service.get_object_members_list("ТаблицаЗначений", "properties", limit=1)
        sobytiya = await service.get_object_members_list("ТаблицаЗначений", "events", limit=1)

        ozhidaemyi = metody["total"] + svoystva["total"] + sobytiya["total"]
        assert vse["total"] == ozhidaemyi, (
            f"all={vse['total']}, сумма по видам={ozhidaemyi} — "
            "документ объекта снова считается членом"
        )
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_metody_za_dvadtsatym_vidny():
    """Методы из хвоста алфавита доходят до вывода — и со строкой вызова."""
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        rezultat = await service.get_object_members_list("ТабличныйДокумент", "methods", limit=100)

        text = spisok_chlenov(
            "ТабличныйДокумент", "methods",
            rezultat["methods"], rezultat["properties"], rezultat["events"],
            rezultat["total"], LIMIT_SOSTAVA_MAX,
        )

        for imya in ("Прочитать", "Показать"):
            assert f"ТабличныйДокумент.{imya}" in text, f"'{imya}' потерян в выводе"
        assert "ТабличныйДокумент.Показать(" in text, (
            "строки вызова нет ни у одного метода: " + text[:400]
        )
    finally:
        await es_client.disconnect()

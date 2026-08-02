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

Третий — того же класса, и дольше всех оставался незамеченным именно из-за
здешних фикстур. Форматтер состава читал поле syntax_ru, удалённое из модели и
из документа индекса, а фикстуры теста это поле подставляли руками и
проверяли только присутствие имён.
Тест не мог упасть за то поведение, которое покрывал: он одинаково проходил и
до, и после удаления поля, пока живой ответ не содержал ни одной строки вызова.
Поэтому фикстуры ниже — настоящие документы индекса help1c_docs, а утверждения
касаются строки вызова.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.mcp_tools import MEMBERS_LIMIT_MAX
from src.core.elasticsearch import es_client
from src.handlers.element_card import member_list
from src.handlers.mcp_formatter import truncate_at_sentence
from src.search.search_service import SearchService

FULL_KEY_DESCRIPTION = (
    "Тип: Строка Ключ регламентного задания. Два регламентных задания с "
    "одинаковым значением ключа могут быть выполнены только последовательно."
)

# Документы индекса help1c_docs как есть (параметры вариантов опущены — строке
# списка они не нужны). Ни у одного нет поля syntax_ru: его нет в индексе.
INSERT_METHOD = {
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

COLUMNS_PROPERTY = {
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

VALUE_TABLE_CONSTRUCTOR = {
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


def members(kind, methods=(), properties=(), events=(), total=None):
    """Состав объекта ТаблицаЗначений с явным total."""
    items = list(methods), list(properties), list(events)
    if total is None:
        total = sum(len(s) for s in items)
    return member_list(
        "ТаблицаЗначений", kind, *items, total=total,
        tool_limit=MEMBERS_LIMIT_MAX,
    )


@pytest.mark.unit
def test_short_description_is_left_intact():
    assert truncate_at_sentence("Добавляет строку.", 200) == "Добавляет строку."


@pytest.mark.unit
def test_truncation_does_not_break_sentence_midway():
    """Показанный текст всегда заканчивается целой фразой.

    Именно это защищает от инверсии смысла: лучше показать меньше фраз,
    чем половину фразы.
    """
    result = truncate_at_sentence(FULL_KEY_DESCRIPTION, 60)

    assert "могут" not in result or "последовательно" in result, (
        f"Фраза оборвана посередине: {result!r}"
    )
    assert result.startswith("Тип: Строка Ключ регламентного задания.")


@pytest.mark.unit
def test_truncation_is_marked():
    """Укороченный текст помечен, чтобы не выглядел полным."""
    result = truncate_at_sentence(FULL_KEY_DESCRIPTION, 60)
    assert result.endswith("…"), result


@pytest.mark.unit
def test_scheduled_job_key_fits_completely():
    """Тот самый случай: 135 знаков влезают в бюджет превью."""
    assert truncate_at_sentence(FULL_KEY_DESCRIPTION, 200) == FULL_KEY_DESCRIPTION


@pytest.mark.unit
def test_every_method_in_member_list_carries_call_line():
    """Состав объекта обязан отвечать на вопрос «как вызывать», а не только «что».

    Прежний форматтер читал удалённое поле syntax_ru, и живой ответ состоял из
    имени и описания: «Вставить (Insert)» — по такой строке агент не напишет
    ни скобок, ни имени объекта.
    """
    text = members("methods", methods=[INSERT_METHOD])

    assert "ТаблицаЗначений.Вставить(<Индекс>)" in text, text
    assert "функция" in text, "вид элемента не назван: " + text


@pytest.mark.unit
def test_constructor_in_member_list_shows_new():
    """members="constructors" у ТаблицаЗначений давал голое «По умолчанию».

    Из такого ответа никак не следует, что вызов пишется как
    «Новый ТаблицаЗначений» — а это единственное, ради чего конструктор
    спрашивают.
    """
    text = members("constructors", methods=[VALUE_TABLE_CONSTRUCTOR])

    assert "Новый ТаблицаЗначений" in text, text
    assert "Конструкторы (1)" in text
    assert "Методы" not in text, "конструктор — не метод: " + text


@pytest.mark.unit
def test_property_in_member_list_carries_access():
    """У свойства строка вызова — обращение через точку, без скобок."""
    text = members("properties", properties=[COLUMNS_PROPERTY])

    assert "ТаблицаЗначений.Колонки" in text
    assert "свойство" in text


@pytest.mark.unit
def test_member_list_is_not_truncated_silently():
    """Все переданные элементы попадают в вывод.

    Раньше форматтер жёстко обрезал на 20 методах, игнорируя limit вызова.
    """
    methods = [
        dict(INSERT_METHOD, name_ru=f"Метод{i:02d}",
             full_path=f"ТаблицаЗначений.Метод{i:02d}",
             call_primary=f"ТаблицаЗначений.Метод{i:02d}()")
        for i in range(46)
    ]

    text = members("methods", methods=methods, total=46)

    missing = [m["full_path"] for m in methods if m["full_path"] not in text]
    assert not missing, f"Не попали в вывод: {missing}"


@pytest.mark.unit
def test_states_when_not_everything_is_shown():
    """Если в индексе элементов больше, чем показано — это сказано прямо."""
    methods = [
        dict(INSERT_METHOD, name_ru=f"Метод{i:02d}",
             full_path=f"ТаблицаЗначений.Метод{i:02d}")
        for i in range(20)
    ]

    text = members("methods", methods=methods, total=46)

    assert "Показано 20 из 46" in text, (
        f"Нет пометки о неполноте выдачи:\n{text[:300]}"
    )


@pytest.mark.unit
def test_hint_about_fetching_the_rest_promises_nothing_impossible():
    """Совет обязан быть выполнимым: смещения у инструмента нет.

    «Повторите вызов с limit=N за остальными» — обещание, которого инструмент
    не выполняет: повтор вернёт те же первые N элементов. Годится только
    «за один вызов не более N» либо «полный список — вот такой вызов».
    """
    methods = [
        dict(INSERT_METHOD, full_path=f"ТаблицаЗначений.Метод{i:02d}") for i in range(5)
    ]

    text = members("methods", methods=methods, total=46)

    assert "за остальными" not in text, text
    assert 'list_1c_object_members(object="ТаблицаЗначений", members="methods", ' \
           'limit=46)' in text, text


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_total_is_real_when_limit_truncates():
    """total отражает число элементов в индексе, а не размер вернувшегося куска."""
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        result = await service.get_object_members_list("ТабличныйДокумент", "methods", limit=5)

        assert len(result["methods"]) == 5
        assert result["total"] > 5, (
            f"total={result['total']} повторяет размер куска вместо числа в индексе"
        )
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_existing_object_without_requested_kind_is_not_reported_missing():
    """total=0 при members="events" у ТаблицаЗначений — но объект есть.

    Разграничение "объекта нет" от "объект есть, но не того вида" делает
    get_object_members_list через отдельный ключ object_exists — раньше оба
    случая одинаково звучали как "объект не найден", и агент слышал это про
    объект, который тут же значился в списке "похожих" на самого себя.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        result = await service.get_object_members_list("ТаблицаЗначений", "events", limit=10)

        assert result["total"] == 0
        assert result.get("object_exists") is True, (
            "ТаблицаЗначений существует, даже если событий у неё нет"
        )
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_nonexistent_object_is_really_not_found():
    """Настоящее отсутствие объекта по-прежнему отличимо от «нет элементов
    этого вида» — object_exists=False только тогда, когда объекта нет вовсе.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        result = await service.get_object_members_list(
            "НесуществующийОбъект123", "all", limit=10
        )

        assert result["total"] == 0
        assert result.get("object_exists") is False
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_object_without_real_members_does_not_catch_itself_on_all():
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
        result = await service.get_object_members_list("JSON", "all", limit=10)

        assert result["total"] == 0, (
            f"Документ самого объекта JSON попал в выборку: total={result['total']}"
        )
        assert result.get("object_exists") is True, "JSON как объект в справке есть"
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_all_counter_equals_sum_by_kinds_without_extra_document():
    """total для all обязан равняться сумме total по methods+properties+events,
    без лишней единицы за документ-описание самого объекта.

    Раньше у ТаблицаЗначений all выдавал 23 при 22 настоящих членах.
    """
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)

        all_members = await service.get_object_members_list("ТаблицаЗначений", "all", limit=1)
        methods = await service.get_object_members_list("ТаблицаЗначений", "methods", limit=1)
        properties = await service.get_object_members_list("ТаблицаЗначений", "properties", limit=1)
        events = await service.get_object_members_list("ТаблицаЗначений", "events", limit=1)

        expected = methods["total"] + properties["total"] + events["total"]
        assert all_members["total"] == expected, (
            f"all={all_members['total']}, сумма по видам={expected} — "
            "документ объекта снова считается членом"
        )
    finally:
        await es_client.disconnect()


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_methods_past_the_twentieth_are_visible():
    """Методы из хвоста алфавита доходят до вывода — и со строкой вызова."""
    assert await es_client.connect(), "Elasticsearch недоступен"
    try:
        service = SearchService(es_client)
        result = await service.get_object_members_list("ТабличныйДокумент", "methods", limit=100)

        text = member_list(
            "ТабличныйДокумент", "methods",
            result["methods"], result["properties"], result["events"],
            result["total"], MEMBERS_LIMIT_MAX,
        )

        for name in ("Прочитать", "Показать"):
            assert f"ТабличныйДокумент.{name}" in text, f"'{name}' потерян в выводе"
        assert "ТабличныйДокумент.Показать(" in text, (
            "строки вызова нет ни у одного метода: " + text[:400]
        )
    finally:
        await es_client.disconnect()

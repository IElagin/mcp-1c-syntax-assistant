"""Тесты карточки элемента.

Карточка — контракт: у неё фиксированный набор полей, и отсутствие данных
помечено явно. Молчаливый пропуск поля неотличим для агента от «данных нет»,
и он достраивает недостающее домыслом.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.handlers.element_card import (
    NOT_IN_HELP,
    render_element_card,
    render_object_card,
    candidate_list,
    list_line,
)

# Реальный документ индекса: сам объект ТаблицаЗначений. variants у документов
# объектов пусты всегда — конструкторы лежат отдельными документами.
VALUE_TABLE_OBJECT = {
    "name": "ТаблицаЗначений", "name_ru": "ТаблицаЗначений",
    "type": "object", "element_kind": "объект",
    "object": "ТаблицаЗначений", "object_ru": "ТаблицаЗначений",
    "full_path": "ТаблицаЗначений", "call_primary": "",
    "variants": [], "availability": ["сервер"], "version_from": "8.0",
    "description": "Таблица значений.", "examples": [],
}

FIND_ROWS_METHOD = {
    "name": "НайтиСтроки (FindRows)",
    "name_ru": "НайтиСтроки",
    "name_en": "FindRows",
    "type": "object_function",
    "element_kind": "функция",
    "object": "ТаблицаЗначений",
    "object_ru": "ТаблицаЗначений",
    "full_path": "ТаблицаЗначений.НайтиСтроки",
    "call_primary": "ТаблицаЗначений.НайтиСтроки(<ПараметрыОтбора>)",
    "variants": [{
        "variant": "",
        "syntax": "НайтиСтроки(<ПараметрыОтбора>)",
        "call": "ТаблицаЗначений.НайтиСтроки(<ПараметрыОтбора>)",
        "parameters": [{
            "name": "ПараметрыОтбора", "type": "Структура", "required": True,
            "description": "Задает условия поиска.",
        }],
        "return_type": "Массив",
        "return_description": "Массив строк таблицы значений.",
    }],
    "availability": ["сервер", "толстый клиент", "внешнее соединение"],
    "version_from": "8.0",
    "description": "Осуществляет поиск строк таблицы значений.",
    "note": "Метод эффективно использовать для выборки неуникальных значений.",
    "examples": [],
}

DELETE_TWO_VARIANTS = {
    "name": "Удалить (Delete)",
    "name_ru": "Удалить",
    "type": "object_procedure",
    "element_kind": "процедура",
    "object": "ДанныеФормыКоллекция",
    "object_ru": "ДанныеФормыКоллекция",
    "full_path": "ДанныеФормыКоллекция.Удалить",
    "call_primary": "ДанныеФормыКоллекция.Удалить(<Индекс>)",
    "variants": [
        {"variant": "По индексу", "syntax": "Удалить(<Индекс>)",
         "call": "ДанныеФормыКоллекция.Удалить(<Индекс>)",
         "parameters": [{"name": "Индекс", "type": "Число", "required": True,
                         "description": "Индекс элемента в коллекции."}],
         "return_type": "", "return_description": ""},
        {"variant": "По элементу", "syntax": "Удалить(<Элемент>)",
         "call": "ДанныеФормыКоллекция.Удалить(<Элемент>)",
         "parameters": [{"name": "Элемент", "type": "ДанныеФормыЭлементКоллекции",
                         "required": True, "description": "Удаляемый элемент."}],
         "return_type": "", "return_description": ""},
    ],
    "availability": ["тонкий клиент", "сервер"],
    "version_from": "8.2",
    "description": "Удаляет элемент из коллекции.",
    "note": "",
    "examples": [],
}

COLUMNS_PROPERTY = {
    "name": "Колонки (Columns)",
    "name_ru": "Колонки",
    "type": "object_property",
    "element_kind": "свойство",
    "object": "ТаблицаЗначений",
    "object_ru": "ТаблицаЗначений",
    "full_path": "ТаблицаЗначений.Колонки",
    "call_primary": "ТаблицаЗначений.Колонки",
    "variants": [],
    "value_type": "КоллекцияКолонокТаблицыЗначений",
    "usage": "только чтение",
    "availability": ["сервер", "толстый клиент"],
    "version_from": "8.0",
    "description": "Содержит коллекцию колонок таблицы значений.",
    "examples": [],
}

# Реальный документ индекса (help1c_docs): Массив.По количеству элементов.
# Единственный вариант вызова, но с непустым именем варианта — проверяет, что
# карточка конструктора не путается с обобщённой веткой elif kind в _heading.
ARRAY_CONSTRUCTOR_BY_COUNT = {
    "name": "По количеству элементов",
    "name_ru": "По количеству элементов",
    "type": "object_constructor",
    "element_kind": "конструктор",
    "object": "Массив",
    "object_ru": "Массив",
    "full_path": "Массив.По количеству элементов",
    "call_primary": "Новый Массив(<КоличествоЭлементов1>,...,<КоличествоЭлементовN>)",
    "variants": [{
        "variant": "По количеству элементов",
        "syntax": "Новый Массив(<КоличествоЭлементов1>,...,<КоличествоЭлементовN>)",
        "call": "Новый Массив(<КоличествоЭлементов1>,...,<КоличествоЭлементовN>)",
        "parameters": [{
            "name": "КоличествоЭлементовN", "type": "Число", "required": False,
            "description": "Каждый параметр определяет количество элементов "
                           "массива в соответствующем измерении.",
        }],
        "return_type": "", "return_description": "",
    }],
    "availability": [],
    "version_from": "8.0",
    "description": "Создает массив из указанного количества элементов.",
    "note": "",
    "examples": ["Массив2 = Новый Массив(10,2,4);"],
}

# Реальный документ индекса: глобальное событие ПередНачаломРаботыСистемы
# (type=global_event). Это единственный случай, где element_kind="событие"
# реально ведёт себя иначе, чем "функция"/"процедура" — только у типа,
# начинающегося с "global", _heading добавляет «глобального контекста».
# Параметр несёт required=None — так размечено в самой справке.
BEFORE_START_EVENT = {
    "name": "ПередНачаломРаботыСистемы (BeforeStart)",
    "name_ru": "ПередНачаломРаботыСистемы",
    "name_en": "BeforeStart",
    "type": "global_event",
    "element_kind": "событие",
    "object": "Global context",
    "object_ru": "Глобальный контекст",
    "full_path": "ПередНачаломРаботыСистемы",
    "call_primary": "ПередНачаломРаботыСистемы(<Отказ>)",
    "variants": [{
        "variant": "",
        "syntax": "ПередНачаломРаботыСистемы(<Отказ>)",
        "call": "ПередНачаломРаботыСистемы(<Отказ>)",
        "parameters": [{
            "name": "Отказ", "type": "Булево", "required": None,
            "description": "Признак отказа от запуска программы.",
        }],
        "return_type": "", "return_description": "",
    }],
    "availability": ["тонкий клиент", "веб-клиент", "сервер", "толстый клиент", "внешнее соединение"],
    "version_from": "8.2",
    "description": "Возникает при старте 1С:Предприятия в режиме приложения "
                   "до открытия главного окна.",
    "note": "",
    "examples": [],
}


@pytest.mark.unit
def test_method_card_carries_call_params_and_return():
    text = render_element_card(FIND_ROWS_METHOD)

    assert "ТаблицаЗначений.НайтиСтроки" in text
    assert "Вызов: ТаблицаЗначений.НайтиСтроки(<ПараметрыОтбора>)" in text
    assert "ПараметрыОтбора" in text and "Структура" in text and "обязательный" in text
    assert "Возвращает: Массив" in text
    assert "сервер" in text
    assert "8.0" in text


@pytest.mark.unit
def test_card_prints_both_variants():
    """Второй способ вызова обязан быть виден: иначе агент о нём не узнает."""
    text = render_element_card(DELETE_TWO_VARIANTS)

    assert "По индексу" in text
    assert "По элементу" in text
    assert "Удалить(<Индекс>)" in text
    assert "Удалить(<Элемент>)" in text


@pytest.mark.unit
def test_procedure_states_it_returns_nothing():
    text = render_element_card(DELETE_TWO_VARIANTS)
    assert "нет (процедура)" in text


@pytest.mark.unit
def test_variant_description_is_shown_under_its_own_variant():
    """«Описание варианта метода:» относится к варианту, а не к элементу.

    Раньше это поле нигде не читалось: у ОповеститьОбИзменении (2 варианта,
    у каждого своё описание варианта и нет общего «Описание:») карточка
    печатала «Описание: в справке отсутствует», хотя оба текста лежали в
    variants[].description. Слить их в одну строку Documentation.description
    нельзя — у двух вариантов разные тексты, и склейка воспроизвела бы ту же
    путаницу, которую задача 1 убрала при разборе.
    """
    doc = dict(DELETE_TWO_VARIANTS)
    doc["variants"] = [
        dict(doc["variants"][0], description="Первый вариант удаляет по индексу."),
        dict(doc["variants"][1], description="Второй вариант удаляет по элементу."),
    ]

    text = render_element_card(doc)

    assert "Описание варианта: Первый вариант удаляет по индексу." in text
    assert "Описание варианта: Второй вариант удаляет по элементу." in text
    # Оба текста видны рядом со своим вариантом, а не слиты в одну строку.
    by_index_pos = text.index("По индексу")
    first_desc_pos = text.index("Первый вариант удаляет по индексу.")
    by_element_pos = text.index("По элементу")
    assert by_index_pos < first_desc_pos < by_element_pos


@pytest.mark.unit
def test_single_unnamed_variant_description_has_no_extra_heading():
    """Один безымянный вариант — без подзаголовка «Вариант …», но с описанием.

    _variant уже решает этот случай для «Вызов:»/«Параметры:» через
    with_name — «Описание варианта:» обязано вести себя так же, а не
    печатать пустой заголовок «Вариант «»» там, где справка имени не дала.
    """
    doc = dict(FIND_ROWS_METHOD)
    doc["variants"] = [dict(doc["variants"][0], description="Пояснение к единственному вызову.")]

    text = render_element_card(doc)

    assert "Описание варианта: Пояснение к единственному вызову." in text
    assert "Вариант «" not in text


@pytest.mark.unit
def test_empty_variants_do_not_hide_params_line():
    """variants=[] — не повод молчать про параметры.

    Спека §5 требует «Параметры: нет» в списке всегда печатаемых полей;
    молчание неотличимо от «параметров нет» и агент об этом не узнает.
    """
    doc = dict(FIND_ROWS_METHOD, variants=[])
    text = render_element_card(doc)
    assert "Параметры: нет" in text


@pytest.mark.unit
def test_constructor_card_names_and_calls_with_new():
    """Реальный конструктор из индекса (Массив.По количеству элементов).

    Утверждения специфичны для конструктора, а не для любого вызываемого
    элемента: заголовок обязан назвать элемент именно «конструктором» (у
    функции с теми же данными было бы «функция объекта Массив»), а строка
    вызова — начинаться со слова «Новый» (так конструкторы объектов и
    вызываются, в отличие от Объект.Метод(...) у функций/процедур).
    """
    text = render_element_card(ARRAY_CONSTRUCTOR_BY_COUNT)

    assert "Массив.По количеству элементов — конструктор объекта Массив" in text

    call_line = next(s for s in text.split("\n") if s.startswith("Вызов:"))
    call = call_line.removeprefix("Вызов:").strip()
    assert call.startswith("Новый"), \
        "конструктор вызывается через «Новый Тип(...)», а не Объект.Метод(...)"
    assert call == "Новый Массив(<КоличествоЭлементов1>,...,<КоличествоЭлементовN>)"

    assert "КоличествоЭлементовN" in text and "Число" in text
    assert "Параметры: нет" not in text
    assert "Пример:" in text


@pytest.mark.unit
def test_global_event_card_names_the_context():
    """Реальное глобальное событие из индекса (ПередНачаломРаботыСистемы).

    Единственное место, где element_kind="событие" отличается от
    "функция"/"процедура" в выводе — формулировка «глобального контекста»
    в _heading, включаемая только когда type начинается с "global". Если
    убрать "событие" из кортежа ("функция", "процедура", "событие"), заголовок
    станет «событие объекта Глобальный контекст» вместо «событие глобального
    контекста» — эта строгая проверка формулировки поймает такую регрессию.
    """
    text = render_element_card(BEFORE_START_EVENT)

    assert "ПередНачаломРаботыСистемы — событие глобального контекста" in text
    assert "Отказ" in text
    assert "обязательность в справке не указана" in text


@pytest.mark.unit
def test_missing_examples_stated_explicitly():
    """Примеры есть лишь у 6% элементов справки — молчать об этом нельзя."""
    text = render_element_card(FIND_ROWS_METHOD)
    assert "Примеров в справке нет" in text


@pytest.mark.unit
def test_missing_availability_stated_explicitly():
    doc = dict(FIND_ROWS_METHOD, availability=[])
    text = render_element_card(doc)
    assert "Доступность: в справке не указана" in text


@pytest.mark.unit
def test_property_card_shows_access_type_and_mode():
    text = render_element_card(COLUMNS_PROPERTY)

    assert "Обращение: ТаблицаЗначений.Колонки" in text
    assert "Вызов:" not in text, "свойство не вызывают"
    assert "Тип значения: КоллекцияКолонокТаблицыЗначений" in text
    assert "Доступ: только чтение" in text


@pytest.mark.unit
def test_unknown_requiredness_is_not_passed_off_as_required():
    """required=None — справка молчит; выдавать это за «обязательный» нельзя."""
    doc = dict(FIND_ROWS_METHOD)
    doc["variants"] = [dict(doc["variants"][0])]
    doc["variants"][0]["parameters"] = [
        {"name": "Х", "type": "Строка", "required": None, "description": "Что-то."}
    ]

    text = render_element_card(doc)

    assert "обязательность в справке не указана" in text
    assert ", обязательный" not in text


@pytest.mark.unit
def test_list_line_is_single_line_and_carries_call():
    line = list_line(FIND_ROWS_METHOD)

    assert "\n" not in line
    assert "ТаблицаЗначений.НайтиСтроки" in line


@pytest.mark.unit
def test_list_line_reports_variants():
    line = list_line(DELETE_TWO_VARIANTS)
    assert "вариантов вызова: 2" in line


@pytest.mark.unit
def test_candidate_list_states_count_and_how_to_narrow():
    text = candidate_list("Количество", [FIND_ROWS_METHOD, COLUMNS_PROPERTY], total=275)

    assert "275" in text
    assert "get_1c_element" in text
    assert "Показано 2 из 275" in text
    assert "Массив" not in text.split("Кандидаты")[0], \
        "в шапке ответа не должно быть произвольно выбранного кандидата"


@pytest.mark.unit
def test_candidates_heading_promises_no_likelihood():
    """Заголовок обязан называть порядок, а не обещать ранжирование.

    «Наиболее вероятные» были заявкой без покрытия: окно набиралось
    фильтрующим запросом с равными оценками, а сортировка шла по алфавиту.
    """
    text = candidate_list("Количество", [FIND_ROWS_METHOD, COLUMNS_PROPERTY], total=275)

    assert "Наиболее вероятные" not in text
    assert "числом элементов в справке" in text


@pytest.mark.unit
def test_candidates_state_when_order_is_not_over_all_matches():
    """Если упорядочены не все совпадения — об этом сказано, а не умолчано."""
    text = candidate_list(
        "Количество", [FIND_ROWS_METHOD], total=900, full_order=False
    )

    assert "не по всем совпадениям" in text


@pytest.mark.unit
def test_object_card_does_not_print_member_lists():
    text = render_object_card(
        VALUE_TABLE_OBJECT, {"methods": 46, "properties": 5, "events": 0}, []
    )

    assert "46" in text and "list_1c_object_members" in text


@pytest.mark.unit
def test_object_card_names_constructors():
    """Конструкторы объекта лежат отдельными документами, и карточка их печатает.

    Раньше карточка читала variants самого объекта — а они пусты у всех 2 506
    документов объектов — и печатала «Конструкторы: в справке не указано».
    Про 307 объектов, конструкторы которых есть в индексе, это была неправда:
    у ТаблицаЗначений там лежит «Новый ТаблицаЗначений».
    """
    text = render_object_card(
        VALUE_TABLE_OBJECT, {"methods": 22, "properties": 2, "events": 0},
        ["Новый ТаблицаЗначений"],
    )

    assert "Конструкторы:" in text
    assert "Новый ТаблицаЗначений" in text
    assert NOT_IN_HELP not in text.split("Описание:")[0]


@pytest.mark.unit
def test_object_card_reports_no_constructors_only_after_checking():
    """Пустой список — «проверено, конструкторов нет»; None — «не проверялись».

    Разница не косметическая: утверждать «в справке не указано», не спросив
    индекс, — ровно тот дефект, ради которого написана вся ветка.
    """
    checked = render_object_card(VALUE_TABLE_OBJECT, {}, [])
    not_checked = render_object_card(VALUE_TABLE_OBJECT, {})

    assert f"Конструкторы: {NOT_IN_HELP}" in checked
    assert "Конструкторы: не проверялись" in not_checked


def _object_document(name: str, object_name: str) -> dict:
    """Документ объекта в том виде, в каком он ложится в индекс.

    Путь собирает боевой код — Documentation.build_call_strings() и
    _prepare_document индексатора. Фикстура с проставленным вручную full_path
    проверяла бы собственное эхо: регрессия в сборке пути прошла бы мимо теста,
    ради которого он написан.
    """
    from src.models.doc_models import Documentation, DocumentType
    from src.parsers.indexer import ElasticsearchIndexer

    doc = Documentation(id="", type=DocumentType.OBJECT, name=name,
                        object=object_name, element_kind="объект")
    doc.build_call_strings()
    return ElasticsearchIndexer(None)._prepare_document(doc)


# Пары (object, имя страницы) взяты из индекса как есть; ожидаемый ключ — тот,
# под которым в индексе действительно лежат члены этих объектов.
OBJECT_PATH_CASES = [
    # 2 286 объектов: object равен имени страницы, склейка удваивала имя.
    ("ТаблицаЗначений", "ТаблицаЗначений", "ТаблицаЗначений"),
    # 104 объекта: имя страницы — заполнитель, тип в object, склейка нужна.
    ("БазовыеВидыРасчета", "<Имя плана видов расчета>",
     "БазовыеВидыРасчета.<Имя плана видов расчета>"),
    # 16 объектов: хвост object повторяет начало имени страницы. Склейка
    # давала «…КубЗапись.<Имя внешнего источника>.<Имя внешнего источника>.
    # <Имя куба>» — такого значения object в индексе нет, и карточка вдобавок
    # печатала «свойств: 0» о двух свойствах, лежащих под неудвоенным ключом.
    ("ВнешнийИсточникДанныхКубЗапись.<Имя внешнего источника>",
     "<Имя внешнего источника>.<Имя куба>",
     "ВнешнийИсточникДанныхКубЗапись.<Имя внешнего источника>.<Имя куба>"),
]


@pytest.mark.unit
@pytest.mark.parametrize("object_name, name, key", OBJECT_PATH_CASES)
def test_object_card_hint_is_built_from_path_without_repeats(object_name, name, key):
    """Совет обязан быть исполнимым — то есть называть ключ индекса без повторов.

    Раньше full_path объекта собирался как object + "." + имя, и удвоенное имя
    текло в совет: list_1c_object_members(object="ТаблицаЗначений.ТаблицаЗначений")
    отвечал «объект в справке не найден».
    """
    doc = _object_document(name, object_name)

    text = render_object_card(doc, {"methods": 22}, [])

    assert doc["full_path"] == key, doc["full_path"]
    assert f'list_1c_object_members(object="{key}")' in text
    segments = key.split(".")
    repeats = [a for a, b in zip(segments, segments[1:]) if a == b]
    assert not repeats, f"сегмент повторён подряд: {repeats}"


@pytest.mark.unit
def test_card_without_members_prints_no_unusable_hint():
    """У 100 страниц справки заголовок разобран как объект, а членов нет.

    «Расширение формы клиентского приложения для документа.Ключ» не встречается
    ни в одном поле object индекса, и совет по нему отвечал «объект в справке не
    найден». Призыв к действию, который не сработает, хуже его отсутствия:
    поле остаётся на месте и прямо говорит, что перечислять нечего.
    """
    doc = _object_document("Ключ", "Расширение формы клиентского приложения для документа")

    text = render_object_card(doc, {"methods": 0, "properties": 0, "events": 0}, [])

    assert "Состав — методов: 0, свойств: 0, событий: 0." in text
    assert "list_1c_object_members(" not in text
    assert "запрашивать нечего" in text

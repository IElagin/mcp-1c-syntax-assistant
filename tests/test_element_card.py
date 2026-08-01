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
OBEKT_TABLITSA_ZNACHENIY = {
    "name": "ТаблицаЗначений", "name_ru": "ТаблицаЗначений",
    "type": "object", "element_kind": "объект",
    "object": "ТаблицаЗначений", "object_ru": "ТаблицаЗначений",
    "full_path": "ТаблицаЗначений", "call_primary": "",
    "variants": [], "availability": ["сервер"], "version_from": "8.0",
    "description": "Таблица значений.", "examples": [],
}

NAYTI_STROKI = {
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

UDALIT_DVA_VARIANTA = {
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

KOLONKI = {
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
MASSIV_PO_KOLICHESTVU_ELEMENTOV = {
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
PERED_NACHALOM_RABOTY_SISTEMY = {
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
def test_kartochka_metoda_neset_vyzov_parametry_i_vozvrat():
    text = render_element_card(NAYTI_STROKI)

    assert "ТаблицаЗначений.НайтиСтроки" in text
    assert "Вызов: ТаблицаЗначений.НайтиСтроки(<ПараметрыОтбора>)" in text
    assert "ПараметрыОтбора" in text and "Структура" in text and "обязательный" in text
    assert "Возвращает: Массив" in text
    assert "сервер" in text
    assert "8.0" in text


@pytest.mark.unit
def test_kartochka_pechataet_oba_varianta():
    """Второй способ вызова обязан быть виден: иначе агент о нём не узнает."""
    text = render_element_card(UDALIT_DVA_VARIANTA)

    assert "По индексу" in text
    assert "По элементу" in text
    assert "Удалить(<Индекс>)" in text
    assert "Удалить(<Элемент>)" in text


@pytest.mark.unit
def test_protsedura_govorit_chto_nichego_ne_vozvrashchaet():
    text = render_element_card(UDALIT_DVA_VARIANTA)
    assert "нет (процедура)" in text


@pytest.mark.unit
def test_pustye_varianty_ne_skryvayut_stroku_parametry():
    """variants=[] — не повод молчать про параметры.

    Спека §5 требует «Параметры: нет» в списке всегда печатаемых полей;
    молчание неотличимо от «параметров нет» и агент об этом не узнает.
    """
    doc = dict(NAYTI_STROKI, variants=[])
    text = render_element_card(doc)
    assert "Параметры: нет" in text


@pytest.mark.unit
def test_kartochka_konstruktora_nazyvaet_i_vyzyvaet_po_novomu():
    """Реальный конструктор из индекса (Массив.По количеству элементов).

    Утверждения специфичны для конструктора, а не для любого вызываемого
    элемента: заголовок обязан назвать элемент именно «конструктором» (у
    функции с теми же данными было бы «функция объекта Массив»), а строка
    вызова — начинаться со слова «Новый» (так конструкторы объектов и
    вызываются, в отличие от Объект.Метод(...) у функций/процедур).
    """
    text = render_element_card(MASSIV_PO_KOLICHESTVU_ELEMENTOV)

    assert "Массив.По количеству элементов — конструктор объекта Массив" in text

    stroka_vyzova = next(s for s in text.split("\n") if s.startswith("Вызов:"))
    vyzov = stroka_vyzova.removeprefix("Вызов:").strip()
    assert vyzov.startswith("Новый"), \
        "конструктор вызывается через «Новый Тип(...)», а не Объект.Метод(...)"
    assert vyzov == "Новый Массив(<КоличествоЭлементов1>,...,<КоличествоЭлементовN>)"

    assert "КоличествоЭлементовN" in text and "Число" in text
    assert "Параметры: нет" not in text
    assert "Пример:" in text


@pytest.mark.unit
def test_kartochka_globalnogo_sobytiya_nazyvaet_kontekst():
    """Реальное глобальное событие из индекса (ПередНачаломРаботыСистемы).

    Единственное место, где element_kind="событие" отличается от
    "функция"/"процедура" в выводе — формулировка «глобального контекста»
    в _heading, включаемая только когда type начинается с "global". Если
    убрать "событие" из кортежа ("функция", "процедура", "событие"), заголовок
    станет «событие объекта Глобальный контекст» вместо «событие глобального
    контекста» — эта строгая проверка формулировки поймает такую регрессию.
    """
    text = render_element_card(PERED_NACHALOM_RABOTY_SISTEMY)

    assert "ПередНачаломРаботыСистемы — событие глобального контекста" in text
    assert "Отказ" in text
    assert "обязательность в справке не указана" in text


@pytest.mark.unit
def test_otsutstvie_primerov_skazano_pryamo():
    """Примеры есть лишь у 6% элементов справки — молчать об этом нельзя."""
    text = render_element_card(NAYTI_STROKI)
    assert "Примеров в справке нет" in text


@pytest.mark.unit
def test_otsutstvie_dostupnosti_skazano_pryamo():
    doc = dict(NAYTI_STROKI, availability=[])
    text = render_element_card(doc)
    assert "Доступность: в справке не указана" in text


@pytest.mark.unit
def test_kartochka_svoystva_obrashchenie_tip_i_dostup():
    text = render_element_card(KOLONKI)

    assert "Обращение: ТаблицаЗначений.Колонки" in text
    assert "Вызов:" not in text, "свойство не вызывают"
    assert "Тип значения: КоллекцияКолонокТаблицыЗначений" in text
    assert "Доступ: только чтение" in text


@pytest.mark.unit
def test_neizvestnaya_obyazatelnost_ne_vydaetsya_za_obyazatelnost():
    """required=None — справка молчит; выдавать это за «обязательный» нельзя."""
    doc = dict(NAYTI_STROKI)
    doc["variants"] = [dict(doc["variants"][0])]
    doc["variants"][0]["parameters"] = [
        {"name": "Х", "type": "Строка", "required": None, "description": "Что-то."}
    ]

    text = render_element_card(doc)

    assert "обязательность в справке не указана" in text
    assert ", обязательный" not in text


@pytest.mark.unit
def test_stroka_spiska_odna_stroka_i_neset_vyzov():
    stroka = list_line(NAYTI_STROKI)

    assert "\n" not in stroka
    assert "ТаблицаЗначений.НайтиСтроки" in stroka


@pytest.mark.unit
def test_stroka_spiska_soobshchaet_o_variantah():
    stroka = list_line(UDALIT_DVA_VARIANTA)
    assert "вариантов вызова: 2" in stroka


@pytest.mark.unit
def test_spisok_kandidatov_nazyvaet_chislo_i_sposob_utochnit():
    text = candidate_list("Количество", [NAYTI_STROKI, KOLONKI], total=275)

    assert "275" in text
    assert "get_1c_element" in text
    assert "Показано 2 из 275" in text
    assert "Массив" not in text.split("Кандидаты")[0], \
        "в шапке ответа не должно быть произвольно выбранного кандидата"


@pytest.mark.unit
def test_zagolovok_kandidatov_ne_obeshchaet_veroyatnosti():
    """Заголовок обязан называть порядок, а не обещать ранжирование.

    «Наиболее вероятные» были заявкой без покрытия: окно набиралось
    фильтрующим запросом с равными оценками, а сортировка шла по алфавиту.
    """
    text = candidate_list("Количество", [NAYTI_STROKI, KOLONKI], total=275)

    assert "Наиболее вероятные" not in text
    assert "числом элементов в справке" in text


@pytest.mark.unit
def test_kandidaty_govoryat_kogda_poryadok_ne_po_vsem_sovpadeniyam():
    """Если упорядочены не все совпадения — об этом сказано, а не умолчано."""
    text = candidate_list(
        "Количество", [NAYTI_STROKI], total=900, full_order=False
    )

    assert "не по всем совпадениям" in text


@pytest.mark.unit
def test_kartochka_obekta_ne_pechataet_spiski_chlenov():
    text = render_object_card(
        OBEKT_TABLITSA_ZNACHENIY, {"methods": 46, "properties": 5, "events": 0}, []
    )

    assert "46" in text and "list_1c_object_members" in text


@pytest.mark.unit
def test_kartochka_obekta_nazyvaet_konstruktory():
    """Конструкторы объекта лежат отдельными документами, и карточка их печатает.

    Раньше карточка читала variants самого объекта — а они пусты у всех 2 506
    документов объектов — и печатала «Конструкторы: в справке не указано».
    Про 307 объектов, конструкторы которых есть в индексе, это была неправда:
    у ТаблицаЗначений там лежит «Новый ТаблицаЗначений».
    """
    text = render_object_card(
        OBEKT_TABLITSA_ZNACHENIY, {"methods": 22, "properties": 2, "events": 0},
        ["Новый ТаблицаЗначений"],
    )

    assert "Конструкторы:" in text
    assert "Новый ТаблицаЗначений" in text
    assert NOT_IN_HELP not in text.split("Описание:")[0]


@pytest.mark.unit
def test_kartochka_obekta_bez_konstruktorov_govorit_eto_tolko_posle_proverki():
    """Пустой список — «проверено, конструкторов нет»; None — «не проверялись».

    Разница не косметическая: утверждать «в справке не указано», не спросив
    индекс, — ровно тот дефект, ради которого написана вся ветка.
    """
    proveryali = render_object_card(OBEKT_TABLITSA_ZNACHENIY, {}, [])
    ne_proveryali = render_object_card(OBEKT_TABLITSA_ZNACHENIY, {})

    assert f"Конструкторы: {NOT_IN_HELP}" in proveryali
    assert "Конструкторы: не проверялись" in ne_proveryali


def _dokument_obekta(name: str, object_name: str) -> dict:
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
PARY_PUTEY_OBEKTOV = [
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
@pytest.mark.parametrize("object_name, name, klyuch", PARY_PUTEY_OBEKTOV)
def test_sovet_kartochki_obekta_sobran_iz_puti_bez_povtorov(object_name, name, klyuch):
    """Совет обязан быть исполнимым — то есть называть ключ индекса без повторов.

    Раньше full_path объекта собирался как object + "." + имя, и удвоенное имя
    текло в совет: list_1c_object_members(object="ТаблицаЗначений.ТаблицаЗначений")
    отвечал «объект в справке не найден».
    """
    doc = _dokument_obekta(name, object_name)

    text = render_object_card(doc, {"methods": 22}, [])

    assert doc["full_path"] == klyuch, doc["full_path"]
    assert f'list_1c_object_members(object="{klyuch}")' in text
    segmenty = klyuch.split(".")
    povtory = [a for a, b in zip(segmenty, segmenty[1:]) if a == b]
    assert not povtory, f"сегмент повторён подряд: {povtory}"


@pytest.mark.unit
def test_kartochka_bez_chlenov_ne_pechataet_neispolnimyy_sovet():
    """У 100 страниц справки заголовок разобран как объект, а членов нет.

    «Расширение формы клиентского приложения для документа.Ключ» не встречается
    ни в одном поле object индекса, и совет по нему отвечал «объект в справке не
    найден». Призыв к действию, который не сработает, хуже его отсутствия:
    поле остаётся на месте и прямо говорит, что перечислять нечего.
    """
    doc = _dokument_obekta("Ключ", "Расширение формы клиентского приложения для документа")

    text = render_object_card(doc, {"methods": 0, "properties": 0, "events": 0}, [])

    assert "Состав — методов: 0, свойств: 0, событий: 0." in text
    assert "list_1c_object_members(" not in text
    assert "запрашивать нечего" in text

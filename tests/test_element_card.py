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
    kartochka,
    kartochka_obekta,
    spisok_kandidatov,
    stroka_spiska,
)

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
# карточка конструктора не путается с обобщённой веткой elif vid в _zagolovok.
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

# Реальный документ индекса: СправочникОбъект.<Имя справочника>.ОбработкаЗаполнения —
# событие объекта (не глобальный контекст). Все три параметра несут
# required=None — так размечено в самой справке для событий этого рода.
SPRAVOCHNIK_OBRABOTKA_ZAPOLNENIYA = {
    "name": "ОбработкаЗаполнения (Filling)",
    "name_ru": "ОбработкаЗаполнения",
    "name_en": "Filling",
    "type": "object_event",
    "element_kind": "событие",
    "object": "СправочникОбъект.<Имя справочника>",
    "object_ru": "СправочникОбъект.<Имя справочника>",
    "full_path": "СправочникОбъект.<Имя справочника>.ОбработкаЗаполнения",
    "call_primary": "СправочникОбъект.<Имя справочника>.ОбработкаЗаполнения"
                    "(<ДанныеЗаполнения>, <ТекстЗаполнения>, <СтандартнаяОбработка>)",
    "variants": [{
        "variant": "",
        "syntax": "ОбработкаЗаполнения(<ДанныеЗаполнения>, <ТекстЗаполнения>, <СтандартнаяОбработка>)",
        "call": "СправочникОбъект.<Имя справочника>.ОбработкаЗаполнения"
                "(<ДанныеЗаполнения>, <ТекстЗаполнения>, <СтандартнаяОбработка>)",
        "parameters": [
            {"name": "ДанныеЗаполнения", "type": "Произвольный", "required": None,
             "description": "Значение, которое используется как основание для заполнения."},
            {"name": "ТекстЗаполнения", "type": "Строка, Неопределено", "required": None,
             "description": "Значение для реквизита Наименование или Код при вводе по строке."},
            {"name": "СтандартнаяОбработка", "type": "Булево", "required": None,
             "description": "Признак выполнения стандартной обработки события."},
        ],
        "return_type": "", "return_description": "",
    }],
    "availability": ["сервер", "толстый клиент", "внешнее соединение"],
    "version_from": "8.0",
    "description": "Возникает при вводе элемента справочника на основании, "
                   "а также при выполнении метода Заполнить.",
    "note": "При копировании данный обработчик не вызывается.",
    "examples": [],
}


@pytest.mark.unit
def test_kartochka_metoda_neset_vyzov_parametry_i_vozvrat():
    text = kartochka(NAYTI_STROKI)

    assert "ТаблицаЗначений.НайтиСтроки" in text
    assert "Вызов: ТаблицаЗначений.НайтиСтроки(<ПараметрыОтбора>)" in text
    assert "ПараметрыОтбора" in text and "Структура" in text and "обязательный" in text
    assert "Возвращает: Массив" in text
    assert "сервер" in text
    assert "8.0" in text


@pytest.mark.unit
def test_kartochka_pechataet_oba_varianta():
    """Второй способ вызова обязан быть виден: иначе агент о нём не узнает."""
    text = kartochka(UDALIT_DVA_VARIANTA)

    assert "По индексу" in text
    assert "По элементу" in text
    assert "Удалить(<Индекс>)" in text
    assert "Удалить(<Элемент>)" in text


@pytest.mark.unit
def test_protsedura_govorit_chto_nichego_ne_vozvrashchaet():
    text = kartochka(UDALIT_DVA_VARIANTA)
    assert "нет (процедура)" in text


@pytest.mark.unit
def test_pustye_varianty_ne_skryvayut_stroku_parametry():
    """variants=[] — не повод молчать про параметры.

    Спека §5 требует «Параметры: нет» в списке всегда печатаемых полей;
    молчание неотличимо от «параметров нет» и агент об этом не узнает.
    """
    doc = dict(NAYTI_STROKI, variants=[])
    text = kartochka(doc)
    assert "Параметры: нет" in text


@pytest.mark.unit
def test_kartochka_konstruktora_realnye_dannye():
    """Реальный конструктор из индекса (Массив.По количеству элементов):
    единственный вариант с непустым именем, обобщённая ветка elif vid в
    _zagolovok не должна путать конструктор с функцией/процедурой/событием."""
    text = kartochka(MASSIV_PO_KOLICHESTVU_ELEMENTOV)

    assert "Массив.По количеству элементов" in text
    assert "Новый Массив(<КоличествоЭлементов1>,...,<КоличествоЭлементовN>)" in text
    assert "КоличествоЭлементовN" in text and "Число" in text
    assert "Параметры: нет" not in text
    assert "Пример:" in text


@pytest.mark.unit
def test_kartochka_sobytiya_realnye_dannye():
    """Реальное событие объекта из индекса (СправочникОбъект.ОбработкаЗаполнения):
    три параметра, у всех required=None в самой справке — не должно
    выдаваться за обязательность, и «нет (процедура)» тут не к месту:
    событие — не процедура."""
    text = kartochka(SPRAVOCHNIK_OBRABOTKA_ZAPOLNENIYA)

    assert "СправочникОбъект.<Имя справочника>.ОбработкаЗаполнения" in text
    assert "ДанныеЗаполнения" in text
    assert "ТекстЗаполнения" in text
    assert "СтандартнаяОбработка" in text
    assert "обязательность в справке не указана" in text
    assert "нет (процедура)" not in text
    assert "Возвращает: в справке не указано" in text


@pytest.mark.unit
def test_otsutstvie_primerov_skazano_pryamo():
    """Примеры есть лишь у 6% элементов справки — молчать об этом нельзя."""
    text = kartochka(NAYTI_STROKI)
    assert "Примеров в справке нет" in text


@pytest.mark.unit
def test_otsutstvie_dostupnosti_skazano_pryamo():
    doc = dict(NAYTI_STROKI, availability=[])
    text = kartochka(doc)
    assert "Доступность: в справке не указана" in text


@pytest.mark.unit
def test_kartochka_svoystva_obrashchenie_tip_i_dostup():
    text = kartochka(KOLONKI)

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

    text = kartochka(doc)

    assert "обязательность в справке не указана" in text
    assert ", обязательный" not in text


@pytest.mark.unit
def test_stroka_spiska_odna_stroka_i_neset_vyzov():
    stroka = stroka_spiska(NAYTI_STROKI)

    assert "\n" not in stroka
    assert "ТаблицаЗначений.НайтиСтроки" in stroka


@pytest.mark.unit
def test_stroka_spiska_soobshchaet_o_variantah():
    stroka = stroka_spiska(UDALIT_DVA_VARIANTA)
    assert "вариантов вызова: 2" in stroka


@pytest.mark.unit
def test_spisok_kandidatov_nazyvaet_chislo_i_sposob_utochnit():
    text = spisok_kandidatov("Количество", [NAYTI_STROKI, KOLONKI], vsego=275)

    assert "275" in text
    assert "get_1c_element" in text
    assert "Показано 2 из 275" in text
    assert "Массив" not in text.split("Наиболее вероятные:")[0], \
        "в шапке ответа не должно быть произвольно выбранного кандидата"


@pytest.mark.unit
def test_kartochka_obekta_ne_pechataet_spiski_chlenov():
    obekt = {
        "name": "ТаблицаЗначений", "name_ru": "ТаблицаЗначений",
        "type": "object", "element_kind": "объект",
        "object": "ТаблицаЗначений", "object_ru": "ТаблицаЗначений",
        "full_path": "ТаблицаЗначений", "call_primary": "",
        "variants": [], "availability": ["сервер"], "version_from": "8.0",
        "description": "Таблица значений.", "examples": [],
    }

    text = kartochka_obekta(obekt, {"methods": 46, "properties": 5, "events": 0})

    assert "46" in text and "list_1c_object_members" in text

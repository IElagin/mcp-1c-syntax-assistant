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

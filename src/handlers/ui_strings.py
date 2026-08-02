"""Строки ответа сервера на языке пользователя.

Карточка — контракт: набор полей фиксирован, отсутствие данных помечается
явно. Значит переводить надо не только метки, но и формулировки отсутствия:
английская карточка с русским «в справке не указано» ровно так же неотличима
от «поле пропущено», как русская без него.
"""

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class UiStrings:
    """Все строки, которые сервер печатает пользователю, на одном языке.

    Шаблоны используют именованные подстановки: порядок слов в английском
    предложении не обязан совпадать с русским, а позиционный {} это бы
    навязал.
    """

    lang: str

    # Виды элементов. Ключи — значения element_kind, они выводятся из типа
    # документа и остаются русскими на обоих языках.
    element_kind_names: Dict[str, str]

    # Заголовок карточки
    heading_global: str          # «{kind} глобального контекста»
    heading_of_object: str       # «{kind} объекта {owner}»
    object_word: str             # «объект»

    # Метки вызова. Ключи те же — значения element_kind.
    call: str                    # «Вызов»
    call_property: str           # «Обращение»
    call_object: str             # «Конструкторы»

    # Параметры
    parameters: str              # «Параметры:»
    no_parameters: str           # «Параметры: нет»
    required: str                # «обязательный»
    optional: str                # «необязательный»
    requiredness_unknown: str    # «обязательность в справке не указана»

    # Возврат, доступность, версия
    returns: str                 # «Возвращает: {value}»
    returns_nothing: str         # «Возвращает: нет (процедура)»
    availability: str            # «Доступность: {items}»
    availability_unknown: str    # «Доступность: в справке не указана»
    available_since: str         # «Доступно с: {version}»

    # Тело карточки
    not_in_help: str             # «в справке не указано»
    description: str             # «Описание: {text}»
    description_missing: str     # «в справке отсутствует»
    note: str                    # «Примечание: {text}»
    example: str                 # «Пример:»
    no_examples: str             # «Примеров в справке нет.»
    value_type: str              # «Тип значения: {value}»
    access: str                  # «Доступ: {value}»
    variant_named: str           # «Вариант «{name}»»
    variant_count: str           # «Вариантов вызова: {count}»
    variant_count_short: str     # «(вариантов вызова: {count})»

    # «Описание варианта: …» — привязано к конкретному варианту вызова, а не
    # к элементу целиком (задача 1: у метода с несколькими вариантами
    # описания вариантов разные, и склейка в одно поле их бы стёрла).
    variant_description: str     # «Описание варианта: {text}»

    # Карточка объекта. not_checked — фрагмент, а не готовая фраза: он всегда
    # сочетается с меткой вызова (_call_label), как и not_in_help в соседней
    # ветке той же функции («{label}: не проверялись» / «{label}: {not_in_help}»).
    # Так рендер не должен помнить и заново не нарушить правило «render_object_card
    # зовут только для объектов» — label вычисляется одинаково во всех ветках.
    not_checked: str                # «не проверялись»
    composition: str               # «Состав — {parts}.»
    member_names_genitive: Dict[str, str]  # ключи methods / properties / events
    listing_hint: str              # «Перечень: list_1c_object_members(object="{key}")»
    nothing_to_list: str           # «Перечень: запрашивать нечего — …»

    # Списки и подсказки
    members_header: str          # «Состав объекта {obj}.»
    methods_word: str            # «Методы»
    constructors_word: str       # «Конструкторы»
    properties_word: str         # «Свойства»
    events_word: str             # «События»
    shown_of_total: str          # «Показано {shown} из {total}. Полный список: {call}.»
    shown_of_total_capped: str   # «Показано {shown} из {total}. За один вызов …»
    full_card_hint: str          # «Полная карточка: get_1c_element(name=…, object="{obj}")»

    # Омонимия
    ambiguous_header: str        # «Имя «{name}» найдено у {total} элементов — …»
    ambiguous_hint: str          # «Уточните объект: get_1c_element(…)»
    candidates_header: str       # «Кандидаты (сначала типы языка, …):»
    partial_order_note: str      # «(порядок построен не по всем совпадениям …)»


# Значения списаны дословно из src/handlers/element_card.py — вплоть до
# кавычек-ёлочек, тире и пробелов. Существующие тесты карточки проверяют эти
# формулировки как есть, и любое расхождение здесь их сломает.
RU_STRINGS = UiStrings(
    lang="ru",
    element_kind_names={
        "функция": "функция", "процедура": "процедура", "свойство": "свойство",
        "событие": "событие", "конструктор": "конструктор", "объект": "объект",
    },
    heading_global="{kind} глобального контекста",
    heading_of_object="{kind} объекта {owner}",
    object_word="объект",
    call="Вызов",
    call_property="Обращение",
    call_object="Конструкторы",
    parameters="Параметры:",
    no_parameters="Параметры: нет",
    required="обязательный",
    optional="необязательный",
    requiredness_unknown="обязательность в справке не указана",
    returns="Возвращает: {value}",
    returns_nothing="Возвращает: нет (процедура)",
    availability="Доступность: {items}",
    availability_unknown="Доступность: в справке не указана",
    available_since="Доступно с: {version}",
    not_in_help="в справке не указано",
    description="Описание: {text}",
    description_missing="в справке отсутствует",
    note="Примечание: {text}",
    example="Пример:",
    no_examples="Примеров в справке нет.",
    value_type="Тип значения: {value}",
    access="Доступ: {value}",
    variant_named="Вариант «{name}»",
    variant_count="Вариантов вызова: {count}",
    variant_count_short="(вариантов вызова: {count})",
    variant_description="Описание варианта: {text}",
    not_checked="не проверялись",
    composition="Состав — {parts}.",
    member_names_genitive={
        "methods": "методов", "properties": "свойств", "events": "событий",
    },
    listing_hint='Перечень: list_1c_object_members(object="{key}")',
    nothing_to_list=(
        'Перечень: запрашивать нечего — под именем «{key}» в справке '
        'нет ни одного метода, свойства или события.'
    ),
    members_header="Состав объекта {obj}.",
    methods_word="Методы",
    constructors_word="Конструкторы",
    properties_word="Свойства",
    events_word="События",
    shown_of_total="Показано {shown} из {total}. Полный список: {call}.",
    shown_of_total_capped=(
        "Показано {shown} из {total}. За один вызов можно получить "
        "не более {limit}: {call}."
    ),
    full_card_hint='Полная карточка: get_1c_element(name=…, object="{obj}")',
    ambiguous_header=(
        "Имя «{name}» найдено у {total} элементов — "
        "карточка не может быть выбрана однозначно."
    ),
    ambiguous_hint='Уточните объект: get_1c_element(name="{name}", object="<объект>")',
    candidates_header=(
        "Кандидаты (сначала типы языка, внутри — объекты с бо́льшим числом "
        "элементов в справке):"
    ),
    partial_order_note=(
        "(порядок построен не по всем совпадениям — их слишком много "
        "для одного запроса)"
    ),
)

# Английские формулировки отсутствия данных переведены по смыслу, а не
# буквально: «not stated in the reference» несёт ту же мысль, что «в справке
# не указано» — данных нет в источнике, а не в ответе.
EN_STRINGS = UiStrings(
    lang="en",
    element_kind_names={
        "функция": "function", "процедура": "procedure", "свойство": "property",
        "событие": "event", "конструктор": "constructor", "объект": "object",
    },
    heading_global="{kind} of the global context",
    heading_of_object="{kind} of {owner}",
    object_word="object",
    call="Call",
    # Не "Access" — это слово занято полем access ниже («Access: read only»),
    # и карточка свойства печатала бы «Access:» дважды с разным смыслом:
    # как к свойству обратиться в коде — и можно ли в него писать. Reference
    # называет первое, не пересекаясь со вторым.
    call_property="Reference",
    call_object="Constructors",
    parameters="Parameters:",
    no_parameters="Parameters: none",
    required="required",
    optional="optional",
    requiredness_unknown="requirement not stated in the reference",
    returns="Returns: {value}",
    returns_nothing="Returns: nothing (procedure)",
    availability="Availability: {items}",
    availability_unknown="Availability: not stated in the reference",
    available_since="Available since: {version}",
    not_in_help="not stated in the reference",
    description="Description: {text}",
    description_missing="absent from the reference",
    note="Note: {text}",
    example="Example:",
    no_examples="No examples in the reference.",
    value_type="Value type: {value}",
    access="Access: {value}",
    variant_named='Variant "{name}"',
    variant_count="Call variants: {count}",
    variant_count_short="(call variants: {count})",
    variant_description="Variant description: {text}",
    not_checked="not checked",
    composition="Members — {parts}.",
    member_names_genitive={
        "methods": "methods", "properties": "properties", "events": "events",
    },
    listing_hint='Full list: list_1c_object_members(object="{key}")',
    nothing_to_list=(
        'Full list: nothing to request — the reference has no method, property '
        'or event under the name "{key}".'
    ),
    members_header="Members of {obj}.",
    methods_word="Methods",
    constructors_word="Constructors",
    properties_word="Properties",
    events_word="Events",
    shown_of_total="Shown {shown} of {total}. Full list: {call}.",
    shown_of_total_capped=(
        "Shown {shown} of {total}. A single call returns at most {limit}: {call}."
    ),
    full_card_hint='Full card: get_1c_element(name=…, object="{obj}")',
    ambiguous_header=(
        'The name "{name}" belongs to {total} elements — a single card cannot '
        "be chosen unambiguously."
    ),
    ambiguous_hint='Specify the object: get_1c_element(name="{name}", object="<object>")',
    candidates_header=(
        "Candidates (language types first, then objects with more elements in "
        "the reference):"
    ),
    partial_order_note=(
        "(the order does not cover all matches — there are too many for one query)"
    ),
)


_STRINGS: Dict[str, UiStrings] = {"ru": RU_STRINGS, "en": EN_STRINGS}


def strings_for(lang: str) -> UiStrings:
    """Таблица строк по коду языка. Неизвестный язык — ошибка."""
    try:
        return _STRINGS[lang]
    except KeyError:
        raise ValueError(
            f"Неизвестный язык ответа: {lang!r}. Доступны: " + ", ".join(sorted(_STRINGS))
        ) from None

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
    # Строка конструктора с именем варианта. Собирается не в карточке, а в
    # search_service.constructor_lines — единственной функции сборки ответа,
    # которая долго оставалась вне этой таблицы, и потому печатала русское
    # «— вариант «…»» в английской карточке любого объекта с двумя и более
    # конструкторами.
    constructor_variant: str       # «{call} — вариант «{name}»»
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

    # Сообщения обработчиков mcp_handlers.py: карточка отвечает "что вызывать",
    # а эти строки — "почему карточки нет". Английский агент, получивший здесь
    # русский текст, не может прочитать ни причину, ни совет, который из неё
    # следует — ровно тот же дефект, что решает вся эта таблица для карточки.

    # find_1c_help вернул пусто (_why_empty)
    nothing_found: str            # «По запросу «{query}» ничего не найдено.»
    object_exists_but_empty: str  # «Объект «{object}» в справке есть, но…»
    object_not_found: str         # «Объект «{object}» в справке не найден — выдачу обнулил фильтр…»
    object_name_differs_hint: str  # «Имя объекта в справке может отличаться…»
    kind_filter_hint: str         # «Поиск был ограничен видом kind="{kind}"…»
    no_filters_hint: str          # «Ни фильтра по объекту, ни фильтра по виду не было…»

    # Фрагмент, а не готовая фраза: вставляется вместо пустого списка похожих
    # объектов в трёх местах (_why_empty, get_1c_element, list_1c_object_members).
    no_similar_objects: str       # «подходящих не найдено»

    # get_1c_element: элемент искали у объекта, которого в справке нет
    object_missing_for_element: str  # «Объект «{object}» в справке не найден, поэтому элемент…»

    # get_1c_element: у элемента нет варианта с таким именем
    variant_not_found: str        # «Варианта «{variant}» у элемента «{name}» нет…»
    single_variant_no_name: str   # «вариант единственный и без имени»

    # get_1c_element: точного совпадения по имени нет вообще
    element_not_found: str        # «Элемент с точным именем «{name}» в справке не найден.»
    similar_by_name: str          # «Похожие по имени:»
    no_similar: str               # «Похожих по имени тоже нет — проверьте написание.»

    # list_1c_object_members: объект есть, но состав пуст
    no_members_at_all: str        # «…но ни методов, ни свойств, ни событий, ни конструкторов…»
    no_members_of_kind: str       # «…но {kind} у него нет. Попробуйте members="all"…»

    # list_1c_object_members: объекта в справке нет вовсе
    object_missing: str           # «Объект «{object}» в справке не найден. Похожие объекты: {similar}.»

    # find_1c_help: выдача непуста — шапка и хвост-совет успешного ответа.
    # Оставить их русскими значило бы напечатать half-английскую карточку:
    # список между ними уже переведён (list_line получает strings), а шапка и
    # совет — нет.
    found_count: str               # «Найдено {total} элементов по запросу «{query}».»
    full_card_hint_generic: str    # «Полная карточка: get_1c_element(name=…, object=…)»

    # Кросс-языковые запросы (mcp_handlers._language_mismatch). Молчаливое
    # «ничего не найдено» здесь — не честный отрицательный ответ, а введение
    # в заблуждение: элемент существует, просто не в этой книге и не под этим
    # именем. Обе строки печатаются только при lang="en" — при lang="ru" эта
    # проверка не срабатывает вовсе (русская книга несёт оба имени), так что
    # в RU_STRINGS они не нужны по смыслу, но живут в общей таблице как единый
    # контракт полей.
    english_index_missing: str        # «English reference is not indexed: …»
    russian_name_in_english_book: str  # «The English reference book contains no Russian names…»

    # Заголовки ошибок mcp_formatter.create_error_response. Ошибка на языке,
    # которого агент не читает, ничем не лучше ошибки без текста: он не может
    # решить следующий шаг.
    #
    # search_failed — деталь под этим заголовком, и она приходит из слоя поиска.
    # Пока её там держали литералом, обработчик подставлял переведённый
    # заголовок к непереведённой детали: «Search error: Ошибка выполнения
    # поиска».
    search_failed: str                 # «Ошибка выполнения поиска»
    search_error_title: str            # «Ошибка поиска»
    internal_search_error_title: str   # «Внутренняя ошибка поиска»
    card_error_title: str              # «Ошибка получения карточки»
    generic_error_title: str           # «Ошибка»
    members_internal_error_title: str  # «Ошибка получения состава»


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
    constructor_variant="{call} — вариант «{name}»",
    composition="Состав — {parts}.",
    member_names_genitive={
        "methods": "методов", "properties": "свойств", "events": "событий",
        "constructors": "конструкторов",
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
    nothing_found="По запросу «{query}» ничего не найдено.",
    object_exists_but_empty=(
        "Объект «{object}» в справке есть, но подходящих элементов у него не "
        'нашлось. Весь его состав: list_1c_object_members(object="{object}").'
    ),
    object_not_found=(
        "Объект «{object}» в справке не найден — выдачу обнулил фильтр по "
        "нему, а не отсутствие элемента. Похожие объекты: {similar}."
    ),
    object_name_differs_hint=(
        "Имя объекта в справке может отличаться от идентификатора в коде: "
        "например, менеджер фоновых заданий зовётся МенеджерФоновыхЗаданий."
    ),
    kind_filter_hint=(
        'Поиск был ограничен видом kind="{kind}" — повторите с kind="any", '
        "чтобы искать по всем видам элементов."
    ),
    no_filters_hint=(
        "Ни фильтра по объекту, ни фильтра по виду не было — совпадений нет "
        "во всей справке. Что можно сделать: проверить имя по-русски и "
        "по-английски; поискать по словам из описания; если известен "
        "объект — посмотреть его состав через list_1c_object_members."
    ),
    no_similar_objects="подходящих не найдено",
    object_missing_for_element=(
        "Объект «{object}» в справке не найден, поэтому элемент «{name}» у "
        "него искать негде. Похожие объекты: {similar}."
    ),
    variant_not_found=(
        'Варианта «{variant}» у элемента «{name}» нет. Доступные варианты: '
        "{variants}."
    ),
    single_variant_no_name="вариант единственный и без имени",
    element_not_found='Элемент с точным именем «{name}» в справке не найден.',
    similar_by_name="Похожие по имени:",
    no_similar="Похожих по имени тоже нет — проверьте написание.",
    no_members_at_all=(
        "Объект «{object}» в справке есть, но ни методов, ни свойств, ни "
        "событий, ни конструкторов у него не найдено."
    ),
    no_members_of_kind=(
        'Объект «{object}» в справке есть, но {kind} у него нет. Попробуйте '
        'members="all", чтобы увидеть весь состав.'
    ),
    object_missing="Объект «{object}» в справке не найден. Похожие объекты: {similar}.",
    # На практике не печатаются: _language_mismatch срабатывает только при
    # lang="en" (задача 6 — русская книга несёт оба имени, кросс-языковой
    # проблемы у неё нет). Значения — не заглушки, а полноценный русский
    # перевод: таблица строк не оставляет полей без перевода ни при каких
    # условиях, даже недостижимых сегодняшней логикой обработчиков.
    english_index_missing=(
        "Английская справка не проиндексирована: книга shcntx_root.hbk "
        "отсутствует в data/hbk-en. Скопируйте её из каталога bin установленной "
        "1С:Предприятие и перезапустите сервер, либо повторите вызов с "
        'lang="ru". См. docs/CONFIGURATION.md.'
    ),
    russian_name_in_english_book=(
        "Английская справка не содержит русских имён, поэтому такой запрос "
        'заведомо ничего не найдёт. Повторите вызов с lang="ru" либо укажите '
        "английское имя элемента."
    ),
    found_count="Найдено {total} элементов по запросу «{query}».",
    full_card_hint_generic="Полная карточка: get_1c_element(name=…, object=…)",
    search_failed="Ошибка выполнения поиска",
    search_error_title="Ошибка поиска",
    internal_search_error_title="Внутренняя ошибка поиска",
    card_error_title="Ошибка получения карточки",
    generic_error_title="Ошибка",
    members_internal_error_title="Ошибка получения состава",
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
    constructor_variant='{call} — variant "{name}"',
    composition="Members — {parts}.",
    member_names_genitive={
        "methods": "methods", "properties": "properties", "events": "events",
        "constructors": "constructors",
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
    nothing_found='Nothing found for the query "{query}".',
    object_exists_but_empty=(
        'The object "{object}" is in the reference, but no matching elements '
        'were found. Its full member list: list_1c_object_members(object="{object}").'
    ),
    object_not_found=(
        'The object "{object}" was not found in the reference — the object '
        "filter zeroed out the results, not an absence of a matching element. "
        "Similar objects: {similar}."
    ),
    # Пример сохранён по смыслу, а не сокращён до метки: агент, столкнувшийся
    # с этим же расхождением на английской книге, должен понять сам приём —
    # что справочное имя объекта и код-идентификатор не обязаны совпадать, —
    # а не только увидеть перевод русского примера.
    object_name_differs_hint=(
        "The object name in the reference may differ from the identifier used "
        "in code: for example, the manager of background jobs is called "
        "МенеджерФоновыхЗаданий in the reference, not ФоновыеЗадания."
    ),
    kind_filter_hint=(
        'The search was limited to kind="{kind}" — repeat with kind="any" to '
        "search across every kind of element."
    ),
    no_filters_hint=(
        "Neither an object filter nor a kind filter was set — there are no "
        "matches anywhere in the reference. What to try: check the name in "
        "both Russian and English; search by words from the description; if "
        "you know the object, look at its member list via list_1c_object_members."
    ),
    no_similar_objects="none found",
    object_missing_for_element=(
        'The object "{object}" was not found in the reference, so there is '
        'nowhere to look for the element "{name}". Similar objects: {similar}.'
    ),
    variant_not_found=(
        'There is no variant "{variant}" of the element "{name}". '
        "Available variants: {variants}."
    ),
    single_variant_no_name="there is only one variant, and it has no name",
    element_not_found='No element with the exact name "{name}" was found in the reference.',
    similar_by_name="Similar by name:",
    no_similar="There is nothing similar by name either — check the spelling.",
    no_members_at_all=(
        'The object "{object}" is in the reference, but no methods, '
        "properties, events or constructors were found for it."
    ),
    no_members_of_kind=(
        'The object "{object}" is in the reference, but it has no {kind}. '
        'Try members="all" to see the full member list.'
    ),
    object_missing=(
        'The object "{object}" was not found in the reference. Similar '
        "objects: {similar}."
    ),
    english_index_missing=(
        "English reference is not indexed: the book shcntx_root.hbk is missing "
        "from data/hbk-en. Copy it from the bin directory of your 1C:Enterprise "
        "installation and restart the server, or repeat the call with lang=\"ru\". "
        "See docs/CONFIGURATION.md."
    ),
    russian_name_in_english_book=(
        "The English reference book contains no Russian names, so this query "
        "cannot match anything. Repeat the call with lang=\"ru\", or pass the "
        "English name of the element."
    ),
    found_count='Found {total} elements for the query "{query}".',
    full_card_hint_generic="Full card: get_1c_element(name=…, object=…)",
    search_failed="The search request failed",
    search_error_title="Search error",
    internal_search_error_title="Internal search error",
    card_error_title="Error getting the card",
    generic_error_title="Error",
    members_internal_error_title="Error getting the member list",
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

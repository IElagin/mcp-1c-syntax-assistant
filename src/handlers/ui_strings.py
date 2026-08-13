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

    element_kind_names: Dict[str, str]
    book_names: Dict[str, str]

    heading_global: str
    heading_of_object: str
    object_word: str

    call: str
    call_property: str
    call_object: str

    parameters: str
    no_parameters: str
    required: str
    optional: str
    requiredness_unknown: str

    returns: str
    returns_nothing: str
    availability: str
    availability_unknown: str
    available_since: str

    not_in_help: str
    description: str
    description_missing: str
    note: str
    example: str
    no_examples: str
    value_type: str
    access: str
    variant_named: str
    variant_count: str
    variant_count_short: str

    variant_description: str

    not_checked: str
    constructor_variant: str
    composition: str
    member_names_genitive: Dict[str, str]
    listing_hint: str
    nothing_to_list: str

    members_header: str
    methods_word: str
    constructors_word: str
    properties_word: str
    events_word: str
    shown_of_total: str
    shown_of_total_capped: str
    full_card_hint: str

    ambiguous_header: str
    ambiguous_hint: str
    candidates_header: str
    partial_order_note: str

    article_heading: str
    article_book: str
    article_not_found: str
    article_ambiguous: str
    article_book_hint: str

    nothing_found: str
    object_exists_but_empty: str
    object_not_found: str
    object_name_differs_hint: str
    kind_filter_hint: str
    no_filters_hint: str
    articles_not_indexed: str

    no_similar_objects: str

    object_missing_for_element: str

    variant_not_found: str
    single_variant_no_name: str

    element_not_found: str
    element_is_an_article: str
    similar_by_name: str
    no_similar: str

    element_not_in_object: str
    found_elsewhere_header: str
    drop_object_hint: str

    no_members_at_all: str
    no_members_of_kind: str

    object_missing: str

    found_count: str
    full_card_hint_generic: str
    full_article_hint_generic: str

    english_index_missing: str
    russian_name_in_english_book: str

    search_failed: str
    search_error_title: str
    internal_search_error_title: str
    card_error_title: str
    generic_error_title: str
    members_internal_error_title: str


RU_STRINGS = UiStrings(
    lang="ru",
    element_kind_names={
        "функция": "функция", "процедура": "процедура", "свойство": "свойство",
        "событие": "событие", "конструктор": "конструктор", "объект": "объект",
        "статья": "статья",
    },
    book_names={
        "shlang": "язык 1С", "shquery": "язык запросов",
        "shclang": "общий синтаксис", "dcsui": "выражения СКД",
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
    article_heading="{name}",
    article_book="Книга: {book}",
    article_not_found="Статья «{name}» в справке не найдена.",
    article_ambiguous="Заголовок «{name}» встречается в справке {total} раз:",
    article_book_hint=(
        'Повторите вызов, указав книгу: get_1c_article(name="{name}", book="shquery")'
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
    articles_not_indexed=(
        "Статьи не проиндексированы: в индексе нет ни одной. Книги "
        "shlang_ru.hbk, shquery_ru.hbk, shclang_ru.hbk и dcsui_ru.hbk должны "
        "лежать в data/hbk, а индекс — строиться после того, как они там "
        "появились. Каких книг не хватает, показывает поле "
        "missing_article_books в /health. Это не значит, что статьи по "
        "запросу отсутствуют."
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
    element_is_an_article=(
        'Зато под этим заголовком есть статья: get_1c_article(name="{name}").'
    ),
    similar_by_name="Похожие по имени:",
    no_similar="Похожих по имени тоже нет — проверьте написание.",
    element_not_in_object=(
        "У объекта «{object}» нет элемента с точным именем «{name}» — "
        "выдачу обнулил фильтр по объекту, а не отсутствие элемента в справке."
    ),
    found_elsewhere_header=(
        "В справке это имя есть у {total} элементов (сначала типы языка, "
        "внутри — объекты с бо́льшим числом элементов в справке):"
    ),
    drop_object_hint=(
        'Уберите object, чтобы выбрать из них: get_1c_element(name="{name}"), '
        'либо посмотрите весь состав объекта: list_1c_object_members(object="{object}").'
    ),
    no_members_at_all=(
        "Объект «{object}» в справке есть, но ни методов, ни свойств, ни "
        "событий, ни конструкторов у него не найдено."
    ),
    no_members_of_kind=(
        'Объект «{object}» в справке есть, но {kind} у него нет. Попробуйте '
        'members="all", чтобы увидеть весь состав.'
    ),
    object_missing="Объект «{object}» в справке не найден. Похожие объекты: {similar}.",
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
    full_article_hint_generic='Полный текст статьи: get_1c_article(name="…")',
    search_failed="Ошибка выполнения поиска",
    search_error_title="Ошибка поиска",
    internal_search_error_title="Внутренняя ошибка поиска",
    card_error_title="Ошибка получения карточки",
    generic_error_title="Ошибка",
    members_internal_error_title="Ошибка получения состава",
)

EN_STRINGS = UiStrings(
    lang="en",
    element_kind_names={
        "функция": "function", "процедура": "procedure", "свойство": "property",
        "событие": "event", "конструктор": "constructor", "объект": "object",
        "статья": "article",
    },
    book_names={
        "shlang": "1C language", "shquery": "query language",
        "shclang": "common syntax", "dcsui": "DCS expressions",
    },
    heading_global="{kind} of the global context",
    heading_of_object="{kind} of {owner}",
    object_word="object",
    call="Call",
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
    article_heading="{name}",
    article_book="Book: {book}",
    article_not_found="Article “{name}” is not in the help.",
    article_ambiguous="The title “{name}” occurs {total} times in the help:",
    article_book_hint=(
        'Call again naming the book: get_1c_article(name="{name}", book="shquery")'
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
    articles_not_indexed=(
        "Articles are not indexed: the index holds none. shlang_root.hbk, "
        "shquery_root.hbk, shclang_root.hbk and dcsui_root.hbk must be in "
        "data/hbk-en, and the index must be built after they appear there. "
        "The missing_article_books_en field of /health names the books that "
        "are absent. This does not mean no article matches the query."
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
    element_is_an_article=(
        'There is an article under that title: get_1c_article(name="{name}").'
    ),
    similar_by_name="Similar by name:",
    no_similar="There is nothing similar by name either — check the spelling.",
    element_not_in_object=(
        'The object "{object}" has no element with the exact name "{name}" — '
        "the object filter zeroed out the results, not an absence of the "
        "element from the reference."
    ),
    found_elsewhere_header=(
        "The reference does have this name, on {total} elements (language "
        "types first, then objects with more elements in the reference):"
    ),
    drop_object_hint=(
        'Drop object to choose among them: get_1c_element(name="{name}"), or '
        'look at the full member list: list_1c_object_members(object="{object}").'
    ),
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
    full_article_hint_generic='Full article text: get_1c_article(name="…")',
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

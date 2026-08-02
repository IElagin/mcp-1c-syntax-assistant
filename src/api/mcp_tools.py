"""Описания MCP-инструментов и их JSON Schema.

Текст описания — единственное, по чему модель решает, какой инструмент вызвать,
поэтому в каждом описании сказано прямо: когда вызывать, когда не вызывать (с
указанием верного инструмента) и что придёт в ответе. Прежние пять
инструментов пересекались по смыслу: find_1c_help и search_by_context делали
одно, get_quick_reference дублировал get_syntax_info.

Схемы описаны словарями, а не через MCPToolParameter: параметр с enum,
границами и значением по умолчанию в той модели выразить нельзя.
"""

from src.core.config import settings

SEARCH_LIMIT_DEFAULT = 10
MEMBERS_LIMIT_DEFAULT = 100

# Язык ответа по умолчанию, когда инструмент вызван без lang. Читается из
# настройки, а не захардкожен: DEFAULT_HELP_LANG из окружения (задача 4)
# должен влиять и на схему, которую видит модель, и на то, что делает сервер,
# — иначе объявленное умолчание и реальное поведение могли бы разойтись.
DEFAULT_LANG = settings.default_help_lang

# Описание параметра lang — общее для всех трёх инструментов: language of the
# response значит именно это в любой из трёх схем.
LANG_DESCRIPTION = (
    "Язык ответа: ru — русская справка, en — английская. "
    "Это язык карточки, а не язык запроса: имя элемента "
    "можно передать на любом языке. Передавайте en, если "
    "пользователь работает по-английски."
)

# Потолок limit для find_1c_help. Вынесен в константу, чтобы совет "вызовите
# ещё раз с limit=N" (в mcp_handlers и в candidate_list) физически не мог
# предложить число больше того, что схема готова принять: раньше карточка
# советовала limit=total без оглядки на потолок, и для омонимов вроде
# «Количество» (275 совпадений) совет упирался в validation error схемы же.
SEARCH_LIMIT_MAX = 200

# Тот же потолок для состава объекта: совет «повторите с limit=N» обязан
# укладываться в схему list_1c_object_members.
MEMBERS_LIMIT_MAX = 1000

TOOLS = [
    {
        "name": "find_1c_help",
        "description": (
            "Поиск по справке 1С, когда точное имя элемента неизвестно. Ищет по "
            "русским и английским именам, описаниям и синтаксису. Возвращает список "
            "кандидатов по одной строке на элемент. Полную карточку не возвращает — "
            "за ней вызывайте get_1c_element с найденными именем и объектом. Если "
            "имя известно точно, вызывайте get_1c_element сразу. Если нужен весь "
            "состав объекта — list_1c_object_members. Параметром lang задаётся "
            "язык самого ответа, отдельно от языка запроса в query."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Имя элемента, фрагмент имени или описание задачи",
                },
                "kind": {
                    "type": "string",
                    "enum": ["any", "global", "method", "property", "event", "constructor"],
                    "default": "any",
                    "description": (
                        "Чем ограничить поиск: global — глобальные функции, процедуры "
                        "и события; method — методы объектов; property — свойства; "
                        "event — события объектов; constructor — конструкторы"
                    ),
                },
                "object": {
                    "type": "string",
                    "description": "Искать только у этого объекта справки",
                },
                "limit": {
                    "type": "integer",
                    "default": SEARCH_LIMIT_DEFAULT,
                    "minimum": 1,
                    "maximum": SEARCH_LIMIT_MAX,
                    "description": "Сколько кандидатов вернуть",
                },
                "lang": {
                    "type": "string",
                    "enum": ["ru", "en"],
                    "default": DEFAULT_LANG,
                    "description": LANG_DESCRIPTION,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_1c_element",
        "description": (
            "Полная карточка элемента справки 1С: строка вызова, все варианты вызова, "
            "параметры с типами и обязательностью, тип возвращаемого значения, "
            "доступность по контекстам исполнения (тонкий клиент, сервер и прочие), "
            "версия платформы, описание, примечание, пример. Требует точного имени. "
            "Если имя встречается у нескольких объектов, вернётся список кандидатов "
            "вместо карточки — повторите вызов, указав object. Для поиска по описанию "
            "используйте find_1c_help. Параметром lang задаётся язык самой карточки — "
            "имя элемента при этом может быть на любом языке."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Точное имя элемента, русское или английское",
                },
                "object": {
                    "type": "string",
                    "description": (
                        "Объект справки, которому принадлежит элемент — обязателен, "
                        "если имя неуникально"
                    ),
                },
                "variant": {
                    "type": "string",
                    "description": (
                        "Имя варианта вызова, если у элемента их несколько "
                        "(например «По индексу»)"
                    ),
                },
                "lang": {
                    "type": "string",
                    "enum": ["ru", "en"],
                    "default": DEFAULT_LANG,
                    "description": LANG_DESCRIPTION,
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_1c_object_members",
        "description": (
            "Состав объекта 1С: методы, свойства, события, конструкторы, по одной "
            "строке на элемент. Требует точного имени объекта из справки "
            "(МенеджерФоновыхЗаданий, а не идентификатор из кода ФоновыеЗадания). "
            "Если объект не найден, вернутся близкие по имени. За карточкой "
            "отдельного элемента — get_1c_element. Параметром lang задаётся язык "
            "перечня."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "object": {"type": "string", "description": "Имя объекта справки"},
                "members": {
                    "type": "string",
                    "enum": ["all", "methods", "properties", "events", "constructors"],
                    "default": "all",
                    "description": "Какие элементы перечислить",
                },
                "limit": {
                    "type": "integer",
                    "default": MEMBERS_LIMIT_DEFAULT,
                    "minimum": 1,
                    "maximum": MEMBERS_LIMIT_MAX,
                    "description": "Сколько элементов вернуть",
                },
                "lang": {
                    "type": "string",
                    "enum": ["ru", "en"],
                    "default": DEFAULT_LANG,
                    "description": LANG_DESCRIPTION,
                },
            },
            "required": ["object"],
            "additionalProperties": False,
        },
    },
]

# Отображение kind в поле type индекса. Глобальные события попадают только
# под global: в коде их пишут не как методы объекта.
KIND_TO_TYPE = {
    "any": [],
    "global": ["global_function", "global_procedure", "global_event"],
    "method": ["object_function", "object_procedure"],
    "property": ["object_property"],
    "event": ["object_event"],
    "constructor": ["object_constructor"],
}

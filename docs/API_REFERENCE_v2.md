# API Reference v2.0 - 1C Syntax Helper MCP Server

## Обзор

Этот документ содержит полное описание REST API для MCP сервера синтаксис-помощника 1С версии 2.0. API предоставляет функции поиска по документации 1С, управления индексом и мониторинга системы.

## Базовый URL

```
http://localhost:8000
```

## Аутентификация

В текущей версии аутентификация не требуется.

## Rate Limiting

API использует ограничение скорости запросов:
- **60 запросов в минуту** на IP-адрес
- **1000 запросов в час** на IP-адрес

При превышении лимита возвращается статус `429 Too Many Requests` с заголовком `Retry-After`.

## Обработка ошибок

### Коды ошибок

- `400 Bad Request` - Ошибка валидации данных
- `404 Not Found` - Ресурс не найден
- `429 Too Many Requests` - Превышен лимит запросов
- `500 Internal Server Error` - Внутренняя ошибка сервера
- `503 Service Unavailable` - Elasticsearch недоступен

### Формат ошибок

```json
{
  "error": "Error type",
  "message": "Detailed error description"
}
```

## Эндпоинты

### 1. Проверка здоровья системы

**GET** `/health`

Проверяет состояние системы, подключение к Elasticsearch и наличие индекса.

#### Ответ

```json
{
  "status": "healthy|unhealthy",
  "elasticsearch": true,
  "index_exists": true,
  "documents_count": 1234
}
```

#### Поля ответа

- `status` - Общий статус системы
- `elasticsearch` - Статус подключения к Elasticsearch
- `index_exists` - Существует ли индекс
- `documents_count` - Количество документов в индексе

---

### 2. Статус индекса

**GET** `/index/status`

Получает детальную информацию о состоянии индекса.

#### Ответ

```json
{
  "elasticsearch_connected": true,
  "index_exists": true,
  "documents_count": 1234,
  "index_name": "help1c_docs"
}
```

---

### 3. Переиндексация

**POST** `/index/rebuild`

Запускает переиндексацию документации из .hbk файла.

#### Ответ

```json
{
  "status": "success|error",
  "message": "Описание результата",
  "documents_indexed": 1234,
  "file_processed": "/path/to/file.hbk"
}
```

---

### 4. Получение доступных инструментов

**GET** `/tools` (то же самое отдаёт JSON-RPC метод `tools/list` на `/mcp`, см. ниже)

Возвращает список из трёх доступных MCP инструментов в виде JSON Schema
(источник истины — `src/api/mcp_tools.py`).

#### Ответ

```json
{
  "tools": [
    {
      "name": "find_1c_help",
      "description": "Поиск по справке 1С, когда точное имя элемента неизвестно. Ищет по русским и английским именам, описаниям и синтаксису. Возвращает список кандидатов по одной строке на элемент...",
      "inputSchema": {
        "type": "object",
        "properties": {
          "query": {"type": "string", "description": "Имя элемента, фрагмент имени или описание задачи"},
          "kind": {
            "type": "string",
            "enum": ["any", "global", "method", "property", "event", "constructor"],
            "default": "any"
          },
          "object": {"type": "string", "description": "Искать только у этого объекта справки"},
          "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 200}
        },
        "required": ["query"],
        "additionalProperties": false
      }
    }
  ]
}
```

---

### 5. Выполнение MCP запроса

**POST** `/mcp`

Эндпоинт реализует [MCP JSON-RPC 2.0](https://modelcontextprotocol.io/specification/2025-06-18/index)
(`src/api/routes/mcp.py`). Тело запроса — не произвольный `{"tool": ..., "arguments": ...}`,
а JSON-RPC конверт с методами `initialize`, `tools/list`, `tools/call`,
`notifications/initialized`.

#### Тело запроса (`tools/call`)

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "find_1c_help",
    "arguments": {
      "query": "СтрДлина",
      "limit": 10
    }
  }
}
```

#### Параметры

- `jsonrpc` (string, required) - всегда `"2.0"`
- `id` (any, required для запросов, ожидающих ответа)
- `method` (string, required) - `initialize` / `tools/list` / `tools/call` / `notifications/initialized`
- `params.name` (string, required для `tools/call`) - имя инструмента: `find_1c_help`, `get_1c_element` или `list_1c_object_members`
- `params.arguments` (object, required для `tools/call`) - аргументы инструмента

#### Валидация аргументов

Каждый инструмент валидирует `arguments` своей pydantic-моделью
(`Find1CHelpRequest`/`Get1CElementRequest`/`List1CObjectMembersRequest` в
`src/models/mcp_models.py`):

- `extra="forbid"` — незнакомое поле в `arguments` (например, устаревшее
  `object_name` вместо `object`) возвращает ошибку валидации, а не тихо
  отбрасывается
- `kind` (`find_1c_help`) и `members` (`list_1c_object_members`) — только
  значения из `enum` схемы, иное отклоняется
- `limit` — `find_1c_help`: от 1 до 200 (по умолчанию 10); `list_1c_object_members`:
  от 1 до 1000 (по умолчанию 100)

Ограничений на длину или состав символов `query`/`name`/`object` в текущем
контракте нет: класс `SearchRequest` с проверкой длины и запрещённых символов
(`src/core/validation.py`) существует в коде, но не используется ни одним из
трёх инструментов — это модель для прежнего REST-эндпоинта `search_1c_syntax`,
оставшаяся невостребованной.

#### Ответ

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Результат поиска по документации 1С"
      }
    ],
    "isError": false
  }
}
```

При ошибке `isError: true`, а текст ошибки — в `content`, а не только в отдельном
поле: агент не должен принимать пустой `content` за успешный пустой ответ.

#### Ошибки вызова против ошибок сервера

`isError` — про инструмент, который отработал и отказал (негодные аргументы,
нарушенные границы). Ошибки самого вызова возвращаются как ошибки JSON-RPC:

| Что не так | Код | Сообщение |
|---|---|---|
| Имя инструмента не из трёх | `-32602` | `Unknown tool: <имя>. Available tools: find_1c_help, get_1c_element, list_1c_object_members` |
| `arguments` не объект, `params` не объект | `-32602` | называет, что именно должно быть объектом |
| Метод протокола не поддержан | `-32601` | `Method not found: <метод>` |
| Тело не JSON | `-32700` | `Parse error` |
| `jsonrpc` не `"2.0"` | `-32600` | `Invalid Request` |

`-32603 Internal error` остаётся только за настоящими сбоями сервера. Раньше в
него сваливались и промахи вызывающего — неизвестное имя инструмента отдавало
`-32603` с трейсом pydantic, и агент читал это как поломку сервера вместо
исправимой опечатки в своём вызове.

---

### 6. Метрики системы

**GET** `/metrics`

Получение общих метрик системы и производительности.

#### Ответ

```json
{
  "metrics": {
    "counters": {
      "requests.total": 1500,
      "requests.search": 1200,
      "errors.total": 15
    },
    "gauges": {
      "system.cpu.usage_percent": 25.5,
      "system.memory.usage_percent": 68.2,
      "system.disk.free_gb": 45.8
    },
    "timers": {
      "request.duration": {
        "count": 1500,
        "avg": 0.156,
        "min": 0.012,
        "max": 2.345
      }
    }
  },
  "performance": {
    "total_requests": 1500,
    "successful_requests": 1485,
    "failed_requests": 15,
    "success_rate": 99.0,
    "avg_response_time": 0.156,
    "max_response_time": 2.345,
    "min_response_time": 0.012,
    "current_active_requests": 3
  },
  "rate_limiting": {
    "active_clients": 25,
    "total_requests_tracked": 5678
  }
}
```

---

### 7. Метрики клиента

**GET** `/metrics/{client_id}`

Получение метрик rate limiting для конкретного клиента.

#### Параметры пути

- `client_id` (string) - Идентификатор клиента (обычно IP-адрес)

#### Ответ

```json
{
  "client_id": "192.168.1.100",
  "rate_limiting": {
    "requests_per_minute": 15,
    "requests_per_hour": 234,
    "limit_per_minute": 60,
    "limit_per_hour": 1000,
    "remaining_minute": 45,
    "remaining_hour": 766
  }
}
```

## Инструменты MCP

Три инструмента, без пересечения ролей (полное описание, схемы и примеры
ответов — в `docs/MCP_TOOLS_SPECIFICATION.md`).

### find_1c_help

Поиск по справке 1С, когда точное имя элемента неизвестно.

#### Параметры

- `query` (string, required) - Поисковый запрос
- `kind` (string, optional) - Фильтр по виду элемента: `any` (по умолчанию), `global`, `method`, `property`, `event`, `constructor`
- `object` (string, optional) - Искать только у этого объекта справки
- `limit` (integer, optional) - Сколько кандидатов вернуть (1-200, по умолчанию: 10)

#### Пример использования

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "find_1c_help",
    "arguments": {
      "query": "СтрДлина строка",
      "limit": 5
    }
  }
}
```

### get_1c_element

Полная карточка элемента справки 1С: строка вызова, варианты вызова, параметры
с типами и обязательностью, тип возврата, доступность по контекстам
исполнения, версия, описание, примечание, пример. Требует точного имени; при
неуникальном имени вместо карточки возвращается список кандидатов.

#### Параметры

- `name` (string, required) - Точное имя элемента, русское или английское
- `object` (string, optional) - Объект справки — обязателен, если имя неуникально
- `variant` (string, optional) - Имя варианта вызова, если у элемента их несколько

### list_1c_object_members

Состав объекта 1С: методы, свойства, события, конструкторы.

#### Параметры

- `object` (string, required) - Имя объекта справки
- `members` (string, optional) - `all` (по умолчанию), `methods`, `properties`, `events`, `constructors`
- `limit` (integer, optional) - Сколько элементов вернуть (1-1000, по умолчанию: 100)

## Мониторинг и метрики

### Системные метрики

Сервер автоматически собирает следующие метрики:

- **CPU**: Использование процессора
- **Memory**: Использование памяти
- **Disk**: Свободное место на диске
- **Network**: Статистика сети (если доступно)

### Метрики производительности

- **Счетчики**: Общее количество запросов, успешных/неуспешных запросов
- **Таймеры**: Время выполнения запросов
- **Gauges**: Текущие значения системных ресурсов

### Rate Limiting

Каждый клиент отслеживается по IP-адресу с ограничениями:

- 60 запросов в минуту
- 1000 запросов в час

## Безопасность

### Валидация входных данных

Все входные данные проходят строгую валидацию:

- Проверка размера payload (максимум 1MB)
- Валидация типов данных
- Санитизация строк
- Проверка на path traversal

### Безопасные операции

- Все системные команды выполняются через безопасный subprocess
- Валидация имен файлов и путей
- Ограничение размера обрабатываемых файлов
- Таймауты для всех операций

## Конфигурация

### Переменные окружения

- `ELASTICSEARCH_HOST` - Хост Elasticsearch (по умолчанию: localhost)
- `ELASTICSEARCH_PORT` - Порт Elasticsearch (по умолчанию: 9200)
- `ELASTICSEARCH_INDEX` - Имя индекса (по умолчанию: help1c_docs)
- `SERVER_HOST` - Хост сервера (по умолчанию: 0.0.0.0)
- `SERVER_PORT` - Порт сервера (по умолчанию: 8000)
- `LOG_LEVEL` - Уровень логирования (по умолчанию: INFO)

### Лимиты по умолчанию

- Максимальный размер файла: 50MB
- Размер батча для индексации: 100 документов
- Таймаут Elasticsearch: 30 секунд
- Максимальное количество результатов за один вызов — своё у каждого
  инструмента (см. «Инструменты MCP» выше): `find_1c_help` — 200,
  `list_1c_object_members` — 1000. Общего для всех инструментов лимита
  «100» не существует — константа `MAX_SEARCH_RESULTS = 100`
  (`src/core/constants.py`) относится к неиспользуемой модели `SearchRequest`
  (`src/core/validation.py`), а не к текущему контракту.

## Примеры использования

### Поиск функций

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "find_1c_help",
      "arguments": {
        "query": "СтрДлина",
        "limit": 5
      }
    }
  }'
```

### Проверка статуса

```bash
curl http://localhost:8000/health
```

### Переиндексация

```bash
curl -X POST http://localhost:8000/index/rebuild
```

### Получение метрик

```bash
curl http://localhost:8000/metrics
```

## Changelog

### v2.0.0 (текущая версия)

- ✅ Добавлен rate limiting (60/мин, 1000/час)
- ✅ Улучшена валидация входных данных (pydantic модели)
- ✅ Добавлены метрики и мониторинг системы
- ✅ Реализован dependency injection
- ✅ Улучшена обработка ошибок (специфичные исключения)
- ✅ Добавлена безопасность subprocess операций
- ✅ Константы вынесены в отдельный модуль
- ✅ Обновлена документация API

### v1.0.0

- Базовая функциональность поиска
- Индексация .hbk файлов
- MCP протокол
- Интеграция с Elasticsearch

## Архитектурные улучшения

### Исправленные проблемы

1. **Небезопасный subprocess** → Безопасный модуль `src.core.utils.safe_subprocess_run`
2. **Отсутствие валидации** → Строгая валидация через `src.core.validation`
3. **Глобальные состояния** → Dependency injection через `src.core.dependency_injection`
4. **Магические числа** → Константы в `src.core.constants`
5. **Отсутствие rate limiting** → Модуль `src.core.rate_limiter`
6. **Улучшение обработки ошибок** → Специфичные исключения
7. **Добавление метрик** → Модуль `src.core.metrics`
8. **Улучшение типизации** → Строгая типизация во всех модулях
9. **Документация API** → Полная документация с примерами

### Производительность

- Асинхронная обработка запросов
- Batch индексация документов
- Кэширование подключений
- Мониторинг ресурсов системы
- Rate limiting для защиты от перегрузки

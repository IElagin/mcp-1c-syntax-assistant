# Подключение MCP-клиентов

Сервер отдаёт инструменты по HTTP: один эндпоинт `POST http://127.0.0.1:8000/mcp`,
конверт — JSON-RPC 2.0. Отдельный процесс на каждого клиента поднимать не нужно:
подключаются все к одному работающему серверу.

Перед настройкой клиента убедитесь, что сервер поднят и индекс построен:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

```json
{"status":"healthy","elasticsearch":true,"index_exists":true,
 "documents_count":23106,"indexing_status":"idle","indexing_active":false,
 "index_en_exists":true,"documents_count_en":23104,"version":"2.0.0"}
```

Пока `indexing_active` равно `true`, инструменты уже отвечают, но справка ещё
неполная. `index_en_exists`/`documents_count_en` — то же самое для английской
книги; она необязательна, так что оба поля равны `false`/`null`, пока эта
книга не положена рядом с русской и не проиндексирована.

## Проверка эндпоинта до настройки клиента

Если клиент не подключается, полезно знать, сервер виноват или конфигурация.
Три вызова ниже проверяют весь протокол.

Рукопожатие:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/mcp `
  -ContentType 'application/json' `
  -Body '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"1"}}}'
```

```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18",
 "capabilities":{"tools":{}},
 "serverInfo":{"name":"1c-syntax-helper-mcp","version":"2.0.0"}}}
```

Перечень инструментов:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/mcp `
  -ContentType 'application/json' `
  -Body '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
```

Вызов инструмента:

```powershell
$body = @{
  jsonrpc = '2.0'; id = 3; method = 'tools/call'
  params = @{ name = 'get_1c_element'; arguments = @{ name = 'Добавить'; object = 'Массив' } }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/mcp `
  -ContentType 'application/json; charset=utf-8' `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

Кириллицу передавайте байтами в UTF-8, как выше. Если отдать строку и не
указать `charset=utf-8`, консоль перекодирует её по своей кодовой странице и
сервер ответит ошибкой разбора вроде `'utf-8' codec can't decode byte 0xc4`.
Это ошибка отправителя, а не сервера.

Ответ приходит в поле `result` с признаком `isError`:

```json
{"jsonrpc":"2.0","id":3,"result":{
  "content":[{"type":"text","text":"Массив.Добавить — процедура объекта Массив\n…"}],
  "isError":false}}
```

Неизвестное имя инструмента — ошибка вызова, а не поломка сервера:

```json
{"jsonrpc":"2.0","id":4,"error":{"code":-32602,
 "message":"Unknown tool: nope. Available tools: find_1c_help, get_1c_element, list_1c_object_members"}}
```

Это тело приходит с HTTP-статусом **400**, а не 200. `Invoke-RestMethod` на 400
бросает исключение и тела не показывает — чтобы его увидеть, используйте
`Invoke-WebRequest` с `-SkipHttpErrorCheck` (PowerShell 7) или `curl`.

## VS Code

VS Code читает конфигурацию MCP из `.vscode/mcp.json` в корне рабочей области
(на всех проектах — из пользовательского `mcp.json`, команда
**MCP: Open User Configuration** в палитре).

```json
{
  "servers": {
    "1c-syntax": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

После сохранения VS Code предложит запустить сервер. Проверить состояние —
команда **MCP: List Servers** в палитре (`Ctrl+Shift+P`); в списке инструментов
чата должны появиться `find_1c_help`, `get_1c_element` и
`list_1c_object_members`.

## Claude Code

```powershell
claude mcp add --transport http 1c-syntax http://127.0.0.1:8000/mcp
```

По умолчанию сервер прописывается для текущего пользователя. Чтобы он
подключался у всей команды на этом проекте, добавьте `--scope project` — тогда
запись попадёт в файл `.mcp.json` в корне репозитория:

```json
{
  "mcpServers": {
    "1c-syntax": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

Проверить подключение:

```powershell
claude mcp list
```

## Любой другой MCP-клиент

Клиенту нужны три вещи:

| Что | Значение |
|---|---|
| Транспорт | HTTP |
| URL | `http://127.0.0.1:8000/mcp` |
| Аутентификация | нет |

Заголовки, кроме `Content-Type: application/json`, не требуются. Сессии сервер
не хранит: каждый запрос самодостаточен, `Mcp-Session-Id` не выдаётся и не
проверяется.

Клиенты, умеющие только stdio (например, Claude Desktop), подключаются через
мост stdio↔HTTP — отдельную утилиту, которая запускается как локальный процесс
и переправляет вызовы на этот URL. Сервер собственного stdio-режима не имеет.

### Что стоит знать о совместимости

Эндпоинт реализует JSON-RPC 2.0 поверх HTTP, но не весь транспорт Streamable
HTTP из спецификации MCP. Отличия, которые видны клиенту:

- `GET /mcp` открывает поток SSE, но шлёт в него служебные события
  (`{"type":"connection"}`, `{"type":"ping"}`), а не сообщения JSON-RPC.
  Клиент, который читает этот поток как канал сервер→клиент, ничего полезного
  оттуда не получит.
- Уведомление `notifications/initialized` получает в ответ `200` с телом
  `{"status":"ok"}` вместо `202` с пустым телом.

Инструменты при этом работают: `initialize`, `tools/list` и `tools/call` через
`POST /mcp` отвечают корректно — это и проверяют три вызова выше.

## Если не подключается

**Клиент не видит сервер.** Проверьте, что контейнеры подняты и порт слушается
именно на localhost:

```powershell
docker compose ps
```

```
NAME            STATUS                    PORTS
es-1c-helper    Up 28 hours (healthy)     127.0.0.1:9200->9200/tcp
mcp-1c-helper   Up 30 minutes (healthy)   127.0.0.1:8000->8000/tcp
```

Привязка к `127.0.0.1` намеренная. Если клиент работает на другой машине,
читайте [DEPLOYMENT.md](DEPLOYMENT.md) — там про безопасную публикацию наружу.

**Сервер отвечает 503.** Недоступен Elasticsearch. Проверьте:

```powershell
Invoke-RestMethod http://127.0.0.1:9200/_cluster/health
docker compose logs mcp-server --tail 50
```

**Инструменты есть, но ничего не находят.** Индекс пуст или ещё строится —
смотрите `documents_count` в `/health` и раздел о переиндексации в
[CONFIGURATION.md](CONFIGURATION.md).

**Агент зовёт инструмент и получает `-32602`.** Это ошибка вызова: неверное имя
инструмента или негодные аргументы. Текст ошибки называет доступные имена.
Схемы аргументов — в [MCP_TOOLS.md](MCP_TOOLS.md).

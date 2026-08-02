# mcp-1c-syntax-assistant

[![tests](https://github.com/<OWNER>/mcp-1c-syntax-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/<OWNER>/mcp-1c-syntax-assistant/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[Русская версия](README.ru.md)

MCP server that gives AI agents precise answers from the 1C:Enterprise syntax reference.

An agent asks for an element by name and gets back a fixed-shape card — call
string, parameters with types and requiredness, return type, execution
contexts, platform version, description, example. Missing data is stated
outright rather than silently omitted, because a skipped field is
indistinguishable from "no such data" and the model fills the gap by guessing.

Reference content is in Russian: it is parsed from the Russian 1C help book.
See [Language support](#language-support) for what is available in English.

## What an answer looks like

Real output of `get_1c_element(name="Добавить", object="Массив")`:

```
Массив.Добавить — процедура объекта Массив

Вызов: Массив.Добавить(<Значение>)
Параметры:
    Значение — Произвольный, необязательный
      Добавляемое значение. Если не указан, то будет добавлено значение типа Неопределено.

Возвращает: нет (процедура)
Доступность: тонкий клиент, веб-клиент, мобильный клиент, сервер, толстый клиент, внешнее соединение, мобильное приложение (клиент), мобильное приложение (сервер), мобильный автономный сервер
Доступно с: 8.0

Описание: Добавляет элемент в конец массива.
Примечание: При добавлении количество элементов массива увеличивается на 1.
Пример:
  Массив.Добавить("Первый");
  Массив.Добавить("Второй");
```

## Requirements

- Docker and Docker Compose v2
- 4 GB RAM free (Elasticsearch is configured for a 1 GB heap)
- The 1C syntax reference file `shcntx_ru.hbk`

> **The `.hbk` syntax reference file is not included.** It is proprietary and
> ships with your licensed 1C:Enterprise installation — copy it from there.
> Do not redistribute it.

On Windows the file lives next to the platform binaries:

```
C:\Program Files\1cv8\<version>\bin\shcntx_ru.hbk
```

`data/` is git-ignored, so the file never enters the repository by accident.
If you deploy the server for other people, they get the service — not the file.

## Quick start

Clone this repository, then, from its root:

```bash
# 1. Copy the reference book from your 1C installation into data/hbk/
#    Windows: C:\Program Files\1cv8\<version>\bin\shcntx_ru.hbk
cp /path/to/shcntx_ru.hbk data/hbk/

# 2. Start Elasticsearch and the MCP server
docker compose up -d

# 3. Watch the index fill up
curl http://localhost:8000/health
```

Indexing starts automatically on the first run and continues in the
background. `/health` reports its progress:

```json
{"status":"healthy","elasticsearch":true,"index_exists":true,
 "documents_count":23025,"indexing_status":"idle","indexing_active":false,
 "version":"1.0.0"}
```

The server is ready when `indexing_active` is `false` and `documents_count`
has stopped growing. Both containers bind to `127.0.0.1` only — see
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) before exposing anything to a network.

Next: point your editor at the server — [docs/CLIENT_SETUP.md](docs/CLIENT_SETUP.md).

## MCP tools

| Tool | Purpose |
|---|---|
| `find_1c_help` | Find candidates when the exact name is unknown — one line per element, no full card. |
| `get_1c_element` | Full card for an element whose exact name is known; a candidate list instead of a card when the name is ambiguous. |
| `list_1c_object_members` | Methods, properties, events and constructors of one object, one line each. |

Schemas, limits and the exact behaviour on ambiguous or missing names:
[docs/MCP_TOOLS.md](docs/MCP_TOOLS.md).

## Language support

Element names are searchable in both languages. `НайтиСтроки` and `FindRows`
both resolve to the same element, and so do `Добавить` and `Add` — the Russian
reference book carries both names in every element page title
(`<h1>НайтиСтроки (FindRows)</h1>`), and the indexer splits them into separate
`name_ru` and `name_en` fields. Of 20 134 element pages in the current index,
19 841 carry an English name.

**Object names are Russian only.** The 2 506 object pages carry no English name
in their titles, so `list_1c_object_members(object="ValueTable")` and
`get_1c_element(name="Add", object="Array")` both fail to resolve. Use
`ТаблицаЗначений` and `Массив`. The same applies to the 385 constructor pages.

Descriptions, parameters, examples and availability are Russian only, because
the Russian book contains them only in Russian.

Full English reference support is planned — see [Roadmap](#roadmap).

## Differences from the upstream project

Based on [Antonio1C/1c-syntax-helper-mcp](https://github.com/Antonio1C/1c-syntax-helper-mcp)
(MIT), which contributed the FastAPI service layout, `.hbk` extraction through
7-Zip and Elasticsearch indexing. What changed:

- **The element card is a contract, not free text.** A fixed set of fields is
  always printed, and absent data is labelled (`Доступность: в справке не
  указана`, `Примеров в справке нет`) instead of being dropped.
- **Three MCP tools instead of one**, each with an explicit JSON schema, so an
  agent picks a tool by purpose rather than by guessing arguments.
- **Disambiguation instead of a silent pick.** `Добавить` occurs on 197 pages;
  the server returns an ordered candidate list and asks for the object, rather
  than returning an arbitrary one of them as the answer.
- **Call variants, real parameter requiredness and property value types** are
  parsed out of the help HTML.
- **A reproducible search-quality measurement** — `scripts/eval_search.py`
  builds its ground truth from the index itself and reports hit rates.

Full attribution and the complete list of changes: [NOTICE](NOTICE).

## Roadmap

- English reference support from `shcntx_root.hbk`, so that descriptions,
  parameters and examples are available in English too — not just names.
- Reference for the 1C language, the query language and the DCS expression
  language (`shlang`, `shquery`, `shclang`). These books use a different page
  format and need a separate parser.

## License

MIT — see [LICENSE](LICENSE). Attribution of the upstream project and the list
of changes made here: [NOTICE](NOTICE). The upstream project is
[Antonio1C/1c-syntax-helper-mcp](https://github.com/Antonio1C/1c-syntax-helper-mcp).

The licence covers this source code only. It does not cover the 1C:Enterprise
syntax reference file, which is proprietary and is not part of this repository.

## Documentation

All four documents are in Russian.

- [docs/CLIENT_SETUP.md](docs/CLIENT_SETUP.md) — connecting VS Code, Claude Code
  and other MCP clients.
- [docs/MCP_TOOLS.md](docs/MCP_TOOLS.md) — tool schemas, limits, card format,
  behaviour on ambiguous and missing names.
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) — environment variables,
  reindexing, replacing the reference file.
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Windows Server and Linux ARM64,
  multi-architecture images, HTTP endpoints, exposing the service safely.

Contributing to the test suite: [tests/README.md](tests/README.md).

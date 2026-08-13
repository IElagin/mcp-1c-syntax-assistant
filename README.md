# mcp-1c-syntax-assistant

[![tests](https://github.com/IElagin/mcp-1c-syntax-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/IElagin/mcp-1c-syntax-assistant/actions/workflows/ci.yml)
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

No 7-Zip or other archiver needed — the server reads the `.hbk` container
itself.

> **The `.hbk` syntax reference file is not included.** It is proprietary and
> ships with your licensed 1C:Enterprise installation — copy it from there.
> Do not redistribute it.
>
> The repository does carry 25 pages out of the two books — 15 Russian and 10
> English — under `tests/fixtures/`, as samples for the parser tests.
> Synthetic markup checks a defect once it's understood; the real pages catch
> what nobody anticipated — unclosed tags, pseudo-tags like `<Value1>`, nested
> font wrappers, Cyrillic in attributes. Requiring the books themselves
> instead — tens of megabytes, present neither in CI nor in an outside
> reader's checkout — would leave those cases untested. The books as such are
> still not redistributed here.

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
 "documents_count":23491,"indexing_status":"idle","indexing_active":false,
 "index_en_exists":true,"documents_count_en":23104,
 "missing_article_books":[],"missing_article_books_en":[],"version":"2.3.2"}
```

The server is ready when `indexing_active` is `false` and `documents_count`
has stopped growing. `index_en_exists`/`documents_count_en` track the English
book the same way — it's optional, so both fields are `false`/`null` until the
English book is placed alongside the Russian one and indexed. Both containers
bind to `127.0.0.1` only — see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) before
exposing anything to a network.

Next: point your editor at the server — [docs/CLIENT_SETUP.md](docs/CLIENT_SETUP.md).

## MCP tools

| Tool | Purpose |
|---|---|
| `find_1c_help` | Find candidates when the exact name is unknown — one line per element, no full card. |
| `get_1c_element` | Full card for an element whose exact name is known; a candidate list instead of a card when the name is ambiguous. |
| `list_1c_object_members` | Methods, properties, events and constructors of one object, one line each. |
| `get_1c_article` | Full text of an article about a language construct, query syntax, common syntax or a DCS expression function. |

Schemas, limits and the exact behaviour on ambiguous or missing names:
[docs/MCP_TOOLS.md](docs/MCP_TOOLS.md).

## Article books (optional)

Four more books add articles alongside the element cards — full text for
operators and language constructs, query syntax, common source-text syntax,
and DCS expression functions, retrieved whole through `get_1c_article` and
found by `find_1c_help` like everything else. Copy them next to
`shcntx_ru.hbk`:

```bash
cp /path/to/shlang_ru.hbk data/hbk/
cp /path/to/shquery_ru.hbk data/hbk/
cp /path/to/shclang_ru.hbk data/hbk/
cp /path/to/dcsui_ru.hbk data/hbk/
```

| File | Covers |
|---|---|
| `shlang_ru.hbk` | The 1C language: operators, statements, constructs |
| `shquery_ru.hbk` | The query language |
| `shclang_ru.hbk` | Common syntax: source-text format, property access, comments |
| `dcsui_ru.hbk` | DCS expression language functions and operators |

All four are optional and independent of each other and of `shcntx_ru.hbk`:
**without them the server works exactly as before** — the other three tools
are unaffected, and `/health` names the missing ones in
`missing_article_books`. The same four books exist for English, named
`shlang_root.hbk` and so on, and go into `data/hbk-en` next to
`shcntx_root.hbk`; missing ones there are named in `missing_article_books_en`.
Together the eight files weigh under a megabyte, against tens of megabytes
for `shcntx_ru.hbk` alone.

Filenames come from one table in `src/core/constants.py`, not environment
variables — see [docs/CONFIGURATION.md](docs/CONFIGURATION.md). The five
outcomes of `get_1c_article` and the `kind="article"` value of `find_1c_help`:
[docs/MCP_TOOLS.md](docs/MCP_TOOLS.md).

## Language support

Every tool takes a `lang` argument (`"ru"` or `"en"`, default from the
`DEFAULT_HELP_LANG` environment variable) that picks which book the *answer*
comes from — the Russian index or the English one — and therefore its
language. It is a separate axis from the name you pass in.

**Under the default `lang="ru"`, both languages resolve.** `НайтиСтроки` and
`FindRows` both find the same element, and so do `Добавить` and `Add` — the
Russian reference book carries both names in every element page title
(`<h1>НайтиСтроки (FindRows)</h1>`), and the indexer splits them into separate
`name_ru`/`name_en` fields. 20 157 of the 20 159 element pages in the current
index carry an English name; the two without one are structural pages, not
regular elements missing a translation (a section header "Прочие процедуры и
функции" and a page whose own Russian title repeats itself in place of an
English one). Object names resolve too: `list_1c_object_members(object=
"ValueTable")` and `get_1c_element(name="Add", object="Array")` both work,
even though object pages don't print an English name in their own title the
way element pages do — the server backfills it from the optional English
index (see below) onto the matching Russian object page after indexing — in a
single pass, right after both books are indexed. Of the 2 577 object pages,
2 555 (99%) have picked up an English name this way, and all 389 constructor
pages did too; the remaining 22 objects answer only to their Russian name, and
there is nothing to fix on this side: 21 of those pages do not exist in the
English book at all (it holds 23 104 pages against 23 125 in the Russian one),
and the 22nd is titled there with the book's own internal page id rather than a
name, which the backfill refuses to take. Either way, the card itself —
description, parameters, availability, example — is Russian, because that is
the only language the Russian book carries them in.

**`lang="en"` is a different thing: a genuinely English answer, end to end**,
from the optional second book (`shcntx_root.hbk` — see
[docs/CONFIGURATION.md](docs/CONFIGURATION.md#английская-книга-справки)), not
a translation of the Russian one. It requires that book to be indexed, and it
requires an English name — passing a Russian one is refused outright rather
than silently searched for in the Russian index under the guise of an English
answer (see below). Real output of `get_1c_element(name="Add", object="Array",
lang="en")` against the current English index (23 104 documents):

```
Array.Add — procedure of Array

Call: Array.Add(<Value>)
Parameters:
    Value — Arbitrary, optional
      Added value. If not specified, a value of Undefined type will be added.

Returns: nothing (procedure)
Availability: thin client, web-client, mobile client, server, thick client, external connection, mobile application (client), mobile application (server), mobile standalone server
Available since: 8.0

Description: Adds an element to the end of the array.
Note: When an element is added, the number of elements in the array is increased by 1.
Example:
  Array.Add("First");
  Array.Add("Second");
```

A call that mixes languages the wrong way — a Cyrillic name with `lang="en"`,
or any `lang="en"` call before the English book has been indexed — gets an
explained refusal instead of a silent empty answer. The reverse never
happens: `lang="ru"` accepts an English name freely, because the Russian book
carries both. Exact wording of all three refusal cases:
[docs/MCP_TOOLS.md](docs/MCP_TOOLS.md#кросс-языковые-запросы).

## Differences from the upstream project

Based on [Antonio1C/1c-syntax-helper-mcp](https://github.com/Antonio1C/1c-syntax-helper-mcp)
(MIT, as declared in its README), which contributed the FastAPI service layout,
`.hbk` extraction through 7-Zip and Elasticsearch indexing. What changed:

- **The element card is a contract, not free text.** A fixed set of fields is
  always printed, and absent data is labelled (`Доступность: в справке не
  указана`, `Примеров в справке нет`) instead of being dropped.
- **Four MCP tools instead of one**, each with an explicit JSON schema, so an
  agent picks a tool by purpose rather than by guessing arguments.
- **Disambiguation instead of a silent pick.** `Добавить` occurs on 197 pages;
  the server returns an ordered candidate list and asks for the object, rather
  than returning an arbitrary one of them as the answer.
- **Call variants, real parameter requiredness and property value types** are
  parsed out of the help HTML.
- **A reproducible search-quality measurement** — `scripts/eval_search.py`
  builds its ground truth from the index itself and reports hit rates.
- **The `.hbk` container is read directly**, not through 7-Zip: 7-Zip finds a
  zip stream inside it by scanning and silently drops entries it does not
  confirm — a quarter of one of the article books before this change.

Full attribution and the complete list of changes: [NOTICE](NOTICE).

## License

MIT — see [LICENSE](LICENSE). Attribution of the upstream project and the list
of changes made here: [NOTICE](NOTICE). The upstream project is
[Antonio1C/1c-syntax-helper-mcp](https://github.com/Antonio1C/1c-syntax-helper-mcp).

The licence covers this source code only. It does not cover the proprietary
1C:Enterprise syntax reference — neither the `.hbk` files, which are not part
of this repository, nor the 25 sample pages under `tests/fixtures/` that the
parser tests are built on (see [NOTICE](NOTICE)).

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

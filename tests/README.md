# Тесты

407 тестов. Настройки pytest — в `pytest.ini` в корне репозитория, общие
фикстуры и заглушки — в `conftest.py`, тестовые данные — в `fixtures/`.

## Как запускать

Тесты рассчитаны на контур разработки: он собирает образ с dev-зависимостями и
монтирует внутрь `src/`, `tests/`, `pytest.ini` и `scripts/`.

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

Монтирование `src/` здесь принципиально: в продуктовом образе исходники
копируются внутрь, и без монтирования pytest молча проверял бы старую версию
кода и показывал зелёный, которого нет.

Весь набор:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T mcp-server python -m pytest -q
```

Срез без Elasticsearch — тот же, что гоняет CI:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T mcp-server python -m pytest -m "not elasticsearch and not slow" -q
```

Один файл или один тест:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T mcp-server python -m pytest tests/test_element_card.py -v
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T mcp-server python -m pytest tests/test_element_card.py::test_procedure_states_it_returns_nothing -v
```

Покрытие:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T mcp-server python -m pytest --cov=src --cov-report=term-missing
```

## Маркеры

| Маркер | Что помечает | Тестов |
|---|---|---|
| `unit` | Быстрые тесты на заглушках, без внешних зависимостей | 243 |
| `integration` | Тесты с настоящими компонентами — Elasticsearch, файл справки | 55 |
| `slow` | Тесты дольше десятка секунд: полный разбор или полная индексация | 13 |
| `elasticsearch` | Требуют поднятого Elasticsearch с построенным индексом | 52 |
| `parser` | Разбор `.hbk` и HTML справки | 87 |
| `indexer` | Индексация в Elasticsearch | 24 |
| `search` | Поиск и ранжирование | 6 |
| `background` | Фоновые задачи | 0 |
| `retry` | Механизмы повторов | 0 |
| `hbk_en` | Требует английскую книгу справки в `data/hbk-en` | 1 |

`background` и `retry` объявлены в `pytest.ini`, но сейчас ни одним тестом не
используются. Маркер новому тесту ставится обязательно: `--strict-markers`
превращает опечатку в ошибку, а не в молчаливо пропущенный фильтр.

Сумма по `unit` и `integration` (243 + 55 = 298) меньше 407: часть тестов не
помечена ни тем, ни другим — среди них разбор статей (`test_article_parser.py`),
он проверяется как чистая функция строки и маркера не несёт.

Книга справки читается через `HelpBookArchive`
(`tests/test_v8_container.py`), а статьи четырёх книг — через
`article_parser.py` и `article_books.py`
(`tests/test_article_parser.py`, `tests/test_article_parser_real_books.py`,
`tests/test_article_model.py`, `tests/test_article_indexing.py`,
`tests/test_article_index_write.py`, `tests/test_article_search.py`,
`tests/test_get_article.py`, `tests/test_article_books_real_corruption.py`,
`tests/test_article_book_isolation.py`).
`tests/test_indexing_partial_failure.py` и `tests/test_page_loss_accounting.py`
покрывают `MAX_TOLERATED_PAGE_LOSS_SHARE` — книгу, потерявшую при разборе
больше 5% страниц, и способы потерять страницу.
`tests/test_startup_indexing_path.py` держит фоновый путь индексации на том же
`index_hbk_file`, что и ручной.

## Тесты, которым нужен Elasticsearch

52 теста с маркером `elasticsearch` работают против живого кластера и
построенного индекса. Без поднятого контура они падают, а не пропускаются:
зелёный прогон на пустом индексе был бы хуже красного.

Проверить, что контур готов:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Индекс построен, когда `documents_count` больше нуля, а `indexing_active`
равно `false`. Как построить и как переиндексировать —
[docs/CONFIGURATION.md](../docs/CONFIGURATION.md#переиндексация).

CI кластер не поднимает: держать Elasticsearch ради 65 тестов (`elasticsearch`
и `slow`) дорого, а оставшиеся 342 покрывают парсер, карточку и контракт
инструментов.

## Соглашения

- Имя файла: `test_<модуль>.py` для интеграционных, `test_<модуль>_unit.py`
  для юнит-тестов.
- Асинхронный тест не требует `@pytest.mark.asyncio`: в `pytest.ini` включён
  `asyncio_mode = auto`.
- Заглушки — фикстурами в `conftest.py`, а не заново в каждом файле.

### Боевой индекс

Тест вправе читать `help1c_docs` и `help1c_docs_en` — они живые и заполнены.
Перестраивать (`reindex_all`) любой из них тест не вправе: автоюз-фикстура
`refuse_writes_to_the_production_index` в `conftest.py` останавливает такую
попытку до обращения к Elasticsearch. Тесту, которому для перестройки нужен
свой индекс, — фикстура `isolated_index`: она выдаёт временное имя и убирает
индекс за собой. Небольшая книга справки для таких тестов даёт
`hbk_fixture_archive` — без 37 МБ настоящей книги.

Сама книга — контейнер V8, а не просто zip: `build_container` в
`conftest.py` собирает такой контейнер в памяти из словаря
`{имя_файла: содержимое}`, `write_book` сохраняет его во временный файл — оба
без обращения к настоящей поставке 1С. `hbk_fixture_archive` построена поверх
них же.

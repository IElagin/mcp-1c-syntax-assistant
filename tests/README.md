# Тесты

327 тестов. Настройки pytest — в `pytest.ini` в корне репозитория, общие
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
| `unit` | Быстрые тесты на заглушках, без внешних зависимостей | 227 |
| `integration` | Тесты с настоящими компонентами — Elasticsearch, файл справки | 54 |
| `slow` | Тесты дольше десятка секунд: полный разбор или полная индексация | 2 |
| `elasticsearch` | Требуют поднятого Elasticsearch с построенным индексом | 50 |
| `parser` | Разбор `.hbk` и HTML справки | 81 |
| `indexer` | Индексация в Elasticsearch | 13 |
| `search` | Поиск и ранжирование | 6 |
| `background` | Фоновые задачи | 0 |
| `retry` | Механизмы повторов | 0 |
| `hbk_en` | Требует английскую книгу справки в `data/hbk-en` | 1 |

`background` и `retry` объявлены в `pytest.ini`, но сейчас ни одним тестом не
используются. Маркер новому тесту ставится обязательно: `--strict-markers`
превращает опечатку в ошибку, а не в молчаливо пропущенный фильтр.

Сумма по `unit` и `integration` (227 + 54 = 281) меньше 327: часть тестов не
помечена ни тем, ни другим.

## Тесты, которым нужен Elasticsearch

50 тестов с маркером `elasticsearch` работают против живого кластера и
построенного индекса. Без поднятого контура они падают, а не пропускаются:
зелёный прогон на пустом индексе был бы хуже красного.

Проверить, что контур готов:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Индекс построен, когда `documents_count` больше нуля, а `indexing_active`
равно `false`. Как построить и как переиндексировать —
[docs/CONFIGURATION.md](../docs/CONFIGURATION.md#переиндексация).

CI кластер не поднимает: держать Elasticsearch ради 52 тестов (`elasticsearch`
и `slow`) дорого, а оставшиеся 275 покрывают парсер, карточку и контракт
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
индекс за собой. Небольшой архив справки для таких тестов даёт
`hbk_fixture_archive` — без 37 МБ настоящей книги.

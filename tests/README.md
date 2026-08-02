# Тесты

176 тестов. Настройки pytest — в `pytest.ini` в корне репозитория, общие
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
| `unit` | Быстрые тесты на заглушках, без внешних зависимостей | 114 |
| `integration` | Тесты с настоящими компонентами — Elasticsearch, файл справки | 40 |
| `slow` | Тесты дольше десятка секунд: полный разбор или полная индексация | 2 |
| `elasticsearch` | Требуют поднятого Elasticsearch с построенным индексом | 39 |
| `parser` | Разбор `.hbk` и HTML справки | 36 |
| `indexer` | Индексация в Elasticsearch | 13 |
| `search` | Поиск и ранжирование | 7 |
| `background` | Фоновые задачи | 0 |
| `retry` | Механизмы повторов | 0 |

`background` и `retry` объявлены в `pytest.ini`, но сейчас ни одним тестом не
используются. Маркер новому тесту ставится обязательно: `--strict-markers`
превращает опечатку в ошибку, а не в молчаливо пропущенный фильтр.

Сумма по `unit` и `integration` меньше 176: часть тестов не помечена ни тем, ни
другим.

## Тесты, которым нужен Elasticsearch

39 тестов с маркером `elasticsearch` работают против живого кластера и
построенного индекса. Без поднятого контура они падают, а не пропускаются:
зелёный прогон на пустом индексе был бы хуже красного.

Проверить, что контур готов:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Индекс построен, когда `documents_count` больше нуля, а `indexing_active`
равно `false`. Как построить и как переиндексировать —
[docs/CONFIGURATION.md](../docs/CONFIGURATION.md#переиндексация).

CI кластер не поднимает: держать Elasticsearch ради 40 тестов дорого, а
оставшиеся 136 покрывают парсер, карточку и контракт инструментов.

## Соглашения

- Имя файла: `test_<модуль>.py` для интеграционных, `test_<модуль>_unit.py`
  для юнит-тестов.
- Асинхронный тест не требует `@pytest.mark.asyncio`: в `pytest.ini` включён
  `asyncio_mode = auto`.
- Заглушки — фикстурами в `conftest.py`, а не заново в каждом файле.

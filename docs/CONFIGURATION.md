# Конфигурация

Все настройки сервера — переменные окружения. Файл `.env.example` в корне
репозитория — образец: скопируйте его в `.env` и правьте копию.

Прежде чем править `.env`, прочитайте раздел
[«Как настройки попадают в контейнер»](#как-настройки-попадают-в-контейнер) —
он объясняет, почему при запуске через Docker правка `.env` ничего не меняет.

## Переменные окружения

Значения по умолчанию заданы в `src/core/config.py`; таблица повторяет их.

### Elasticsearch

| Переменная | Тип | По умолчанию | Назначение |
|---|---|---|---|
| `ELASTICSEARCH_HOST` | строка | `localhost` | Хост Elasticsearch. Внутри compose-контура — `elasticsearch`, имя сервиса. |
| `ELASTICSEARCH_PORT` | строка | `9200` | Порт Elasticsearch. Вместе с хостом собирается в URL `http://<host>:<port>`. |
| `ELASTICSEARCH_INDEX` | строка | `help1c_docs` | Имя индекса. Меняйте, если на одном кластере живёт несколько книг справки. |
| `ELASTICSEARCH_TIMEOUT` | целое | `30` | Таймаут одного запроса к Elasticsearch, секунды. |
| `ELASTICSEARCH_MAX_RETRIES` | целое | `3` | Сколько раз повторить запрос при обрыве связи или ответе 503/504. |
| `ELASTICSEARCH_RETRY_MIN_WAIT` | целое | `2` | Нижняя граница экспоненциальной паузы между повторами, секунды. |
| `ELASTICSEARCH_RETRY_MAX_WAIT` | целое | `30` | Верхняя граница той же паузы, секунды. |
| `ELASTICSEARCH_RETRY_MULTIPLIER` | целое | `1` | Множитель экспоненты повторов. |

Три переменных `ELASTICSEARCH_RETRY_*` в `.env.example` не перечислены, но
читаются: они управляют декоратором повторов в `src/core/retry.py`.

### Сервер

| Переменная | Тип | По умолчанию | Назначение |
|---|---|---|---|
| `SERVER_HOST` | строка | `0.0.0.0` | Интерфейс, который слушает сервер. Действует только при запуске `python src/main.py`; в контейнере адрес задан в `CMD` образа. |
| `SERVER_PORT` | целое | `8000` | Порт сервера. Та же оговорка. |
| `LOG_LEVEL` | строка | `INFO` | Уровень корневого логгера: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `DEBUG` | булево | `false` | `true` — простой текстовый формат логов в консоли вместо JSON. |
| `CORS_ALLOW_ORIGINS` | строка | `*` | Список источников через запятую; `*` — разрешить все. Учётные данные в CORS выключены всегда: аутентификации у сервера нет. |

Обработчик консоли жёстко настроен на `INFO`, поэтому `LOG_LEVEL=DEBUG`
добавляет отладочные записи только в файл `app.log`, а не в вывод контейнера.

### Данные

| Переменная | Тип | По умолчанию | Назначение |
|---|---|---|---|
| `HBK_DIRECTORY` | путь | `data/hbk` | Каталог, где сервер ищет книгу справки. В контейнере смонтирован из `./data/hbk` только на чтение. |
| `HBK_FILENAME` | строка | `shcntx_ru.hbk` | Имя книги для индексации. В каталоге могут лежать и другие `.hbk`, поэтому выбор явный. |
| `LOGS_DIRECTORY` | путь | `data/logs` | Каталог для `app.log` и `errors.log`. Создаётся при старте, если его нет. |

Значение по умолчанию не совпадает с точкой монтирования тома: том смонтирован
в `/app/logs`, а файлы пишутся в `/app/data/logs`. На хосте в `./data/logs`
из-за этого лежат пустые файлы. Как это исправить и где смотреть настоящие
логи — в [DEPLOYMENT.md](DEPLOYMENT.md#логи).

### Индексация

| Переменная | Тип | По умолчанию | Назначение |
|---|---|---|---|
| `REINDEX_ON_STARTUP` | булево | `false` | `true` — переиндексировать при каждом запуске. `false` — индексировать только если индекс пуст. |

### Переменные без эффекта

Эти четыре переменные есть в `.env.example`, но код их нигде не читает.
Установка любого значения ничего не меняет:

- `MAX_CONCURRENT_REQUESTS`
- `INDEX_BATCH_SIZE`
- `SEARCH_MAX_RESULTS`
- `SEARCH_TIMEOUT_SECONDS`

Ограничение частоты запросов задано константами
`REQUESTS_PER_MINUTE = 60` и `REQUESTS_PER_HOUR = 1000` в
`src/core/constants.py`, а размер пачки при индексации — константой
`BATCH_SIZE = 100` там же. Переменными окружения они не управляются.

Переменная `ELASTICSEARCH_URL` тоже не действует: адрес всегда собирается из
`ELASTICSEARCH_HOST` и `ELASTICSEARCH_PORT`.

## Как настройки попадают в контейнер

Файл `.env` на контейнеры не влияет: `Dockerfile` его не копирует, `env_file` в
compose не подключён. Переменные для контейнера задаются в секции
`environment` файлов `docker-compose.yml` и `docker-compose.dev.yml`. `.env`
работает только при запуске сервера напрямую на хосте, без Docker — тогда его
читает `pydantic-settings`.

Без этого знания легко потерять час: правишь `.env`, перезапускаешь контейнер и
не понимаешь, почему ничего не изменилось.

Чтобы поменять настройку контейнера, добавьте её в `environment` нужного
сервиса:

```yaml
services:
  mcp-server:
    environment:
      - ELASTICSEARCH_HOST=elasticsearch
      - ELASTICSEARCH_PORT=9200
      - LOG_LEVEL=DEBUG
```

и примените изменение:

```powershell
docker compose up -d
```

Проверить, что именно видит контейнер:

```powershell
docker compose exec mcp-server printenv | Select-String 'ELASTICSEARCH|LOG_LEVEL|HBK|REINDEX'
```

## Переиндексация

Индекс строится один раз при первом старте. Переиндексация нужна, когда вы
заменили книгу справки или обновили парсер.

Три способа, в порядке приоритета.

### 1. Флаг `--reindex` при запуске на хосте

```powershell
.\scripts\start_server.ps1 --reindex
```

```cmd
scripts\start_server.bat --reindex
```

Флаг разбирается в `src/main.py` и включает принудительную переиндексацию:
старый индекс удаляется, документы индексируются заново в фоне. Флаг имеет
приоритет над `REINDEX_ON_STARTUP`.

Через `uvicorn` флаг не пройдёт — скрипты запускают `python src/main.py`
именно поэтому.

### 2. Переменная `REINDEX_ON_STARTUP`

Для контейнера — в `docker-compose.dev.yml` или `docker-compose.yml`:

```yaml
services:
  mcp-server:
    environment:
      - REINDEX_ON_STARTUP=true
```

Для запуска на хосте — в `.env`:

```properties
REINDEX_ON_STARTUP=true
```

Верните значение в `false`, когда переиндексация закончится: иначе индекс будет
перестраиваться при каждом старте.

### 3. Эндпоинт `POST /index/rebuild`

Переиндексация работающего сервера, без перезапуска контейнеров:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/index/rebuild
```

```bash
curl -X POST http://localhost:8000/index/rebuild
```

Вызов синхронный: HTTP-запрос ждёт окончания индексации и может упереться в
таймаут клиента. Если ответа не дождались, проверяйте результат через
`GET /index/status`, а не повторяйте вызов вслепую.

Успешный ответ:

```json
{
  "status": "success",
  "message": "Переиндексация завершена успешно",
  "file": "data/hbk/shcntx_ru.hbk",
  "documents_count": 23025
}
```

Если книги нет в каталоге, эндпоинт отвечает 400 с именем файла, которого не
хватает; если недоступен Elasticsearch — 503.

### Как следить за ходом

```powershell
Invoke-RestMethod http://localhost:8000/index/status
```

```json
{
  "elasticsearch_connected": true,
  "index_exists": true,
  "documents_count": 23025,
  "index_name": "help1c_docs",
  "indexing": {
    "is_active": false,
    "status": "idle",
    "progress_percent": 0.0,
    "total_documents": 0,
    "indexed_documents": 0,
    "start_time": null,
    "end_time": null,
    "error_message": null,
    "file_path": null,
    "duration_seconds": null
  }
}
```

Индексация закончена, когда `is_active` равно `false`, а `documents_count`
перестал расти. При сбое причина попадает в `error_message`.

## Замена файла справки

Книга справки живёт в `data/hbk/` и в репозиторий не входит — `data/` внесён в
`.gitignore`. Файл проприетарный: копируйте его из своей лицензионной установки
1С:Предприятие (`C:\Program Files\1cv8\<версия>\bin\shcntx_ru.hbk`) и не
распространяйте.

Порядок замены:

```powershell
# 1. Положить новый файл под тем же именем
Copy-Item "C:\Program Files\1cv8\8.3.26.1234\bin\shcntx_ru.hbk" data\hbk\ -Force

# 2. Переиндексировать
Invoke-RestMethod -Method Post -Uri http://localhost:8000/index/rebuild

# 3. Убедиться, что число документов изменилось
Invoke-RestMethod http://localhost:8000/index/status
```

Каталог `data/hbk` смонтирован в контейнер только на чтение, поэтому новый файл
виден сразу — перезапускать контейнер не нужно.

Если файл называется иначе, задайте `HBK_FILENAME`. Индексируется ровно одна
книга: имя выбирается явно, а не по первому найденному `.hbk`, потому что в
каталоге могут лежать и другие книги — английская `shcntx_root.hbk`, справка по
языку запросов и прочие.

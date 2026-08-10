# Развёртывание

Сервис состоит из двух контейнеров: Elasticsearch и MCP-сервер. Оба описаны в
`docker-compose.yml` и по умолчанию слушают только `127.0.0.1`.

Переменные окружения и переиндексация — в [CONFIGURATION.md](CONFIGURATION.md).
Подключение клиентов — в [CLIENT_SETUP.md](CLIENT_SETUP.md).

## Требования

| | Windows Server | Linux |
|---|---|---|
| ОС | Windows Server 2019 и новее | Ubuntu 20.04+, Debian 11+ или сопоставимый |
| Docker | Docker Desktop | Docker Engine + Compose v2 |
| Память | 4 ГБ, лучше 8 | 4 ГБ, лучше 8 |
| Диск | ~2 ГБ под образы плюс место под индекс | то же |

Проверка окружения:

```powershell
docker --version
docker compose version
```

Elasticsearch поднимается с кучей 1 ГБ (`ES_JAVA_OPTS=-Xms1g -Xmx1g`). На
машине с 4 ГБ памяти этого хватает, но запас невелик — при нехватке контейнер
уходит в перезапуск, и это видно в `docker compose ps`.

## Развёртывание на месте, из исходников

Самый короткий путь, если на сервере есть доступ к репозиторию:

```bash
# Склонировать репозиторий и перейти в его корень
mkdir -p data/hbk data/logs
cp /path/to/shcntx_ru.hbk data/hbk/
docker compose up -d
```

Файл справки копируется из лицензионной установки 1С:Предприятие; в
репозиторий он не входит и распространению не подлежит.

## Развёртывание образом, без доступа к сети

Если на сервере нет ни репозитория, ни доступа к реестру образов, образ
собирается на рабочей машине и переносится файлом.

### Сборка под AMD64

```powershell
docker build -t mcp-1c-syntax:amd64 .
docker save mcp-1c-syntax:amd64 -o mcp-1c-syntax-amd64.tar
```

### Сборка под ARM64

ARM64 нужен для Raspberry Pi 4 и новее, Apple Silicon и ARM-инстансов в
облаках. Сборка под чужую архитектуру требует buildx и эмуляции:

```powershell
docker buildx create --name multiarch --use   # один раз
docker buildx build --platform linux/arm64 -t mcp-1c-syntax:arm64 -o type=docker .
docker save mcp-1c-syntax:arm64 -o mcp-1c-syntax-arm64.tar
```

Базовый образ `python:3.14-slim` существует под обе архитектуры, поэтому
специальных правок в `Dockerfile` не нужно. Сборка под ARM64 через эмуляцию
заметно медленнее нативной — `build-essential` и компиляция `psutil` занимают
основное время. Пакета `p7zip-full` в списке `apt-get install` больше нет:
сервер читает книги справки `.hbk` собственным кодом, а не через внешний
7-Zip.

### Перенос на сервер

Windows Server:

```powershell
# На сервере
New-Item -ItemType Directory -Force C:\mcp-1c-syntax\data\hbk
New-Item -ItemType Directory -Force C:\mcp-1c-syntax\data\logs

# Скопировать mcp-1c-syntax-amd64.tar, docker-compose.yml и shcntx_ru.hbk
cd C:\mcp-1c-syntax
docker load -i mcp-1c-syntax-amd64.tar
```

Linux:

```bash
mkdir -p /opt/mcp-1c-syntax/data/hbk /opt/mcp-1c-syntax/data/logs
# scp mcp-1c-syntax-arm64.tar docker-compose.yml shcntx_ru.hbk на сервер
cd /opt/mcp-1c-syntax
docker load -i mcp-1c-syntax-arm64.tar
```

### Переключить compose на готовый образ

В `docker-compose.yml` на сервере замените сборку на имя загруженного образа:

```yaml
services:
  mcp-server:
    # build: .
    image: mcp-1c-syntax:amd64   # или mcp-1c-syntax:arm64
```

и запустите:

```bash
docker compose up -d
docker compose ps
```

Ожидаемый результат:

```
NAME            STATUS                   PORTS
es-1c-helper    Up 2 minutes (healthy)   127.0.0.1:9200->9200/tcp
mcp-1c-helper   Up 1 minute (healthy)    127.0.0.1:8000->8000/tcp
```

## Как выставить сервис наружу безопасно

По умолчанию оба сервиса слушают только `127.0.0.1`. Elasticsearch поднимается
с `xpack.security.enabled=false` — выставлять его наружу нельзя ни при каких
условиях. Если MCP-сервер нужен коллегам по сети, откройте наружу только порт
8000 и только через обратный прокси с TLS и ограничением по адресам; порт
Elasticsearch оставьте на localhost.

Что это значит на практике.

**Не делайте так.** Смена привязки в `docker-compose.yml` на `0.0.0.0`
открывает Elasticsearch без аутентификации всем, кто дотянется до порта: чтение
и запись индекса, удаление данных, а через него — разведка сети изнутри.

```yaml
# Так — нельзя
elasticsearch:
  ports:
    - "9200:9200"
```

**Делайте так.** Порт Elasticsearch остаётся как есть, перед MCP-сервером
ставится обратный прокси, который завершает TLS и пускает только своих:

```nginx
server {
    listen 443 ssl;
    server_name mcp.example.com;

    ssl_certificate     /etc/ssl/certs/mcp.crt;
    ssl_certificate_key /etc/ssl/private/mcp.key;

    # Только своя подсеть — подставьте её вместо этой строки
    allow 10.0.0.0/8;
    deny  all;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        # /mcp умеет отдавать поток SSE — буферизация его ломает
        proxy_buffering off;
        proxy_read_timeout 3600s;
    }
}
```

Помните, чего у сервера нет: аутентификации, авторизации и разделения прав.
Всё, кто дотянулся до порта 8000, — один анонимный пользователь. Ограничение по
частоте (60 запросов в минуту и 1000 в час с одного адреса) защищает от
случайной лавины, но не от злоупотребления. Разграничение доступа — целиком
задача прокси.

Заодно сузьте CORS: значение по умолчанию `CORS_ALLOW_ORIGINS=*` уместно на
localhost, но не на сервисе, доступном по сети. Учётные данные в CORS выключены
всегда — их у сервера просто нет.

Если сервис нужен только вам и только с рабочей машины, ничего открывать не
надо: значения по умолчанию уже верны.

## HTTP-эндпоинты

Все примеры — с самого сервера. Порт наружу по умолчанию не выставлен.

### `GET /health`

Состояние сервиса. Годится как проба для мониторинга: `status` равен `healthy`,
пока доступен Elasticsearch, в том числе во время индексации.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

```json
{"status":"healthy","elasticsearch":true,"index_exists":true,
 "documents_count":23125,"indexing_status":"idle","indexing_active":false,
 "index_en_exists":true,"documents_count_en":23104,"version":"2.2.0"}
```

`index_en_exists`/`documents_count_en` — то же самое для необязательной
английской книги (см. [CONFIGURATION.md](CONFIGURATION.md#английская-книга-справки));
без неё оба поля равны `false`/`null`.

Этот же запрос стоит в `healthcheck` контейнера, поэтому `docker compose ps`
показывает `(healthy)` только когда сервер отвечает.

### `GET /index/status`

Подробности об индексе и ходе индексации: имя индекса, число документов,
прогресс в процентах, время начала и длительность, текст ошибки при сбое.
Разбор полей — в [CONFIGURATION.md](CONFIGURATION.md#как-следить-за-ходом).

### `POST /index/rebuild`

Переиндексация без перезапуска контейнеров. Вызов синхронный. Подробности и
альтернативные способы — в
[CONFIGURATION.md](CONFIGURATION.md#переиндексация).

### `GET /metrics`

Счётчики, датчики и таймеры сервера, сводка по производительности и состояние
ограничителя частоты. Блок `performance` возвращается целиком всегда, а
`counters`, `gauges` и `timers` в примере ниже сокращены — реальный ответ
содержит их больше:

```json
{
  "metrics": {
    "counters": {"health_check.requests": 69.0},
    "gauges": {"system.cpu.usage_percent": 0.5,
               "system.memory.usage_percent": 19.7,
               "system.disk.free_gb": 931.79},
    "timers": {"request.duration": {"count": 121, "avg": 0.0063,
                                    "min": 0.0005, "max": 0.0215}}
  },
  "performance": {"total_requests": 121, "successful_requests": 112,
                  "failed_requests": 9, "success_rate": 92.56,
                  "avg_response_time": 0.0063, "max_response_time": 0.0215,
                  "min_response_time": 0.0005, "current_active_requests": 0},
  "rate_limiting": {"active_clients": 2, "total_requests_tracked": 122}
}
```

Формат собственный, не Prometheus. Сборщику метрик понадобится разбор JSON.

### `GET /metrics/{client_id}`

Расход лимита одним клиентом; `client_id` — его IP-адрес.

### `GET /docs`

Swagger UI, сгенерированный FastAPI. Схемы MCP-инструментов туда не попадают —
они отдаются по `GET /mcp/tools` и в ответе на `tools/list`.

### `POST /mcp` и `GET /mcp`

Протокол MCP. Описаны в [CLIENT_SETUP.md](CLIENT_SETUP.md).

## Автозапуск

Оба сервиса объявлены с `restart: unless-stopped`, поэтому поднимаются вместе с
демоном Docker.

На Windows Server этого достаточно, если Docker Desktop настроен на запуск при
входе в систему.

На Linux, если compose-контур должен подниматься до входа пользователя, заведите
unit `/etc/systemd/system/mcp-1c-syntax.service` — имя файла определяет имя
сервиса в командах ниже:

```ini
[Unit]
Description=1C Syntax Assistant MCP Server
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/mcp-1c-syntax
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mcp-1c-syntax
```

## Диагностика

### Контейнер не поднимается

```bash
docker compose logs --tail 100
docker compose ps
```

Занятый порт виден сразу — compose откажется стартовать. Проверить, кто держит:

```powershell
netstat -ano | Select-String ':8000'
```

```bash
ss -ltnp | grep -E ':8000|:9200'
```

### Elasticsearch перезапускается по кругу

Почти всегда нехватка памяти: куче нужен 1 ГБ плюс накладные расходы JVM.
Проверьте `docker stats` и свободную память на хосте. На Linux встречается и
слишком низкий `vm.max_map_count`:

```bash
sudo sysctl -w vm.max_map_count=262144
```

### Сервер отвечает 503

Elasticsearch недоступен. Проверьте его напрямую и посмотрите, что видит
MCP-сервер:

```bash
curl http://127.0.0.1:9200/_cluster/health
docker compose logs mcp-server --tail 50
```

### Индексация не запускается

Книга справки не найдена или названа иначе. Сервер не подменяет её первым
попавшимся `.hbk` — сервер с чужой книгой в индексе выглядит исправным, и
расхождение обнаружилось бы только по языку ответов.

```bash
docker compose exec mcp-server ls -l /app/data/hbk
docker compose logs mcp-server | grep -i "книга справки"
```

Если имя файла другое, задайте `HBK_FILENAME` — см.
[CONFIGURATION.md](CONFIGURATION.md#данные).

### Ответ 429

Сработало ограничение частоты: 60 запросов в минуту или 1000 в час с одного
адреса. В ответе есть заголовок `Retry-After`. Лимиты заданы константами в
`src/core/constants.py` и переменными окружения не управляются.

### Логи

Основной источник — поток контейнера, формат JSON:

```bash
docker compose logs -f mcp-server
```

Дополнительно сервер пишет два файла в каталог `LOGS_DIRECTORY`: `app.log`
(уровень `DEBUG` и выше) и `errors.log` (только `ERROR` и выше). Каталог
смонтирован из `./data/logs`, поэтому файлы доступны прямо с хоста и переживают
пересоздание контейнера:

```bash
tail -n 50 data/logs/errors.log
```

```powershell
Get-Content data\logs\errors.log -Tail 50
```

Формат обоих файлов — JSON, по записи на строку.

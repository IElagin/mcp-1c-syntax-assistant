# Инструкция по развертыванию

Руководство по развертыванию MCP-сервера синтаксис-помощника 1С на Windows Server и Linux Server (ARM64).

## 📋 Содержание

1. [Требования](#требования)
2. [Подготовка Docker образа](#подготовка-docker-образа)
3. [Развертывание на сервере](#развертывание-на-сервере)
4. [Проверка работоспособности](#проверка-работоспособности)
5. [Подключение клиентов](#подключение-клиентов)
6. [Обновление .hbk файла](#обновление-hbk-файла)
7. [Управление сервисом](#управление-сервисом)

---

## 🖥️ Требования

### Windows Server
- Windows Server 2019+
- Docker Desktop
- 4+ ГБ RAM (рекомендуется 8 ГБ)

### Linux Server (ARM64)
- Ubuntu 18.04+ / Debian 10+ / CentOS 8+ или другой Linux
- Docker и Docker Compose установлены
- 4+ ГБ RAM (рекомендуется 8 ГБ)

### Проверка Docker:
```powershell
# Windows
docker --version
docker compose version
```

```bash
# Linux
docker --version
docker compose version
```

---

## 📦 Подготовка Docker образа

### На вашей рабочей машине:

#### Для серверов AMD64 (Intel/AMD)

```powershell
# 1. Перейти в директорию проекта
cd C:\help1c-mcp

# 2. Собрать Docker образ для AMD64
docker build -t help1c-mcp:amd64 .

# 3. Экспортировать образ в файл
docker save help1c-mcp:amd64 -o help1c-mcp-amd64.tar

# Образ сохранится в файл help1c-mcp-amd64.tar (~500 МБ)
```

#### Для серверов ARM64 (ARM, Raspberry Pi 4+, Apple Silicon)

```powershell
# 1. Перейти в директорию проекта
cd C:\help1c-mcp

# 2. Собрать Docker образ для ARM64 (требует Docker Buildx)
docker buildx build --platform linux/arm64 -t help1c-mcp:arm64 -o type=docker .

# 3. Экспортировать образ в файл
docker save help1c-mcp:arm64 -o help1c-mcp-arm64.tar

# Образ сохранится в файл help1c-mcp-arm64.tar (~500 МБ)

# Примечание: Если Docker Buildx не установлен, используйте:
# docker buildx create --name multiarch
# docker buildx use multiarch
```

---

## 🚀 Развертывание на сервере

### Развертывание на Windows Server (AMD64)

#### Шаг 1: Копирование файлов на сервер

Скопируйте на сервер в папку `C:\help1c-mcp\`:

```
C:\help1c-mcp\
├── help1c-mcp-amd64.tar     # Docker образ для AMD64
├── docker-compose.yml       # Конфигурация
└── data\
    └── hbk\
        └── 1c_documentation.hbk  # Файл документации 1С
```

**Через сетевую папку:**
```powershell
# Создать директорию на сервере
New-Item -Path "C:\help1c-mcp" -ItemType Directory
New-Item -Path "C:\help1c-mcp\data\hbk" -ItemType Directory

# Скопировать файлы
Copy-Item "C:\help1c-mcp\help1c-mcp-amd64.tar" "\\SERVER\C$\help1c-mcp\"
Copy-Item "C:\help1c-mcp\docker-compose.yml" "\\SERVER\C$\help1c-mcp\"
Copy-Item "C:\help1c-mcp\data\hbk\*.hbk" "\\SERVER\C$\help1c-mcp\data\hbk\"
```

#### Шаг 2: Загрузка образа на сервере

На сервере в PowerShell:

```powershell
# Перейти в директорию
cd C:\help1c-mcp

# Загрузить Docker образ
docker load -i help1c-mcp-amd64.tar

# Проверить, что образ загружен
docker images | Select-String "help1c-mcp"
```

#### Шаг 3: Обновить docker-compose.yml

Замените в `C:\help1c-mcp\docker-compose.yml` строку `build: .` на `image: help1c-mcp:amd64`:

```yaml
mcp-server:
  image: help1c-mcp:amd64     # ← Изменить эту строку
  container_name: mcp-1c-helper
  ports:
    - "8000:8000"
  # ... остальное без изменений
```

#### Шаг 4: Запуск сервиса

```powershell
# Запустить контейнеры
docker compose up -d

# Проверить статус
docker compose ps
```

---

### Развертывание на Linux Server (ARM64)

#### Шаг 1: Подготовка на Windows машине

На вашей Windows машине соберите образ для ARM64:

```powershell
cd C:\help1c-mcp

# Создать builder если еще не создан
docker buildx create --name multiarch --use

# Собрать для ARM64 и сохранить как tar
docker buildx build --platform linux/arm64 -t help1c-mcp:arm64 -o type=docker .

# Экспортировать
docker save help1c-mcp:arm64 -o help1c-mcp-arm64.tar
```

#### Шаг 2: Копирование файлов на Linux сервер

```bash
# На Linux сервере создать директорию
mkdir -p /opt/help1c-mcp/data/hbk

# Скопировать файлы со своей машины на сервер (выполнить на Windows)
scp help1c-mcp-arm64.tar user@server:/opt/help1c-mcp/
scp docker-compose.yml user@server:/opt/help1c-mcp/
scp data/hbk/*.hbk user@server:/opt/help1c-mcp/data/hbk/

# Или через rsync для больших файлов
rsync -avz help1c-mcp-arm64.tar user@server:/opt/help1c-mcp/
rsync -avz docker-compose.yml user@server:/opt/help1c-mcp/
rsync -avz data/hbk/ user@server:/opt/help1c-mcp/data/hbk/
```

#### Шаг 3: Загрузка образа на Linux сервере

На сервере выполните:

```bash
cd /opt/help1c-mcp

# Загрузить Docker образ
docker load -i help1c-mcp-arm64.tar

# Переименовать образ для удобства (опционально)
docker tag help1c-mcp:arm64 help1c-mcp:latest

# Проверить загруженный образ
docker images | grep help1c-mcp
```

#### Шаг 4: Обновить docker-compose.yml на Linux

На сервере отредактируйте `docker-compose.yml`:

```bash
# Отредактировать файл
nano /opt/help1c-mcp/docker-compose.yml

# Убедиться, что указано:
# image: help1c-mcp:arm64  (или help1c-mcp:latest если переименовали)
# volumes указывают на правильные пути для Linux:
#   - ./data/hbk:/app/data/hbk
#   - ./logs:/app/logs
```

#### Шаг 5: Запуск контейнеров на Linux

```bash
cd /opt/help1c-mcp

# Создать директорию логов если ее еще нет
mkdir -p logs

# Запустить контейнеры
docker compose up -d

# Проверить статус
docker compose ps
```

**Ожидаемый результат:**
```
NAME              STATUS              PORTS
es-1c-helper      Up 2 minutes        0.0.0.0:9200->9200/tcp
mcp-1c-helper     Up 1 minute         0.0.0.0:8000->8000/tcp
```

---

## ✅ Проверка работоспособности

### На сервере:

```powershell
# Проверка health endpoint
Invoke-RestMethod http://localhost:8000/health

# Проверка статуса индекса
Invoke-RestMethod http://localhost:8000/index/status
```

**Ожидаемый результат:**
```json
{
  "status": "healthy",
  "elasticsearch": "connected",
  "index_exists": true,
  "documents_count": 1234
}
```

### С клиентской машины:

Замените `SERVER_IP` на IP адрес сервера (например, `192.168.1.100`):

```powershell
Invoke-RestMethod http://SERVER_IP:8000/health
```

---

## 💻 Подключение клиентов

### Настройка VS Code на клиентских машинах

**Файл:** `%APPDATA%\Code\User\settings.json` (Windows) или `~/.config/Code/User/settings.json` (Linux)

```json
{
  "mcp.servers": {
    "1c-syntax-helper": {
      "command": "curl",
      "args": [
        "-X", "POST",
        "-H", "Content-Type: application/json",
        "-d", "@-",
        "http://SERVER_IP:8000/mcp"
      ]
    }
  }
}
```

**Замените `SERVER_IP`** на реальный IP адрес сервера:
- Пример: `http://192.168.1.100:8000/mcp`
- Или DNS имя: `http://help1c-server.local:8000/mcp`

### Проверка подключения в VS Code

1. Откройте VS Code
2. Нажмите `Ctrl+Shift+P`
3. Введите "MCP" и выберите команду для проверки подключения
4. В чате с AI попросите: "Найди справку по СтрДлина"

---

## 🔄 Обновление .hbk файла

### На Windows Server

```powershell
# 1. Заменить файл на сервере
Copy-Item "путь\к\новому\файлу.hbk" "C:\help1c-mcp\data\hbk\1c_documentation.hbk" -Force

# 2. Запустить реиндексацию через API
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/index/rebuild"

# 3. Проверить результат
Invoke-RestMethod -Uri "http://localhost:8000/index/status"
```

**Время обновления:** ~1-5 минут  
**Преимущества:** Контейнеры не перезагружаются, пользователи не отключаются

### На Linux Server

```bash
# 1. Заменить файл на сервере
cd /opt/help1c-mcp
cp /путь/к/новому/файлу.hbk data/hbk/1c_documentation.hbk

# 2. Запустить реиндексацию через API
curl -X POST http://localhost:8000/index/rebuild

# 3. Проверить результат
curl http://localhost:8000/index/status
```

**Время обновления:** ~1-5 минут  
**Преимущества:** Контейнеры не перезагружаются, пользователи не отключаются

### Если нужно перезагрузить контейнер

```powershell
# Windows Server
cd C:\help1c-mcp
docker compose restart mcp-server

# Или Linux Server
cd /opt/help1c-mcp
docker compose restart
```

**Простой:** ~30 секунд

### Автоматизация

Создайте файл `C:\help1c-mcp\update-hbk.ps1`:

```powershell
$HbkSource = "\\server\share\1c_documentation.hbk"
$HbkDest = "C:\help1c-mcp\data\hbk\1c_documentation.hbk"

Write-Host "Копирование файла..."
Copy-Item $HbkSource $HbkDest -Force

Write-Host "Реиндексация..."
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/index/rebuild"

Write-Host "Готово!"
Invoke-RestMethod -Uri "http://localhost:8000/index/status"
```

Запускать: `.\update-hbk.ps1Просмотр логов только MCP сервера
docker compose logs -f mcp-server

# Просмотр статуса
docker compose ps

# Обновление образов (после изменения кода)
docker compose up -d --build

# Полная очистка (с удалением данных)
docker compose down -v
```

### Автоматический запуск при загрузке сервера

**Linux (systemd):**

Создайте файл `/etc/systemd/system/help1c-mcp.service`:

```ini
[Unit]
Description=1C Syntax Helper MCP Server
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/help1c-mcp
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

Активируйте сервис:
```bash
sudo systemctl daemon-reload
sudo systemctl enable help1c-mcp
sudo systemctl start help1c-mcp
sudo systemctl status help1c-mcp
```

**Windows Server:**

В `docker-compose.yml` уже установлен `restart: unless-stopped`, поэтому контейнеры автоматически запустятся при загрузке сервера (если Docker Desktop настроен на автозапуск).

---

## 🛠️ Устранение проблем

### Контейнеры не запускаются

**Windows Server:**
```powershell
# Посмотреть логи
docker compose logs

# Порты заняты? Проверить:
netstat -ano | findstr ":8000"
netstat -ano | findstr ":9200"

# Полная переустановка
docker compose down -v
docker compose up -d
```

**Linux Server:**
```bash
# Посмотреть логи
docker compose logs

# Порты заняты? Проверить:
netstat -tulpn | grep -E ":8000|:9200"

# Полная переустановка
docker compose down -v
docker compose up -d
```

### Нет доступа с клиентских машин

**Windows Server:**
```powershell
# Открыть порт в firewall
New-NetFirewallRule -DisplayName "Help1C MCP" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow

# Проверить доступность
Test-NetConnection -ComputerName SERVER_IP -Port 8000
```

**Linux Server:**
```bash
# Ubuntu/Debian
sudo ufw allow 8000/tcp
sudo ufw reload

# CentOS/RHEL
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

### Индексация не работает

**Windows Server:**
```powershell
# Проверить наличие файла
dir C:\help1c-mcp\data\hbk\

# Посмотреть логи контейнера
docker compose logs mcp-server

# Перезапустить реиндексацию
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/index/rebuild"
```

**Linux Server:**
```bash
# Проверить наличие файла
ls -lh /opt/help1c-mcp/data/hbk/

# Посмотреть логи контейнера
docker compose logs mcp-server

# Перезапустить реиндексацию
curl -X POST http://localhost:8000/index/rebuild
```

### Проверить статус здоровья сервиса

**Windows Server:**
```powershell
Invoke-RestMethod http://localhost:8000/health
```

**Linux Server:**
```bash
curl http://localhost:8000/health
```

---

## ✅ Чек-лист развертывания

### Windows Server
- [ ] Docker Desktop установлен и запущен
- [ ] Образ `help1c-mcp:amd64` собран
- [ ] Файл `help1c-mcp-amd64.tar` создан
- [ ] Файлы скопированы в `C:\help1c-mcp\`
- [ ] .hbk файл на месте: `C:\help1c-mcp\data\hbk\1c_documentation.hbk`
- [ ] `docker-compose.yml` обновлен (image: help1c-mcp:amd64)
- [ ] Контейнеры запущены: `docker compose ps`
- [ ] Health check работает: `Invoke-RestMethod http://localhost:8000/health`
- [ ] Порт 8000 открыт в firewall
- [ ] Клиенты могут подключиться: `Invoke-RestMethod http://SERVER_IP:8000/health`

### Linux Server (ARM64)
- [ ] Образ `help1c-mcp:arm64` собран на Windows
- [ ] Файл `help1c-mcp-arm64.tar` создан
- [ ] Файлы скопированы в `/opt/help1c-mcp/`
- [ ] .hbk файл на месте: `/opt/help1c-mcp/data/hbk/1c_documentation.hbk`
- [ ] `docker-compose.yml` обновлен (image: help1c-mcp:arm64)
- [ ] Образ загружен: `docker images | grep help1c-mcp`
- [ ] Контейнеры запущены: `docker compose ps`
- [ ] Health check работает: `curl http://localhost:8000/health`
- [ ] Порт 8000 открыт в firewall (`ufw allow 8000/tcp`)
- [ ] Клиенты могут подключиться: `curl http://SERVER_IP:8000/health`

---

**Дата:** 29.12.2025  
**Версия:** 3
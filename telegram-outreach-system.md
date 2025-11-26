# Telegram Outreach System

Система автоматизированной рассылки сообщений в Telegram с управлением пулом аккаунтов.

## Архитектура

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│  Google Sheets  │◄────│      n8n        │────►│ Telethon API    │
│                 │     │                 │     │                 │
│  • Accounts     │     │  • Workflows    │     │  • Отправка     │
│  • Dialogs      │     │  • GPT логика   │     │  • Приём        │
│  • Users        │     │  • Webhooks     │     │  • Аккаунты     │
│  • Logs         │     │                 │     │  • Прокси       │
│  • Settings     │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Компоненты

### 1. Telethon API Service

FastAPI сервис для работы с Telegram аккаунтами.

**Endpoints:**

| Method | Endpoint | Описание |
|--------|----------|----------|
| POST | /accounts/upload | Загрузка нового аккаунта (tdata/session) |
| POST | /accounts/process | Обработка файла из /incoming |
| GET | /accounts | Список всех аккаунтов |
| POST | /accounts/{id}/check | Проверка статуса аккаунта |
| DELETE | /accounts/{id} | Удаление аккаунта |
| PUT | /accounts/{id}/proxy | Настройка прокси для аккаунта |
| DELETE | /accounts/{id}/proxy | Отключить прокси для аккаунта |
| POST | /send | Отправка сообщения |
| GET | /dialogs/{user_id} | История диалога |
| POST | /settings/proxy | Глобальные настройки прокси |
| GET | /settings | Получить все настройки |

---

## Загрузка аккаунтов

### Поддерживаемые форматы

| Формат | Описание |
|--------|----------|
| ZIP с tdata | Архив с папкой tdata от Telegram Desktop |
| Папка tdata | Напрямую папка tdata |
| .session файл | Готовый файл сессии Telethon |
| Session string | Текстовая строка сессии |

### Способы загрузки

#### Способ 1: Напрямую на сервер (scp/sftp)

```
┌─────────────────────────────────────────────────────────────┐
│                  ПРЯМАЯ ЗАГРУЗКА                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  scp account.zip user@server:/app/incoming/                 │
│       │                                                     │
│       ▼                                                     │
│  File Watcher (inotify или cron каждую минуту)              │
│       │                                                     │
│       ▼                                                     │
│  Новый файл? → POST http://localhost:8000/accounts/process  │
│       │         { "file_path": "/app/incoming/account.zip" }│
│       │                                                     │
│       ▼                                                     │
│  Telethon API обрабатывает                                  │
│       │                                                     │
│       ▼                                                     │
│  Перемещает обработанный файл в /backups                    │
│       │                                                     │
│       ▼                                                     │
│  Webhook → n8n (результат)                                  │
│       │                                                     │
│       ▼                                                     │
│  n8n: добавить в Google Sheets + уведомление                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**File Watcher скрипт (inotify):**

```bash
#!/bin/bash
# /app/scripts/watch_incoming.sh

INCOMING_DIR="/app/incoming"
API_URL="http://localhost:8000/accounts/process"

inotifywait -m -e close_write --format '%f' "$INCOMING_DIR" | while read FILE
do
    if [[ "$FILE" == *.zip ]]; then
        echo "Новый файл: $FILE"
        curl -X POST "$API_URL" \
            -H "Content-Type: application/json" \
            -d "{\"file_path\": \"$INCOMING_DIR/$FILE\"}"
    fi
done
```

**Альтернатива через cron (проще):**

```bash
# crontab -e
* * * * * /app/scripts/process_incoming.sh
```

```bash
#!/bin/bash
# /app/scripts/process_incoming.sh

INCOMING_DIR="/app/incoming"
API_URL="http://localhost:8000/accounts/process"

for file in "$INCOMING_DIR"/*.zip; do
    [ -e "$file" ] || continue
    
    echo "Обработка: $file"
    curl -X POST "$API_URL" \
        -H "Content-Type: application/json" \
        -d "{\"file_path\": \"$file\"}"
done
```

#### Способ 2: Через n8n форму

```
┌─────────────────────────────────────────────────────────────┐
│                  ЗАГРУЗКА ЧЕРЕЗ N8N                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  n8n Form Trigger: https://n8n.server.com/form/add-account  │
│       │                                                     │
│       │  Поля формы:                                        │
│       │  • file: ZIP файл                                   │
│       │  • notes: комментарий (опционально)                 │
│       │                                                     │
│       ▼                                                     │
│  n8n: сохранить файл в /uploads/                            │
│       │                                                     │
│       ▼                                                     │
│  HTTP POST → Telethon API /accounts/upload                  │
│       │      multipart/form-data с файлом                   │
│       │                                                     │
│       ▼                                                     │
│  Telethon API обрабатывает                                  │
│       │                                                     │
│       ├── Success                                           │
│       │      │                                              │
│       │      ▼                                              │
│       │   Google Sheets: добавить аккаунт                   │
│       │      │                                              │
│       │      ▼                                              │
│       │   Response: "Аккаунт +7999... добавлен"             │
│       │                                                     │
│       └── Error                                             │
│              │                                              │
│              ▼                                              │
│           Response: "Ошибка: {причина}"                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Структура папок загрузки

```
/app
├── /incoming                    # Прямая загрузка (scp/sftp)
│   └── *.zip                    # Сюда кидаешь файлы
│
├── /uploads                     # Загрузки через n8n
│   └── /upload_{uuid}
│       └── *.zip
│
├── /temp                        # Временная распаковка
│   └── /processing_{uuid}
│       └── tdata/
│
├── /sessions                    # Готовые .session
│   └── +79991234567.session
│
└── /backups                     # Бэкапы оригиналов
    └── +79991234567_tdata.zip
```

### Процесс загрузки

```
Входной файл (ZIP/tdata/session)
         │
         ▼
┌─────────────────────────┐
│ 1. Определить тип       │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 2. Распаковать (если    │
│    ZIP)                 │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 3. Конвертировать       │
│    tdata → .session     │
│    (opentele)           │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 4. Проверить аккаунт    │
│    • Живой?             │
│    • phone, username    │
│    • Ограничения        │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 5. Сохранить в          │
│    /sessions/           │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 6. Добавить в базу      │
│    status = "warming"   │
└─────────────────────────┘
```

### API загрузки

**Через форму (multipart):**

```
POST /accounts/upload
Content-Type: multipart/form-data

Body:
  - file: ZIP или .session файл
  - type: "tdata_zip" | "tdata_folder" | "session_file" | "session_string"
  - notes: "комментарий" (опционально)

Response (success):
{
    "success": true,
    "account": {
        "id": "acc_5",
        "phone": "+79991234567",
        "username": "user123",
        "first_name": "Иван",
        "status": "warming",
        "message": "Аккаунт добавлен, начинается прогрев"
    }
}

Response (error):
{
    "success": false,
    "error": "account_banned | invalid_tdata | already_exists | conversion_failed",
    "message": "Описание ошибки"
}
```

**Обработка файла из /incoming:**

```
POST /accounts/process
Content-Type: application/json

Body:
{
    "file_path": "/app/incoming/account.zip",
    "notes": "комментарий" (опционально)
}

Response: аналогично /accounts/upload
```

### Код конвертации tdata

```python
# converter.py

from opentele.tl import TelegramClient
from opentele.api import API
import shutil
import zipfile
from pathlib import Path
from uuid import uuid4

async def process_tdata(zip_path: str, notes: str = "") -> dict:
    """Обработка ZIP с tdata"""
    
    temp_dir = Path(f"/app/temp/processing_{uuid4()}")
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # 1. Распаковать
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # 2. Найти tdata
        tdata_path = find_tdata_folder(temp_dir)
        if not tdata_path:
            raise ValueError("tdata папка не найдена в архиве")
        
        # 3. Конвертировать через opentele
        client = TelegramClient(str(tdata_path))
        session_path = f"/app/sessions/{uuid4()}"
        
        telethon_client = await client.ToTelethon(
            session=session_path,
            flag=API.TelegramDesktop
        )
        
        # 4. Проверить и получить инфо
        await telethon_client.connect()
        me = await telethon_client.get_me()
        
        if not me:
            raise ValueError("Не удалось получить информацию об аккаунте")
        
        # 5. Переименовать session файл
        final_session = f"/app/sessions/{me.phone}.session"
        shutil.move(f"{session_path}.session", final_session)
        
        # 6. Бэкап оригинала
        shutil.copy(zip_path, f"/app/backups/{me.phone}_tdata.zip")
        
        # 7. Удалить из incoming
        Path(zip_path).unlink()
        
        await telethon_client.disconnect()
        
        return {
            "success": True,
            "account": {
                "phone": me.phone,
                "username": me.username,
                "first_name": me.first_name,
                "session_file": final_session,
                "status": "warming",
                "notes": notes
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
    
    finally:
        # Очистка temp
        shutil.rmtree(temp_dir, ignore_errors=True)


def find_tdata_folder(base_path: Path) -> Path | None:
    """Поиск папки tdata в распакованном архиве"""
    
    # Прямо в корне
    if (base_path / "tdata").exists():
        return base_path / "tdata"
    
    # В подпапке
    for item in base_path.iterdir():
        if item.is_dir():
            if (item / "tdata").exists():
                return item / "tdata"
            if item.name == "tdata":
                return item
    
    return None
```

### Статусы аккаунтов

| Статус | Описание | Лимит сообщений/день |
|--------|----------|---------------------|
| checking | Только загружен, проверяется | 0 |
| warming | Новый, прогревается | 2-3 |
| active | Рабочий, полный лимит | 7-10 |
| cooldown | Временный отдых (flood warning) | 0 |
| limited | Ограничен Telegram | 0 |
| banned | Забанен | 0 |

### Прогрев аккаунта

```
День 1-2:   Подписка на каналы, чтение (без отправок)
День 3-4:   2-3 сообщения
День 5-7:   5 сообщений/день
День 8+:    status → "active", полный лимит 7-10
```

---

## Прокси

### Обзор

Прокси защищают от бана IP сервера при массовой рассылке. По умолчанию выключены, можно включить глобально или для отдельных аккаунтов.

### Логика выбора прокси

```
Отправка сообщения от acc_1
         │
         ▼
┌─────────────────────────────────────┐
│ Проверить Settings.proxy_enabled   │
└───────────────┬─────────────────────┘
                │
        ┌───────┴───────┐
        │               │
        ▼               ▼
     FALSE            TRUE
        │               │
        ▼               ▼
   Без прокси    Проверить acc_1.use_proxy
                        │
                ┌───────┴───────┐
                │               │
                ▼               ▼
             FALSE            TRUE
                │               │
                ▼               ▼
           Без прокси    Есть proxy_host у acc_1?
                                │
                        ┌───────┴───────┐
                        │               │
                        ▼               ▼
                       Да              Нет
                        │               │
                        ▼               ▼
                  Прокси acc_1    Default прокси из Settings
```

### Типы прокси

| Тип | Описание | Рекомендация |
|-----|----------|--------------|
| socks5 | SOCKS5 прокси | Рекомендуется |
| http | HTTP/HTTPS прокси | Поддерживается |
| mtproto | MTProto прокси | Для обхода блокировок |

### API управления прокси

**Глобальные настройки:**

```
POST /settings/proxy
Content-Type: application/json

Body:
{
    "enabled": true,
    "default_proxy": {
        "type": "socks5",
        "host": "1.2.3.4",
        "port": 1080,
        "username": "user",      // опционально
        "password": "pass"       // опционально
    }
}

Response:
{
    "success": true,
    "message": "Прокси включен глобально"
}
```

**Прокси для конкретного аккаунта:**

```
PUT /accounts/{id}/proxy
Content-Type: application/json

Body:
{
    "use_proxy": true,
    "type": "socks5",
    "host": "5.6.7.8",
    "port": 1080,
    "username": "user",
    "password": "pass"
}

Response:
{
    "success": true,
    "message": "Прокси настроен для аккаунта acc_1"
}
```

**Отключить прокси для аккаунта:**

```
DELETE /accounts/{id}/proxy

Response:
{
    "success": true,
    "message": "Прокси отключен для аккаунта acc_1"
}
```

### Код работы с прокси

```python
# proxy.py

import socks
from telethon import TelegramClient

def get_proxy_config(account: dict, settings: dict) -> dict | None:
    """Определить прокси для аккаунта"""
    
    # Глобально выключено
    if not settings.get('proxy_enabled', False):
        return None
    
    # Для аккаунта выключено
    if not account.get('use_proxy', False):
        return None
    
    # Прокси аккаунта или дефолтный
    host = account.get('proxy_host') or settings.get('default_proxy_host')
    port = account.get('proxy_port') or settings.get('default_proxy_port')
    
    if not host or not port:
        return None
    
    proxy_type_str = account.get('proxy_type') or settings.get('default_proxy_type', 'socks5')
    
    # Определить тип
    if proxy_type_str == 'socks5':
        proxy_type = socks.SOCKS5
    elif proxy_type_str == 'socks4':
        proxy_type = socks.SOCKS4
    elif proxy_type_str == 'http':
        proxy_type = socks.HTTP
    else:
        proxy_type = socks.SOCKS5
    
    proxy = {
        'proxy_type': proxy_type,
        'addr': host,
        'port': int(port),
    }
    
    # Авторизация (если есть)
    user = account.get('proxy_user') or settings.get('default_proxy_user')
    password = account.get('proxy_pass') or settings.get('default_proxy_pass')
    
    if user:
        proxy['username'] = user
        proxy['password'] = password
    
    return proxy


async def get_client(account: dict, settings: dict) -> TelegramClient:
    """Создать клиент с учётом прокси"""
    
    proxy = get_proxy_config(account, settings)
    
    client = TelegramClient(
        account['session_file'],
        settings['api_id'],
        settings['api_hash'],
        proxy=proxy
    )
    
    return client
```

### Рекомендации по прокси

1. **Резидентные прокси** — выглядят как обычные пользователи, лучше датацентровых

2. **Один прокси = один аккаунт** — привязка IP к аккаунту выглядит естественнее

3. **Провайдеры:** Bright Data, IPRoyal, Smartproxy — есть ротация по странам

4. **Для малых объёмов (20-30 сообщений)** — можно начать без прокси

5. **Мониторинг** — если начинаются баны, включить прокси

---

## Отправка сообщений

### Типы сообщений

| Тип | Описание | Параметры |
|-----|----------|-----------|
| text | Текстовое сообщение | content |
| photo | Картинка | file_url/file_base64, caption |
| video_note | Кружок | file_url/file_base64 (квадратное видео, до 60 сек) |
| voice | Голосовое | file_url/file_base64 (.ogg) |
| video | Видео | file_url/file_base64, caption |
| document | Документ/файл | file_url/file_base64, caption, filename |

### API отправки

```
POST /send
Content-Type: application/json

Body:
{
    "user_id": 123456789,
    "account_id": "acc_1",           // опционально, если не указан — автовыбор
    "type": "text | photo | video_note | voice | video | document",
    
    // Для текста:
    "content": "Текст сообщения",
    
    // Для медиа (один из вариантов):
    "file_url": "https://...",       // URL для скачивания
    "file_base64": "base64string",   // Base64 файла
    "file_path": "/path/to/file",    // Локальный путь (для сервера)
    
    // Дополнительно для медиа:
    "caption": "Подпись к фото/видео",
    "filename": "document.pdf"       // Для документов
}

Response (success):
{
    "success": true,
    "message_id": 12345,
    "account_id": "acc_1",
    "account_phone": "+79991234567",
    "proxy_used": true               // использовался ли прокси
}

Response (error):
{
    "success": false,
    "error": "no_available_accounts | user_blocked | flood_wait | account_banned",
    "message": "Описание ошибки",
    "retry_after": 3600              // Для flood_wait — секунды ожидания
}
```

### Требования к файлам

**Кружок (video_note):**
- Формат: MP4
- Разрешение: квадратное (384x384 или 640x640 рекомендуется)
- Длительность: до 60 секунд
- Кодек: H.264

**Голосовое (voice):**
- Формат: OGG с кодеком OPUS
- Или: любой аудиофайл (конвертируется автоматически)

**Фото (photo):**
- Форматы: JPG, PNG, WebP
- Максимум: 10 МБ

**Видео (video):**
- Формат: MP4
- Максимум: 50 МБ (для обычных аккаунтов)

### Автовыбор аккаунта

Если `account_id` не указан, система выбирает автоматически:

```
1. status = "active" ИЛИ "warming"
2. daily_sent < лимит (7 для active, 3 для warming)
3. cooldown_until пустой ИЛИ < now()
4. Не использовался для этого user_id раньше
5. Сортировка: меньше daily_sent → выше приоритет
```

---

## Приём ответов

### Webhook входящих сообщений

Telethon слушает все аккаунты и отправляет входящие в n8n:

```
POST {N8N_WEBHOOK_URL}/incoming

Body:
{
    "user_id": 123456789,
    "username": "john_doe",
    "first_name": "Иван",
    "account_id": "acc_1",
    "account_phone": "+79991234567",
    "message": {
        "id": 12345,
        "text": "Да, расскажи подробнее",
        "date": "2024-01-15T14:30:00Z",
        "type": "text | photo | voice | video | document",
        "file_id": "...",            // Если есть медиа
        "caption": "..."             // Если есть подпись
    }
}
```

### Поток обработки ответа

```
Входящее сообщение на acc_1 от user 123456
         │
         ▼
┌─────────────────────────────────┐
│ Telethon отправляет в n8n       │
│ webhook /incoming               │
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│ n8n: найти диалог в Sheets      │
│ WHERE user_id = 123456          │
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│ Получить stage и account_id     │
│ Проверить: account_id = acc_1?  │
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│ Определить тип ответа:          │
│ • Негатив → стоп               │
│ • Позитив → след. по скрипту   │
│ • Вопрос → GPT                 │
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│ Wait 30-120 сек                 │
│ (естественная задержка)         │
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│ POST /send                      │
│ account_id = acc_1 (тот же!)    │
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│ Обновить Sheets:                │
│ • Dialogs: stage++              │
│ • Accounts: daily_sent++        │
│ • Logs: новая запись            │
└─────────────────────────────────┘
```

---

## Google Sheets структура

### Лист: Accounts

| Колонка | Тип | Описание |
|---------|-----|----------|
| id | string | Уникальный ID (acc_1, acc_2...) |
| phone | string | Номер телефона |
| username | string | Username в Telegram |
| first_name | string | Имя |
| session_file | string | Путь к .session файлу |
| status | string | checking/warming/active/cooldown/limited/banned |
| daily_sent | number | Отправлено сегодня |
| total_sent | number | Отправлено всего |
| cooldown_until | datetime | До когда отдыхает |
| last_used_at | datetime | Последнее использование |
| added_at | datetime | Дата добавления |
| flood_count | number | Сколько раз flood warning |
| use_proxy | boolean | Использовать прокси (TRUE/FALSE) |
| proxy_type | string | socks5/http (если use_proxy=TRUE) |
| proxy_host | string | Хост прокси |
| proxy_port | number | Порт прокси |
| proxy_user | string | Логин прокси (опционально) |
| proxy_pass | string | Пароль прокси (опционально) |
| notes | string | Комментарии |

**Пример:**

| id | phone | status | daily_sent | use_proxy | proxy_type | proxy_host | proxy_port |
|----|-------|--------|------------|-----------|------------|------------|------------|
| acc_1 | +79991234567 | active | 3 | FALSE | | | |
| acc_2 | +79887654321 | warming | 1 | TRUE | socks5 | 1.2.3.4 | 1080 |
| acc_3 | +79776543210 | cooldown | 7 | TRUE | http | 5.6.7.8 | 8080 |

### Лист: Settings

| key | value | description |
|-----|-------|-------------|
| proxy_enabled | FALSE | Глобальный переключатель прокси |
| default_proxy_type | socks5 | socks5 / http |
| default_proxy_host | | Прокси по умолчанию |
| default_proxy_port | | |
| default_proxy_user | | |
| default_proxy_pass | | |
| api_id | 12345678 | Telegram API ID |
| api_hash | abcdef... | Telegram API Hash |
| max_daily_active | 7 | Лимит для active аккаунтов |
| max_daily_warming | 3 | Лимит для warming аккаунтов |
| cooldown_hours | 24 | Часы cooldown после flood |

### Лист: Dialogs

| Колонка | Тип | Описание |
|---------|-----|----------|
| user_id | number | Telegram user ID |
| account_id | string | ID аккаунта (привязка) |
| account_phone | string | Телефон аккаунта |
| stage | number/string | Этап скрипта (1,2,3... или "stopped") |
| status | string | active/stopped/converted |
| first_message_at | datetime | Первое сообщение |
| last_message_sent | string | Последнее отправленное |
| last_response | string | Последний ответ юзера |
| last_response_at | datetime | Время ответа |
| next_message_type | string | Тип след. сообщения |
| notes | string | Комментарии |

**Пример:**

| user_id | account_id | stage | status | last_response |
|---------|------------|-------|--------|---------------|
| 123456 | acc_1 | 2 | active | Да, интересно |
| 789012 | acc_2 | stopped | stopped | Не пиши мне |
| 456789 | acc_1 | 3 | active | Давай созвонимся |

### Лист: Users (очередь на рассылку)

| Колонка | Тип | Описание |
|---------|-----|----------|
| user_id | number | Telegram user ID |
| username | string | Username (если известен) |
| source | string | Откуда взят контакт |
| added_at | datetime | Дата добавления |
| status | string | pending/contacted/in_progress/completed/failed |
| assigned_account | string | Назначенный аккаунт |
| priority | number | Приоритет (1-10) |

### Лист: Logs

| Колонка | Тип | Описание |
|---------|-----|----------|
| timestamp | datetime | Время события |
| account_id | string | ID аккаунта |
| user_id | number | User ID |
| action | string | send/receive/error/status_change |
| message_type | string | text/photo/video_note/voice |
| result | string | success/error |
| error | string | Текст ошибки |
| proxy_used | boolean | Использовался ли прокси |
| details | string | Дополнительно |

### Лист: Scripts (шаблоны сообщений)

| Колонка | Тип | Описание |
|---------|-----|----------|
| stage | number | Номер этапа |
| type | string | text/photo/video_note/voice |
| content | string | Текст или описание |
| file_url | string | URL файла (для медиа) |
| caption | string | Подпись (для медиа) |
| delay_min | number | Мин. задержка перед отправкой (сек) |
| delay_max | number | Макс. задержка (сек) |
| condition | string | Условие (optional) |

**Пример:**

| stage | type | content | file_url | delay_min | delay_max |
|-------|------|---------|----------|-----------|-----------|
| 1 | video_note | Приветственный кружок | https://drive.google.com/... | 0 | 0 |
| 2 | text | Занимаюсь автоматизацией интеграций. Актуально? | | 30 | 90 |
| 3 | photo | Пример работы | https://drive.google.com/... | 60 | 180 |
| 4 | text | Могу показать подробнее. Удобно созвониться? | | 60 | 120 |

---

## n8n Workflows

### 1. Account Upload (форма)

```
┌──────────────────┐
│   Form Trigger   │
│   /add-account   │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│   Write Binary   │
│   File to Disk   │
│   /uploads/      │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│   HTTP Request   │
│   POST /accounts │
│   /upload        │
└────────┬─────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐ ┌───────┐
│Success│ │ Error │
└───┬───┘ └───┬───┘
    │         │
    ▼         ▼
┌───────┐ ┌────────┐
│Sheets │ │Respond │
│Add Row│ │Error   │
└───┬───┘ └────────┘
    │
    ▼
┌────────┐
│Respond │
│Success │
└────────┘
```

### 2. Account Upload (incoming folder)

```
Webhook POST /account-processed (от file watcher)
         │
         ▼
    Parse response from Telethon API
         │
         ├── Success
         │      │
         │      ▼
         │   Google Sheets: Add row (Accounts)
         │      │
         │      ▼
         │   Telegram notification: "Аккаунт {phone} добавлен"
         │
         └── Error
                │
                ▼
           Telegram notification: "Ошибка загрузки: {error}"
```

### 3. Daily Reset

```
Schedule: каждый день 00:00
         │
         ▼
    Google Sheets: Read all (Accounts)
         │
         ▼
    Loop: для каждого аккаунта
         │
         ▼
    Update: daily_sent = 0
         │
         ▼
    If cooldown_until < now():
         Update: status = "active", cooldown_until = ""
```

### 4. Outreach Sender

```
Schedule: каждые 30-60 минут
         │
         ▼
    Google Sheets: Read (Users WHERE status = "pending")
         │
         ▼
    Limit: взять N пользователей
         │
         ▼
    Loop: для каждого
         │
         ├── Google Sheets: найти свободный аккаунт
         │
         ├── Google Sheets: Read (Scripts WHERE stage = 1)
         │
         ├── HTTP → Telethon /send
         │
         ├── Google Sheets: Update Users (status = "contacted")
         │
         ├── Google Sheets: Add row (Dialogs)
         │
         └── Wait: random 60-180 сек
```

### 5. Response Handler

```
Webhook POST /incoming (от Telethon)
         │
         ▼
    Google Sheets: Find (Dialogs WHERE user_id = {user_id})
         │
         ├── Not found → ignore (не наш контакт)
         │
         └── Found
                │
                ▼
         Check негатив:
         IF contains ["нет", "отстань", "спам", "стоп"]:
                │
                ├── Update Dialogs: status = "stopped"
                └── Exit
                │
                ▼
         Google Sheets: Read (Scripts WHERE stage = current + 1)
                │
                ├── No more stages → Update: status = "completed"
                │
                └── Has next stage
                       │
                       ▼
                  Wait: delay_min - delay_max
                       │
                       ▼
                  HTTP → Telethon /send
                  {
                      account_id: same as dialog,
                      type: script.type,
                      content/file_url: script.content
                  }
                       │
                       ▼
                  Google Sheets: Update Dialogs
                  (stage++, last_message_sent, last_response)
                       │
                       ▼
                  Google Sheets: Update Accounts
                  (daily_sent++, total_sent++)
                       │
                       ▼
                  Google Sheets: Add row (Logs)
```

### 6. Health Check

```
Schedule: каждые 6 часов
         │
         ▼
    Google Sheets: Read (Accounts WHERE status IN ["active", "warming"])
         │
         ▼
    Loop: для каждого
         │
         ├── HTTP → Telethon /accounts/{id}/check
         │
         ├── If banned:
         │      Update: status = "banned"
         │      Notification: "Аккаунт {phone} забанен"
         │
         └── If limited:
                Update: status = "limited"
                Notification: "Аккаунт {phone} ограничен"
```

### 7. Follow-up (напоминания)

```
Schedule: каждые 4 часа
         │
         ▼
    Google Sheets: Read (Dialogs WHERE
        status = "active" AND
        last_response_at < now() - 24h AND
        stage < max_stage
    )
         │
         ▼
    Loop: для каждого
         │
         ├── Check: уже отправляли follow-up?
         │
         └── HTTP → Telethon /send
             "Привет! Видел моё сообщение?"
```

### 8. Proxy Toggle

```
Webhook POST /toggle-proxy
         │
         ▼
    Google Sheets: Read (Settings WHERE key = "proxy_enabled")
         │
         ▼
    Toggle value: TRUE ↔ FALSE
         │
         ▼
    Google Sheets: Update (Settings)
         │
         ▼
    Response: "Прокси {enabled/disabled}"
```

---

## Структура файлов сервера

```
/app
├── /incoming                    # Прямая загрузка (scp/sftp)
│   └── *.zip
│
├── /uploads                     # Загрузки через n8n
│   └── /upload_{uuid}
│
├── /sessions                    # .session файлы
│   ├── +79991234567.session
│   ├── +79887654321.session
│   └── ...
│
├── /temp                        # Временные файлы
│   └── /processing_{uuid}
│       └── tdata/
│
├── /media                       # Медиа для отправки
│   ├── /video_notes
│   │   └── greeting.mp4
│   ├── /photos
│   │   └── example.jpg
│   └── /voices
│       └── intro.ogg
│
├── /backups                     # Бэкапы tdata
│   └── +79991234567_tdata.zip
│
├── /scripts                     # Bash скрипты
│   ├── watch_incoming.sh
│   └── process_incoming.sh
│
├── main.py                      # FastAPI приложение
├── accounts.py                  # Управление аккаунтами
├── sender.py                    # Логика отправки
├── listener.py                  # Приём сообщений
├── converter.py                 # Конвертация tdata
├── proxy.py                     # Работа с прокси
├── config.py                    # Настройки
├── sheets.py                    # Google Sheets интеграция
└── requirements.txt
```

---

## Конфигурация

### Environment variables

```bash
# Telegram
API_ID=12345678
API_HASH=abcdef1234567890

# n8n webhooks
N8N_WEBHOOK_INCOMING=https://n8n.example.com/webhook/incoming
N8N_WEBHOOK_STATUS=https://n8n.example.com/webhook/status
N8N_WEBHOOK_ACCOUNT=https://n8n.example.com/webhook/account-processed

# Google Sheets
GOOGLE_SHEETS_ID=1abc...xyz
GOOGLE_CREDENTIALS_FILE=/app/credentials.json

# Limits
MAX_DAILY_ACTIVE=7
MAX_DAILY_WARMING=3
COOLDOWN_HOURS=24

# Proxy (defaults, можно переопределить в Settings)
PROXY_ENABLED=false
DEFAULT_PROXY_TYPE=socks5
DEFAULT_PROXY_HOST=
DEFAULT_PROXY_PORT=
DEFAULT_PROXY_USER=
DEFAULT_PROXY_PASS=

# Server
HOST=0.0.0.0
PORT=8000

# Paths
INCOMING_DIR=/app/incoming
SESSIONS_DIR=/app/sessions
BACKUPS_DIR=/app/backups
```

---

## Безопасность

### Рекомендации

1. **API_ID/API_HASH** — получать со своего аккаунта на my.telegram.org, не использовать с купленных

2. **Задержки** — минимум 30-60 секунд между сообщениями, рандомизировать

3. **Лимиты** — не более 7-10 сообщений/день с одного аккаунта

4. **Персонализация** — использовать вариации текста, имена, разные типы контента

5. **Негатив** — сразу останавливать диалог при негативной реакции

6. **Прогрев** — новые аккаунты обязательно прогревать 5-7 дней

7. **Мониторинг** — следить за flood warnings, при повторных — увеличивать cooldown

8. **Прокси** — использовать резидентные прокси при масштабировании

9. **IP** — не хостить критичные сервисы на том же сервере

---

## Типичные ошибки и решения

| Ошибка | Причина | Решение |
|--------|---------|---------|
| FloodWaitError | Слишком много запросов | status = cooldown, ждать указанное время |
| UserBannedInChannelError | Юзер заблокировал | Пометить диалог как failed |
| PeerIdInvalidError | Неверный user_id | Проверить источник данных |
| SessionExpiredError | Сессия истекла | Перелогиниться или удалить аккаунт |
| PhoneNumberBannedError | Аккаунт забанен | status = banned |
| ConnectionError (proxy) | Прокси недоступен | Проверить прокси, отключить если не работает |

---

## Roadmap

- [ ] Telethon API service (FastAPI)
- [ ] Конвертация tdata → session
- [ ] File watcher для /incoming
- [ ] n8n workflow: загрузка аккаунтов (форма)
- [ ] n8n workflow: загрузка аккаунтов (incoming)
- [ ] n8n workflow: отправка первых сообщений
- [ ] n8n workflow: обработка ответов
- [ ] Поддержка прокси
- [ ] GPT интеграция для умных ответов
- [ ] Веб-интерфейс для управления
- [ ] Статистика и аналитика

# Telegram Outreach System - Web Interface

Полнофункциональный веб-интерфейс на Flask с Bootstrap 5.

## 🚀 Быстрый старт

```bash
cd /root/telespam/telespam
git pull origin claude/implement-system-from-md-01EpcBwxCBNrC3QRHmtTsEns

# Установить зависимости
pip install flask==3.0.0

# Запустить веб-интерфейс
python web_app.py
```

Откроется на **http://localhost:5000**

## 📋 Возможности

### ✅ Реализовано

1. **Аутентификация**
   - Регистрация по email/password
   - Вход/выход
   - Session-based auth

2. **Dashboard**
   - Статистика в реальном времени
   - Карточки с метриками
   - Последние кампании
   - Обзор аккаунтов и пользователей

3. **Кампании**
   - Создание новых кампаний
   - Выбор аккаунтов и пользователей
   - Real-time прогресс (AJAX polling каждые 2 сек)
   - История всех запусков
   - Логи активности

4. **Аккаунты**
   - Просмотр всех Telegram аккаунтов
   - Статистика отправки
   - Rate limits (час/день)
   - Статус прокси

5. **Пользователи**
   - Добавление пользователей для рассылки
   - Поиск по username/user_id/phone
   - Приоритеты
   - Статусы (pending/contacted/completed)

6. **Прокси**
   - Добавление SOCKS5/HTTP прокси
   - Парсинг proxy strings
   - Тестирование подключения
   - Статус (working/failed/untested)

## 🗂️ Структура

```
telespam/
├── web_app.py              # Flask приложение
├── database.py             # SQLite модели (Users, Campaigns)
├── templates/              # HTML шаблоны (Bootstrap 5)
│   ├── base.html          # Базовый layout
│   ├── login.html         # Вход
│   ├── register.html      # Регистрация
│   ├── dashboard.html     # Главная
│   ├── campaigns.html     # Список кампаний
│   ├── new_campaign.html  # Создание кампании
│   ├── campaign_detail.html # Детали + прогресс
│   ├── accounts.html      # Аккаунты
│   ├── users.html         # Пользователи
│   ├── proxies.html       # Прокси
│   ├── 404.html           # Страница не найдена
│   └── 500.html           # Ошибка сервера
├── mock_sheets.py         # Backend (общий с CLI)
├── rate_limiter.py        # Лимиты (общий с CLI)
├── proxy_manager.py       # Прокси (общий с CLI)
└── telespam.db           # SQLite база (автоматически)
```

## 🎯 Архитектура (CLI + Web)

### Общий код (работает и в CLI и в Web):
- `mock_sheets.py` - хранение аккаунтов, пользователей
- `rate_limiter.py` - лимитирование сообщений
- `proxy_manager.py` - управление прокси
- `account_manager.py` - профили аккаунтов

### Web-только:
- `database.py` - пользователи веб-интерфейса, кампании
- `web_app.py` - Flask routes
- `templates/` - Bootstrap 5 UI

### CLI-только:
- `cli_menu.py` - интерактивное меню
- `add_account_cli.py`, `add_users_cli.py` и т.д.

## 📱 Использование

### 1. Первый запуск

```bash
python web_app.py
```

Откройте http://localhost:5000 и зарегистрируйтесь.

### 2. Добавление аккаунтов

Аккаунты добавляются через **CLI** (они автоматически появятся в вебе):

```bash
python cli_menu.py
# Выберите вариант 1, 1a или 1b
```

### 3. Добавление пользователей

Через веб-интерфейс:
- Перейти в "Users"
- Нажать "Add User"
- Указать username, user_id или phone

Или через CLI:
```bash
python cli_menu.py
# Выберите вариант 2
```

### 4. Создание кампании

1. Перейти в "Campaigns" → "New Campaign"
2. Указать название и сообщение
3. Выбрать аккаунты для отправки
4. Выбрать пользователей
5. Нажать "Create Campaign"
6. Наблюдать прогресс в реальном времени

## 🔧 API Endpoints

### Аутентификация
- `GET/POST /register` - Регистрация
- `GET/POST /login` - Вход
- `GET /logout` - Выход

### Основные
- `GET /` - Dashboard
- `GET /campaigns` - Список кампаний
- `GET/POST /campaigns/new` - Создать кампанию
- `GET /campaigns/<id>` - Детали кампании
- `POST /campaigns/<id>/start` - Запустить
- `GET /campaigns/<id>/progress` - Прогресс (JSON)

### Управление
- `GET /accounts` - Аккаунты
- `GET /users` - Пользователи
- `POST /users/add` - Добавить пользователя
- `GET/POST /proxies` - Прокси
- `POST /proxies/add` - Добавить прокси

### API
- `GET /api/stats` - Статистика (JSON)

## 🌐 Деплой на продакшн

### Автоматический деплой (Рекомендуется)

```bash
cd /root/telespam/telespam
sudo bash deploy.sh
```

Скрипт автоматически:
- Установит gunicorn
- Настроит systemd service
- Настроит Nginx reverse proxy
- Запустит все сервисы

После деплоя:
```bash
# Установить SSL сертификат
sudo certbot --nginx -d tgspam.mrktgu.ru

# Проверить статус
sudo systemctl status telespam-web

# Смотреть логи
sudo journalctl -u telespam-web -f
```

---

### Ручной деплой (если нужно)

#### 1. Установить Gunicorn

```bash
pip install gunicorn
which gunicorn  # Должно показать /usr/local/bin/gunicorn
```

#### 2. Создать systemd service

Файл: `/etc/systemd/system/telespam-web.service`

```ini
[Unit]
Description=Telegram Outreach Web Interface
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/telespam/telespam
Environment="SECRET_KEY=change-this-to-random-secret-key"
ExecStart=/usr/local/bin/gunicorn -w 4 -b 127.0.0.1:5000 web_app:app --timeout 120
Restart=always

[Install]
WantedBy=multi-user.target
```

**Важно:** Используйте `/usr/local/bin/gunicorn` (не `/usr/bin/gunicorn`)!

Запустить службу:
```bash
sudo systemctl daemon-reload
sudo systemctl enable telespam-web
sudo systemctl start telespam-web
sudo systemctl status telespam-web
```

#### 3. Настроить Nginx

Файл: `/etc/nginx/sites-available/tgspam.mrktgu.ru`

```nginx
server {
    listen 80;
    server_name tgspam.mrktgu.ru;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeout settings
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Static files
    location /static {
        alias /root/telespam/telespam/static;
        expires 30d;
    }

    client_max_body_size 100M;
}
```

Активировать:
```bash
sudo ln -s /etc/nginx/sites-available/tgspam.mrktgu.ru /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

#### 4. Установить SSL

```bash
sudo certbot --nginx -d tgspam.mrktgu.ru
```

## 🔐 Безопасность

### Рекомендации:

1. **Изменить SECRET_KEY**
   ```bash
   export SECRET_KEY="your-very-long-random-secret-key-here"
   ```

2. **Использовать HTTPS** (обязательно в продакшене)

3. **Ограничить доступ** (firewall, IP whitelist)

4. **Регулярные бэкапы** `telespam.db`

## 📊 База данных

SQLite база автоматически создается при первом запуске:

```
telespam.db
├── users (веб-пользователи)
├── campaigns (история запусков)
└── campaign_logs (логи активности)
```

Для бэкапа:
```bash
cp telespam.db telespam.db.backup
```

## 🐛 Отладка

### Включить debug mode:

В `web_app.py` последняя строка:
```python
app.run(host='0.0.0.0', port=5000, debug=True)
```

### Логи:

```bash
# Смотреть логи systemd
sudo journalctl -u telespam-web -f

# Или запустить напрямую
python web_app.py
```

## ✅ Что работает

- ✅ Регистрация/вход по email
- ✅ Dashboard с live статистикой
- ✅ Создание кампаний
- ✅ Real-time прогресс (AJAX)
- ✅ Управление пользователями
- ✅ Управление прокси
- ✅ Просмотр аккаунтов
- ✅ История кампаний
- ✅ Логи активности
- ✅ Адаптивный дизайн (mobile-friendly)
- ✅ Общий backend с CLI

## 📝 TODO (если нужно)

- [ ] Запуск кампаний (сейчас только создание и прогресс)
- [ ] Редактирование кампаний
- [ ] Удаление пользователей/прокси
- [ ] Экспорт результатов
- [ ] Графики статистики
- [ ] Email уведомления

## 🆘 Поддержка

Вопросы и проблемы:
- Проверьте логи: `sudo journalctl -u telespam-web -f`
- Убедитесь что установлен Flask: `pip install flask==3.0.0`
- Проверьте что порт 5000 свободен: `netstat -tulpn | grep 5000`

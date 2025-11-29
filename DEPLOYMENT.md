# Deployment Guide - tgspam.mrktgu.ru

Полное руководство по развертыванию Telegram Outreach Web Interface на продакшн сервере.

## 📋 Требования

- Ubuntu/Debian сервер
- Python 3.8+
- Nginx
- Certbot (для SSL)
- Доступ к серверу через SSH
- DNS настроен: tgspam.mrktgu.ru → IP сервера

## 🚀 Быстрое развертывание (Автоматическое)

### Шаг 1: Подготовка

```bash
# Подключиться к серверу
ssh root@your-server-ip

# Перейти в директорию проекта
cd /root/telespam/telespam

# Обновить код
git pull origin claude/implement-system-from-md-01EpcBwxCBNrC3QRHmtTsEns
```

### Шаг 2: Запустить автоматический деплой

```bash
sudo bash deploy.sh
```

Скрипт автоматически выполнит:
1. ✅ Установку gunicorn
2. ✅ Установку Flask
3. ✅ Настройку systemd service
4. ✅ Настройку Nginx reverse proxy
5. ✅ Запуск всех сервисов

### Шаг 3: Установить SSL

```bash
sudo certbot --nginx -d tgspam.mrktgu.ru
```

Следовать инструкциям certbot, выбрать:
- Email для уведомлений
- Согласиться с условиями
- Redirect HTTP to HTTPS: Yes (рекомендуется)

### Шаг 4: Проверка

```bash
# Проверить статус службы
sudo systemctl status telespam-web

# Проверить логи
sudo journalctl -u telespam-web -f
```

Открыть в браузере:
- **https://tgspam.mrktgu.ru**

Должна открыться страница регистрации!

---

## 🔧 Ручное развертывание

Если автоматический скрипт не работает, следуйте этим шагам:

### 1. Установить зависимости

```bash
# Установить gunicorn
pip install gunicorn

# Проверить установку
which gunicorn
# Должно показать: /usr/local/bin/gunicorn

# Установить Flask
pip install flask==3.0.0
```

### 2. Создать systemd service

```bash
sudo nano /etc/systemd/system/telespam-web.service
```

Вставить:

```ini
[Unit]
Description=Telegram Outreach Web Interface
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/telespam/telespam
Environment="SECRET_KEY=your-very-long-random-secret-key-here"
ExecStart=/usr/local/bin/gunicorn -w 4 -b 127.0.0.1:5000 web_app:app --timeout 120
Restart=always

[Install]
WantedBy=multi-user.target
```

**ВАЖНО:** Замените `SECRET_KEY` на случайную строку!

Сгенерировать SECRET_KEY:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Сохранить и запустить:
```bash
sudo systemctl daemon-reload
sudo systemctl enable telespam-web
sudo systemctl start telespam-web
sudo systemctl status telespam-web
```

### 3. Настроить Nginx

```bash
sudo nano /etc/nginx/sites-available/tgspam.mrktgu.ru
```

Вставить:

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

Активировать конфигурацию:
```bash
sudo ln -s /etc/nginx/sites-available/tgspam.mrktgu.ru /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 4. Установить SSL

```bash
sudo certbot --nginx -d tgspam.mrktgu.ru
```

---

## ✅ Проверка после деплоя

### 1. Проверить службу

```bash
sudo systemctl status telespam-web
```

Должно показать: **Active: active (running)**

### 2. Проверить логи

```bash
# Логи службы
sudo journalctl -u telespam-web -f

# Логи Nginx
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### 3. Проверить порты

```bash
sudo netstat -tulpn | grep 5000
```

Должно показать gunicorn слушает на 127.0.0.1:5000

### 4. Проверить веб-интерфейс

Открыть в браузере:
- http://tgspam.mrktgu.ru (перенаправит на HTTPS если SSL установлен)
- https://tgspam.mrktgu.ru

Должна открыться страница регистрации с Bootstrap 5 UI.

---

## 🔐 Безопасность

### 1. Изменить SECRET_KEY

В `/etc/systemd/system/telespam-web.service`:

```ini
Environment="SECRET_KEY=your-very-long-random-secret-key-here"
```

Сгенерировать новый ключ:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

После изменения:
```bash
sudo systemctl daemon-reload
sudo systemctl restart telespam-web
```

### 2. Firewall

```bash
# Разрешить только HTTPS
sudo ufw allow 443/tcp
sudo ufw allow 80/tcp  # для Let's Encrypt
sudo ufw enable
```

### 3. Ограничить доступ (опционально)

Если нужен доступ только с определенных IP:

```nginx
# В конфигурации Nginx
location / {
    allow 1.2.3.4;  # Ваш IP
    deny all;

    proxy_pass http://127.0.0.1:5000;
    # ... остальное
}
```

### 4. Регулярные бэкапы

```bash
# Создать бэкап базы данных
cp /root/telespam/telespam/telespam.db /root/backups/telespam-$(date +%Y%m%d).db

# Создать cron для автоматического бэкапа
crontab -e
```

Добавить:
```
0 2 * * * cp /root/telespam/telespam/telespam.db /root/backups/telespam-$(date +\%Y\%m\%d).db
```

---

## 🐛 Troubleshooting

### Проблема: Служба не запускается

```bash
# Проверить логи
sudo journalctl -u telespam-web -n 50

# Проверить что gunicorn установлен
which gunicorn

# Проверить что Flask установлен
python3 -c "import flask; print(flask.__version__)"

# Попробовать запустить вручную
cd /root/telespam/telespam
gunicorn -w 1 -b 127.0.0.1:5000 web_app:app
```

### Проблема: 502 Bad Gateway

Nginx не может подключиться к gunicorn:

```bash
# Проверить что служба запущена
sudo systemctl status telespam-web

# Проверить что порт 5000 слушается
sudo netstat -tulpn | grep 5000

# Проверить логи Nginx
sudo tail -f /var/log/nginx/error.log
```

### Проблема: Permission denied

```bash
# Проверить права на файлы
ls -la /root/telespam/telespam/

# Проверить права на sessions
ls -la /root/telespam/telespam/sessions/

# При необходимости исправить
chmod -R 755 /root/telespam/telespam/
```

### Проблема: Database locked

Если SQLite база заблокирована:

```bash
# Остановить службу
sudo systemctl stop telespam-web

# Проверить процессы
ps aux | grep web_app

# Удалить lock файл
rm -f /root/telespam/telespam/telespam.db-journal

# Запустить снова
sudo systemctl start telespam-web
```

---

## 🔄 Обновление

После изменений в коде:

```bash
cd /root/telespam/telespam

# Получить обновления
git pull origin claude/implement-system-from-md-01EpcBwxCBNrC3QRHmtTsEns

# Перезапустить службу
sudo systemctl restart telespam-web

# Проверить статус
sudo systemctl status telespam-web

# Смотреть логи
sudo journalctl -u telespam-web -f
```

---

## 📊 Мониторинг

### Смотреть логи в реальном времени

```bash
# Логи приложения
sudo journalctl -u telespam-web -f

# Логи Nginx access
sudo tail -f /var/log/nginx/access.log

# Логи Nginx error
sudo tail -f /var/log/nginx/error.log
```

### Проверить использование ресурсов

```bash
# Процессы gunicorn
ps aux | grep gunicorn

# Использование памяти
free -h

# Использование диска
df -h
```

### Перезапуск служб

```bash
# Перезапустить веб-приложение
sudo systemctl restart telespam-web

# Перезапустить Nginx
sudo systemctl restart nginx

# Перезапустить обе службы
sudo systemctl restart telespam-web nginx
```

---

## ✨ Первый вход

После успешного деплоя:

1. Открыть https://tgspam.mrktgu.ru
2. Нажать "Register"
3. Ввести email и пароль
4. Войти в систему
5. Добавить аккаунты через CLI (они появятся в вебе автоматически)
6. Добавить пользователей через веб-интерфейс
7. Создать первую кампанию!

---

## 📞 Поддержка

Если что-то не работает:

1. Проверьте логи: `sudo journalctl -u telespam-web -f`
2. Проверьте статус: `sudo systemctl status telespam-web`
3. Проверьте Nginx: `sudo nginx -t`
4. Проверьте DNS: `nslookup tgspam.mrktgu.ru`
5. Проверьте SSL: `sudo certbot certificates`

# Исправление прав доступа к базе данных

## Проблема
Ошибка `attempt to write a readonly database` возникает, когда база данных SQLite недоступна для записи.

## Важно: Разница между системным пользователем и зарегистрированным пользователем

**Системный пользователь (пользователь ОС)** - это пользователь, от имени которого запускается веб-сервер (gunicorn). Это может быть:
- `www-data` (стандартный пользователь для веб-серверов на Debian/Ubuntu)
- `gunicorn` (специальный пользователь для gunicorn)
- `root` (не рекомендуется для продакшена)
- Другой системный пользователь, указанный в systemd service

**Зарегистрированный пользователь в веб-интерфейсе** - это запись в таблице `users` в базе данных. Это просто данные для авторизации в веб-интерфейсе, а не системный пользователь ОС.

**База данных должна принадлежать системному пользователю**, который запускает веб-сервер, а НЕ зарегистрированному пользователю в веб-интерфейсе.

Пример:
- Веб-сервер запускается от пользователя `www-data` (системный пользователь)
- В веб-интерфейсе зарегистрирован пользователь `admin@example.com` (запись в БД)
- База данных `telespam.db` должна принадлежать `www-data`, а не `admin@example.com`

## Быстрое решение

### Вариант 1: Автоматический скрипт (рекомендуется)

```bash
# Локально (macOS/Linux)
bash fix_db_permissions_simple.sh

# На сервере (может потребоваться sudo)
sudo bash fix_db_permissions_simple.sh
```

### Вариант 2: Ручное исправление

```bash
# 1. Найдите путь к базе данных
cd /path/to/telespam
ls -la telespam.db

# 2. Исправьте права на директорию
chmod 755 .

# 3. Исправьте права на файл базы данных
chmod 664 telespam.db

# 4. Если запущено от другого пользователя (например, gunicorn)
# Определите пользователя веб-сервера
ps aux | grep gunicorn | grep -v grep

# Установите владельца
sudo chown gunicorn_user:gunicorn_user telespam.db
sudo chown gunicorn_user:gunicorn_user .
```

### Вариант 3: Для systemd сервиса

```bash
# 1. Определите системного пользователя из systemd (это НЕ зарегистрированный пользователь в веб-интерфейсе!)
SYSTEM_USER=$(sudo systemctl show -p User telespam-web.service | cut -d= -f2)
echo "Системный пользователь веб-сервера: $SYSTEM_USER"

# 2. Исправьте права (база данных должна принадлежать системному пользователю)
sudo chmod 755 /path/to/telespam
sudo chmod 664 /path/to/telespam/telespam.db
sudo chown $SYSTEM_USER:$SYSTEM_USER /path/to/telespam/telespam.db
sudo chown $SYSTEM_USER:$SYSTEM_USER /path/to/telespam

# 3. Также исправьте права на WAL и SHM файлы
sudo chmod 664 /path/to/telespam/telespam.db-wal 2>/dev/null || true
sudo chmod 664 /path/to/telespam/telespam.db-shm 2>/dev/null || true
sudo chown $SYSTEM_USER:$SYSTEM_USER /path/to/telespam/telespam.db-wal 2>/dev/null || true
sudo chown $SYSTEM_USER:$SYSTEM_USER /path/to/telespam/telespam.db-shm 2>/dev/null || true

# 4. Перезапустите сервис
sudo systemctl restart telespam-web
```

## Автоматическое исправление в коде

Код в `database.py` теперь автоматически пытается исправить права доступа при обнаружении ошибки `readonly`. Однако, если у процесса нет прав на изменение прав доступа, потребуется ручное исправление.

## Проверка прав

```bash
# Проверьте текущие права
ls -la telespam.db

# Должно быть примерно так:
# -rw-rw-r-- 1 user user 123456 Dec  6 12:00 telespam.db
#   ^^^ ^^^ ^^^
#   ||| ||| |||
#   ||| ||| +++-- другие пользователи: чтение
#   ||| +++------ группа: чтение и запись
#   +++---------- владелец: чтение и запись
```

## Типичные проблемы

### 1. Файл создан от root, а веб-сервер работает от другого системного пользователя

**Проблема**: База данных создана от `root`, но веб-сервер работает от другого пользователя (например, `www-data`).

**Решение**: Измените владельца на системного пользователя веб-сервера (НЕ на зарегистрированного пользователя в веб-интерфейсе!):

```bash
# Определите системного пользователя веб-сервера
SYSTEM_USER=$(sudo systemctl show -p User telespam-web.service | cut -d= -f2)
# или
SYSTEM_USER=$(ps aux | grep gunicorn | grep -v grep | head -1 | awk '{print $1}')

# Измените владельца
sudo chown $SYSTEM_USER:$SYSTEM_USER telespam.db
sudo chown $SYSTEM_USER:$SYSTEM_USER telespam.db-wal 2>/dev/null || true
sudo chown $SYSTEM_USER:$SYSTEM_USER telespam.db-shm 2>/dev/null || true
```

### 2. Директория недоступна для записи

```bash
# Решение: исправьте права на директорию
chmod 755 /path/to/telespam
```

### 3. Файл находится в защищенной директории

```bash
# Решение: переместите базу данных в доступную директорию
# Или измените путь в database.py
```

## Настройка пути к базе данных

По умолчанию база данных находится в `telespam.db` в корне проекта.

Чтобы изменить путь, отредактируйте инициализацию в `database.py`:

```python
# В конце файла database.py
db = Database("custom/path/to/database.db")
```

Или через переменную окружения:

```bash
export DB_PATH="/path/to/custom/database.db"
```

## Логирование

При возникновении ошибки `readonly`, код автоматически:
1. Пытается исправить права на файл (`chmod 664`)
2. Пытается исправить права на директорию (`chmod 755`)
3. Повторяет попытку подключения
4. Выдает подробное сообщение об ошибке с текущими правами

## Дополнительная информация

- SQLite требует права на запись как для файла, так и для директории
- WAL (Write-Ahead Logging) режим создает дополнительные файлы (`-wal`, `-shm`)
- Эти файлы также должны быть доступны для записи


# Исправление прав доступа к базе данных

## Проблема
Ошибка `attempt to write a readonly database` возникает, когда база данных SQLite недоступна для записи.

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
# 1. Определите пользователя из systemd
sudo systemctl show -p User telespam-web.service

# 2. Исправьте права
sudo chmod 755 /path/to/telespam
sudo chmod 664 /path/to/telespam/telespam.db
sudo chown gunicorn_user:gunicorn_user /path/to/telespam/telespam.db
sudo chown gunicorn_user:gunicorn_user /path/to/telespam

# 3. Перезапустите сервис
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

### 1. Файл создан от root, а веб-сервер работает от другого пользователя

```bash
# Решение: измените владельца
sudo chown www-data:www-data telespam.db
# или
sudo chown gunicorn:gunicorn telespam.db
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


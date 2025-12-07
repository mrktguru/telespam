# Debugging "Worker failed to boot" Error

Если gunicorn не может запустить worker, выполните следующие шаги:

## Шаг 1: Запустите диагностический скрипт

```bash
cd /root/telespam/telespam
python3 diagnose_web_app.py
```

Этот скрипт проверит:
- Версию Python
- Все импорты
- Инициализацию базы данных
- Импорт web_app.py

## Шаг 2: Проверьте логи gunicorn напрямую

```bash
cd /root/telespam/telespam
gunicorn --check-config web_app:app
```

Или попробуйте запустить напрямую:

```bash
cd /root/telespam/telespam
python3 -c "from web_app import app; print('OK')"
```

## Шаг 3: Проверьте синтаксис

```bash
cd /root/telespam/telespam
python3 -m py_compile web_app.py
python3 -m py_compile database.py
python3 -m py_compile accounts.py
```

## Шаг 4: Проверьте зависимости

```bash
pip3 list | grep -E "(flask|telethon|sqlite)"
```

## Шаг 5: Проверьте права доступа к базе данных

```bash
cd /root/telespam/telespam
ls -la telespam.db*
chmod 664 telespam.db 2>/dev/null
chmod 664 telespam.db-wal 2>/dev/null
chmod 664 telespam.db-shm 2>/dev/null
```

## Шаг 6: Проверьте рабочую директорию

Gunicorn должен запускаться из директории, где находится `web_app.py`:

```bash
cd /root/telespam/telespam
pwd  # Должно быть /root/telespam/telespam
ls web_app.py  # Должен существовать
```

## Шаг 7: Проверьте systemd service файл

```bash
cat /etc/systemd/system/telespam-web.service
```

Убедитесь, что:
- `WorkingDirectory` указывает на правильную директорию
- `ExecStart` использует правильный путь к gunicorn
- `User` имеет права на доступ к файлам

## Шаг 8: Попробуйте запустить вручную

```bash
cd /root/telespam/telespam
source /path/to/venv/bin/activate  # Если используется venv
gunicorn --bind 127.0.0.1:5000 web_app:app
```

Если это работает, проблема в systemd конфигурации.

## Частые проблемы:

1. **Синтаксическая ошибка в Python коде** - проверьте `python3 -m py_compile web_app.py`
2. **Отсутствующие зависимости** - проверьте `pip3 list`
3. **Проблемы с правами доступа к базе данных** - проверьте `ls -la telespam.db*`
4. **Неправильная рабочая директория** - проверьте `WorkingDirectory` в systemd service
5. **Проблемы с путями** - убедитесь, что все пути относительные или абсолютные правильно указаны


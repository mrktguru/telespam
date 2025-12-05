# Проверка API Credentials

## Проблема
Ошибки "No user has 'username' as username" при отправке, хотя username существует.

Это может быть из-за:
1. **API_ID/API_HASH не установлены или неправильные**
2. Аккаунт-отправитель имеет ограничения
3. Аккаунт новый и не может искать пользователей

## Шаг 1: Проверьте API credentials

Выполните на сервере:
```bash
cd ~/telespam/telespam
python3 -c "import config; print(f'API_ID: {config.API_ID}'); print(f'API_HASH: {config.API_HASH}')"
```

Если выводит `None` - credentials не установлены!

## Шаг 2: Создайте .env файл

```bash
cd ~/telespam/telespam
nano .env
```

Добавьте (замените на ваши реальные значения):
```
API_ID=your_api_id_here
API_HASH=your_api_hash_here
```

Получить API_ID и API_HASH можно на: https://my.telegram.org/apps

## Шаг 3: Перезапустите сервис

```bash
sudo systemctl restart telespam
```

## Шаг 4: Проверьте логи отправки

Добавьте в начало функции send_message_to_user диагностику:
```python
print(f"DEBUG: API_ID = {config.API_ID}")
print(f"DEBUG: API_HASH = {config.API_HASH}")
```

## Альтернативная проблема: Ограничения аккаунта

Если API credentials правильные, проблема может быть в аккаунте 12297082263:
- Аккаунт новый (< 7 дней) - не может искать пользователей
- Аккаунт имеет флуд-ограничения
- Аккаунт забанен за спам

**Решение:** Используйте другой, старый аккаунт для отправки.

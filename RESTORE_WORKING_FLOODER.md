# Восстановление рабочего флудера

## Проблема

Вы откатили проект и потеряли рабочую конфигурацию. Сейчас не работает отправка потому что:

1. ❌ Нет username для пользователей
2. ❌ Нет session файлов с закэшированными entities
3. ❌ Telethon не может найти access_hash для незнакомых пользователей

## Как это работало раньше

**КЛЮЧЕВОЙ МОМЕНТ:** Отправка незнакомым пользователям работает ТОЛЬКО если:
- ✅ У вас есть **username** пользователя, ИЛИ
- ✅ У вас есть **access_hash** (получен из парсинга чатов или диалогов)

**БЕЗ username или access_hash - отправка НЕВОЗМОЖНА!** Это ограничение Telegram API.

## Решение: Пошаговая инструкция

### Шаг 1: Добавьте аккаунт с session/tdata

Если у вас есть купленный аккаунт с session файлом:

```bash
# Скопируйте session файл в папку sessions/
mkdir -p sessions
cp /path/to/your/37258591162.session sessions/

# Добавьте аккаунт в базу через CLI
python3 main.py
# Выберите: 1. Add account (TDATA/SESSION/JSON)
```

**ВАЖНО:** Убедитесь что session создан с вашими API credentials (api_id=37708785)!

Если session создан с другими credentials (например Telegram Desktop api_id=611335), нужно:
1. Либо пересоздать session с правильными credentials
2. Либо использовать те же credentials что были при создании

### Шаг 2: Получите usernames для целевых пользователей

#### Вариант A: Если у вас уже есть usernames

Создайте CSV файл `users_to_send.csv`:

```csv
username,user_id,phone,priority
champfreak,7115610560,,1
some_user,157625351,,1
another_user,123456789,,1
```

Затем импортируйте:

```bash
python3 main.py
# Выберите: 2. Add users for outreach
```

#### Вариант B: Парсинг из общих чатов/каналов

Если у вас есть общий чат с целевыми пользователями:

```bash
# Распарсите участников чата
python3 parse_chat_members.py @your_channel

# Это создаст файл parsed_users.json
# И закэширует access_hash в session файле
```

После парсинга вы сможете отправлять сообщения этим пользователям по user_id!

### Шаг 3: Настройте API credentials

Убедитесь что в `.env` файле:

```
API_ID=37708785
API_HASH=7ed610a63e994fc092c67de2140a7465
```

### Шаг 4: Запустите отправку

```bash
python3 start_outreach_cli.py
```

## Технические детали

### Почему нужен username или access_hash?

Telegram API требует передавать `InputPeer` для отправки сообщений:

```python
# ❌ НЕ РАБОТАЕТ для незнакомых пользователей:
await client.send_message(157625351, "message")

# ✅ РАБОТАЕТ - с username:
await client.send_message("@username", "message")

# ✅ РАБОТАЕТ - с access_hash:
from telethon.tl.types import InputPeerUser
peer = InputPeerUser(user_id=157625351, access_hash=123456789012345)
await client.send_message(peer, "message")
```

### Откуда взять access_hash?

1. **Из контактов** - если пользователь в контактах
2. **Из диалогов** - если был диалог с пользователем
3. **Из чатов/каналов** - если пользователь в общем чате
4. **Из поиска по username** - `client.get_entity("@username")` кэширует access_hash

### Как работает кэширование в Telethon?

Когда вы вызываете:
```python
user = await client.get_entity("@username")
```

Telethon:
1. Запрашивает данные пользователя у Telegram
2. Получает `user_id` И `access_hash`
3. **Кэширует их в session файле**
4. Теперь можете отправлять по `user_id` без username!

```python
# Первый раз - резолвим username
user = await client.get_entity("@username")

# access_hash закэширован в session!
# Теперь можем использовать user_id
await client.send_message(user.id, "message")  # ✅ Работает!
```

## Практический пример: Полный workflow

### 1. Подготовка

```bash
# Добавьте session файл
cp your_account.session sessions/37258591162.session

# Добавьте аккаунт
python3 main.py  # Выберите option 1
```

### 2. Получение entities

**Вариант 1 - Есть usernames:**

```bash
# Создайте CSV с usernames
cat > users.csv << EOF
username,user_id,phone,priority
testuser,123456789,,1
anotheruser,987654321,,1
EOF

# Импортируйте
python3 main.py  # Выберите option 2
```

**Вариант 2 - Парсинг чата:**

```bash
# Распарсите чат
python3 parse_chat_members.py @target_channel

# Entities теперь в session файле!
```

### 3. Отправка

```bash
# Запустите рассылку
python3 start_outreach_cli.py
```

## Отладка

### Проверка session файла:

```bash
python3 test_send_message.py
# Попробуйте отправить тестовое сообщение
```

### Проверка entities в session:

```python
from telethon import TelegramClient

client = TelegramClient('sessions/37258591162', 37708785, 'your_api_hash')
await client.connect()

# Попробуйте получить entity
try:
    user = await client.get_entity(157625351)
    print(f"✅ Entity found: {user.first_name}")
except:
    print("❌ Entity not found - нужен username или парсинг")

await client.disconnect()
```

### Проверка API credentials:

```bash
python3 test_auth_key.py sessions/37258591162.session
```

## Частые ошибки

### "Could not find the input entity"

**Причина:** Нет access_hash для этого пользователя

**Решение:**
1. Добавьте username в CSV
2. Или распарсите из общего чата

### "No available accounts"

**Причина:**
1. Аккаунты не добавлены в базу
2. Статус аккаунта не `active` или `warming`
3. Достигнут дневной лимит

**Решение:**
```bash
python3 main.py  # Option 3 - View system status
```

### "Session file not found"

**Причина:** Session файл не в папке `sessions/`

**Решение:**
```bash
mkdir -p sessions
cp your_account.session sessions/PHONE.session
```

## Выводы

Для работы флудера **ОБЯЗАТЕЛЬНО** нужно:

1. ✅ Session/tdata файлы с правильными API credentials
2. ✅ Username ИЛИ access_hash для каждого целевого пользователя
3. ✅ Аккаунты добавлены в базу с правильным статусом

**БЕЗ username или access_hash отправка незнакомым людям НЕВОЗМОЖНА!**

---

**Рекомендуемый workflow:**

1. Парсите участников целевых чатов → получаете access_hash
2. Сохраняете user_id + username в CSV
3. Импортируете в базу
4. Запускаете рассылку

**Или:**

1. Парсите только usernames
2. Сохраняете в CSV
3. Импортируете
4. Первая отправка резолвит username → кэширует access_hash
5. Последующие отправки работают даже если username изменится

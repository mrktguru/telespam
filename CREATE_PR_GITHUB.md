# Как создавать Pull Requests на GitHub

## ✅ Pull Request успешно создан!

**PR #115**: Fix: Simplify username resolution for spam/outreach to unknown users  
**URL**: https://github.com/mrktguru/telespam/pull/115  
**Status**: OPEN (готов к мержу)

---

## GitHub Token сохранен

Ваш GitHub Personal Access Token сохранен в файле `.github-token` (добавлен в .gitignore для безопасности).

**Token**: `ghp_XXXX...` (сохранен локально в `.github-token`)

### Где используется токен:

1. **Git remote** настроен на использование токена:
   ```bash
   git remote -v
   # origin https://YOUR_TOKEN@github.com/mrktguru/telespam.git
   ```

2. **Git credentials** сохранены в `~/.git-credentials`:
   ```bash
   cat ~/.git-credentials
   # https://YOUR_TOKEN@github.com
   ```

---

## Как использовать в будущем

### 1. Push изменений в GitHub

```bash
cd /project/workspace/telespam

# Создать новую ветку
git checkout -b feature/my-new-feature

# Сделать изменения и закоммитить
git add .
git commit -m "feat: add new feature"

# Запушить (токен уже настроен!)
git push -u origin feature/my-new-feature
```

### 2. Создать Pull Request через API

```bash
# Прочитать токен из файла
GITHUB_TOKEN=$(cat .github-token)

# Создать PR
curl -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/mrktguru/telespam/pulls \
  -d '{
    "title": "My New Feature",
    "head": "feature/my-new-feature",
    "base": "main",
    "body": "Description of the changes"
  }'
```

### 3. Создать PR через веб-интерфейс

После `git push`, GitHub покажет ссылку:
```
remote: Create a pull request for 'feature/my-new-feature' on GitHub by visiting:
remote:   https://github.com/mrktguru/telespam/pull/new/feature/my-new-feature
```

Просто откройте эту ссылку в браузере.

---

## Текущий PR #115

### Что делает этот PR:

**Проблема**:
- Ошибка при отправке сообщений по username незнакомым пользователям
- Система пыталась получить `access_hash`, что не работает для spam/outreach

**Решение**:
- Упростили код: отправка напрямую по username без access_hash
- Telethon сам разрешает username и отправляет сообщения
- Удалено 112 строк сложной логики, добавлено 12 строк простой

**Изменения**:
- `web_app.py`: Упрощена функция `send_message_to_user()`
- Добавлены 3 документа с инструкциями

**Проверки пройдены**:
- ✅ Python syntax validation
- ✅ AST parsing
- ✅ No breaking changes

### Как смержить PR:

#### Вариант 1: Через веб-интерфейс (рекомендуется)

1. Откройте: https://github.com/mrktguru/telespam/pull/115
2. Нажмите зеленую кнопку **"Merge pull request"**
3. Подтвердите: **"Confirm merge"**
4. Готово! ✅

#### Вариант 2: Через командную строку

```bash
cd /project/workspace/telespam

# Переключиться на main
git checkout main

# Смержить изменения
git merge fix/username-spam-direct-send

# Запушить в main
git push origin main
```

#### Вариант 3: Через GitHub CLI (если установлен)

```bash
gh pr merge 115 --merge
```

---

## После мержа

### 1. Развернуть на production сервере

```bash
# На production сервере
cd /path/to/telespam
git pull origin main

# Перезапустить приложение
sudo systemctl restart telespam-web
# или
pkill -f web_app.py && python3 web_app.py &
```

### 2. Протестировать фикс

```bash
# В логах должно быть:
tail -f /var/log/telespam/web_app.log

# Или через systemd:
journalctl -u telespam-web -f
```

Ожидаемый результат:
```
DEBUG: ===== PRIORITY 1: Sending by USERNAME: mrgekko =====
DEBUG: For spam/outreach to unknown users, sending directly by username
DEBUG: ✓ Using direct username for spam: @mrgekko
✓ Sent to mrgekko (Username) from 12094332128
DEBUG: ✓ Message sent successfully using method: direct_username
```

### 3. Удалить feature branch (опционально)

```bash
# Локально
git branch -d fix/username-spam-direct-send

# На GitHub
git push origin --delete fix/username-spam-direct-send
```

---

## Управление токеном

### Проверить текущий токен:

```bash
cat /project/workspace/telespam/.github-token
```

### Обновить токен (если истек или изменился):

```bash
cd /project/workspace/telespam

# Обновить в файле
echo "NEW_TOKEN_HERE" > .github-token

# Обновить git remote
git remote set-url origin https://$(cat .github-token)@github.com/mrktguru/telespam.git

# Обновить credentials
echo "https://$(cat .github-token)@github.com" > ~/.git-credentials
```

### Отозвать токен (для безопасности):

1. Откройте: https://github.com/settings/tokens
2. Найдите ваш токен в списке
3. Нажмите **"Delete"**
4. Создайте новый токен с разрешениями `repo` (full control)
5. Обновите токен как указано выше

---

## Дополнительные команды

### Посмотреть все открытые PR:

```bash
GITHUB_TOKEN=$(cat .github-token)
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/mrktguru/telespam/pulls?state=open | \
  python3 -c "import sys, json; prs = json.load(sys.stdin); [print(f'PR #{pr[\"number\"]}: {pr[\"title\"]}') for pr in prs]"
```

### Закрыть PR без мержа:

```bash
GITHUB_TOKEN=$(cat .github-token)
curl -X PATCH \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/mrktguru/telespam/pulls/115 \
  -d '{"state": "closed"}'
```

### Добавить комментарий к PR:

```bash
GITHUB_TOKEN=$(cat .github-token)
curl -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/mrktguru/telespam/issues/115/comments \
  -d '{"body": "LGTM! Ready to merge ✅"}'
```

---

## Workflow для будущих изменений

### Стандартный процесс:

1. **Создать feature branch**:
   ```bash
   git checkout -b feature/description
   ```

2. **Сделать изменения**:
   ```bash
   # Редактировать файлы
   git add .
   git commit -m "feat: description"
   ```

3. **Запушить** (токен уже настроен):
   ```bash
   git push -u origin feature/description
   ```

4. **Создать PR**:
   - Через веб: открыть ссылку из output
   - Через API: использовать команду curl выше

5. **Смержить PR**:
   - Через веб: нажать "Merge pull request"
   - Через CLI: `git merge` команды

6. **Развернуть**:
   ```bash
   # На production
   git pull origin main
   sudo systemctl restart telespam-web
   ```

7. **Протестировать** и проверить логи

---

## Безопасность

### ⚠️ Важно:

1. **Не коммитьте токен в git**:
   - Файл `.github-token` добавлен в `.gitignore` ✅
   
2. **Не делитесь токеном публично**:
   - Это ваш личный токен с полным доступом к репозиторию
   
3. **Храните токен безопасно**:
   - Файл `.github-token` доступен только на этом сервере
   - `~/.git-credentials` также локальный файл
   
4. **Периодически обновляйте токен**:
   - GitHub рекомендует создавать токены с истечением срока
   - Создайте новый токен перед истечением старого

---

## Готово! ✅

- ✅ GitHub токен сохранен и настроен
- ✅ Pull Request #115 создан и открыт
- ✅ Изменения готовы к мержу
- ✅ Документация добавлена

**Следующий шаг**: Смержить PR и развернуть на production!

**PR URL**: https://github.com/mrktguru/telespam/pull/115

#!/bin/bash
# Диагностика проблемы отправки

echo "=== ПРОВЕРКА API CREDENTIALS ==="
cd ~/telespam/telespam
python3 -c "import config; print(f'API_ID: {config.API_ID}'); print(f'API_HASH: {\"SET\" if config.API_HASH else \"NOT SET\"}')"

echo ""
echo "=== ПРОВЕРКА ЛОГОВ ОТПРАВКИ ==="
echo "Ищем DEBUG вывод с API credentials..."
sudo journalctl -u telespam-web --since "5 minutes ago" | grep "DEBUG: API_ID" | tail -5

echo ""
echo "=== ИНФОРМАЦИЯ ОБ АККАУНТЕ ==="
echo "Проверяем статус аккаунта 12297082263..."
sqlite3 telespam.db "SELECT phone, status, created_at, last_used_at FROM accounts WHERE phone LIKE '%12297082263%';"

echo ""
echo "=== ВОЗМОЖНЫЕ ПРИЧИНЫ ==="
echo "1. Аккаунт новый (< 7 дней) - не может искать пользователей"
echo "2. Аккаунт имеет спам-ограничения"
echo "3. Аккаунт не прошел warming период"
echo "4. API credentials неправильные"

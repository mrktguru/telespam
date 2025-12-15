#!/bin/bash
# 🔍 Campaign Issue Diagnostic Script

echo "=========================================="
echo "🔍 Diagnosing Campaign Issues"
echo "=========================================="
echo ""

DB_FILE="telespam.db"

if [ ! -f "$DB_FILE" ]; then
    echo "❌ Database file not found: $DB_FILE"
    exit 1
fi

echo "Step 1: Checking last campaign..."
echo "---"
sqlite3 "$DB_FILE" << 'EOF'
SELECT 
    id, 
    name, 
    status, 
    total_users, 
    sent_count, 
    failed_count,
    created_at
FROM campaigns 
ORDER BY id DESC 
LIMIT 3;
EOF
echo ""

echo "Step 2: Checking campaign users for last campaign..."
LAST_CAMPAIGN_ID=$(sqlite3 "$DB_FILE" "SELECT id FROM campaigns ORDER BY id DESC LIMIT 1;")
echo "Campaign ID: $LAST_CAMPAIGN_ID"
echo "---"
sqlite3 "$DB_FILE" << EOF
SELECT 
    COUNT(*) as total_users
FROM campaign_users 
WHERE campaign_id = $LAST_CAMPAIGN_ID;
EOF
echo ""

echo "Step 3: Checking campaign users details..."
echo "---"
sqlite3 "$DB_FILE" << EOF
SELECT 
    id,
    username,
    user_id,
    phone,
    status,
    priority
FROM campaign_users 
WHERE campaign_id = $LAST_CAMPAIGN_ID
LIMIT 10;
EOF
echo ""

echo "Step 4: Checking campaign settings..."
echo "---"
sqlite3 "$DB_FILE" << EOF
SELECT settings FROM campaigns WHERE id = $LAST_CAMPAIGN_ID;
EOF
echo ""

echo "Step 5: Checking campaign logs..."
echo "---"
sqlite3 "$DB_FILE" << EOF
SELECT 
    message,
    level,
    timestamp
FROM campaign_logs 
WHERE campaign_id = $LAST_CAMPAIGN_ID
ORDER BY timestamp DESC
LIMIT 10;
EOF
echo ""

echo "Step 6: Checking account_campaign_limits..."
echo "---"
sqlite3 "$DB_FILE" << EOF
SELECT 
    account_phone,
    messages_sent,
    messages_limit,
    status
FROM account_campaign_limits
WHERE campaign_id = $LAST_CAMPAIGN_ID;
EOF
echo ""

echo "Step 7: Recent service logs..."
echo "---"
sudo journalctl -u telespam-web --since "5 minutes ago" | tail -50
echo ""

echo "=========================================="
echo "Diagnosis Complete!"
echo "=========================================="

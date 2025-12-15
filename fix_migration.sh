#!/bin/bash
# 🔧 Fix Migration Script
# This script manually creates the account_campaign_limits table if it doesn't exist

echo "=========================================="
echo "🔧 Fixing Migration Issue"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

DB_FILE="telespam.db"

if [ ! -f "$DB_FILE" ]; then
    echo -e "${RED}✗ Database file not found: $DB_FILE${NC}"
    exit 1
fi

echo "Step 1: Checking if table exists..."
TABLE_EXISTS=$(sqlite3 "$DB_FILE" "SELECT name FROM sqlite_master WHERE type='table' AND name='account_campaign_limits';" 2>&1)

if [ -n "$TABLE_EXISTS" ]; then
    echo -e "${GREEN}✓ Table account_campaign_limits already exists${NC}"
    echo "No fix needed!"
    exit 0
fi

echo -e "${YELLOW}⚠ Table account_campaign_limits does NOT exist${NC}"
echo ""

echo "Step 2: Creating table manually..."

# Create the table with SQL
sqlite3 "$DB_FILE" << 'EOF'
-- Create account_campaign_limits table
CREATE TABLE IF NOT EXISTS account_campaign_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    account_phone TEXT NOT NULL,
    messages_sent INTEGER DEFAULT 0,
    messages_limit INTEGER DEFAULT 3,
    last_sent_at TIMESTAMP,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (campaign_id) REFERENCES campaigns (id) ON DELETE CASCADE,
    UNIQUE(campaign_id, account_phone)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_account_limits_campaign 
    ON account_campaign_limits(campaign_id, account_phone);

CREATE INDEX IF NOT EXISTS idx_account_limits_status 
    ON account_campaign_limits(campaign_id, status);
EOF

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Table created successfully${NC}"
else
    echo -e "${RED}✗ Failed to create table${NC}"
    exit 1
fi

echo ""
echo "Step 3: Verifying table..."
TABLE_CHECK=$(sqlite3 "$DB_FILE" "SELECT name FROM sqlite_master WHERE type='table' AND name='account_campaign_limits';")

if [ "$TABLE_CHECK" = "account_campaign_limits" ]; then
    echo -e "${GREEN}✓ Table verified: account_campaign_limits${NC}"
else
    echo -e "${RED}✗ Verification failed${NC}"
    exit 1
fi

echo ""
echo "Step 4: Checking table schema..."
sqlite3 "$DB_FILE" ".schema account_campaign_limits"

echo ""
echo "=========================================="
echo -e "${GREEN}✅ Migration Fixed!${NC}"
echo "=========================================="
echo ""
echo "Now you can run: ./QUICK_DEPLOY.sh"
echo "Or manually restart: sudo systemctl start telespam-web"

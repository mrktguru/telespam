#!/bin/bash
# 🚀 Quick Deploy Script for Worker Pool System
# Usage: ./QUICK_DEPLOY.sh
# Run this on your production server

set -e  # Exit on error

echo "=========================================="
echo "🚀 Worker Pool System Deployment"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Backup Database
echo "Step 1/9: Backing up database..."
mkdir -p backups
BACKUP_FILE="backups/telespam_backup_$(date +%Y%m%d_%H%M%S).db"
if [ -f telespam.db ]; then
    cp telespam.db "$BACKUP_FILE"
    echo -e "${GREEN}✓ Database backed up to: $BACKUP_FILE${NC}"
else
    echo -e "${YELLOW}⚠ No database found, skipping backup${NC}"
fi

# Step 2: Stop Service
echo ""
echo "Step 2/9: Stopping telespam-web service..."
sudo systemctl stop telespam-web || echo -e "${YELLOW}⚠ Service not running${NC}"
echo -e "${GREEN}✓ Service stopped${NC}"

# Step 3: Pull Latest Code
echo ""
echo "Step 3/9: Pulling latest code from GitHub..."
git checkout main
git pull origin main
echo -e "${GREEN}✓ Code updated${NC}"

# Step 4: Verify New Files
echo ""
echo "Step 4/9: Verifying new files..."
MISSING=0
for file in campaign_worker.py campaign_runner_v2.py migrations/001_add_campaign_improvements.sql apply_migration.py; do
    if [ ! -f "$file" ]; then
        echo -e "${RED}✗ Missing: $file${NC}"
        MISSING=1
    else
        echo -e "${GREEN}✓ Found: $file${NC}"
    fi
done

if [ $MISSING -eq 1 ]; then
    echo -e "${RED}✗ Some files are missing! Deployment cannot continue.${NC}"
    exit 1
fi

# Step 5: Check Import in web_app.py
echo ""
echo "Step 5/9: Checking web_app.py integration..."
if grep -q "from campaign_runner_v2 import run_campaign_task_v2" web_app.py; then
    echo -e "${GREEN}✓ web_app.py has worker pool import${NC}"
else
    echo -e "${RED}✗ web_app.py missing worker pool import!${NC}"
    echo "Please ensure PR #124 is merged and pulled."
    exit 1
fi

# Step 6: Apply Database Migration
echo ""
echo "Step 6/9: Applying database migration..."
if python3 apply_migration.py migrations/001_add_campaign_improvements.sql; then
    echo -e "${GREEN}✓ Migration applied successfully${NC}"
else
    echo -e "${YELLOW}⚠ Migration may have already been applied${NC}"
fi

# Step 7: Verify Migration
echo ""
echo "Step 7/9: Verifying migration..."
if sqlite3 telespam.db "SELECT name FROM sqlite_master WHERE type='table' AND name='account_campaign_limits';" | grep -q "account_campaign_limits"; then
    echo -e "${GREEN}✓ Table account_campaign_limits exists${NC}"
else
    echo -e "${RED}✗ Migration verification failed!${NC}"
    exit 1
fi

# Step 8: Test Imports
echo ""
echo "Step 8/9: Testing Python imports..."
if python3 -c "
from campaign_worker import CampaignWorker, CampaignCoordinator
from campaign_runner_v2 import run_campaign_task_v2
from database import Database
print('✓ All imports successful')
" 2>&1; then
    echo -e "${GREEN}✓ All worker pool imports successful${NC}"
else
    echo -e "${RED}✗ Import test failed!${NC}"
    exit 1
fi

# Step 9: Start Service
echo ""
echo "Step 9/9: Starting telespam-web service..."
sudo systemctl start telespam-web
sleep 2

# Check if service started successfully
if sudo systemctl is-active --quiet telespam-web; then
    echo -e "${GREEN}✓ Service started successfully${NC}"
else
    echo -e "${RED}✗ Service failed to start!${NC}"
    echo "Check logs with: sudo journalctl -u telespam-web -n 50"
    exit 1
fi

# Final Summary
echo ""
echo "=========================================="
echo -e "${GREEN}🎉 Deployment Complete!${NC}"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Monitor logs: sudo journalctl -u telespam-web -f"
echo "2. Test web interface: curl -I http://localhost:5000/login"
echo "3. Create a test campaign with 1-2 users"
echo "4. Watch for worker pool activity in logs"
echo ""
echo "Backup location: $BACKUP_FILE"
echo ""
echo "For detailed testing, see: DEPLOYMENT_WORKER_POOL.md"
echo "=========================================="

# 🚀 Worker Pool System Deployment Guide

## Overview
This guide covers deploying the Worker Pool system (PRs #121, #122, #123, #124) to production.

---

## 📋 Pre-Deployment Checklist

Before starting, verify:
- ✅ All PRs (#121, #122, #123, #124) are merged to main
- ✅ You have SSH access to the server
- ✅ You have sudo/systemctl permissions
- ✅ Database backup is available (safety first!)

---

## 🔧 Deployment Steps

### Step 1: Connect to Server
```bash
ssh your-server
cd /path/to/telespam
```

### Step 2: Backup Current Database (CRITICAL!)
```bash
# Create backup directory
mkdir -p backups

# Backup database with timestamp
cp telespam.db "backups/telespam_backup_$(date +%Y%m%d_%H%M%S).db"

# Verify backup exists
ls -lh backups/
```

### Step 3: Stop Web Service
```bash
# Stop the service to avoid conflicts during update
sudo systemctl stop telespam-web

# Verify it's stopped
sudo systemctl status telespam-web
```

### Step 4: Pull Latest Code
```bash
# Ensure you're on main branch
git checkout main

# Pull all merged changes
git pull origin main

# Verify you have all the new files
ls -la | grep -E "campaign_worker|campaign_runner_v2|migrations"
```

### Step 5: Apply Database Migration
```bash
# Apply the migration for worker pool tables
python3 apply_migration.py migrations/001_add_campaign_improvements.sql

# Expected output:
# ✓ Migration applied successfully
# ✓ Tables created: account_campaign_limits
# ✓ Columns added to campaigns table
```

**Verify migration:**
```bash
sqlite3 telespam.db "SELECT name FROM sqlite_master WHERE type='table' AND name='account_campaign_limits';"
# Should output: account_campaign_limits
```

### Step 6: Verify New Files Present
```bash
# Check all worker pool files are present
ls -la campaign_worker.py          # Worker pool classes
ls -la campaign_runner_v2.py       # New campaign runner
ls -la migrations/001_*.sql        # Migration file

# Check web_app.py has new import
grep "campaign_runner_v2" web_app.py
# Should show: from campaign_runner_v2 import run_campaign_task_v2
```

### Step 7: Test Import (Quick Sanity Check)
```bash
# Quick test to ensure no import errors
python3 -c "
from campaign_worker import CampaignWorker, CampaignCoordinator
from campaign_runner_v2 import run_campaign_task_v2
from database import Database
print('✓ All worker pool imports successful')
"
```

### Step 8: Start Web Service
```bash
# Start the service with new code
sudo systemctl start telespam-web

# Check status
sudo systemctl status telespam-web

# Should show: active (running)
```

### Step 9: Monitor Logs
```bash
# Monitor logs for any errors (Ctrl+C to exit)
sudo journalctl -u telespam-web -f

# Look for:
# ✓ "WEB INTERFACE STARTING"
# ✓ No import errors
# ✓ No database errors
```

---

## 🧪 Post-Deployment Testing

### Test 1: Web Interface Access
```bash
# Check if web interface is accessible
curl -I http://localhost:5000/login

# Should return: HTTP/1.1 200 OK
```

### Test 2: Create Test Campaign
1. Log in to web interface
2. Go to **Campaigns** → **New Campaign**
3. Create a small test campaign (1-2 users)
4. Start the campaign
5. Monitor logs for worker pool activity:

```bash
sudo journalctl -u telespam-web -f | grep -E "CampaignWorker|CampaignCoordinator|worker pool"
```

**Expected log entries:**
```
✓ CampaignCoordinator initialized for campaign X
✓ Starting worker pool with N accounts
✓ CampaignWorker-account_phone starting...
✓ Account account_phone sent message to user_username
```

### Test 3: Test Continue/Restart
1. Stop the test campaign
2. Click **Continue** button → Should resume correctly
3. Click **Restart** button → Should reset and restart

### Test 4: Check Account Limits
```bash
# Query database to see account limits being tracked
sqlite3 telespam.db "SELECT * FROM account_campaign_limits LIMIT 5;"

# Should show records like:
# account_id|campaign_id|messages_sent|last_message_at|...
```

---

## 🔍 Troubleshooting

### Issue: Import Error
```
Error: cannot import name 'CampaignWorker'
```

**Solution:**
```bash
# Check if file exists and has correct permissions
ls -la campaign_worker.py
# Should be readable: -rw-r--r--

# Check syntax
python3 -m py_compile campaign_worker.py

# If syntax error, re-pull from git
git checkout main
git pull origin main --force
```

### Issue: Database Migration Failed
```
Error: table account_campaign_limits already exists
```

**Solution:**
```bash
# Migration already applied, skip it
echo "Migration already applied, continuing..."

# Verify table exists
sqlite3 telespam.db ".schema account_campaign_limits"
```

### Issue: Service Won't Start
```
Failed to start telespam-web.service
```

**Solution:**
```bash
# Check detailed error
sudo journalctl -u telespam-web -n 50 --no-pager

# Common fixes:
# 1. Check port 5000 not in use
sudo lsof -i :5000

# 2. Check file permissions
ls -la web_app.py
chmod +x web_app.py

# 3. Check Python path
which python3
```

### Issue: Old Campaign Runner Still Running
```
Campaigns still using sequential sending
```

**Solution:**
```bash
# Verify web_app.py has new imports
grep "run_campaign_task_v2" web_app.py

# Should show 3 occurrences in:
# - start_campaign()
# - continue_campaign()  
# - restart_campaign()

# If not found, pull again
git pull origin main --force
sudo systemctl restart telespam-web
```

---

## 🎯 Verification Checklist

After deployment, verify:

- [ ] Web service is running: `sudo systemctl status telespam-web`
- [ ] No errors in logs: `sudo journalctl -u telespam-web -n 50`
- [ ] New table exists: `sqlite3 telespam.db "SELECT name FROM sqlite_master WHERE name='account_campaign_limits';"`
- [ ] Test campaign starts successfully
- [ ] Worker pool logs appear when campaign runs
- [ ] Continue button works
- [ ] Restart button works
- [ ] Account limits are tracked in database

---

## 📊 Feature Verification

### Parallel Sending
**Test:** Start campaign with 3+ accounts and 10+ users

**Expected:** Logs show multiple workers running simultaneously:
```
CampaignWorker-account1 starting...
CampaignWorker-account2 starting...
CampaignWorker-account3 starting...
Account account1 sent message to user1
Account account2 sent message to user2  # Happens in parallel!
```

### Account Limits
**Test:** Set account limit to 5 messages, start campaign with 10 users

**Expected:** 
- Campaign sends 5 messages per account
- Logs show: "Account account_phone reached limit (5/5)"
- Database shows limits: `SELECT * FROM account_campaign_limits;`

### Proxy Rotation
**Test:** Configure 2+ proxies in campaign, start campaign

**Expected:** Logs show different proxies being used:
```
Using campaign proxy proxy1 for account account1
Using campaign proxy proxy2 for account account2
```

### Continue/Restart
**Test:** Stop campaign mid-run, then Continue

**Expected:**
- Campaign resumes from where it stopped
- No duplicate messages sent
- Logs show: "Campaign continued"

**Test:** Stop campaign, then Restart

**Expected:**
- All users reset to 'new' status
- All account limits cleared
- Campaign starts from beginning
- Logs show: "Campaign restarted: N users reset"

---

## 🚨 Rollback Procedure (If Needed)

If something goes wrong, rollback:

### Quick Rollback
```bash
# 1. Stop service
sudo systemctl stop telespam-web

# 2. Restore database backup
cp backups/telespam_backup_YYYYMMDD_HHMMSS.db telespam.db

# 3. Revert to previous code version
git log --oneline | head -5  # Find commit before PRs
git checkout <commit-before-PRs>

# 4. Restart service
sudo systemctl start telespam-web

# 5. Verify old version works
curl -I http://localhost:5000/login
```

---

## 📈 Performance Monitoring

After deployment, monitor:

### System Resources
```bash
# CPU and memory usage
top -p $(pgrep -f web_app.py)

# Disk space (database grows with limits tracking)
du -h telespam.db
```

### Campaign Performance
```bash
# Active campaigns
sqlite3 telespam.db "SELECT id, name, status FROM campaigns WHERE status='running';"

# Messages sent per account
sqlite3 telespam.db "SELECT account_id, SUM(messages_sent) FROM account_campaign_limits GROUP BY account_id;"
```

### Error Rate
```bash
# Check for errors in last hour
sudo journalctl -u telespam-web --since "1 hour ago" | grep -i error | wc -l

# Should be 0 or very low
```

---

## 🎉 Success Indicators

Deployment is successful when:

1. ✅ Service starts without errors
2. ✅ Web interface is accessible
3. ✅ Test campaign runs with parallel workers
4. ✅ Account limits are tracked
5. ✅ Continue/Restart buttons work
6. ✅ No error spikes in logs
7. ✅ Database migration applied successfully
8. ✅ All worker pool logs appear during campaigns

---

## 📞 Support

If issues persist:

1. **Check logs:** `sudo journalctl -u telespam-web -n 100`
2. **Check database:** `sqlite3 telespam.db ".tables"`
3. **Verify files:** `git status` and `git log -5`
4. **Review GitHub:** Check PRs #121, #122, #123, #124 for context

---

## 📝 Notes

- **Database growth:** The `account_campaign_limits` table will grow with usage. Plan for cleanup/archiving strategy.
- **Log rotation:** Ensure systemd logs are rotated to prevent disk space issues.
- **Proxy limits:** Monitor proxy traffic usage if using DataImpulse or similar services.
- **Account bans:** Monitor for Telegram account restrictions and adjust delays/limits accordingly.

---

**Deployment Date:** _[Fill in after deployment]_  
**Deployed By:** _[Your name]_  
**Server:** _[Server name/IP]_  
**Status:** _[Success/Issues/Rollback]_

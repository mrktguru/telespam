# Deployment Issues and Solutions

## 🔴 Problem Summary

After merging PR #115 (username sending fix), users reported:

1. **Error returned**: `"No user has mrgekko as username"` - this error should have been fixed by PR #115
2. **Proxy disappeared**: After adding account, proxy configuration was lost
3. **Empty database**: No accounts in the database despite web UI showing them

## 🔍 Root Cause Analysis

### Issue 1: Code Not Deployed

**Symptoms:**
```
✗ Failed to send to mrgekko: Invalid user_id format: None - No user has "mrgekko" as username
```

**Root Cause:**
- PR #115 was merged to `main` branch ✅
- BUT: The running application is NOT using the latest code ❌
- Git repository shows correct code, but **deployment not updated**

**Evidence:**
```bash
# Check git log - PR #115 is merged
git log --oneline | grep "username"
# 7ae1212 Merge pull request #115 from mrktguru/fix/username-spam-direct-send
# 0c5a663 fix: simplify username resolution for spam/outreach to unknown users

# Check current code - CORRECT
grep "PRIORITY 1: For username" web_app.py
# Found: Direct username sending code ✅

# But error logs show OLD code is running
# This means: Application needs restart with new code
```

### Issue 2: Database Empty

**Symptoms:**
```bash
sqlite3 telespam.db "SELECT * FROM accounts"
# Returns: empty
```

**Possible Causes:**

#### A. Different Database File
The application might be using a different database file location:
- Development: `/project/workspace/telespam/telespam.db`
- Production: `/var/www/telespam/telespam.db` or similar
- Docker: `/app/telespam.db`

#### B. Session Files Instead of Database
Some deployments store accounts in session files only:
- Sessions in: `sessions/*.session`
- No database records
- Account data derived from session files at runtime

#### C. Mock/Test Mode
Check if application is running in test mode:
```python
# In web_app.py line 6:
os.environ['USE_MOCK_STORAGE'] = 'true'
```

This forces mock storage instead of real database!

### Issue 3: Proxy Disappearing

**Symptoms:**
- User adds proxy via web UI
- Adds account with proxy
- Proxy configuration lost

**Possible Causes:**

#### A. Session Creation Issue
When adding account via `add_account_from_session_data.py`:
1. Session is created without proxy info
2. Proxy is stored in database
3. But session file doesn't contain proxy config
4. Next app restart: Session loads without proxy

#### B. Database Transaction Rollback
```python
# If add_account() fails partially:
db.add_account({
    'phone': phone,
    'proxy_host': proxy_host,  # Might be lost if transaction rolls back
    ...
})
# Transaction fails → proxy data lost
```

#### C. add_account_from_session_data.py Doesn't Store Proxy
The script might not accept or store proxy configuration at all.

## ✅ Solutions

### Solution 1: Restart Application with Latest Code

**For systemd service:**
```bash
# Pull latest code
cd /path/to/telespam
git checkout main
git pull origin main

# Restart service
sudo systemctl restart telespam
# or
sudo systemctl restart telespam-web

# Verify restart
sudo systemctl status telespam
```

**For Docker:**
```bash
# Rebuild and restart
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Or restart existing container
docker restart telespam_web
```

**For screen/tmux:**
```bash
# Find running process
ps aux | grep web_app.py

# Kill it
kill <PID>

# Start again
cd /path/to/telespam
python3 web_app.py
# or
screen -S telespam
python3 web_app.py
```

**For PM2:**
```bash
pm2 restart telespam
# or
pm2 reload telespam
```

### Solution 2: Fix Database Connection

#### Step 1: Find Which Database File is Used

Add debugging to `web_app.py`:
```python
# After line 20 (from database import db)
print(f"DEBUG: Database file location: {db.db_file}")
print(f"DEBUG: Database file exists: {os.path.exists(db.db_file)}")
```

#### Step 2: Verify Database Location

```bash
# Check application logs for database path
tail -f /var/log/telespam.log | grep "Database"

# Or check database.py:
grep "self.db_file" database.py
```

#### Step 3: Use Correct Database

**Option A: Point to correct database**
```bash
# In config.py or .env:
DATABASE_PATH=/path/to/actual/telespam.db
```

**Option B: Migrate data**
```bash
# If accounts are in old location, migrate them:
cp /old/path/telespam.db /new/path/telespam.db
```

### Solution 3: Fix Mock Storage Mode

**Problem:** Line 6 in `web_app.py`:
```python
os.environ['USE_MOCK_STORAGE'] = 'true'
```

**Solution:** Remove or comment out this line:
```python
# os.environ['USE_MOCK_STORAGE'] = 'true'  # REMOVE THIS FOR PRODUCTION
```

This line forces the app to use mock/test storage instead of real database!

### Solution 4: Fix Proxy Persistence

#### Add Proxy Support to add_account_from_session_data.py

```python
# add_account_from_session_data.py - Add proxy parameters:

def add_account_from_session(
    session_string: str,
    proxy_host: str = None,
    proxy_port: int = None,
    proxy_type: str = None,
    proxy_user: str = None,
    proxy_pass: str = None
):
    # ... existing code ...
    
    # Add account to database with proxy
    account_data = {
        'id': str(me.id),
        'phone': me.phone,
        'username': me.username,
        'first_name': me.first_name or '',
        'last_name': me.last_name or '',
        'session_file': session_file,
        'status': 'active',
        'api_id': str(config.API_ID),
        'api_hash': config.API_HASH,
    }
    
    # Add proxy if provided
    if proxy_host and proxy_port:
        account_data.update({
            'use_proxy': True,
            'proxy_type': proxy_type or 'socks5',
            'proxy_host': proxy_host,
            'proxy_port': str(proxy_port),
            'proxy_user': proxy_user,
            'proxy_pass': proxy_pass,
        })
    
    db.add_account(account_data)
```

#### Verify Proxy Saved

```bash
# After adding account, check database:
sqlite3 telespam.db "SELECT phone, use_proxy, proxy_host, proxy_port FROM accounts WHERE phone='<phone>'"
```

## 🔬 Diagnostic Checklist

Run these commands to diagnose your deployment:

### 1. Check Git Status
```bash
cd /path/to/telespam
git branch                    # Current branch?
git log --oneline -5          # Latest commits?
git status                    # Uncommitted changes?
```

### 2. Check Running Process
```bash
ps aux | grep web_app.py      # Process running?
systemctl status telespam     # Service status?
docker ps | grep telespam     # Docker container?
```

### 3. Check Database
```bash
cd /path/to/telespam
ls -la *.db                   # Database files?
sqlite3 telespam.db ".tables" # Tables exist?
sqlite3 telespam.db "SELECT COUNT(*) FROM accounts"  # Accounts count?
```

### 4. Check Application Logs
```bash
tail -100 /var/log/telespam.log
# or
docker logs telespam_web --tail 100
# or
pm2 logs telespam
```

### 5. Check Mock Storage Mode
```bash
grep "USE_MOCK_STORAGE" web_app.py
# Should be commented out or removed for production
```

### 6. Test Username Sending
```bash
# Check if the fix is actually running:
grep -A 5 "PRIORITY 1: For username" web_app.py
# Should show: Direct username sending without access_hash
```

## 📋 Deployment Workflow (Recommended)

### Every Time You Deploy Changes:

```bash
# 1. Pull latest code
git checkout main
git pull origin main

# 2. Check for database migrations
# (if any schema changes)
python3 database.py  # or migration script

# 3. Restart application
sudo systemctl restart telespam
# or
docker-compose restart
# or
pm2 restart telespam

# 4. Verify deployment
curl http://localhost:5000/api/stats  # Check API responds
tail -20 logs/telespam.log             # Check startup logs

# 5. Test critical functionality
# - Login to web UI
# - Check accounts list
# - Try sending a test message
```

## 🚨 Emergency Rollback

If new deployment breaks things:

```bash
# 1. Find last working commit
git log --oneline

# 2. Rollback
git checkout <last-working-commit>

# 3. Restart
sudo systemctl restart telespam

# 4. Or use previous Docker image
docker-compose down
docker-compose up -d telespam:previous-tag
```

## 📝 Recommendations

### For Production Deployments:

1. **Use proper deployment tool**
   - GitHub Actions CI/CD
   - Jenkins
   - GitLab CI/CD
   - Capistrano
   - Ansible

2. **Automated deployment script**
   ```bash
   #!/bin/bash
   # deploy.sh
   cd /var/www/telespam
   git pull origin main
   pip install -r requirements.txt  # If dependencies changed
   sudo systemctl restart telespam
   sleep 5
   curl -f http://localhost:5000/api/stats || exit 1
   echo "Deployment successful!"
   ```

3. **Health checks**
   - API endpoint: `/health` or `/api/stats`
   - Check logs after restart
   - Automated tests

4. **Remove debug/mock code**
   - Comment out `USE_MOCK_STORAGE`
   - Remove debug prints in production
   - Use proper logging (not print())

5. **Database backups**
   ```bash
   # Daily backup
   0 2 * * * /usr/bin/sqlite3 /var/www/telespam/telespam.db ".backup '/backup/telespam_$(date +\%Y\%m\%d).db'"
   ```

## 🔧 Next Steps

1. **Identify your deployment method** (systemd/Docker/PM2/screen)
2. **Restart application** with latest code from main branch
3. **Verify** that PR #115 fix is actually running
4. **Test** sending to username (should work now)
5. **Fix** proxy persistence if still an issue
6. **Remove** `USE_MOCK_STORAGE` line from web_app.py

---

**Created:** 2025-12-15  
**Related PRs:** #115, #116, #117, #118, #119  
**Status:** Active investigation

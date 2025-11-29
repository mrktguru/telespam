# 🔧 TROUBLESHOOTING GUIDE - Campaign Errors

## 🎯 Problem: Campaign fails with "failed" status

This guide will help you diagnose why campaigns are failing.

---

## 📊 What's New in This Update

### Improved Error Logging

The system now provides **detailed error messages** including:

1. ✅ **API credentials validation** - Checks if API_ID and API_HASH are configured
2. ✅ **Full traceback logging** - Shows exact line and cause of errors
3. ✅ **.env file loading feedback** - Confirms if .env file is found and loaded
4. ✅ **Step-by-step campaign progress** - Each action is logged

---

## 🔍 Step 1: Check .env File

### On your server (38.244.194.181):

```bash
# Navigate to application directory
cd /path/to/telespam

# Check if .env exists
ls -la .env

# View .env content (be careful with secrets!)
cat .env
```

### Your .env should contain:

```env
# Telegram API Configuration
API_ID=12345678
API_HASH=your_actual_api_hash_here

# Use mock storage
USE_MOCK_STORAGE=true

# Web app secret
SECRET_KEY=your-secret-key

# Server
HOST=0.0.0.0
PORT=5000
```

### ⚠️ Common Issues:

1. **File doesn't exist** → Create it with real credentials
2. **Wrong location** → Must be in same directory as `web_app.py`
3. **Wrong format** → No spaces around `=`, no quotes needed
4. **Wrong permissions** → Run `chmod 600 .env`

---

## 🔍 Step 2: Check Application Startup Logs

When the application starts, it now prints diagnostic information:

```bash
# View systemd logs (if using systemd)
sudo journalctl -u telespam-web -n 50

# Or check the console output if running manually
python3 web_app.py
```

### Look for these messages:

✅ **GOOD** - .env file found and API credentials loaded:
```
✓ Loaded .env file from: /path/to/telespam/.env
✓ API_ID loaded: 12345678
✓ API_HASH loaded: abcdef1234...
```

❌ **BAD** - Missing .env or credentials:
```
⚠ No .env file found at: /path/to/telespam/.env
  Using environment variables only
✗ ERROR: API_ID or API_HASH not found!
  API_ID: None
  API_HASH: None
```

---

## 🔍 Step 3: Check Campaign Logs

After starting a campaign, check the detailed logs in the web interface:

1. Go to **Campaigns** → Select your campaign
2. **Scroll down to "Campaign Logs"**
3. Look for these messages:

### If API credentials are missing:

```
CRITICAL: API_ID or API_HASH not configured! Check .env file.
```

**Solution:** Create or fix your .env file (see Step 1)

### If session files are missing:

```
✗ Failed to send to @username from +1234567890: Session file not found: /path/to/sessions/1234567890.session
```

**Solution:** Add Telegram accounts using the CLI:
```bash
python3 add_account_cli.py
```

### If account not authorized:

```
✗ Failed to send to @username from +1234567890: Account not authorized
```

**Solution:** Re-authorize the account:
```bash
python3 add_account_cli.py
# Or delete the session and re-add
```

### Full traceback visible:

```
Campaign CRITICAL error: 'NoneType' object has no attribute 'connect'
Traceback: 
  File "web_app.py", line 180, in run_campaign_task
    success, error_msg = loop.run_until_complete(...)
  ...
```

This shows the exact error and line number!

---

## 🔍 Step 4: Test Manually

### Test 1: Check if .env loads correctly

```bash
cd /path/to/telespam
python3 -c "import config; print(f'API_ID: {config.API_ID}'); print(f'API_HASH: {config.API_HASH[:10] if config.API_HASH else None}...')"
```

**Expected output:**
```
✓ Loaded .env file from: /path/to/telespam/.env
✓ API_ID loaded: 12345678
✓ API_HASH loaded: abcdef1234...
API_ID: 12345678
API_HASH: abcdef1234...
```

### Test 2: List session files

```bash
ls -la sessions/
```

Should show `.session` files for each Telegram account.

### Test 3: Check database

```bash
sqlite3 telespam.db "SELECT id, name, status FROM campaigns ORDER BY id DESC LIMIT 5;"
```

Shows recent campaigns and their status.

---

## 🛠️ Common Fixes

### Fix 1: Create .env file

```bash
cd /path/to/telespam

cat > .env << 'EOF'
API_ID=YOUR_API_ID
API_HASH=YOUR_API_HASH
USE_MOCK_STORAGE=true
SECRET_KEY=random-secret-key-here
HOST=0.0.0.0
PORT=5000
EOF

chmod 600 .env
```

### Fix 2: Restart application

```bash
# If using systemd
sudo systemctl restart telespam-web

# If running manually
pkill -f web_app.py
python3 web_app.py
```

### Fix 3: Add Telegram accounts

```bash
python3 add_account_cli.py
# Follow prompts to authorize account
```

### Fix 4: Check file permissions

```bash
# Fix .env permissions
chmod 600 .env

# Fix sessions directory
chmod 700 sessions/
chmod 600 sessions/*.session
```

---

## 📞 Getting More Help

### Check these files in order:

1. **Campaign logs in web interface** - Most detailed errors
2. **Application logs** - `journalctl -u telespam-web -f` or console output
3. **Database** - `sqlite3 telespam.db`

### Share these details if asking for help:

1. Output of `.env` check (Step 1)
2. Application startup logs (Step 2)
3. Campaign error logs from web interface (Step 3)
4. Manual test results (Step 4)

---

## ✅ Success Indicators

You'll know it's working when you see:

1. ✅ `.env file loaded` message on startup
2. ✅ `API_ID loaded: XXXXX` message  
3. ✅ Campaign logs show: `API_ID configured: XXXXX`
4. ✅ Campaign logs show: `Starting campaign: X accounts, Y users`
5. ✅ Campaign logs show: `✓ Sent to @username from +phone`

---

## 🎯 Quick Checklist

Before starting a campaign, verify:

- [ ] `.env` file exists in application directory
- [ ] `API_ID` and `API_HASH` are set in `.env`
- [ ] Application shows "✓ Loaded .env file" on startup
- [ ] At least one Telegram account added (session file exists)
- [ ] At least one user added for outreach
- [ ] Campaign created with selected accounts and users

---

**Updated:** 2025-11-29  
**Version:** 2.0 with enhanced error logging

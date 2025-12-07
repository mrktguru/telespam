# Debugging Boot Failure Errors

## Recent Fixes Applied

### 1. Mock Storage Support in sender.py
**Problem:** sender.py was using database functions (accounts.py) even when `USE_MOCK_STORAGE=true` was set.

**Fix:** Added conditional imports and logic to use `mock_sheets` when in mock storage mode.

**How to verify:**
```bash
cd ~/telespam
git pull origin claude/audit-project-changes-01RhbB1KccoAFLjDsmGAnVR9
python3 start_outreach_cli.py
```

### 2. Account Availability with None Values
**Problem:** When `daily_sent` or `total_sent` were set to `None`, the code would fail with `TypeError`.

**Fix:** Updated `mock_sheets.get_available_accounts()` to handle None values using `or 0` operator.

### 3. Entity Resolution for Unfamiliar Users
**Problem:** Telethon cannot send messages to users by ID alone if the account has never interacted with them.

**Fix:** Added `get_entity()` call before sending messages, with `GetUsersRequest` fallback for access_hash retrieval.

**Important:** This still has limitations - if the account has never contacted the user, you MUST provide:
- Username (`@username`), OR
- Phone number, OR
- The user must be in the account's contacts

## Common Errors and Solutions

### Error: "No available accounts"

**Causes:**
1. Account status is not `active` or `warming`
2. Account has reached daily limit
3. Account is in cooldown
4. `daily_sent` or `total_sent` are set to `None` (fixed)

**Check account status:**
```python
python3 -c "
import os
os.environ['USE_MOCK_STORAGE'] = 'true'
from mock_sheets import sheets_manager

for acc in sheets_manager.get_all_accounts():
    print(f\"{acc.get('id')}: {acc.get('phone')} [{acc.get('status')}] sent={acc.get('daily_sent')}/{acc.get('total_sent')}\")
"
```

**Fix account status:**
```python
python3 -c "
import os
os.environ['USE_MOCK_STORAGE'] = 'true'
from mock_sheets import sheets_manager

# Set account to active and reset counters
sheets_manager.update_account('acc_1', {
    'status': 'active',
    'daily_sent': 0,
    'total_sent': 0,
    'cooldown_until': ''
})
print('✓ Account reset to active status')
"
```

### Error: "Could not find the input entity for PeerUser"

**Causes:**
1. Account has never interacted with the target user
2. No username or phone provided in CSV
3. User ID is invalid

**Solution:** Add username to your CSV:
```csv
username,user_id,phone,priority
champfreak,7115610560,,1
testuser,157625351,,2
```

**Or check if user exists:**
```python
# Run test_send_message.py to verify you can reach the user
python3 test_send_message.py
```

### Error: "safe_input() missing 1 required positional argument"

**Status:** FIXED in latest commit

### Error: "SyntaxError: invalid syntax" at line 179

**Cause:** Production server has older code from PR #80

**Solution:** Pull latest changes and restart service:
```bash
cd ~/telespam/telespam  # or /root/telespam/telespam
git pull origin claude/audit-project-changes-01RhbB1KccoAFLjDsmGAnVR9
sudo systemctl restart telespam-web
```

## Testing Message Sending

### Option 1: Test with CLI (using mock storage)
```bash
python3 start_outreach_cli.py
# Select option to send test message
```

### Option 2: Test with interactive script
```bash
python3 test_send_message.py
```

### Option 3: Direct Python test
```python
python3 -c "
import asyncio
import os
os.environ['USE_MOCK_STORAGE'] = 'true'

from sender import send_message

async def test():
    result = await send_message(
        user_id=7115610560,  # @champfreak
        message_type='text',
        content='Test message',
        account_id='acc_1'  # Your account ID
    )
    print(f'Result: {result}')

asyncio.run(test())
"
```

## Checking Logs

### Production server logs:
```bash
sudo journalctl -u telespam-web -f
```

### Check for specific errors:
```bash
sudo journalctl -u telespam-web --since "1 hour ago" | grep -i error
```

### Check account usage:
```bash
sudo journalctl -u telespam-web --since "1 hour ago" | grep "DEBUG: Using API_ID"
```

## Environment Variables

Make sure these are set correctly:

### In .env file:
```
API_ID=37708785
API_HASH=7ed610a63e994fc092c67de2140a7465
USE_MOCK_STORAGE=false
HOST=0.0.0.0
PORT=8000
```

### For CLI testing (automatic):
The CLI scripts automatically set `USE_MOCK_STORAGE=true` in code.

## Database vs Mock Storage

### Mock Storage (for testing):
- Data stored in `test_data.json`
- Set via `os.environ['USE_MOCK_STORAGE'] = 'true'`
- Used by CLI scripts automatically

### Database Storage (for production):
- Data stored in `telespam.db` (SQLite)
- Default mode when `USE_MOCK_STORAGE` is not set
- Used by web application

**Important:** Don't mix modes! If you add accounts in mock storage mode, they won't be visible in database mode and vice versa.

## File Locations

- **Session files:** `sessions/*.session`
- **Database:** `telespam.db`
- **Mock storage:** `test_data.json`
- **Logs:** `sudo journalctl -u telespam-web`
- **Config:** `.env`

## Quick Fix Checklist

When boot fails:

- [ ] Pull latest changes from branch
- [ ] Check `.env` file has correct API credentials
- [ ] Verify Python version: `python3 --version` (should be 3.8+)
- [ ] Check syntax: `python3 -m py_compile web_app.py`
- [ ] Review logs: `sudo journalctl -u telespam-web --since "5 minutes ago"`
- [ ] Restart service: `sudo systemctl restart telespam-web`
- [ ] Check status: `sudo systemctl status telespam-web`

## Need More Help?

Run the diagnostic script:
```bash
./diagnose_sending.sh
```

Or check the comprehensive deployment script:
```bash
./deploy_to_production.sh
```

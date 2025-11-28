# Testing Guide - Without Google Sheets and n8n

This guide shows how to test the Telegram Outreach System using mock storage, without requiring Google Sheets or n8n setup.

## Quick Start

### 1. Enable Mock Storage Mode

```bash
# Copy test environment file
cp .env.test .env

# Or manually set the environment variable
export USE_MOCK_STORAGE=true
```

### 2. Test Storage Functions

```bash
# Run interactive test menu
python test_terminal.py

# Or run all tests automatically
python test_terminal.py --auto
```

### 3. Test API Server

```bash
# Terminal 1: Start API server with mock storage
USE_MOCK_STORAGE=true python main.py

# Terminal 2: Run API tests
./test_api_curl.sh

# Or run all API tests automatically
./test_api_curl.sh --auto
```

## Mock Storage Features

The mock storage (`mock_sheets.py`) provides:

- ✅ In-memory database (no Google Sheets needed)
- ✅ Persistent storage in `test_data.json`
- ✅ Same API as real Google Sheets integration
- ✅ Visible logs in terminal
- ✅ Easy data inspection and debugging

## Testing Scenarios

### Scenario 1: Basic Storage Operations

```bash
python test_terminal.py
```

Then select from the menu:
1. Run all tests - Tests all storage operations
2. Add test account - Create test accounts
3. View storage summary - See current data
4. Clear all data - Reset for fresh testing

### Scenario 2: API Endpoints Testing

**Start the server:**
```bash
# Use test environment
cp .env.test .env

# Start API server
USE_MOCK_STORAGE=true python main.py
```

**Test endpoints with curl:**
```bash
# In another terminal
./test_api_curl.sh
```

**Or test individual endpoints:**

```bash
# Get API info
curl http://localhost:8000/

# Get health status
curl http://localhost:8000/health

# Get all accounts
curl http://localhost:8000/accounts

# Get specific account
curl http://localhost:8000/accounts/test_1

# Get settings
curl http://localhost:8000/settings

# Update proxy settings
curl -X POST http://localhost:8000/settings/proxy \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "default_proxy": {
      "type": "socks5",
      "host": "1.2.3.4",
      "port": 1080
    }
  }'
```

### Scenario 3: Adding Test Accounts

**Via Python:**
```python
from mock_sheets import sheets_manager

# Add test account
sheets_manager.add_test_account("test_1", "+79991234567")

# View accounts
sheets_manager.print_summary()
```

**Via API (simulated):**
```bash
# Note: This requires actual tdata/session files
curl -X POST http://localhost:8000/accounts/upload \
  -F "file=@test_account.zip" \
  -F "notes=Test account"
```

### Scenario 4: Testing Message Flow

```bash
# 1. Add test account
python -c "
from mock_sheets import sheets_manager
sheets_manager.add_test_account('test_1', '+79991234567')
sheets_manager.update_account('test_1', {'status': 'active'})
"

# 2. Start API server
USE_MOCK_STORAGE=true python main.py &

# 3. Send test message
curl -X POST http://localhost:8000/send \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 123456789,
    "type": "text",
    "content": "Test message"
  }'

# Note: This will fail without real Telegram session,
# but you can see the account selection logic working
```

### Scenario 5: Testing Proxy Configuration

```bash
# Start server
USE_MOCK_STORAGE=true python main.py &

# Enable proxy globally
curl -X POST http://localhost:8000/settings/proxy \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "default_proxy": {
      "type": "socks5",
      "host": "1.2.3.4",
      "port": 1080
    }
  }'

# Set proxy for specific account
curl -X PUT http://localhost:8000/accounts/test_1/proxy \
  -H "Content-Type: application/json" \
  -d '{
    "use_proxy": true,
    "type": "socks5",
    "host": "5.6.7.8",
    "port": 1080
  }'

# Verify settings
curl http://localhost:8000/settings
```

## Inspecting Test Data

### View JSON data file:
```bash
cat test_data.json | jq '.'
```

### View in Python:
```python
python -c "
from mock_sheets import sheets_manager
sheets_manager.print_summary()
"
```

### View specific data:
```python
python -c "
from mock_sheets import sheets_manager

# All accounts
print('Accounts:', sheets_manager.get_all_accounts())

# All settings
print('Settings:', sheets_manager.get_settings())

# Available accounts for sending
print('Available:', sheets_manager.get_available_accounts())
"
```

## Testing API Documentation

When the server is running, visit:
- API docs: http://localhost:8000/docs
- Alternative docs: http://localhost:8000/redoc

These provide interactive API testing in your browser.

## Common Testing Tasks

### Reset everything:
```bash
python -c "
from mock_sheets import sheets_manager
sheets_manager.clear_all_data()
"
```

### Add multiple test accounts:
```bash
python -c "
from mock_sheets import sheets_manager
for i in range(1, 6):
    sheets_manager.add_test_account(f'acc_{i}', f'+7999{i}{i}{i}{i}{i}{i}{i}')
sheets_manager.print_summary()
"
```

### Simulate account usage:
```bash
python -c "
from mock_sheets import sheets_manager
sheets_manager.add_test_account('test_1', '+79991234567')
sheets_manager.update_account('test_1', {
    'status': 'active',
    'daily_sent': 5,
    'total_sent': 100
})
"
```

### Add test logs:
```bash
python -c "
from mock_sheets import sheets_manager
sheets_manager.add_log({
    'account_id': 'test_1',
    'user_id': 123456789,
    'action': 'send',
    'message_type': 'text',
    'result': 'success',
    'proxy_used': False
})
"
```

## Troubleshooting

### "Module not found" errors:
```bash
# Make sure you're in the project directory
cd /path/to/telespam

# Install dependencies
pip install -r requirements.txt
```

### API server won't start:
```bash
# Check if port is already in use
lsof -i :8000

# Use different port
PORT=8001 USE_MOCK_STORAGE=true python main.py
```

### Mock storage not working:
```bash
# Verify environment variable
python -c "import config; print('Mock storage:', config.USE_MOCK_STORAGE)"

# Should output: Mock storage: True
```

### Test data file not created:
```bash
# Check permissions
ls -la test_data.json

# Manually create if needed
python -c "
from mock_sheets import sheets_manager
sheets_manager.add_test_account('test', '+79991234567')
"
```

## What Works Without Real Telegram Accounts

✅ **Works:**
- All storage operations (add, get, update, delete)
- Settings management
- Account selection logic
- Proxy configuration
- API endpoints structure
- Request/response validation
- Logging system
- Data persistence

❌ **Doesn't Work:**
- Actual message sending (needs real Telegram session)
- Message receiving (needs real Telegram session)
- Account status checking (needs real Telegram session)
- tdata/session file conversion (needs real files)

## Transitioning to Production

When you're ready to use real Telegram accounts:

1. **Get Telegram API credentials:**
   - Visit https://my.telegram.org
   - Create an application
   - Note your API_ID and API_HASH

2. **Set up Google Sheets:**
   - Create a Google Cloud project
   - Enable Google Sheets API
   - Create service account
   - Download credentials.json

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env:
   # - Set USE_MOCK_STORAGE=false
   # - Add your API_ID and API_HASH
   # - Add Google Sheets ID
   # - Configure n8n webhooks (optional)
   ```

4. **Start with real storage:**
   ```bash
   python main.py
   ```

## Tips

- Use `test_terminal.py` for quick storage testing
- Use `test_api_curl.sh` for API endpoint testing
- Keep `test_data.json` for inspection between tests
- Check terminal logs for detailed operation info
- Use `--auto` flags for automated testing in CI/CD

## Need Help?

- Check logs in terminal output
- Inspect `test_data.json` for data state
- Use API docs at http://localhost:8000/docs
- Review main README.md for full documentation

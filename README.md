# Telegram Outreach System

Automated Telegram outreach system with account pool management, Google Sheets integration, and n8n workflows.

## Features

- **Account Management**: Upload and manage multiple Telegram accounts (tdata or session files)
- **Automated Messaging**: Send text, photos, videos, voice messages, and video notes
- **Proxy Support**: SOCKS5/HTTP proxy support per account or globally
- **Message Listening**: Automatically receive and process incoming messages
- **Google Sheets Integration**: Store accounts, dialogs, users, and logs in Google Sheets
- **Account Warming**: Gradual account warming to avoid bans
- **Flood Protection**: Automatic cooldown when hitting rate limits
- **n8n Integration**: Webhooks for workflow automation

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│  Google Sheets  │◄────│      n8n        │────►│ FastAPI Service │
│                 │     │                 │     │                 │
│  • Accounts     │     │  • Workflows    │     │  • Telethon     │
│  • Dialogs      │     │  • GPT logic    │     │  • Converter    │
│  • Users        │     │  • Webhooks     │     │  • Listener     │
│  • Logs         │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Installation

### Prerequisites

- Python 3.9+
- Telegram API credentials (get from https://my.telegram.org)
- Google Service Account (for Sheets integration)
- n8n instance (optional, for automation)

### Setup

1. **Clone the repository**

```bash
git clone <repository-url>
cd telespam
```

2. **Install dependencies**

```bash
pip install -r requirements.txt
```

3. **Configure environment variables**

```bash
cp .env.example .env
# Edit .env with your configuration
nano .env
```

4. **Set up Google Sheets**

- Create a Google Cloud project
- Enable Google Sheets API
- Create a Service Account and download credentials JSON
- Save credentials to `credentials.json`
- Create a new Google Spreadsheet
- Share it with your service account email
- Copy the spreadsheet ID to `.env`

5. **Create required sheets**

Create the following sheets in your Google Spreadsheet:

- **Accounts**: Account management
- **Dialogs**: Conversation tracking
- **Users**: User queue
- **Logs**: Activity logs
- **Settings**: System settings
- **Scripts**: Message templates

See `telegram-outreach-system.md` for detailed sheet structures.

## Running the Application

### Start the API server

```bash
python main.py
```

The API will be available at `http://localhost:8000`

### API Documentation

Once running, visit `http://localhost:8000/docs` for interactive API documentation.

### File Watcher (Optional)

To automatically process files uploaded to the `incoming/` directory:

**Option 1: Using inotify (recommended)**

```bash
# Install inotify-tools
apt-get install inotify-tools

# Run the watcher
./scripts/watch_incoming.sh
```

**Option 2: Using cron**

```bash
# Add to crontab
crontab -e

# Add this line to run every minute
* * * * * /path/to/telespam/scripts/process_incoming.sh
```

## Usage

### Uploading Accounts

**Method 1: Via API**

```bash
curl -X POST "http://localhost:8000/accounts/upload" \
  -F "file=@account.zip" \
  -F "notes=My account"
```

**Method 2: Direct upload to server**

```bash
# Upload file to incoming directory
scp account.zip user@server:/app/incoming/

# File watcher will automatically process it
```

### Sending Messages

**Text message:**

```bash
curl -X POST "http://localhost:8000/send" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 123456789,
    "type": "text",
    "content": "Hello from the outreach system!"
  }'
```

**Photo with caption:**

```bash
curl -X POST "http://localhost:8000/send" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 123456789,
    "type": "photo",
    "file_url": "https://example.com/image.jpg",
    "caption": "Check this out!"
  }'
```

**Video note (circle):**

```bash
curl -X POST "http://localhost:8000/send" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 123456789,
    "type": "video_note",
    "file_path": "/app/media/video_notes/greeting.mp4"
  }'
```

### Managing Proxy

**Enable proxy globally:**

```bash
curl -X POST "http://localhost:8000/settings/proxy" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "default_proxy": {
      "type": "socks5",
      "host": "1.2.3.4",
      "port": 1080,
      "username": "user",
      "password": "pass"
    }
  }'
```

**Set proxy for specific account:**

```bash
curl -X PUT "http://localhost:8000/accounts/acc_1/proxy" \
  -H "Content-Type: application/json" \
  -d '{
    "use_proxy": true,
    "type": "socks5",
    "host": "5.6.7.8",
    "port": 1080
  }'
```

### Checking Account Status

```bash
curl -X POST "http://localhost:8000/accounts/acc_1/check"
```

### Getting Dialog History

```bash
curl "http://localhost:8000/dialogs/123456789?limit=50"
```

## API Endpoints

### Accounts

- `POST /accounts/upload` - Upload account file
- `POST /accounts/process` - Process file from incoming directory
- `GET /accounts` - List all accounts
- `GET /accounts/{id}` - Get specific account
- `POST /accounts/{id}/check` - Check account status
- `DELETE /accounts/{id}` - Delete account
- `PUT /accounts/{id}/proxy` - Set account proxy
- `DELETE /accounts/{id}/proxy` - Disable account proxy

### Messages

- `POST /send` - Send message
- `GET /dialogs/{user_id}` - Get dialog history

### Settings

- `GET /settings` - Get all settings
- `POST /settings/proxy` - Update proxy settings

### System

- `GET /` - API info
- `GET /health` - Health check

## Account Statuses

| Status | Description | Daily Limit |
|--------|-------------|-------------|
| checking | Just uploaded, being verified | 0 |
| warming | New account, warming up | 2-3 |
| active | Ready for full use | 7-10 |
| cooldown | Temporary rest (flood warning) | 0 |
| limited | Limited by Telegram | 0 |
| banned | Banned | 0 |

## Account Warming Strategy

```
Day 1-2:   Subscribe to channels, read messages (no sending)
Day 3-4:   Send 2-3 messages
Day 5-7:   Send 5 messages/day
Day 8+:    Status → "active", full limit 7-10 messages/day
```

## Best Practices

1. **API Credentials**: Use your own API_ID/API_HASH from my.telegram.org
2. **Delays**: Wait 30-60 seconds between messages, randomize timing
3. **Limits**: Don't exceed 7-10 messages/day per account
4. **Personalization**: Use message variations, names, different content types
5. **Negative Responses**: Stop dialog immediately if user responds negatively
6. **Warming**: Always warm new accounts for 5-7 days
7. **Monitoring**: Watch for flood warnings, increase cooldown if repeated
8. **Proxy**: Use residential proxies when scaling up
9. **Safety**: Don't host on same server as critical services

## Troubleshooting

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| FloodWaitError | Too many requests | Account set to cooldown automatically |
| UserBannedInChannelError | User blocked account | Mark dialog as failed |
| PeerIdInvalidError | Invalid user_id | Check data source |
| SessionExpiredError | Session expired | Re-authenticate or delete account |
| PhoneNumberBannedError | Account banned | Update status to banned |
| Proxy connection error | Proxy unavailable | Check proxy, disable if not working |

### Logs

Check Google Sheets "Logs" tab for detailed activity logs.

### Debug Mode

For more verbose logging, run with:

```bash
python main.py --log-level debug
```

## File Structure

```
/app
├── incoming/           # Direct upload directory
├── uploads/           # Web upload directory
├── sessions/          # Session files
├── temp/              # Temporary files
├── media/             # Media files for sending
├── backups/           # Account backups
├── scripts/           # Helper scripts
├── main.py            # FastAPI application
├── config.py          # Configuration
├── converter.py       # tdata conversion
├── accounts.py        # Account management
├── sender.py          # Message sending
├── listener.py        # Message receiving
├── proxy.py           # Proxy management
├── sheets.py          # Google Sheets integration
└── requirements.txt   # Dependencies
```

## Security Considerations

- Never commit `.env` or `credentials.json`
- Use strong credentials for proxy authentication
- Rotate accounts regularly
- Monitor for suspicious activity
- Keep API credentials secure
- Use HTTPS for n8n webhooks

## License

This project is for educational purposes. Use responsibly and in accordance with Telegram's Terms of Service.

## Support

For issues and questions, see the documentation in `telegram-outreach-system.md`

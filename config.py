"""Configuration settings for Telegram Outreach System"""

import os
from pathlib import Path

# Load environment variables (optional)
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✓ Loaded .env file from: {env_file}")
    else:
        print(f"⚠ No .env file found at: {env_file}")
        print(f"  Using environment variables only")
except ImportError:
    print("Warning: python-dotenv not installed, using environment variables only")

# Base directory
BASE_DIR = Path(__file__).parent

# Telegram API settings
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

# Debug: Print API credentials status on load
if API_ID and API_HASH:
    print(f"✓ API_ID loaded: {API_ID}")
    print(f"✓ API_HASH loaded: {API_HASH[:10]}..." if len(API_HASH) > 10 else "✓ API_HASH loaded")
else:
    print("✗ ERROR: API_ID or API_HASH not found!")
    print(f"  API_ID: {API_ID}")
    print(f"  API_HASH: {API_HASH}")

# n8n webhooks
N8N_WEBHOOK_INCOMING = os.getenv("N8N_WEBHOOK_INCOMING")
N8N_WEBHOOK_STATUS = os.getenv("N8N_WEBHOOK_STATUS")
N8N_WEBHOOK_ACCOUNT = os.getenv("N8N_WEBHOOK_ACCOUNT")

# Google Sheets settings
GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID")
GOOGLE_CREDENTIALS_FILE = os.getenv(
    "GOOGLE_CREDENTIALS_FILE",
    str(BASE_DIR / "credentials.json")
)

# Testing mode - use mock storage instead of Google Sheets
USE_MOCK_STORAGE = os.getenv("USE_MOCK_STORAGE", "false").lower() == "true"

# Limits
MAX_DAILY_ACTIVE = int(os.getenv("MAX_DAILY_ACTIVE", "7"))
MAX_DAILY_WARMING = int(os.getenv("MAX_DAILY_WARMING", "3"))
COOLDOWN_HOURS = int(os.getenv("COOLDOWN_HOURS", "24"))

# Proxy settings (defaults)
PROXY_ENABLED = os.getenv("PROXY_ENABLED", "false").lower() == "true"
DEFAULT_PROXY_TYPE = os.getenv("DEFAULT_PROXY_TYPE", "socks5")
DEFAULT_PROXY_HOST = os.getenv("DEFAULT_PROXY_HOST", "")
DEFAULT_PROXY_PORT = os.getenv("DEFAULT_PROXY_PORT", "")
DEFAULT_PROXY_USER = os.getenv("DEFAULT_PROXY_USER", "")
DEFAULT_PROXY_PASS = os.getenv("DEFAULT_PROXY_PASS", "")

# Server settings
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Directory paths
INCOMING_DIR = Path(os.getenv("INCOMING_DIR", str(BASE_DIR / "incoming")))
UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", str(BASE_DIR / "uploads")))
SESSIONS_DIR = Path(os.getenv("SESSIONS_DIR", str(BASE_DIR / "sessions")))
TEMP_DIR = Path(os.getenv("TEMP_DIR", str(BASE_DIR / "temp")))
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", str(BASE_DIR / "media")))
BACKUPS_DIR = Path(os.getenv("BACKUPS_DIR", str(BASE_DIR / "backups")))

# Create directories if they don't exist
for directory in [INCOMING_DIR, UPLOADS_DIR, SESSIONS_DIR, TEMP_DIR, MEDIA_DIR, BACKUPS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Account statuses
class AccountStatus:
    CHECKING = "checking"
    WARMING = "warming"
    ACTIVE = "active"
    COOLDOWN = "cooldown"
    LIMITED = "limited"
    BANNED = "banned"

# Message types
class MessageType:
    TEXT = "text"
    PHOTO = "photo"
    VIDEO_NOTE = "video_note"
    VOICE = "voice"
    VIDEO = "video"
    DOCUMENT = "document"

# Error codes
class ErrorCode:
    ACCOUNT_BANNED = "account_banned"
    INVALID_TDATA = "invalid_tdata"
    ALREADY_EXISTS = "already_exists"
    CONVERSION_FAILED = "conversion_failed"
    NO_AVAILABLE_ACCOUNTS = "no_available_accounts"
    USER_BLOCKED = "user_blocked"
    FLOOD_WAIT = "flood_wait"

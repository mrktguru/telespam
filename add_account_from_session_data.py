#!/usr/bin/env python3
"""
Add account from session data (AUTH KEY, DC ID, USER ID)
"""

import asyncio
import sys
import os
import sqlite3
from pathlib import Path
from datetime import datetime

# Use database for accounts
from database import db

# Import config to use proper API credentials from .env
import config


async def create_session_file(session_path: str, auth_key: bytes, dc_id: int):
    """
    Create Telethon session file with proper structure

    Args:
        session_path: Path to .session file (without .session extension)
        auth_key: Authorization key (bytes)
        dc_id: Data center ID (1-5)
    """
    from telethon import TelegramClient
    from telethon.sessions import SQLiteSession

    # Default DC addresses
    dc_addresses = {
        1: ('149.154.175.53', 443),
        2: ('149.154.167.51', 443),
        3: ('149.154.175.100', 443),
        4: ('149.154.167.91', 443),
        5: ('91.108.56.130', 443),
    }

    if dc_id not in dc_addresses:
        raise ValueError(f"Unknown DC ID: {dc_id}")

    server_address, port = dc_addresses[dc_id]

    # Create a temporary client to initialize the session structure
    # IMPORTANT: Use API credentials from .env for spam/outreach functionality!
    # Telegram Desktop credentials (611335) DON'T WORK for unknown users
    if not config.API_ID or not config.API_HASH:
        raise ValueError("API_ID and API_HASH must be set in .env file! Get them from https://my.telegram.org")
    
    temp_client = TelegramClient(session_path, api_id=config.API_ID, api_hash=config.API_HASH)

    # Don't connect, just create the session file structure
    # This will create the proper SQLite structure
    session = temp_client.session

    # Now manually update the session with our auth_key
    session_file = f"{session_path}.session"

    # Connect to the SQLite database
    conn = sqlite3.connect(session_file)
    cursor = conn.cursor()

    # Update sessions table with our auth_key and dc_id
    cursor.execute('''
        INSERT OR REPLACE INTO sessions
        (dc_id, server_address, port, auth_key, takeout_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (dc_id, server_address, port, auth_key, None))

    conn.commit()
    conn.close()


async def add_account_from_session_data():
    """Add account from AUTH KEY and DC ID"""

    print("\n" + "=" * 70)
    print("  ADD ACCOUNT FROM SESSION DATA")
    print("=" * 70)
    print()
    print("This method uses existing AUTH KEY and DC ID to create a session")
    print()

    # Get phone number
    print("📱 Step 1: Phone Number")
    print()
    phone = input("Phone (with country code, e.g., +79991234567): ").strip()

    if not phone:
        print("❌ Phone number is required!")
        return 1

    # Get AUTH KEY
    print()
    print("🔑 Step 2: AUTH KEY")
    print()
    print("Enter AUTH KEY in hex format (256 characters / 128 bytes)")
    print("Example: a1b2c3d4e5f6...")
    print()
    auth_key_hex = input("AUTH KEY (hex): ").strip()

    if not auth_key_hex:
        print("❌ AUTH KEY is required!")
        return 1

    # Validate and convert AUTH KEY
    try:
        # Remove spaces and common separators
        auth_key_hex = auth_key_hex.replace(' ', '').replace(':', '').replace('-', '')

        # Convert hex to bytes
        auth_key = bytes.fromhex(auth_key_hex)

        # AUTH KEY should be 256 bytes (2048 bits) or 128 bytes (1024 bits)
        if len(auth_key) not in [128, 256]:
            print(f"❌ Invalid AUTH KEY length: {len(auth_key)} bytes")
            print(f"   Expected: 128 or 256 bytes (got {len(auth_key_hex)} hex chars)")
            return 1

        print(f"✓ AUTH KEY: {len(auth_key)} bytes")

    except ValueError as e:
        print(f"❌ Invalid AUTH KEY format: {e}")
        print("   AUTH KEY must be in hex format (0-9, a-f)")
        return 1

    # Get DC ID
    print()
    print("🌐 Step 3: DC ID (Data Center)")
    print()
    print("Valid DC IDs: 1, 2, 3, 4, 5")
    print()
    dc_id_str = input("DC ID: ").strip()

    try:
        dc_id = int(dc_id_str)
        if dc_id not in [1, 2, 3, 4, 5]:
            print("❌ DC ID must be between 1 and 5")
            return 1
    except ValueError:
        print("❌ DC ID must be a number")
        return 1

    # Get USER ID (optional)
    print()
    print("👤 Step 4: USER ID (optional)")
    print()
    user_id_str = input("USER ID (press Enter to skip): ").strip()

    user_id = None
    if user_id_str:
        try:
            user_id = int(user_id_str)
        except ValueError:
            print("⚠️  Invalid USER ID, skipping...")

    # Normalize phone and create session directory
    from phone_utils import normalize_phone, phone_to_filename

    phone = normalize_phone(phone)
    session_name = phone_to_filename(phone)

    sessions_dir = Path(__file__).parent / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_file = sessions_dir / f"{session_name}.session"

    print()
    print("=" * 70)
    print("  Creating Session...")
    print("=" * 70)
    print()

    try:
        # Create session file
        await create_session_file(str(session_file.with_suffix('')), auth_key, dc_id)
        print(f"✓ Session file created: {session_file}")

        # Test connection
        print()
        print("🔌 Testing connection...")

        from telethon import TelegramClient

        # IMPORTANT: Use API credentials from .env for spam/outreach functionality!
        # Telegram Desktop credentials (611335) DON'T WORK for unknown users
        if not config.API_ID or not config.API_HASH:
            raise ValueError("API_ID and API_HASH must be set in .env file! Get them from https://my.telegram.org")

        client = TelegramClient(
            str(session_file.with_suffix('')),
            api_id=config.API_ID,
            api_hash=config.API_HASH
        )

        await client.connect()

        if not await client.is_user_authorized():
            print("❌ Session is not authorized!")
            print("   The AUTH KEY may be invalid or expired")
            await client.disconnect()
            session_file.unlink()
            return 1

        # Get account info
        me = await client.get_me()

        print()
        print("=" * 70)
        print("✅ CONNECTION SUCCESSFUL!")
        print("=" * 70)
        print(f"Phone: {me.phone}")
        print(f"Username: @{me.username}" if me.username else "Username: (not set)")
        print(f"Name: {me.first_name} {me.last_name or ''}")
        print(f"User ID: {me.id}")
        print()

        await client.disconnect()

        # Add to system
        print("💾 Adding to system...")
        print()

        account_id = f"acc_{session_name}"

        # IMPORTANT: Use API credentials from .env for spam/outreach functionality!
        # These credentials are saved to database and used for all future operations
        if not config.API_ID or not config.API_HASH:
            raise ValueError("API_ID and API_HASH must be set in .env file! Get them from https://my.telegram.org")

        account_data = {
            'id': account_id,
            'phone': me.phone,
            'username': me.username,
            'first_name': me.first_name,
            'last_name': me.last_name or '',
            'user_id': me.id,
            'session_file': str(session_file),
            'api_id': config.API_ID,
            'api_hash': config.API_HASH,
            'status': 'warming',
            'daily_sent': 0,
            'total_sent': 0,
            'last_message_time': None,
            'warming_stage': 1,
            'proxy': None,
            'added_at': datetime.now().isoformat(),
            'type': 'session_data',
            'dc_id': dc_id
        }

        db.add_account(account_data)

        print("=" * 70)
        print("🎉 SUCCESS! Account added to system")
        print("=" * 70)
        print()
        print(f"Account ID: {account_id}")
        print(f"DC ID: {dc_id}")
        print(f"Status: warming (safe mode)")
        print(f"Session: {session_file}")
        print()
        print("✅ Ready to use!")
        print()
        print("Next steps:")
        print("  1. Add users for outreach: python add_users_cli.py")
        print("  2. Start campaign: python start_outreach_cli.py")
        print()

        return 0

    except Exception as e:
        print()
        print(f"❌ Error: {e}")
        print()

        # Clean up failed session
        if session_file.exists():
            session_file.unlink()

        return 1


def main():
    try:
        return asyncio.run(add_account_from_session_data())
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())

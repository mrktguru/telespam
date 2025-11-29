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

# Set mock storage mode
os.environ['USE_MOCK_STORAGE'] = 'true'

from mock_sheets import sheets_manager


def create_session_file(session_path: str, auth_key: bytes, dc_id: int,
                        server_address: str = None, port: int = None):
    """
    Create Telethon session file manually

    Args:
        session_path: Path to .session file
        auth_key: Authorization key (bytes)
        dc_id: Data center ID (1-5)
        server_address: Optional server address
        port: Optional port
    """

    # Default DC addresses
    dc_addresses = {
        1: ('149.154.175.53', 443),
        2: ('149.154.167.51', 443),
        3: ('149.154.175.100', 443),
        4: ('149.154.167.91', 443),
        5: ('91.108.56.130', 443),
    }

    if not server_address or not port:
        if dc_id in dc_addresses:
            server_address, port = dc_addresses[dc_id]
        else:
            raise ValueError(f"Unknown DC ID: {dc_id}")

    # Create SQLite database
    conn = sqlite3.connect(session_path)
    cursor = conn.cursor()

    # Create tables (Telethon session structure)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            dc_id INTEGER PRIMARY KEY,
            server_address TEXT,
            port INTEGER,
            auth_key BLOB,
            takeout_id INTEGER
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS entities (
            id INTEGER PRIMARY KEY,
            hash INTEGER NOT NULL,
            username TEXT,
            phone TEXT,
            name TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS version (
            version INTEGER PRIMARY KEY
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sent_files (
            md5_digest BLOB,
            file_size INTEGER,
            type INTEGER,
            id INTEGER,
            hash INTEGER,
            PRIMARY KEY(md5_digest, file_size, type)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS update_state (
            id INTEGER PRIMARY KEY,
            pts INTEGER,
            qts INTEGER,
            date INTEGER,
            seq INTEGER
        )
    ''')

    # Insert data (with takeout_id = NULL)
    cursor.execute('INSERT OR REPLACE INTO sessions VALUES (?, ?, ?, ?, ?)',
                   (dc_id, server_address, port, auth_key, None))

    cursor.execute('INSERT OR REPLACE INTO version VALUES (?)', (9,))

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

    # Create session directory
    sessions_dir = Path(__file__).parent / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    session_name = phone.replace('+', '').replace(' ', '')
    session_file = sessions_dir / f"{session_name}.session"

    print()
    print("=" * 70)
    print("  Creating Session...")
    print("=" * 70)
    print()

    try:
        # Create session file
        create_session_file(str(session_file), auth_key, dc_id)
        print(f"✓ Session file created: {session_file}")

        # Test connection
        print()
        print("🔌 Testing connection...")

        from telethon import TelegramClient

        # Note: We don't have API ID/Hash, but we can use dummy values
        # since we already have auth_key
        client = TelegramClient(
            str(session_file.with_suffix('')),
            api_id=1,  # Dummy value
            api_hash='x' * 32  # Dummy value
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

        account_data = {
            'id': account_id,
            'phone': me.phone,
            'username': me.username,
            'first_name': me.first_name,
            'last_name': me.last_name or '',
            'user_id': me.id,
            'session_file': str(session_file),
            'api_id': 1,  # Dummy
            'api_hash': 'x' * 32,  # Dummy
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

        sheets_manager.add_account(account_data)

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

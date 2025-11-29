#!/usr/bin/env python3
"""
Add account manually via phone number + API credentials
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime

# Set mock storage mode
os.environ['USE_MOCK_STORAGE'] = 'true'

from mock_sheets import sheets_manager


async def create_and_add_account():
    """Create session and add to system"""

    print("\n" + "=" * 70)
    print("  ADD ACCOUNT MANUALLY - Phone + API Credentials")
    print("=" * 70)
    print()

    # Import telethon
    try:
        from telethon import TelegramClient
    except ImportError:
        print("❌ Telethon not installed!")
        print("Install it with: pip install telethon")
        return 1

    # Get API credentials
    print("📋 Step 1: API Credentials")
    print()
    print("Get them from: https://my.telegram.org → API development tools")
    print()

    api_id = input("API ID: ").strip()
    api_hash = input("API Hash: ").strip()

    if not api_id or not api_hash:
        print("❌ API ID and Hash are required!")
        return 1

    # Validate API Hash (should be 32 hex characters)
    if len(api_hash) != 32:
        print("❌ Invalid API Hash!")
        print(f"   API Hash must be exactly 32 characters")
        print(f"   You entered: {len(api_hash)} characters")
        print()
        print("💡 Get correct API Hash from https://my.telegram.org")
        print("   It looks like: abc123def456...")
        return 1

    try:
        api_id = int(api_id)
    except ValueError:
        print("❌ API ID must be a number!")
        return 1

    # Validate API ID range (must fit in 32-bit signed integer)
    if api_id <= 0 or api_id > 2147483647:
        print("❌ Invalid API ID!")
        print(f"   API ID must be between 1 and 2147483647")
        print(f"   You entered: {api_id}")
        print()
        print("💡 Get correct API ID from https://my.telegram.org")
        print("   It's usually 7-8 digits (e.g., 1234567 or 12345678)")
        return 1

    # Get phone number
    print()
    print("📱 Step 2: Phone Number")
    print()
    phone = input("Phone (with country code, e.g., +79991234567): ").strip()

    if not phone:
        print("❌ Phone number is required!")
        return 1

    # Normalize phone and create session directory
    from phone_utils import normalize_phone, phone_to_filename

    phone = normalize_phone(phone)
    session_name = phone_to_filename(phone)

    sessions_dir = Path(__file__).parent / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_file = sessions_dir / f"{session_name}.session"

    print()
    print("🔐 Step 3: Authentication")
    print()

    # Create client
    client = TelegramClient(str(session_file.with_suffix('')), api_id, api_hash)

    try:
        # Connect
        await client.connect()

        # Check if already authorized
        if not await client.is_user_authorized():
            print("📨 Sending code to your Telegram app...")
            await client.send_code_request(phone)

            code = input("\nEnter the code you received: ").strip()

            try:
                await client.sign_in(phone, code)
            except Exception as e:
                if "password" in str(e).lower() or "2fa" in str(e).lower():
                    password = input("Enter your 2FA password: ").strip()
                    await client.sign_in(password=password)
                else:
                    raise

        # Get account info
        me = await client.get_me()

        print()
        print("=" * 70)
        print("✅ SESSION CREATED!")
        print("=" * 70)
        print(f"Phone: {me.phone}")
        print(f"Username: @{me.username}" if me.username else "Username: (not set)")
        print(f"Name: {me.first_name} {me.last_name or ''}")
        print(f"User ID: {me.id}")
        print()

        await client.disconnect()

        # Add to system
        print("💾 Step 4: Adding to System")
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
            'api_id': api_id,
            'api_hash': api_hash,
            'status': 'warming',
            'daily_sent': 0,
            'total_sent': 0,
            'last_message_time': None,
            'warming_stage': 1,
            'proxy': None,
            'added_at': datetime.now().isoformat(),
            'type': 'manual'  # Mark as manually added
        }

        sheets_manager.add_account(account_data)

        print("=" * 70)
        print("🎉 SUCCESS! Account added to system")
        print("=" * 70)
        print()
        print(f"Account ID: {account_id}")
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

        if client.is_connected():
            await client.disconnect()

        # Clean up failed session
        if session_file.exists():
            session_file.unlink()

        return 1


def main():
    try:
        return asyncio.run(create_and_add_account())
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())

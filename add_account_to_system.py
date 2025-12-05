#!/usr/bin/env python3
"""
Add your Telegram session to the outreach system
"""

import asyncio
import sys
import os
from pathlib import Path


async def add_account():
    """Add account to the system"""

    print("=" * 60)
    print("  ADD ACCOUNT TO SYSTEM")
    print("=" * 60)
    print()

    # Check if using mock storage
    use_mock = os.getenv('USE_MOCK_STORAGE', 'false').lower() == 'true'

    if use_mock:
        print("ℹ️  Using MOCK storage (test mode)")
    else:
        print("ℹ️  Using Google Sheets storage (production mode)")

    print()

    # Import telethon
    try:
        from telethon import TelegramClient
    except ImportError:
        print("❌ Telethon not installed!")
        print("Install it with: pip install telethon")
        sys.exit(1)

    # Load config
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except:
        pass

    # Get API credentials
    api_id = os.getenv('API_ID')
    api_hash = os.getenv('API_HASH')

    if not api_id or not api_hash:
        print("❌ API credentials not found in .env")
        sys.exit(1)

    # Find session files
    sessions_dir = Path(__file__).parent / "sessions"
    session_files = list(sessions_dir.glob("*.session"))

    if not session_files:
        print("❌ No session files found!")
        print("Please run create_session.py first")
        sys.exit(1)

    # Select session
    print("Available sessions:")
    for i, session_file in enumerate(session_files, 1):
        print(f"{i}. {session_file.stem}")

    print()
    if len(session_files) == 1:
        selected_session = session_files[0]
        print(f"Using session: {selected_session.stem}")
    else:
        choice = input(f"Select session (1-{len(session_files)}): ").strip()
        try:
            selected_session = session_files[int(choice) - 1]
        except:
            print("❌ Invalid choice")
            sys.exit(1)

    print()

    # Create client
    client = TelegramClient(
        str(selected_session.with_suffix('')),
        int(api_id),
        api_hash
    )

    try:
        await client.connect()

        if not await client.is_user_authorized():
            print("❌ Session expired!")
            await client.disconnect()
            sys.exit(1)

        # Get account info
        me = await client.get_me()

        print("Account information:")
        print(f"  Phone: {me.phone}")
        print(f"  Username: @{me.username}" if me.username else "  Username: (not set)")
        print(f"  Name: {me.first_name} {me.last_name or ''}")
        print(f"  User ID: {me.id}")
        print()

        await client.disconnect()

        # Add to system - use database
        from database import db
        from datetime import datetime

        # Generate account ID
        accounts = db.get_all_accounts()
        max_id = 0
        for acc in accounts:
            acc_id = acc.get('id', '')
            if acc_id.startswith('acc_'):
                try:
                    num = int(acc_id.replace('acc_', ''))
                    max_id = max(max_id, num)
                except:
                    pass

        account_id = f"acc_{max_id + 1}"

        # Prepare account data
        account = {
            "id": account_id,
            "phone": me.phone,
            "username": me.username or "",
            "first_name": me.first_name,
            "session_file": str(selected_session),
            "status": "active",  # Set as active for immediate use
            "daily_sent": 0,
            "total_sent": 0,
            "cooldown_until": None,
            "last_used_at": datetime.now().isoformat(),
            "added_at": datetime.now().isoformat(),
            "flood_count": 0,
            "use_proxy": False,
            "proxy": None,
            "notes": "Main account"
        }

        # Add to database
        success = db.add_account(account)

        if success:
            print("=" * 60)
            print("✅ ACCOUNT ADDED TO SYSTEM!")
            print("=" * 60)
            print(f"Account ID: {account_id}")
            print(f"Phone: {me.phone}")
            print(f"Status: active")
            print()
            print("You can now use this account for sending messages!")
            print()

            # Show summary
            all_accounts = db.get_all_accounts()
            print(f"Total accounts in system: {len(all_accounts)}")

        else:
            print("❌ Failed to add account")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        await client.disconnect()
        sys.exit(1)


if __name__ == "__main__":
    print()
    asyncio.run(add_account())
    print()
    print("Next steps:")
    print("1. Start the API server: python main.py")
    print("2. Send messages via API or test_send_message.py")
    print()

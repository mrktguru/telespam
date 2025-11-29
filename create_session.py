#!/usr/bin/env python3
"""
Create Telegram session for your account
This script will help you authenticate and create a .session file
"""

import asyncio
import sys
from pathlib import Path


async def create_session():
    """Create Telegram session interactively"""

    print("=" * 60)
    print("  TELEGRAM SESSION CREATOR")
    print("=" * 60)
    print()

    # Import telethon
    try:
        from telethon import TelegramClient
    except ImportError:
        print("❌ Telethon not installed!")
        print("Install it with: pip install telethon")
        sys.exit(1)

    # Get API credentials
    print("First, you need API credentials from https://my.telegram.org")
    print()
    print("Steps to get credentials:")
    print("1. Go to https://my.telegram.org")
    print("2. Login with your phone number")
    print("3. Go to 'API development tools'")
    print("4. Create an app if you don't have one")
    print("5. Copy API ID and API Hash")
    print()

    api_id = input("Enter your API ID: ").strip()
    api_hash = input("Enter your API Hash: ").strip()

    if not api_id or not api_hash:
        print("❌ API ID and Hash are required!")
        sys.exit(1)

    # Get phone number
    print()
    phone = input("Enter your phone number (with country code, e.g., +79991234567): ").strip()

    if not phone:
        print("❌ Phone number is required!")
        sys.exit(1)

    # Normalize phone and create session file
    from phone_utils import normalize_phone, phone_to_filename

    phone = normalize_phone(phone)
    session_name = phone_to_filename(phone)

    # Create session file
    session_file = Path(__file__).parent / "sessions" / f"{session_name}.session"
    session_file.parent.mkdir(parents=True, exist_ok=True)

    print()
    print(f"Creating session: {session_file}")
    print()

    # Create client
    client = TelegramClient(str(session_file.with_suffix('')), int(api_id), api_hash)

    try:
        # Connect
        await client.connect()

        # Check if already authorized
        if not await client.is_user_authorized():
            print("Sending code to your Telegram app...")
            await client.send_code_request(phone)

            code = input("Enter the code you received: ").strip()

            try:
                await client.sign_in(phone, code)
            except Exception as e:
                if "password" in str(e).lower():
                    password = input("Enter your 2FA password: ").strip()
                    await client.sign_in(password=password)
                else:
                    raise

        # Get account info
        me = await client.get_me()

        print()
        print("=" * 60)
        print("✅ SUCCESS! Session created")
        print("=" * 60)
        print(f"Phone: {me.phone}")
        print(f"Username: @{me.username}" if me.username else "Username: (not set)")
        print(f"Name: {me.first_name} {me.last_name or ''}")
        print(f"User ID: {me.id}")
        print()
        print(f"Session file: {session_file}")
        print()
        print("You can now use this session for sending messages!")
        print()

        # Save credentials to .env
        env_file = Path(__file__).parent / ".env"

        print("Would you like to save API credentials to .env? (yes/no)")
        save_env = input().strip().lower()

        if save_env == 'yes':
            # Read existing .env or create new
            env_content = ""
            if env_file.exists():
                env_content = env_file.read_text()

            # Update or add API credentials
            lines = env_content.split('\n') if env_content else []
            new_lines = []
            api_id_found = False
            api_hash_found = False
            mock_storage_found = False

            for line in lines:
                if line.startswith('API_ID='):
                    new_lines.append(f'API_ID={api_id}')
                    api_id_found = True
                elif line.startswith('API_HASH='):
                    new_lines.append(f'API_HASH={api_hash}')
                    api_hash_found = True
                elif line.startswith('USE_MOCK_STORAGE='):
                    new_lines.append('USE_MOCK_STORAGE=false')
                    mock_storage_found = True
                else:
                    new_lines.append(line)

            if not api_id_found:
                new_lines.insert(0, f'API_ID={api_id}')
            if not api_hash_found:
                new_lines.insert(1, f'API_HASH={api_hash}')
            if not mock_storage_found:
                new_lines.append('USE_MOCK_STORAGE=false')

            env_file.write_text('\n'.join(new_lines))
            print(f"✅ Saved to {env_file}")

        await client.disconnect()

        return {
            'phone': me.phone,
            'username': me.username,
            'first_name': me.first_name,
            'user_id': me.id,
            'session_file': str(session_file)
        }

    except Exception as e:
        print(f"❌ Error: {e}")
        await client.disconnect()
        sys.exit(1)


if __name__ == "__main__":
    print()
    result = asyncio.run(create_session())
    print()
    print("Next steps:")
    print("1. Use test_send_message.py to send a test message")
    print("2. Or add this account to the system with add_account_to_system.py")
    print()

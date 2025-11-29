#!/usr/bin/env python3
"""
Test AUTH KEY with different API credentials
"""

import asyncio
import sys
from pathlib import Path
from telethon import TelegramClient

# Different official Telegram API credentials to try
API_CREDENTIALS = {
    'Telegram Desktop': {
        'api_id': 611335,
        'api_hash': 'd524b414d21f4d37f08684c1df41ac9c'
    },
    'Telegram Android': {
        'api_id': 6,
        'api_hash': 'eb06d4abfb49dc3eeb1aeb98ae0f581e'
    },
    'Telegram iOS': {
        'api_id': 1,
        'api_hash': 'e17ac360fd072f83d5d08db45ce9a121'
    },
    'Telegram Web': {
        'api_id': 2496,
        'api_hash': '8da85b0d5bfe62527e5b244c209159c3'
    }
}


async def test_session_with_credentials(session_file: str):
    """Test existing session file with different API credentials"""

    print("\n" + "=" * 70)
    print("  AUTH KEY TESTER - Try different API credentials")
    print("=" * 70)
    print()

    session_path = Path(session_file)

    if not session_path.exists():
        print(f"❌ Session file not found: {session_file}")
        return 1

    print(f"📁 Session file: {session_path}")
    print()
    print("Testing with different API credentials...")
    print()

    for name, creds in API_CREDENTIALS.items():
        print(f"🔍 Trying: {name}")
        print(f"   API ID: {creds['api_id']}")

        try:
            # Create client with these credentials
            client = TelegramClient(
                str(session_path.with_suffix('')),
                api_id=creds['api_id'],
                api_hash=creds['api_hash']
            )

            await client.connect()

            if await client.is_user_authorized():
                me = await client.get_me()

                print(f"   ✅ SUCCESS!")
                print(f"   Phone: {me.phone}")
                print(f"   Username: @{me.username}" if me.username else "   Username: (not set)")
                print(f"   Name: {me.first_name} {me.last_name or ''}")
                print()
                print("=" * 70)
                print(f"🎉 WORKING CREDENTIALS: {name}")
                print("=" * 70)
                print(f"   API ID: {creds['api_id']}")
                print(f"   API Hash: {creds['api_hash']}")
                print()

                await client.disconnect()
                return 0
            else:
                print(f"   ❌ Not authorized")

            await client.disconnect()

        except Exception as e:
            print(f"   ❌ Error: {str(e)[:50]}...")

        print()

    print("=" * 70)
    print("❌ No working credentials found")
    print("=" * 70)
    print()
    print("The AUTH KEY may be invalid or expired.")
    print()

    return 1


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_auth_key.py <session_file>")
        print()
        print("Example:")
        print("  python test_auth_key.py sessions/37258591162.session")
        return 1

    session_file = sys.argv[1]
    return asyncio.run(test_session_with_credentials(session_file))


if __name__ == "__main__":
    sys.exit(main())

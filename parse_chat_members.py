#!/usr/bin/env python3
"""
Parse users from chat to get their access_hash
Then you can send messages to them even without username
"""

import asyncio
from telethon import TelegramClient
from pathlib import Path
import json

# Your API credentials
API_ID = 37708785
API_HASH = "7ed610a63e994fc092c67de2140a7465"

async def parse_chat_members(chat_link_or_username):
    """Parse all members from a chat to get their entities with access_hash"""

    # Find your session file
    session_file = Path("sessions/37258591162.session")
    if not session_file.exists():
        print("❌ Session file not found!")
        print("First add your account with: python add_account_cli.py")
        return

    client = TelegramClient(
        str(session_file.with_suffix('')),
        API_ID,
        API_HASH
    )

    await client.connect()

    if not await client.is_user_authorized():
        print("❌ Session expired!")
        return

    print(f"✅ Logged in")
    print(f"📥 Parsing members from: {chat_link_or_username}")
    print()

    try:
        # Get chat entity
        chat = await client.get_entity(chat_link_or_username)
        print(f"✅ Found chat: {chat.title if hasattr(chat, 'title') else chat_link_or_username}")

        # Get all participants
        users_data = []
        async for user in client.iter_participants(chat):
            if not user.bot:  # Skip bots
                user_info = {
                    'user_id': user.id,
                    'username': user.username if user.username else None,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'phone': user.phone if hasattr(user, 'phone') and user.phone else None,
                    'access_hash': user.access_hash
                }
                users_data.append(user_info)

                username_display = f"@{user.username}" if user.username else "(no username)"
                print(f"  ✓ {user.id:12} | {username_display:20} | {user.first_name}")

        print()
        print(f"✅ Parsed {len(users_data)} users")

        # Save to JSON
        output_file = Path("parsed_users.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(users_data, f, indent=2, ensure_ascii=False)

        print(f"💾 Saved to: {output_file}")
        print()
        print("Now you can send messages to these users using their user_id")
        print("because Telethon cached their access_hash in the session!")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python parse_chat_members.py <chat_username_or_link>")
        print()
        print("Examples:")
        print("  python parse_chat_members.py @mychannel")
        print("  python parse_chat_members.py https://t.me/mychat")
        print("  python parse_chat_members.py +ABcdEf12345")
        sys.exit(1)

    chat = sys.argv[1]
    asyncio.run(parse_chat_members(chat))

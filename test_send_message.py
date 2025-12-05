#!/usr/bin/env python3
"""
Send a real test message using your Telegram session
"""

import asyncio
import sys
import os
from pathlib import Path


def safe_input(prompt):
    """Input with UTF-8 encoding fix for terminal issues"""
    try:
        return input(prompt)
    except UnicodeDecodeError:
        # Fix encoding for terminals that don't use UTF-8
        sys.stdin.reconfigure(encoding='utf-8', errors='replace')
        return input(prompt)


async def send_test_message():
    """Send test message to specified user"""

    print("=" * 60)
    print("  TELEGRAM TEST MESSAGE SENDER")
    print("=" * 60)
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
        print()
        print("Please run create_session.py first, or set API_ID and API_HASH in .env")
        sys.exit(1)

    # Find session files
    sessions_dir = Path(__file__).parent / "sessions"
    session_files = list(sessions_dir.glob("*.session"))

    if not session_files:
        print("❌ No session files found!")
        print()
        print("Please run create_session.py first to create a session")
        sys.exit(1)

    # Import phone utils
    from phone_utils import filename_to_phone

    # Select session
    print("Available sessions:")
    for i, session_file in enumerate(session_files, 1):
        phone_display = filename_to_phone(session_file.stem)
        print(f"{i}. {phone_display}")

    print()
    if len(session_files) == 1:
        selected_session = session_files[0]
        print(f"Using session: {selected_session.stem}")
    else:
        choice = safe_input(f"Select session (1-{len(session_files)}): ").strip()
        try:
            selected_session = session_files[int(choice) - 1]
        except:
            print("❌ Invalid choice")
            sys.exit(1)

    print()

    # Get target user info
    print("Target user information:")
    print("Default: @champfreak (ID: 7115610560)")
    print()

    use_default = safe_input("Use default target? (yes/no): ").strip().lower()

    if use_default == 'yes':
        target_username = "champfreak"
        target_id = 7115610560
        print(f"Using: @{target_username} (ID: {target_id})")
    else:
        target_input = safe_input("Enter username (without @) or user ID: ").strip()

        if target_input.isdigit():
            target_id = int(target_input)
            target_username = None
        else:
            target_username = target_input.replace('@', '')
            target_id = None

    print()

    # Get message
    print("Message types:")
    print("1. Text message")
    print("2. Photo")
    print("3. Video note (circle)")
    print()

    msg_type = safe_input("Select type (1-3, default 1): ").strip() or "1"

    # Create client
    client = TelegramClient(
        str(selected_session.with_suffix('')),
        int(api_id),
        api_hash
    )

    try:
        await client.connect()

        if not await client.is_user_authorized():
            print("❌ Session expired! Please run create_session.py again")
            await client.disconnect()
            sys.exit(1)

        # Get account info
        me = await client.get_me()
        print(f"✅ Logged in as: {me.first_name} (@{me.username if me.username else 'no username'})")
        print()

        # Resolve target
        if target_username:
            try:
                entity = await client.get_entity(target_username)
                target_id = entity.id
                print(f"✅ Found user: {entity.first_name} (@{target_username}, ID: {target_id})")
            except Exception as e:
                print(f"❌ Could not find user @{target_username}: {e}")
                await client.disconnect()
                sys.exit(1)
        else:
            try:
                entity = await client.get_entity(target_id)
                print(f"✅ Found user: {entity.first_name} (ID: {target_id})")
            except Exception as e:
                print(f"❌ Could not find user ID {target_id}: {e}")
                await client.disconnect()
                sys.exit(1)

        print()

        # Send message based on type
        if msg_type == "1":
            # Text message
            default_text = "🤖 Test message from Telegram Outreach System!\n\nThis is a test to verify the system is working."
            print(f"Default message:\n{default_text}")
            print()

            custom = safe_input("Use custom message? (yes/no): ").strip().lower()

            if custom == 'yes':
                print("Enter your message (press Enter twice to finish):")
                lines = []
                while True:
                    line = safe_input()
                    if not line and lines:
                        break
                    lines.append(line)
                message_text = '\n'.join(lines)
            else:
                message_text = default_text

            print()
            print("Sending message...")
            sent = await client.send_message(target_id, message_text)

            print()
            print("=" * 60)
            print("✅ MESSAGE SENT SUCCESSFULLY!")
            print("=" * 60)
            print(f"Message ID: {sent.id}")
            print(f"Date: {sent.date}")
            print(f"Text: {sent.text[:50]}...")

        elif msg_type == "2":
            # Photo
            photo_path = safe_input("Enter path to photo: ").strip()

            if not Path(photo_path).exists():
                print(f"❌ File not found: {photo_path}")
                await client.disconnect()
                sys.exit(1)

            caption = safe_input("Enter caption (optional): ").strip()

            print("Sending photo...")
            sent = await client.send_file(
                target_id,
                photo_path,
                caption=caption if caption else None
            )

            print()
            print("=" * 60)
            print("✅ PHOTO SENT SUCCESSFULLY!")
            print("=" * 60)
            print(f"Message ID: {sent.id}")

        elif msg_type == "3":
            # Video note
            video_path = safe_input("Enter path to video: ").strip()

            if not Path(video_path).exists():
                print(f"❌ File not found: {video_path}")
                await client.disconnect()
                sys.exit(1)

            print("Sending video note...")
            sent = await client.send_file(
                target_id,
                video_path,
                video_note=True
            )

            print()
            print("=" * 60)
            print("✅ VIDEO NOTE SENT SUCCESSFULLY!")
            print("=" * 60)
            print(f"Message ID: {sent.id}")

        else:
            print("❌ Invalid message type")

        await client.disconnect()
        print()

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        await client.disconnect()
        sys.exit(1)


if __name__ == "__main__":
    print()
    asyncio.run(send_test_message())
    print()
    print("✅ Test completed!")
    print()

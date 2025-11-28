#!/usr/bin/env python3
"""
CLI Account Loader - Add accounts in different formats
Supports: TDATA, SESSION files, JSON credentials
"""

import asyncio
import sys
import os
import json
import shutil
import zipfile
from pathlib import Path
from datetime import datetime

# Set mock storage mode
os.environ['USE_MOCK_STORAGE'] = 'true'

from mock_sheets import sheets_manager


def print_header(text):
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_success(text):
    print(f"✓ {text}")


def print_error(text):
    print(f"✗ {text}")


def print_info(text):
    print(f"ℹ {text}")


async def load_from_tdata(tdata_path: str):
    """Load account from tdata folder or ZIP"""

    print_header("Loading from TDATA")

    tdata_path = Path(tdata_path)

    if not tdata_path.exists():
        print_error(f"Path not found: {tdata_path}")
        return False

    # Import converter
    from converter import detect_and_process
    from accounts import add_account

    print_info(f"Processing: {tdata_path}")

    # Process tdata
    result = await detect_and_process(str(tdata_path), "CLI added account")

    if result['success']:
        print_success("TDATA converted successfully!")

        account_data = result['account']
        print_info(f"Phone: {account_data.get('phone')}")
        print_info(f"Username: @{account_data.get('username')}" if account_data.get('username') else "Username: (not set)")
        print_info(f"Name: {account_data.get('first_name')}")

        # Add to system
        add_result = await add_account(account_data)

        if add_result['success']:
            print_success(f"Account added: {add_result['account']['id']}")
            return True
        else:
            print_error(f"Failed to add account: {add_result.get('error')}")
            return False
    else:
        print_error(f"Conversion failed: {result.get('error')}")
        return False


async def load_from_session(session_path: str):
    """Load account from existing .session file"""

    print_header("Loading from SESSION file")

    session_path = Path(session_path)

    if not session_path.exists():
        print_error(f"Session file not found: {session_path}")
        return False

    from converter import process_session_file
    from accounts import add_account

    print_info(f"Processing: {session_path}")

    # Process session
    result = await process_session_file(str(session_path), "CLI added account")

    if result['success']:
        print_success("Session loaded successfully!")

        account_data = result['account']
        print_info(f"Phone: {account_data.get('phone')}")
        print_info(f"Username: @{account_data.get('username')}" if account_data.get('username') else "Username: (not set)")
        print_info(f"Name: {account_data.get('first_name')}")

        # Add to system
        add_result = await add_account(account_data)

        if add_result['success']:
            print_success(f"Account added: {add_result['account']['id']}")
            return True
        else:
            print_error(f"Failed to add account: {add_result.get('error')}")
            return False
    else:
        print_error(f"Failed to load session: {result.get('error')}")
        return False


async def load_from_json(json_path: str):
    """Load account from JSON credentials and create session"""

    print_header("Loading from JSON credentials")

    json_path = Path(json_path)

    if not json_path.exists():
        print_error(f"JSON file not found: {json_path}")
        return False

    try:
        with open(json_path, 'r') as f:
            creds = json.load(f)

        print_info("JSON format:")
        print_info('  {"phone": "+79991234567", "api_id": 12345, "api_hash": "abc..."}')
        print_info('  Optional: "password" for 2FA')
        print()

        # Validate required fields
        required = ['phone', 'api_id', 'api_hash']
        missing = [f for f in required if f not in creds]

        if missing:
            print_error(f"Missing required fields: {', '.join(missing)}")
            return False

        from telethon import TelegramClient
        from accounts import add_account

        phone = creds['phone']
        api_id = int(creds['api_id'])
        api_hash = creds['api_hash']
        password = creds.get('password')

        print_info(f"Phone: {phone}")
        print_info(f"API ID: {api_id}")

        # Create session
        sessions_dir = Path(__file__).parent / "sessions"
        sessions_dir.mkdir(exist_ok=True)

        session_file = sessions_dir / f"{phone}.session"

        client = TelegramClient(str(session_file.with_suffix('')), api_id, api_hash)

        try:
            await client.connect()

            if not await client.is_user_authorized():
                print_info("Sending auth code...")
                await client.send_code_request(phone)

                code = input("Enter the code you received: ").strip()

                try:
                    await client.sign_in(phone, code)
                except Exception as e:
                    if "password" in str(e).lower() or password:
                        if not password:
                            password = input("Enter your 2FA password: ").strip()
                        await client.sign_in(password=password)
                    else:
                        raise

            # Get account info
            me = await client.get_me()

            print_success("Session created successfully!")
            print_info(f"Phone: {me.phone}")
            print_info(f"Username: @{me.username}" if me.username else "Username: (not set)")
            print_info(f"Name: {me.first_name} {me.last_name or ''}")
            print_info(f"User ID: {me.id}")

            await client.disconnect()

            # Add to system
            account_data = {
                'phone': me.phone,
                'username': me.username or '',
                'first_name': me.first_name,
                'last_name': me.last_name or '',
                'session_file': str(session_file),
                'status': 'active',
                'notes': 'CLI added from JSON'
            }

            add_result = await add_account(account_data)

            if add_result['success']:
                print_success(f"Account added: {add_result['account']['id']}")
                return True
            else:
                print_error(f"Failed to add account: {add_result.get('error')}")
                return False

        except Exception as e:
            print_error(f"Error creating session: {e}")
            await client.disconnect()
            return False

    except json.JSONDecodeError:
        print_error("Invalid JSON file")
        return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


async def interactive_mode():
    """Interactive account loading"""

    print_header("ACCOUNT LOADER - Interactive Mode")

    print("Select account format:")
    print("1. TDATA folder or ZIP")
    print("2. SESSION file (.session)")
    print("3. JSON credentials (will create session)")
    print("4. Current session (from create_session.py)")
    print()

    choice = input("Select (1-4): ").strip()

    if choice == "1":
        path = input("Enter path to TDATA folder or ZIP: ").strip()
        return await load_from_tdata(path)

    elif choice == "2":
        path = input("Enter path to .session file: ").strip()
        return await load_from_session(path)

    elif choice == "3":
        print()
        print_info("Create JSON file with format:")
        print(json.dumps({
            "phone": "+79991234567",
            "api_id": 12345678,
            "api_hash": "your_api_hash",
            "password": "2fa_password (optional)"
        }, indent=2))
        print()

        path = input("Enter path to JSON file: ").strip()
        return await load_from_json(path)

    elif choice == "4":
        # Find existing sessions
        sessions_dir = Path(__file__).parent / "sessions"
        session_files = list(sessions_dir.glob("*.session"))

        if not session_files:
            print_error("No session files found!")
            print_info("Run create_session.py first")
            return False

        print()
        print("Available sessions:")
        for i, sf in enumerate(session_files, 1):
            print(f"{i}. {sf.stem}")

        idx = input(f"\nSelect session (1-{len(session_files)}): ").strip()

        try:
            selected = session_files[int(idx) - 1]
            return await load_from_session(str(selected))
        except:
            print_error("Invalid selection")
            return False
    else:
        print_error("Invalid choice")
        return False


async def main():
    """Main function"""

    print_header("TELEGRAM ACCOUNT LOADER")
    print_info("Add accounts in different formats: TDATA, SESSION, JSON")
    print_info("Using MOCK storage (test_data.json)")
    print()

    if len(sys.argv) > 1:
        # Command line mode
        file_path = sys.argv[1]
        file_ext = Path(file_path).suffix.lower()

        if file_ext == '.zip' or Path(file_path).is_dir():
            success = await load_from_tdata(file_path)
        elif file_ext == '.session':
            success = await load_from_session(file_path)
        elif file_ext == '.json':
            success = await load_from_json(file_path)
        else:
            print_error(f"Unsupported file type: {file_ext}")
            success = False
    else:
        # Interactive mode
        success = await interactive_mode()

    if success:
        print()
        print_header("CURRENT ACCOUNTS")
        sheets_manager.print_summary()
        print()
        print_success("Account loaded successfully!")
        print()
        print_info("Next steps:")
        print_info("1. Add users for outreach: python add_users_cli.py")
        print_info("2. Start outreach: python start_outreach_cli.py")
        return 0
    else:
        print()
        print_error("Failed to load account")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

#!/usr/bin/env python3
"""
CLI Outreach Launcher - Send messages to user list
"""

import asyncio
import sys
import os
import random
from pathlib import Path
from datetime import datetime

# Set mock storage mode
os.environ['USE_MOCK_STORAGE'] = 'true'

from mock_sheets import sheets_manager


def safe_input(prompt=""):
    """Input with UTF-8 encoding fix for terminal issues"""
    try:
        return input(prompt)
    except UnicodeDecodeError:
        # Fix encoding for terminals that don't use UTF-8
        sys.stdin.reconfigure(encoding='utf-8', errors='replace')
        return input(prompt)


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


async def send_message_to_user(account, user, message_text, settings):
    """Send message to a single user"""

    from sender import send_message

    try:
        # Get user identifiers - prefer username over user_id for strangers
        user_id = user.get('user_id')
        username = user.get('username')

        # PRIORITY: Use username if available (works for strangers)
        if username:
            # Username is best for strangers - send directly by username
            from telethon import TelegramClient
            from proxy import get_client

            client = await get_client(account, settings)
            await client.connect()

            try:
                # Send directly to username (no need to resolve first)
                target = username if not username.startswith('@') else username[1:]

                # Send message
                sent_msg = await client.send_message(f"@{target}", message_text or "")

                print_success(f"Message sent to @{target}")

                # Increment account usage
                daily_sent = int(account.get('daily_sent') or 0) + 1
                total_sent = int(account.get('total_sent') or 0) + 1
                sheets_manager.update_account(account['id'], {
                    'daily_sent': daily_sent,
                    'total_sent': total_sent
                })

                # Log success
                sheets_manager.add_log({
                    "account_id": account['id'],
                    "user_id": user_id or 0,
                    "action": "send",
                    "message_type": "text",
                    "result": "success",
                    "details": f"Message sent to @{target}"
                })

                await client.disconnect()

                return {
                    'success': True,
                    'message': f'Sent to @{target}',
                    'message_id': sent_msg.id if sent_msg else None
                }
            except Exception as e:
                print_error(f"Could not send to @{username}: {e}")

                # Log error
                sheets_manager.add_log({
                    "account_id": account['id'],
                    "user_id": user_id or 0,
                    "action": "send",
                    "message_type": "text",
                    "result": "error",
                    "details": f"Error sending to @{username}: {str(e)}"
                })

                await client.disconnect()
                return {
                    'success': False,
                    'error': f'Could not send to username: {e}'
                }

        # FALLBACK: Use user_id if no username (requires prior interaction)
        elif user_id:
            # Send message via sender.py (has entity resolution logic)
            result = await send_message(
                user_id=user_id,
                message_type='text',
                content=message_text,
                account_id=account['id']
            )
            return result
        else:
            return {
                'success': False,
                'error': 'No username or user_id provided'
            }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


async def run_outreach(message_text=None, delay_min=30, delay_max=90, max_messages=None, dry_run=False):
    """Run outreach campaign"""

    print_header("TELEGRAM OUTREACH - Starting")

    # Get accounts
    accounts = sheets_manager.get_available_accounts()

    if not accounts:
        print_error("No available accounts!")
        print_info("Add accounts with: python add_account_cli.py")
        return False

    print_success(f"Found {len(accounts)} available account(s)")

    # Let user select account
    print()
    print("Available accounts:")
    for i, acc in enumerate(accounts, 1):
        print_info(f"  {i}. {acc['phone']} (sent today: {acc.get('daily_sent', 0)})")

    print()
    if len(accounts) > 1:
        account_choice = safe_input(f"Select account (1-{len(accounts)}) or 'all' for round-robin [all]: ").strip().lower()
    else:
        account_choice = "1"
        print_info(f"Using only account: {accounts[0]['phone']}")

    # Filter selected account(s)
    selected_accounts = []
    if account_choice == '' or account_choice == 'all':
        selected_accounts = accounts
        print_success(f"Using all {len(accounts)} account(s) in round-robin mode")
    else:
        try:
            account_index = int(account_choice) - 1
            if 0 <= account_index < len(accounts):
                selected_accounts = [accounts[account_index]]
                print_success(f"Using account: {selected_accounts[0]['phone']}")
            else:
                print_error("Invalid account number!")
                return False
        except ValueError:
            print_error("Invalid input!")
            return False

    print()

    # Get users
    users = sheets_manager.get_pending_users(limit=100)

    if not users:
        print_error("No pending users!")
        print_info("Add users with: python add_users_cli.py")
        return False

    print_success(f"Found {len(users)} pending user(s)")
    print()

    # Prepare message
    if not message_text:
        print("Enter your message:")
        print("(You can use {name} placeholder for personalization)")
        print("(Press Enter twice when done)")
        print()

        lines = []
        while True:
            line = safe_input()
            if not line and lines:
                break
            lines.append(line)

        message_text = '\n'.join(lines)

    if not message_text:
        print_error("Message cannot be empty!")
        return False

    print()
    print_header("MESSAGE PREVIEW")
    print(message_text)
    print("=" * 60)
    print()

    # Confirm
    if not dry_run:
        confirm = safe_input("Start outreach? (yes/no): ").strip().lower()
        if confirm != 'yes':
            print_info("Cancelled")
            return False

    # Limit messages
    if max_messages:
        users = users[:max_messages]

    print()
    print_header(f"{'DRY RUN - ' if dry_run else ''}Sending to {len(users)} user(s)")
    print()

    # Get settings
    settings = sheets_manager.get_settings()

    # Send messages
    sent_count = 0
    failed_count = 0
    account_index = 0

    for i, user in enumerate(users, 1):
        # Select account (round-robin or single)
        account = selected_accounts[account_index % len(selected_accounts)]

        username = f"@{user.get('username')}" if user.get('username') else ""
        user_id = user.get('user_id', 0)
        target_display = username or str(user_id)

        print(f"[{i}/{len(users)}] Sending to {target_display} via {account['phone']}...")

        if dry_run:
            print_info("DRY RUN - Message not sent")
            sent_count += 1
            await asyncio.sleep(1)  # Simulate delay
            continue

        # Personalize message
        personalized_message = message_text
        if '{name}' in message_text:
            # Try to get name (would need to fetch from Telegram)
            personalized_message = message_text.replace('{name}', username or 'there')

        # Send
        result = await send_message_to_user(account, user, personalized_message, settings)

        if result['success']:
            print_success(f"Sent! Message ID: {result.get('message_id')}")

            # Update user status
            sheets_manager.update_user_status(
                user_id,
                'contacted',
                account['id']
            )

            # Create dialog record
            sheets_manager.add_dialog({
                'user_id': user_id,
                'account_id': account['id'],
                'account_phone': account['phone'],
                'stage': 1,
                'status': 'active',
                'last_message_sent': personalized_message[:100]
            })

            sent_count += 1

            # Rotate to next account
            account_index += 1

        else:
            error = result.get('error', 'Unknown error')
            print_error(f"Failed: {error}")
            failed_count += 1

            # If flood wait, pause and retry with next account
            if 'flood' in error.lower():
                print_info(f"Switching to next account...")
                account_index += 1

                # Refresh accounts list
                accounts = sheets_manager.get_available_accounts()

                if not accounts:
                    print_error("No more available accounts!")
                    break

        # Delay before next message
        if i < len(users):
            delay = random.randint(delay_min, delay_max)
            print_info(f"Waiting {delay}s before next message...")
            await asyncio.sleep(delay)

        print()

    # Summary
    print_header("OUTREACH COMPLETE")
    print_success(f"Sent: {sent_count}")
    print_error(f"Failed: {failed_count}")
    print()

    # Show updated summary
    sheets_manager.print_summary()

    return True


def show_stats():
    """Show outreach statistics"""

    print_header("OUTREACH STATISTICS")

    accounts = sheets_manager.get_all_accounts()
    users = sheets_manager.users
    dialogs = sheets_manager.dialogs

    print(f"Accounts: {len(accounts)}")
    print(f"Total users: {len(users)}")
    print(f"Active dialogs: {len(dialogs)}")
    print()

    # User stats
    pending = len([u for u in users if u.get('status') == 'pending'])
    contacted = len([u for u in users if u.get('status') == 'contacted'])
    completed = len([u for u in users if u.get('status') == 'completed'])

    print("User status:")
    print(f"  Pending: {pending}")
    print(f"  Contacted: {contacted}")
    print(f"  Completed: {completed}")
    print()

    # Account stats
    print("Accounts usage today:")
    for acc in accounts:
        print(f"  {acc['id']} ({acc['phone']}): {acc.get('daily_sent', 0)} sent")


async def main():
    """Main function"""

    print_header("TELEGRAM OUTREACH LAUNCHER")
    print_info("Send messages to your user list")
    print_info("Using MOCK storage (test_data.json)")
    print()

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "--stats":
            show_stats()
            return 0
        elif command == "--dry-run":
            max_msg = int(sys.argv[2]) if len(sys.argv) > 2 else 3
            await run_outreach(dry_run=True, max_messages=max_msg)
            return 0

    # Interactive menu
    print("Options:")
    print("1. Start outreach (interactive)")
    print("2. Start with default message (first 3 users)")
    print("3. Show statistics")
    print("4. Dry run (test without sending)")
    print()

    choice = safe_input("Select (1-4): ").strip()

    if choice == "1":
        await run_outreach()
    elif choice == "2":
        default_msg = "👋 Hi! I came across your profile and thought you might be interested in what we're building. Would love to connect!"
        await run_outreach(message_text=default_msg, max_messages=3)
    elif choice == "3":
        show_stats()
    elif choice == "4":
        max_msg = int(safe_input("How many users to test? (default 3): ").strip() or "3")
        await run_outreach(dry_run=True, max_messages=max_msg)
    else:
        print_error("Invalid choice")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

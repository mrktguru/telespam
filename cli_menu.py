#!/usr/bin/env python3
"""
Unified CLI Menu - Main interface for Telegram Outreach System
"""

import asyncio
import sys
import os
import subprocess

# Use database for accounts
from database import db


def print_header(text):
    print("\n" + "=" * 70)
    print(f"  {text.center(66)}")
    print("=" * 70)


def print_success(text):
    print(f"✓ {text}")


def print_error(text):
    print(f"✗ {text}")


def print_info(text):
    print(f"ℹ {text}")


def show_dashboard():
    """Show system dashboard"""

    print_header("DASHBOARD")

    accounts = db.get_all_accounts()
    # Still use sheets_manager for users, dialogs, logs (not migrated yet)
    from sheets_loader import sheets_manager
    users = sheets_manager.users
    dialogs = sheets_manager.dialogs
    logs = sheets_manager.logs[-10:]  # Last 10 logs

    # Accounts summary
    print("\n📱 ACCOUNTS:")
    if accounts:
        # Filter available accounts manually
        from accounts import is_account_available
        available = [acc for acc in accounts if is_account_available(acc)]
        print(f"   Total: {len(accounts)} | Available: {len(available)}")
        for acc in accounts[:5]:
            status_icon = "🟢" if acc.get('status') == 'active' else "🟡" if acc.get('status') == 'warming' else "🔴"
            print(f"   {status_icon} {acc['id']}: {acc.get('phone', 'N/A')} - sent today: {acc.get('daily_sent', 0)}")
        if len(accounts) > 5:
            print(f"   ... and {len(accounts) - 5} more")
    else:
        print("   No accounts added yet")

    # Users summary
    print("\n👥 USERS:")
    if users:
        pending = len([u for u in users if u.get('status') == 'pending'])
        contacted = len([u for u in users if u.get('status') == 'contacted'])
        completed = len([u for u in users if u.get('status') == 'completed'])

        print(f"   Total: {len(users)}")
        print(f"   📋 Pending: {pending} | 📤 Contacted: {contacted} | ✅ Completed: {completed}")
    else:
        print("   No users in the list yet")

    # Dialogs summary
    print(f"\n💬 ACTIVE DIALOGS: {len(dialogs)}")

    # Recent activity
    print("\n📊 RECENT ACTIVITY:")
    if logs:
        for log in logs[-5:]:
            action = log.get('action', 'unknown')
            result = log.get('result', 'unknown')
            icon = "✓" if result == 'success' else "✗"
            print(f"   {icon} {action} - {log.get('account_id', 'N/A')}")
    else:
        print("   No activity yet")

    print()


def run_script(script_name, *args):
    """Run a Python script"""
    try:
        cmd = [sys.executable, script_name] + list(args)
        subprocess.run(cmd)
    except Exception as e:
        print_error(f"Error running {script_name}: {e}")


async def main_menu():
    """Main menu"""

    while True:
        show_dashboard()

        print_header("MAIN MENU")
        print()
        print("🔧 SETUP:")
        print("  1. Add account (TDATA/SESSION/JSON)")
        print("  1a. Add account manually (phone + API credentials)")
        print("  1b. Add account from session data (AUTH KEY + DC ID)")
        print("  2. Add users for outreach")
        print("  3. View system status")
        print("  3a. Manage account profile (name, photo, bio)")
        print("  3b. Manage proxies")
        print()
        print("🚀 OUTREACH:")
        print("  4. Start outreach campaign")
        print("  4a. Manage rate limits (messages per day/hour)")
        print("  5. View outreach statistics")
        print("  6. Dry run (test without sending)")
        print()
        print("🧪 TESTING:")
        print("  7. Send test message")
        print("  8. Test storage operations")
        print()
        print("💾 DATA:")
        print("  9. View all data (JSON)")
        print("  10. Clear all data")
        print()
        print("  0. Exit")
        print()

        choice = input("Select option: ").strip()

        if choice == "1":
            run_script("add_account_cli.py")

        elif choice == "1a" or choice.lower() == "1a":
            run_script("add_account_manual.py")

        elif choice == "1b" or choice.lower() == "1b":
            run_script("add_account_from_session_data.py")

        elif choice == "1c" or choice.lower() == "1c":
            run_script("delete_account_cli.py")

        elif choice == "2":
            run_script("add_users_cli.py")

        elif choice == "3":
            sheets_manager.print_summary()
            input("\nPress Enter to continue...")

        elif choice == "3a" or choice.lower() == "3a":
            run_script("account_manager.py")

        elif choice == "3b" or choice.lower() == "3b":
            run_script("proxy_manager.py")

        elif choice == "4":
            run_script("start_outreach_cli.py")

        elif choice == "4a" or choice.lower() == "4a":
            run_script("rate_limiter.py")

        elif choice == "5":
            run_script("start_outreach_cli.py", "--stats")

        elif choice == "6":
            num = input("Test with how many users? (default 3): ").strip() or "3"
            run_script("start_outreach_cli.py", "--dry-run", num)

        elif choice == "7":
            run_script("test_send_message.py")

        elif choice == "8":
            run_script("test_terminal.py")

        elif choice == "9":
            import json
            from pathlib import Path

            data_file = Path(__file__).parent / "test_data.json"
            if data_file.exists():
                with open(data_file, 'r') as f:
                    data = json.load(f)
                print("\n" + json.dumps(data, indent=2))
            else:
                print_error("No data file found")

            input("\nPress Enter to continue...")

        elif choice == "10":
            confirm = input("⚠️  Clear ALL data? (yes/no): ").strip().lower()
            if confirm == 'yes':
                from sheets_loader import sheets_manager
                sheets_manager.clear_all_data()
                print_success("All data cleared")
            else:
                print_info("Cancelled")

            input("\nPress Enter to continue...")

        elif choice == "0":
            print()
            print_success("Goodbye! 👋")
            print()
            break

        else:
            print_error("Invalid option")
            input("\nPress Enter to continue...")


def main():
    """Main function"""

    print_header("🚀 TELEGRAM OUTREACH SYSTEM")
    print()
    print_info("CLI Mode - All operations through terminal")
    print_info("Data stored in: test_data.json")
    print()

    try:
        asyncio.run(main_menu())
    except KeyboardInterrupt:
        print()
        print_info("Interrupted by user")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())

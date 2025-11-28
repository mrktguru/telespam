#!/usr/bin/env python3
"""
CLI User List Manager - Add users for outreach
"""

import sys
import os
import json
from pathlib import Path

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


def add_user_interactive():
    """Add single user interactively"""

    print_header("Add User")

    print("Enter user details:")
    print()

    # Get user info
    user_input = input("Enter username (without @) or user ID: ").strip()

    if user_input.isdigit():
        user_id = int(user_input)
        username = ""
    else:
        username = user_input.replace('@', '')
        user_id = 0  # Will be resolved during sending

    source = input("Source (optional, e.g., 'LinkedIn', 'Manual'): ").strip() or "Manual"
    priority = input("Priority (1-10, default 5): ").strip() or "5"

    try:
        priority = int(priority)
        if priority < 1 or priority > 10:
            priority = 5
    except:
        priority = 5

    # Generate user_id if only username provided
    if not user_id:
        # Use hash of username as temporary ID
        user_id = hash(username) % 1000000000

    # Create user record
    user = {
        'user_id': user_id,
        'username': username,
        'source': source,
        'added_at': None,  # Will be set by sheets_manager
        'status': 'pending',
        'assigned_account': '',
        'priority': priority
    }

    # Add to storage (using internal method)
    sheets_manager.users.append(user)
    sheets_manager._save_to_file()

    print_success(f"User added: {username or user_id} (priority: {priority})")

    return True


def add_users_from_file(file_path: str):
    """Add multiple users from file"""

    print_header("Add Users from File")

    file_path = Path(file_path)

    if not file_path.exists():
        print_error(f"File not found: {file_path}")
        return False

    try:
        with open(file_path, 'r') as f:
            if file_path.suffix == '.json':
                # JSON format
                data = json.load(f)

                if isinstance(data, list):
                    users_data = data
                else:
                    users_data = data.get('users', [])

                print_info(f"Loading {len(users_data)} users from JSON...")

            else:
                # Text format (one per line)
                lines = f.read().strip().split('\n')
                users_data = []

                for line in lines:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    # Parse line: username or user_id [source] [priority]
                    parts = line.split()

                    if not parts:
                        continue

                    user_input = parts[0]

                    if user_input.isdigit():
                        user_id = int(user_input)
                        username = ""
                    else:
                        username = user_input.replace('@', '')
                        user_id = hash(username) % 1000000000

                    source = parts[1] if len(parts) > 1 else "File"
                    priority = int(parts[2]) if len(parts) > 2 else 5

                    users_data.append({
                        'user_id': user_id,
                        'username': username,
                        'source': source,
                        'priority': priority
                    })

                print_info(f"Loading {len(users_data)} users from text file...")

        # Add all users
        added = 0

        for user_data in users_data:
            user = {
                'user_id': user_data.get('user_id') or hash(user_data.get('username', '')) % 1000000000,
                'username': user_data.get('username', ''),
                'source': user_data.get('source', 'File'),
                'added_at': None,
                'status': 'pending',
                'assigned_account': '',
                'priority': user_data.get('priority', 5)
            }

            sheets_manager.users.append(user)
            added += 1

        sheets_manager._save_to_file()

        print_success(f"Added {added} users")
        return True

    except json.JSONDecodeError:
        print_error("Invalid JSON file")
        return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


def list_users():
    """List all users"""

    print_header("User List")

    users = sheets_manager.users

    if not users:
        print_info("No users in the list")
        return

    print(f"\nTotal users: {len(users)}")
    print()

    # Group by status
    pending = [u for u in users if u.get('status') == 'pending']
    contacted = [u for u in users if u.get('status') == 'contacted']
    completed = [u for u in users if u.get('status') == 'completed']

    print(f"Pending: {len(pending)}")
    print(f"Contacted: {len(contacted)}")
    print(f"Completed: {len(completed)}")
    print()

    # Show pending users
    if pending:
        print("Pending users (sorted by priority):")
        pending.sort(key=lambda x: x.get('priority', 0), reverse=True)

        for i, user in enumerate(pending[:20], 1):
            username = f"@{user.get('username')}" if user.get('username') else ""
            user_id = user.get('user_id', 0)
            priority = user.get('priority', 5)
            source = user.get('source', '')

            print(f"{i:2}. {username or user_id} - priority: {priority} - source: {source}")

        if len(pending) > 20:
            print(f"... and {len(pending) - 20} more")


def clear_users():
    """Clear all users"""

    confirm = input("Clear ALL users? (yes/no): ").strip().lower()

    if confirm == 'yes':
        sheets_manager.users = []
        sheets_manager._save_to_file()
        print_success("All users cleared")
    else:
        print_info("Cancelled")


def interactive_menu():
    """Interactive menu"""

    while True:
        print_header("USER LIST MANAGER")

        print("1. Add user (interactive)")
        print("2. Add users from file")
        print("3. List users")
        print("4. Clear all users")
        print("5. Exit")
        print()

        choice = input("Select (1-5): ").strip()

        if choice == "1":
            add_user_interactive()
        elif choice == "2":
            file_path = input("Enter file path (JSON or TXT): ").strip()
            add_users_from_file(file_path)
        elif choice == "3":
            list_users()
        elif choice == "4":
            clear_users()
        elif choice == "5":
            break
        else:
            print_error("Invalid choice")


def main():
    """Main function"""

    print_header("USER LIST MANAGER")
    print_info("Add users for Telegram outreach")
    print_info("Using MOCK storage (test_data.json)")
    print()

    if len(sys.argv) > 1:
        # Command line mode
        file_path = sys.argv[1]

        if file_path == "--list":
            list_users()
        elif file_path == "--clear":
            clear_users()
        else:
            add_users_from_file(file_path)
    else:
        # Interactive mode
        print_info("Formats supported:")
        print_info("1. JSON: [{\"user_id\": 123, \"username\": \"user\", \"priority\": 5}, ...]")
        print_info("2. TXT: one user per line: @username or user_id")
        print()

        interactive_menu()

    print()
    print_header("SUMMARY")
    list_users()
    print()

    print_info("Next steps:")
    print_info("1. Check accounts: python test_terminal.py (option 6)")
    print_info("2. Start outreach: python start_outreach_cli.py")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())

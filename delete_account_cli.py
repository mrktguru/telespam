#!/usr/bin/env python3
"""
Delete Account CLI - Remove accounts from the system
"""

import os
import sys
from pathlib import Path

# Use database for accounts
from database import db


def print_header():
    print("\n" + "=" * 70)
    print("  DELETE TELEGRAM ACCOUNT".center(70))
    print("=" * 70 + "\n")


def list_accounts():
    """List all accounts with index"""
    accounts = db.get_all_accounts()
    
    if not accounts:
        print("✗ No accounts found in the system\n")
        return None
    
    print("Current accounts:\n")
    for i, acc in enumerate(accounts, 1):
        phone = acc.get('phone', 'N/A')
        status = acc.get('status', 'unknown')
        username = acc.get('username', '')
        first_name = acc.get('first_name', '')
        acc_id = acc.get('id', 'N/A')
        
        print(f"  {i}. [{status}] {phone}")
        if username:
            print(f"      @{username}")
        if first_name:
            print(f"      {first_name}")
        print(f"      ID: {acc_id}")
        print()
    
    return accounts


def main():
    """Main function"""
    
    print_header()
    
    # List accounts
    accounts = list_accounts()
    
    if not accounts:
        return 1
    
    # Get selection
    print("Select account to delete:")
    print("  - Enter account number (1-{})".format(len(accounts)))
    print("  - Enter account ID directly")
    print("  - Enter 0 to cancel\n")
    
    selection = input("Your choice: ").strip()
    
    if selection == '0':
        print("\n✓ Cancelled\n")
        return 0
    
    # Try to parse as number (account index)
    account_id = None
    try:
        idx = int(selection)
        if 1 <= idx <= len(accounts):
            account_id = accounts[idx - 1].get('id')
        else:
            print(f"\n✗ Invalid account number. Must be between 1 and {len(accounts)}\n")
            return 1
    except ValueError:
        # Not a number, assume it's an account ID
        account_id = selection
    
    if not account_id:
        print("\n✗ Invalid selection\n")
        return 1
    
    # Get account details for confirmation
    account = db.get_account(account_id)
    if not account:
        print(f"\n✗ Account not found: {account_id}\n")
        return 1
    
    # Confirm deletion
    phone = account.get('phone', 'N/A')
    username = account.get('username', '')
    
    print(f"\n⚠️  WARNING: You are about to delete:")
    print(f"   Phone: {phone}")
    if username:
        print(f"   Username: @{username}")
    print(f"   ID: {account_id}")
    print()
    print("This action CANNOT be undone!")
    print()
    
    confirm = input("Type 'DELETE' to confirm: ").strip()
    
    if confirm != 'DELETE':
        print("\n✓ Deletion cancelled\n")
        return 0
    
    # Delete account
    success = db.delete_account(account_id)
    
    if success:
        print(f"\n✓ Account {phone} deleted successfully!\n")
        
        # Optional: Delete session file
        session_file = Path(__file__).parent / 'sessions' / f'{phone.replace("+", "")}.session'
        if session_file.exists():
            delete_session = input("Also delete session file? (y/n): ").strip().lower()
            if delete_session == 'y':
                try:
                    session_file.unlink()
                    print(f"✓ Session file deleted: {session_file}\n")
                except Exception as e:
                    print(f"✗ Could not delete session file: {e}\n")
        
        return 0
    else:
        print(f"\n✗ Failed to delete account\n")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n✓ Cancelled by user\n")
        sys.exit(0)

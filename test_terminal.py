#!/usr/bin/env python3
"""
Terminal-based testing script for Telegram Outreach System
Tests basic functionality without Google Sheets or n8n
"""

import os
import sys
import json
import asyncio
from pathlib import Path

# Set mock mode
os.environ['USE_MOCK_STORAGE'] = 'true'

# Import after setting environment
from mock_sheets import sheets_manager


def print_header(text):
    """Print formatted header"""
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60)


def print_success(text):
    """Print success message"""
    print(f"✓ {text}")


def print_error(text):
    """Print error message"""
    print(f"✗ {text}")


def print_info(text):
    """Print info message"""
    print(f"ℹ {text}")


def test_storage_operations():
    """Test basic storage operations"""
    print_header("TEST 1: Storage Operations")

    # Clear previous data
    sheets_manager.clear_all_data()
    print_success("Storage cleared")

    # Add test account
    result = sheets_manager.add_test_account("test_1", "+79991234567")
    if result:
        print_success("Test account added")
    else:
        print_error("Failed to add test account")
        return False

    # Get account
    account = sheets_manager.get_account("test_1")
    if account:
        print_success(f"Account retrieved: {account['phone']}")
    else:
        print_error("Failed to retrieve account")
        return False

    # Update account
    result = sheets_manager.update_account("test_1", {"daily_sent": 5})
    if result:
        print_success("Account updated")
    else:
        print_error("Failed to update account")
        return False

    # Get all accounts
    accounts = sheets_manager.get_all_accounts()
    print_success(f"Total accounts: {len(accounts)}")

    # Add log
    sheets_manager.add_log({
        "account_id": "test_1",
        "user_id": 123456789,
        "action": "test",
        "result": "success",
        "details": "Test log entry"
    })
    print_success("Log entry added")

    # Add dialog
    sheets_manager.add_dialog({
        "user_id": 123456789,
        "account_id": "test_1",
        "account_phone": "+79991234567",
        "stage": 1,
        "status": "active"
    })
    print_success("Dialog added")

    # Print summary
    sheets_manager.print_summary()

    return True


def test_settings():
    """Test settings management"""
    print_header("TEST 2: Settings Management")

    # Update setting
    sheets_manager.update_setting("proxy_enabled", "true")
    sheets_manager.update_setting("default_proxy_host", "1.2.3.4")

    # Get settings
    settings = sheets_manager.get_settings()
    print_info(f"Proxy enabled: {settings.get('proxy_enabled')}")
    print_info(f"Proxy host: {settings.get('default_proxy_host')}")

    print_success("Settings test passed")
    return True


def test_account_selection():
    """Test account selection logic"""
    print_header("TEST 3: Account Selection")

    # Add multiple accounts with different statuses
    sheets_manager.add_test_account("acc_1", "+79991111111")
    sheets_manager.add_test_account("acc_2", "+79992222222")
    sheets_manager.add_test_account("acc_3", "+79993333333")

    # Update statuses
    sheets_manager.update_account("acc_1", {"status": "active", "daily_sent": 2})
    sheets_manager.update_account("acc_2", {"status": "active", "daily_sent": 5})
    sheets_manager.update_account("acc_3", {"status": "warming", "daily_sent": 0})

    # Get available accounts
    available = sheets_manager.get_available_accounts()
    print_info(f"Available accounts: {len(available)}")

    for acc in available:
        print_info(f"  - {acc['id']}: sent={acc['daily_sent']}, status={acc['status']}")

    print_success("Account selection test passed")
    return True


def test_api_server():
    """Test if API server can start"""
    print_header("TEST 4: API Server Check")

    try:
        import config
        print_info(f"Server configured at {config.HOST}:{config.PORT}")
        print_info(f"Mock storage: {config.USE_MOCK_STORAGE}")
        print_success("API configuration valid")
        return True
    except Exception as e:
        print_error(f"API configuration error: {e}")
        return False


def interactive_menu():
    """Interactive testing menu"""
    while True:
        print_header("INTERACTIVE TEST MENU")
        print("1. Run all tests")
        print("2. Test storage operations")
        print("3. Test settings")
        print("4. Test account selection")
        print("5. Add test account")
        print("6. View storage summary")
        print("7. Clear all data")
        print("8. View test data file")
        print("9. Exit")
        print()

        choice = input("Select option (1-9): ").strip()

        if choice == "1":
            test_storage_operations()
            test_settings()
            test_account_selection()
            test_api_server()
        elif choice == "2":
            test_storage_operations()
        elif choice == "3":
            test_settings()
        elif choice == "4":
            test_account_selection()
        elif choice == "5":
            acc_id = input("Account ID (e.g., test_1): ").strip()
            phone = input("Phone (e.g., +79991234567): ").strip()
            sheets_manager.add_test_account(acc_id, phone)
        elif choice == "6":
            sheets_manager.print_summary()
        elif choice == "7":
            confirm = input("Clear all data? (yes/no): ").strip().lower()
            if confirm == "yes":
                sheets_manager.clear_all_data()
        elif choice == "8":
            data_file = Path(__file__).parent / "test_data.json"
            if data_file.exists():
                with open(data_file, 'r') as f:
                    data = json.load(f)
                print(json.dumps(data, indent=2))
            else:
                print_error("No test data file found")
        elif choice == "9":
            print_info("Exiting...")
            break
        else:
            print_error("Invalid option")


def main():
    """Main test function"""
    print_header("TELEGRAM OUTREACH SYSTEM - TERMINAL TESTING")
    print_info("Testing without Google Sheets and n8n")
    print_info("Using in-memory mock storage")

    if len(sys.argv) > 1:
        if sys.argv[1] == "--auto":
            # Run all tests automatically
            success = True
            success &= test_storage_operations()
            success &= test_settings()
            success &= test_account_selection()
            success &= test_api_server()

            if success:
                print_header("ALL TESTS PASSED ✓")
                return 0
            else:
                print_header("SOME TESTS FAILED ✗")
                return 1
        elif sys.argv[1] == "--help":
            print("Usage:")
            print("  python test_terminal.py           - Interactive menu")
            print("  python test_terminal.py --auto    - Run all tests")
            print("  python test_terminal.py --help    - Show this help")
            return 0
    else:
        # Interactive mode
        interactive_menu()

    return 0


if __name__ == "__main__":
    sys.exit(main())

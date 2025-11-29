"""Mock storage for testing without Google Sheets"""

from typing import Dict, List, Optional
from datetime import datetime
import json
from pathlib import Path


class MockSheetsManager:
    """In-memory storage manager for testing without Google Sheets"""

    def __init__(self):
        self.accounts: List[Dict] = []
        self.dialogs: List[Dict] = []
        self.users: List[Dict] = []
        self.logs: List[Dict] = []
        self.settings: Dict[str, str] = {
            "proxy_enabled": "false",
            "default_proxy_type": "socks5",
            "default_proxy_host": "",
            "default_proxy_port": "",
            "api_id": "",
            "api_hash": "",
            "max_daily_active": "7",
            "max_daily_warming": "3",
            "cooldown_hours": "24"
        }
        self.storage_file = Path(__file__).parent / "test_data.json"
        self._load_from_file()

    def _load_from_file(self):
        """Load data from JSON file if exists"""
        if self.storage_file.exists():
            try:
                with open(self.storage_file, 'r') as f:
                    data = json.load(f)
                    self.accounts = data.get('accounts', [])
                    self.dialogs = data.get('dialogs', [])
                    self.users = data.get('users', [])
                    self.logs = data.get('logs', [])
                    self.settings = data.get('settings', self.settings)
                print(f"Loaded test data from {self.storage_file}")
            except Exception as e:
                print(f"Could not load test data: {e}")

    def _save_to_file(self):
        """Save data to JSON file"""
        try:
            data = {
                'accounts': self.accounts,
                'dialogs': self.dialogs,
                'users': self.users,
                'logs': self.logs[-100:],  # Keep last 100 logs
                'settings': self.settings
            }
            with open(self.storage_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Could not save test data: {e}")

    # Accounts operations

    def add_account(self, account: Dict) -> bool:
        """Add new account (always starts as 'free' account without campaign_id)"""
        self.accounts.append(account)
        self._save_to_file()
        print(f"✓ Account added: {account.get('id')} - {account.get('phone')}")
        return True

    def get_account(self, account_id: str) -> Optional[Dict]:
        """Get account by ID"""
        for account in self.accounts:
            if account.get('id') == account_id:
                return account
        return None

    def get_all_accounts(self) -> List[Dict]:
        """Get all accounts"""
        return self.accounts

    def update_account(self, account_id: str, updates: Dict) -> bool:
        """Update account fields (including ID if 'new_id' is in updates)"""
        for i, account in enumerate(self.accounts):
            if account.get('id') == account_id:
                # Handle ID change if requested
                if 'new_id' in updates:
                    new_id = updates.pop('new_id')
                    self.accounts[i]['id'] = new_id
                    print(f"✓ Account ID changed: {account_id} → {new_id}")
                
                self.accounts[i].update(updates)
                self._save_to_file()
                print(f"✓ Account updated: {self.accounts[i].get('id')} - {updates}")
                return True
        return False

    def delete_account(self, account_id: str) -> bool:
        """Delete account by ID"""
        for i, account in enumerate(self.accounts):
            if account.get('id') == account_id:
                phone = account.get('phone', 'N/A')
                self.accounts.pop(i)
                self._save_to_file()
                print(f"✓ Account deleted: {account_id} - {phone}")
                return True
        print(f"✗ Account not found: {account_id}")
        return False

    def get_available_accounts(self, limit: int = 10) -> List[Dict]:
        """Get accounts available for sending"""
        import config

        available = []
        for account in self.accounts:
            status = account.get('status', '')
            if status not in ['active', 'warming']:
                continue

            daily_sent = int(account.get('daily_sent', 0))
            max_daily = config.MAX_DAILY_ACTIVE if status == 'active' else config.MAX_DAILY_WARMING

            if daily_sent >= max_daily:
                continue

            cooldown_until = account.get('cooldown_until', '')
            if cooldown_until and cooldown_until > datetime.now().isoformat():
                continue

            available.append(account)

        # Sort by daily_sent
        available.sort(key=lambda x: x.get('daily_sent', 0))
        return available[:limit]

    # Settings operations

    def get_settings(self) -> Dict:
        """Get all settings"""
        return self.settings.copy()

    def update_setting(self, key: str, value: str) -> bool:
        """Update a setting"""
        self.settings[key] = value
        self._save_to_file()
        print(f"✓ Setting updated: {key} = {value}")
        return True

    # Dialogs operations

    def add_dialog(self, dialog: Dict) -> bool:
        """Add new dialog"""
        self.dialogs.append(dialog)
        self._save_to_file()
        print(f"✓ Dialog added: user_id={dialog.get('user_id')}, account={dialog.get('account_id')}")
        return True

    def get_dialog(self, user_id: int) -> Optional[Dict]:
        """Get dialog by user_id"""
        for dialog in self.dialogs:
            if dialog.get('user_id') == user_id:
                return dialog
        return None

    def update_dialog(self, user_id: int, updates: Dict) -> bool:
        """Update dialog fields"""
        for i, dialog in enumerate(self.dialogs):
            if dialog.get('user_id') == user_id:
                self.dialogs[i].update(updates)
                self._save_to_file()
                return True
        return False

    # Logs operations

    def add_log(self, log: Dict) -> bool:
        """Add log entry"""
        log['timestamp'] = datetime.now().isoformat()
        self.logs.append(log)

        # Print log for visibility
        action = log.get('action', 'unknown')
        result = log.get('result', 'unknown')
        account_id = log.get('account_id', 'N/A')
        user_id = log.get('user_id', 'N/A')

        symbol = "✓" if result == "success" else "✗"
        print(f"{symbol} LOG [{action}] account={account_id}, user={user_id}, result={result}")

        if log.get('error'):
            print(f"  Error: {log.get('error')}")

        # Save periodically (every 10 logs)
        if len(self.logs) % 10 == 0:
            self._save_to_file()

        return True

    # Users operations

    def add_user(self, user_data: Dict) -> bool:
        """Add new user for outreach"""
        # Generate a unique ID if user_id not provided
        if not user_data.get('user_id'):
            # Use timestamp-based ID
            import time
            user_data['user_id'] = int(time.time() * 1000)

        # Add timestamp
        user_data['added_at'] = datetime.now().isoformat()

        # Set default status if not provided
        if 'status' not in user_data:
            user_data['status'] = 'pending'

        # Set campaign_id if not provided (null/None means no campaign assigned)
        if 'campaign_id' not in user_data:
            user_data['campaign_id'] = None

        self.users.append(user_data)
        self._save_to_file()
        print(f"✓ User added: {user_data.get('username') or user_data.get('user_id') or user_data.get('phone')}")
        return True

    def get_pending_users(self, limit: int = 10) -> List[Dict]:
        """Get users with status 'pending'"""
        pending = [u for u in self.users if u.get('status') == 'pending']
        pending.sort(key=lambda x: x.get('priority', 0), reverse=True)
        return pending[:limit]

    def update_user_status(self, user_id: int, status: str, assigned_account: str = '') -> bool:
        """Update user status"""
        for i, user in enumerate(self.users):
            if user.get('user_id') == user_id:
                self.users[i]['status'] = status
                if assigned_account:
                    self.users[i]['assigned_account'] = assigned_account
                self._save_to_file()
                return True
        return False

    def delete_users(self, user_ids: List) -> int:
        """Delete multiple users by ID. Returns count of deleted users."""
        deleted_count = 0
        user_ids_set = set(str(uid) for uid in user_ids)
        
        # Filter out users with matching IDs
        original_count = len(self.users)
        self.users = [u for u in self.users if str(u.get('user_id')) not in user_ids_set]
        deleted_count = original_count - len(self.users)
        
        if deleted_count > 0:
            self._save_to_file()
            print(f"✓ Deleted {deleted_count} user(s)")
        
        return deleted_count

    # Additional methods for testing

    def add_test_account(self, account_id: str = "test_acc_1", phone: str = "+79991234567"):
        """Add a test account for development"""
        account = {
            "id": account_id,
            "phone": phone,
            "username": "test_user",
            "first_name": "Test",
            "session_file": f"/app/sessions/{phone}.session",
            "status": "active",
            "daily_sent": 0,
            "total_sent": 0,
            "cooldown_until": "",
            "last_used_at": datetime.now().isoformat(),
            "added_at": datetime.now().isoformat(),
            "flood_count": 0,
            "use_proxy": False,
            "proxy_type": "",
            "proxy_host": "",
            "proxy_port": "",
            "proxy_user": "",
            "proxy_pass": "",
            "notes": "Test account"
        }
        return self.add_account(account)

    def clear_all_data(self):
        """Clear all data (for testing)"""
        self.accounts = []
        self.dialogs = []
        self.users = []
        self.logs = []
        self._save_to_file()
        print("✓ All data cleared")

    def print_summary(self):
        """Print data summary"""
        print("\n" + "="*50)
        print("MOCK STORAGE SUMMARY")
        print("="*50)
        print(f"Accounts: {len(self.accounts)}")
        for acc in self.accounts:
            print(f"  - {acc.get('id')}: {acc.get('phone')} [{acc.get('status')}] sent={acc.get('daily_sent')}/{acc.get('total_sent')}")
        print(f"Dialogs: {len(self.dialogs)}")
        print(f"Users: {len(self.users)}")
        print(f"Logs: {len(self.logs)}")
        print(f"Storage file: {self.storage_file}")
        print("="*50 + "\n")


# Global mock instance
sheets_manager = MockSheetsManager()

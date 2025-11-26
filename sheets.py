"""Google Sheets integration for Telegram Outreach System"""

import gspread
from google.oauth2.service_account import Credentials
from typing import Dict, List, Optional
from datetime import datetime
import config

# Google Sheets API scopes
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]


class SheetsManager:
    """Manager for Google Sheets operations"""

    def __init__(self):
        self.credentials = None
        self.client = None
        self.spreadsheet = None
        self._connect()

    def _connect(self):
        """Connect to Google Sheets"""
        try:
            self.credentials = Credentials.from_service_account_file(
                config.GOOGLE_CREDENTIALS_FILE,
                scopes=SCOPES
            )
            self.client = gspread.authorize(self.credentials)
            self.spreadsheet = self.client.open_by_key(config.GOOGLE_SHEETS_ID)
        except Exception as e:
            print(f"Failed to connect to Google Sheets: {e}")
            # Continue without sheets for now

    def get_worksheet(self, name: str):
        """Get worksheet by name"""
        if not self.spreadsheet:
            return None
        try:
            return self.spreadsheet.worksheet(name)
        except gspread.exceptions.WorksheetNotFound:
            # Create worksheet if it doesn't exist
            return self.spreadsheet.add_worksheet(title=name, rows=100, cols=20)

    # Accounts operations

    def add_account(self, account: Dict) -> bool:
        """Add new account to Accounts sheet"""
        try:
            worksheet = self.get_worksheet("Accounts")
            if not worksheet:
                return False

            row = [
                account.get('id', ''),
                account.get('phone', ''),
                account.get('username', ''),
                account.get('first_name', ''),
                account.get('session_file', ''),
                account.get('status', 'checking'),
                0,  # daily_sent
                0,  # total_sent
                '',  # cooldown_until
                datetime.now().isoformat(),  # last_used_at
                datetime.now().isoformat(),  # added_at
                0,  # flood_count
                account.get('use_proxy', False),
                account.get('proxy_type', ''),
                account.get('proxy_host', ''),
                account.get('proxy_port', ''),
                account.get('proxy_user', ''),
                account.get('proxy_pass', ''),
                account.get('notes', '')
            ]

            worksheet.append_row(row)
            return True
        except Exception as e:
            print(f"Error adding account to sheets: {e}")
            return False

    def get_account(self, account_id: str) -> Optional[Dict]:
        """Get account by ID"""
        try:
            worksheet = self.get_worksheet("Accounts")
            if not worksheet:
                return None

            records = worksheet.get_all_records()
            for record in records:
                if record.get('id') == account_id:
                    return record
            return None
        except Exception as e:
            print(f"Error getting account: {e}")
            return None

    def get_all_accounts(self) -> List[Dict]:
        """Get all accounts"""
        try:
            worksheet = self.get_worksheet("Accounts")
            if not worksheet:
                return []
            return worksheet.get_all_records()
        except Exception as e:
            print(f"Error getting accounts: {e}")
            return []

    def update_account(self, account_id: str, updates: Dict) -> bool:
        """Update account fields"""
        try:
            worksheet = self.get_worksheet("Accounts")
            if not worksheet:
                return False

            # Find the row
            cell = worksheet.find(account_id)
            if not cell:
                return False

            row_num = cell.row
            headers = worksheet.row_values(1)

            # Update each field
            for key, value in updates.items():
                if key in headers:
                    col_num = headers.index(key) + 1
                    worksheet.update_cell(row_num, col_num, value)

            return True
        except Exception as e:
            print(f"Error updating account: {e}")
            return False

    def get_available_accounts(self, limit: int = 10) -> List[Dict]:
        """Get accounts available for sending"""
        try:
            worksheet = self.get_worksheet("Accounts")
            if not worksheet:
                return []

            records = worksheet.get_all_records()
            available = []

            for record in records:
                status = record.get('status', '')
                if status not in ['active', 'warming']:
                    continue

                daily_sent = int(record.get('daily_sent', 0))
                max_daily = config.MAX_DAILY_ACTIVE if status == 'active' else config.MAX_DAILY_WARMING

                if daily_sent >= max_daily:
                    continue

                cooldown_until = record.get('cooldown_until', '')
                if cooldown_until and cooldown_until > datetime.now().isoformat():
                    continue

                available.append(record)

            # Sort by daily_sent (lower first)
            available.sort(key=lambda x: x.get('daily_sent', 0))

            return available[:limit]
        except Exception as e:
            print(f"Error getting available accounts: {e}")
            return []

    # Settings operations

    def get_settings(self) -> Dict:
        """Get all settings as dict"""
        try:
            worksheet = self.get_worksheet("Settings")
            if not worksheet:
                return {}

            records = worksheet.get_all_records()
            settings = {}
            for record in records:
                key = record.get('key', '')
                value = record.get('value', '')
                if key:
                    settings[key] = value

            return settings
        except Exception as e:
            print(f"Error getting settings: {e}")
            return {}

    def update_setting(self, key: str, value: str) -> bool:
        """Update a setting"""
        try:
            worksheet = self.get_worksheet("Settings")
            if not worksheet:
                return False

            # Find the setting
            cell = worksheet.find(key)
            if cell:
                # Update existing
                worksheet.update_cell(cell.row, 2, value)  # Column 2 is 'value'
            else:
                # Add new setting
                worksheet.append_row([key, value, ''])

            return True
        except Exception as e:
            print(f"Error updating setting: {e}")
            return False

    # Dialogs operations

    def add_dialog(self, dialog: Dict) -> bool:
        """Add new dialog"""
        try:
            worksheet = self.get_worksheet("Dialogs")
            if not worksheet:
                return False

            row = [
                dialog.get('user_id', ''),
                dialog.get('account_id', ''),
                dialog.get('account_phone', ''),
                dialog.get('stage', 1),
                dialog.get('status', 'active'),
                datetime.now().isoformat(),  # first_message_at
                dialog.get('last_message_sent', ''),
                '',  # last_response
                '',  # last_response_at
                dialog.get('next_message_type', ''),
                dialog.get('notes', '')
            ]

            worksheet.append_row(row)
            return True
        except Exception as e:
            print(f"Error adding dialog: {e}")
            return False

    def get_dialog(self, user_id: int) -> Optional[Dict]:
        """Get dialog by user_id"""
        try:
            worksheet = self.get_worksheet("Dialogs")
            if not worksheet:
                return None

            records = worksheet.get_all_records()
            for record in records:
                if record.get('user_id') == user_id:
                    return record
            return None
        except Exception as e:
            print(f"Error getting dialog: {e}")
            return None

    def update_dialog(self, user_id: int, updates: Dict) -> bool:
        """Update dialog fields"""
        try:
            worksheet = self.get_worksheet("Dialogs")
            if not worksheet:
                return False

            # Find the row
            cell = worksheet.find(str(user_id))
            if not cell:
                return False

            row_num = cell.row
            headers = worksheet.row_values(1)

            # Update each field
            for key, value in updates.items():
                if key in headers:
                    col_num = headers.index(key) + 1
                    worksheet.update_cell(row_num, col_num, value)

            return True
        except Exception as e:
            print(f"Error updating dialog: {e}")
            return False

    # Logs operations

    def add_log(self, log: Dict) -> bool:
        """Add log entry"""
        try:
            worksheet = self.get_worksheet("Logs")
            if not worksheet:
                return False

            row = [
                datetime.now().isoformat(),  # timestamp
                log.get('account_id', ''),
                log.get('user_id', ''),
                log.get('action', ''),
                log.get('message_type', ''),
                log.get('result', ''),
                log.get('error', ''),
                log.get('proxy_used', False),
                log.get('details', '')
            ]

            worksheet.append_row(row)
            return True
        except Exception as e:
            print(f"Error adding log: {e}")
            return False

    # Users operations

    def get_pending_users(self, limit: int = 10) -> List[Dict]:
        """Get users with status 'pending'"""
        try:
            worksheet = self.get_worksheet("Users")
            if not worksheet:
                return []

            records = worksheet.get_all_records()
            pending = [r for r in records if r.get('status') == 'pending']

            # Sort by priority (higher first)
            pending.sort(key=lambda x: x.get('priority', 0), reverse=True)

            return pending[:limit]
        except Exception as e:
            print(f"Error getting pending users: {e}")
            return []

    def update_user_status(self, user_id: int, status: str, assigned_account: str = '') -> bool:
        """Update user status"""
        try:
            worksheet = self.get_worksheet("Users")
            if not worksheet:
                return False

            cell = worksheet.find(str(user_id))
            if not cell:
                return False

            row_num = cell.row
            headers = worksheet.row_values(1)

            if 'status' in headers:
                col_num = headers.index('status') + 1
                worksheet.update_cell(row_num, col_num, status)

            if assigned_account and 'assigned_account' in headers:
                col_num = headers.index('assigned_account') + 1
                worksheet.update_cell(row_num, col_num, assigned_account)

            return True
        except Exception as e:
            print(f"Error updating user status: {e}")
            return False


# Global instance
sheets_manager = SheetsManager()

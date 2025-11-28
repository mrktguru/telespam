"""Account management for Telegram Outreach System"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
from telethon.errors import (
    FloodWaitError,
    UserBannedInChannelError,
    SessionExpiredError,
    PhoneNumberBannedError
)
import config
from sheets_loader import sheets_manager
from proxy import get_client
from uuid import uuid4


async def check_account_status(account_id: str) -> Dict:
    """
    Check if account is alive and get current status

    Args:
        account_id: Account ID to check

    Returns:
        Dict with status and account info
    """

    try:
        # Get account from sheets
        account = sheets_manager.get_account(account_id)
        if not account:
            return {
                "success": False,
                "error": "Account not found"
            }

        # Get settings for proxy
        settings = sheets_manager.get_settings()

        # Create client
        client = await get_client(account, settings)

        # Connect and check
        await client.connect()

        if not await client.is_user_authorized():
            await client.disconnect()
            return {
                "success": False,
                "error": "Session expired",
                "status": config.AccountStatus.BANNED
            }

        # Get account info
        me = await client.get_me()

        await client.disconnect()

        # Update status in sheets
        sheets_manager.update_account(account_id, {
            "status": config.AccountStatus.ACTIVE,
            "last_used_at": datetime.now().isoformat()
        })

        return {
            "success": True,
            "account": {
                "id": account_id,
                "phone": me.phone,
                "username": me.username,
                "first_name": me.first_name,
                "status": config.AccountStatus.ACTIVE
            }
        }

    except PhoneNumberBannedError:
        # Account is banned
        sheets_manager.update_account(account_id, {
            "status": config.AccountStatus.BANNED
        })
        return {
            "success": False,
            "error": "Account is banned",
            "status": config.AccountStatus.BANNED
        }

    except SessionExpiredError:
        # Session expired
        sheets_manager.update_account(account_id, {
            "status": config.AccountStatus.BANNED
        })
        return {
            "success": False,
            "error": "Session expired",
            "status": config.AccountStatus.BANNED
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def select_account_for_user(user_id: int, preferred_account_id: Optional[str] = None) -> Optional[Dict]:
    """
    Select best account for sending to a user

    Args:
        user_id: Target user ID
        preferred_account_id: Preferred account ID (if specified)

    Returns:
        Account dict or None if no account available
    """

    # If preferred account is specified, check if it's available
    if preferred_account_id:
        account = sheets_manager.get_account(preferred_account_id)
        if account and is_account_available(account):
            return account

    # Check if we already have a dialog with this user
    dialog = sheets_manager.get_dialog(user_id)
    if dialog and dialog.get('account_id'):
        # Use the same account for continuity
        account = sheets_manager.get_account(dialog['account_id'])
        if account and is_account_available(account):
            return account

    # Get available accounts
    available = sheets_manager.get_available_accounts()

    if not available:
        return None

    # Return first available (already sorted by daily_sent)
    return available[0]


def is_account_available(account: Dict) -> bool:
    """
    Check if account is available for sending

    Args:
        account: Account dict

    Returns:
        True if account can send messages
    """

    # Check status
    status = account.get('status', '')
    if status not in [config.AccountStatus.ACTIVE, config.AccountStatus.WARMING]:
        return False

    # Check daily limit
    daily_sent = int(account.get('daily_sent', 0))
    max_daily = config.MAX_DAILY_ACTIVE if status == config.AccountStatus.ACTIVE else config.MAX_DAILY_WARMING

    if daily_sent >= max_daily:
        return False

    # Check cooldown
    cooldown_until = account.get('cooldown_until', '')
    if cooldown_until:
        try:
            cooldown_time = datetime.fromisoformat(cooldown_until)
            if cooldown_time > datetime.now():
                return False
        except:
            pass

    return True


def increment_account_usage(account_id: str):
    """
    Increment account usage counters

    Args:
        account_id: Account ID
    """

    account = sheets_manager.get_account(account_id)
    if not account:
        return

    daily_sent = int(account.get('daily_sent', 0)) + 1
    total_sent = int(account.get('total_sent', 0)) + 1

    sheets_manager.update_account(account_id, {
        "daily_sent": daily_sent,
        "total_sent": total_sent,
        "last_used_at": datetime.now().isoformat()
    })


def set_account_cooldown(account_id: str, hours: Optional[int] = None):
    """
    Set account to cooldown status

    Args:
        account_id: Account ID
        hours: Cooldown duration in hours (default from config)
    """

    if hours is None:
        hours = config.COOLDOWN_HOURS

    cooldown_until = datetime.now() + timedelta(hours=hours)

    account = sheets_manager.get_account(account_id)
    flood_count = int(account.get('flood_count', 0)) + 1 if account else 1

    sheets_manager.update_account(account_id, {
        "status": config.AccountStatus.COOLDOWN,
        "cooldown_until": cooldown_until.isoformat(),
        "flood_count": flood_count
    })


def generate_account_id() -> str:
    """
    Generate unique account ID

    Returns:
        Account ID string
    """

    # Get existing accounts to find next ID
    accounts = sheets_manager.get_all_accounts()

    # Extract numeric IDs
    max_id = 0
    for acc in accounts:
        acc_id = acc.get('id', '')
        if acc_id.startswith('acc_'):
            try:
                num = int(acc_id.replace('acc_', ''))
                max_id = max(max_id, num)
            except:
                pass

    return f"acc_{max_id + 1}"


async def add_account(account_data: Dict) -> Dict:
    """
    Add new account to the system

    Args:
        account_data: Account information from converter

    Returns:
        Dict with success status
    """

    try:
        # Generate account ID
        account_id = generate_account_id()

        # Prepare account record
        account = {
            "id": account_id,
            "phone": account_data.get('phone'),
            "username": account_data.get('username', ''),
            "first_name": account_data.get('first_name', ''),
            "session_file": account_data.get('session_file'),
            "status": account_data.get('status', config.AccountStatus.WARMING),
            "notes": account_data.get('notes', ''),
            "use_proxy": False,
            "proxy_type": "",
            "proxy_host": "",
            "proxy_port": "",
            "proxy_user": "",
            "proxy_pass": ""
        }

        # Add to sheets
        success = sheets_manager.add_account(account)

        if success:
            # Log the addition
            sheets_manager.add_log({
                "account_id": account_id,
                "action": "account_added",
                "result": "success",
                "details": f"Account {account['phone']} added"
            })

            return {
                "success": True,
                "account": account
            }
        else:
            return {
                "success": False,
                "error": "Failed to add account to sheets"
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def delete_account(account_id: str) -> Dict:
    """
    Delete account from system

    Args:
        account_id: Account ID to delete

    Returns:
        Dict with success status
    """

    try:
        # Get account
        account = sheets_manager.get_account(account_id)
        if not account:
            return {
                "success": False,
                "error": "Account not found"
            }

        # Delete session file
        session_file = account.get('session_file')
        if session_file:
            Path(session_file).unlink(missing_ok=True)

        # TODO: Delete from sheets (sheets_manager doesn't have delete method yet)
        # For now, just set status to banned
        sheets_manager.update_account(account_id, {
            "status": config.AccountStatus.BANNED
        })

        # Log the deletion
        sheets_manager.add_log({
            "account_id": account_id,
            "action": "account_deleted",
            "result": "success",
            "details": f"Account {account.get('phone')} deleted"
        })

        return {
            "success": True,
            "message": f"Account {account_id} deleted"
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

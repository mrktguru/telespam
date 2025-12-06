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
from database import db
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
        # Get account from database
        account = db.get_account(account_id)
        if not account:
            return {
                "success": False,
                "error": "Account not found"
            }

        # Get settings for proxy from config
        settings = {
            "proxy_enabled": config.PROXY_ENABLED,
            "default_proxy_type": config.DEFAULT_PROXY_TYPE,
            "default_proxy_host": config.DEFAULT_PROXY_HOST,
            "default_proxy_port": config.DEFAULT_PROXY_PORT,
            "default_proxy_user": config.DEFAULT_PROXY_USER,
            "default_proxy_pass": config.DEFAULT_PROXY_PASS,
            "api_id": config.API_ID,
            "api_hash": config.API_HASH
        }

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

        # Update status in database
        db.update_account(account_id, {
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
        db.update_account(account_id, {
            "status": config.AccountStatus.BANNED
        })
        return {
            "success": False,
            "error": "Account is banned",
            "status": config.AccountStatus.BANNED
        }

    except SessionExpiredError:
        # Session expired
        db.update_account(account_id, {
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
        account = db.get_account(preferred_account_id)
        if account and is_account_available(account):
            return account

    # Check if we already have a conversation with this user
    conversation = db.get_conversation_by_user_id(str(user_id))
    if conversation and conversation.get('account_id'):
        # Use the same account for continuity
        account = db.get_account(conversation['account_id'])
        if account and is_account_available(account):
            return account

    # Get available accounts
    available = get_available_accounts(limit=10)

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


def get_available_accounts(limit: int = 10) -> List[Dict]:
    """
    Get accounts available for sending

    Args:
        limit: Maximum number of accounts to return

    Returns:
        List of available account dicts
    """
    accounts = db.get_all_accounts()
    
    # Filter available accounts
    available = [acc for acc in accounts if is_account_available(acc)]
    
    # Sort by daily_sent (ascending) to balance load
    available.sort(key=lambda x: int(x.get('daily_sent', 0)))
    
    # Return limited number
    return available[:limit]


def increment_account_usage(account_id: str):
    """
    Increment account usage counters

    Args:
        account_id: Account ID
    """

    account = db.get_account(account_id)
    if not account:
        return

    daily_sent = int(account.get('daily_sent', 0)) + 1
    total_sent = int(account.get('total_sent', 0)) + 1

    db.update_account(account_id, {
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

    account = db.get_account(account_id)
    flood_count = int(account.get('flood_count', 0)) + 1 if account else 1

    db.update_account(account_id, {
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
    accounts = db.get_all_accounts()

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
            "last_name": account_data.get('last_name', ''),
            "session_file": account_data.get('session_file'),
            "status": account_data.get('status', config.AccountStatus.WARMING),
            "notes": account_data.get('notes', ''),
            "api_id": account_data.get('api_id'),  # Store API credentials
            "api_hash": account_data.get('api_hash'),  # Store API credentials
            "use_proxy": False,
            "proxy_type": "",
            "proxy_host": "",
            "proxy_port": "",
            "proxy_user": "",
            "proxy_pass": ""
        }

        # Add to database
        from database import db
        from datetime import datetime
        import traceback
        
        # Ensure all required fields
        account['added_at'] = account.get('added_at', datetime.now().isoformat())
        account['last_used_at'] = account.get('last_used_at', datetime.now().isoformat())
        account['daily_sent'] = account.get('daily_sent', 0)
        account['total_sent'] = account.get('total_sent', 0)
        account['flood_count'] = account.get('flood_count', 0)
        
        # Log account data before adding (for debugging)
        print(f"DEBUG: Adding account to database: id={account.get('id')}, phone={account.get('phone')}, api_id={account.get('api_id')}")
        
        try:
            success = db.add_account(account)
        except Exception as db_error:
            error_trace = traceback.format_exc()
            print(f"ERROR: Database error when adding account: {db_error}")
            print(f"ERROR: Traceback: {error_trace}")
            return {
                "success": False,
                "error": f"Database error: {str(db_error)}"
            }

        if success:
            print(f"DEBUG: Account {account.get('id')} added successfully")
            return {
                "success": True,
                "account": account
            }
        else:
            print(f"ERROR: db.add_account returned False for account {account.get('id')}")
            return {
                "success": False,
                "error": "Failed to add account to database (db.add_account returned False)"
            }

    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"ERROR: Exception in add_account: {e}")
        print(f"ERROR: Traceback: {error_trace}")
        return {
            "success": False,
            "error": f"Error: {str(e)}"
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
        account = db.get_account(account_id)
        if not account:
            return {
                "success": False,
                "error": "Account not found"
            }

        # Delete session file
        session_file = account.get('session_file')
        if session_file:
            Path(session_file).unlink(missing_ok=True)

        # Delete from database
        success = db.delete_account(account_id)
        if not success:
            return {
                "success": False,
                "error": "Failed to delete account"
            }

        # Log the deletion to database (if there are active campaigns)
        try:
            campaigns = db.get_all_campaigns()
            for campaign in campaigns:
                db.add_campaign_log(
                    campaign['id'],
                    f"Account {account.get('phone')} deleted",
                    level='info',
                    details=f"Account ID: {account_id}"
                )
        except:
            pass

        return {
            "success": True,
            "message": f"Account {account_id} deleted"
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

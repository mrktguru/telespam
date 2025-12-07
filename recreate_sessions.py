#!/usr/bin/env python3
"""
Recreate session files with correct API credentials
This script will:
1. Check all accounts in database
2. For each account, verify session file uses correct API credentials
3. If session was created with wrong credentials, recreate it
"""

import asyncio
import sys
from pathlib import Path

# Import config and database
try:
    from config import API_ID, API_HASH, SESSIONS_DIR
    from database import Database
    from telethon import TelegramClient
except ImportError as e:
    print(f"❌ Error importing modules: {e}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)

print("=" * 80)
print("  RECREATE SESSIONS WITH CORRECT API CREDENTIALS")
print("=" * 80)
print()

# Validate API credentials
if not API_ID or not API_HASH:
    print("❌ ERROR: API_ID or API_HASH not set in config!")
    sys.exit(1)

print(f"📋 Using API credentials from config:")
print(f"   API_ID: {API_ID}")
print(f"   API_HASH: {API_HASH[:20]}...")
print()

# Get all accounts
try:
    db = Database()
    accounts = db.get_all_accounts()
    print(f"Found {len(accounts)} accounts in database")
    print()
except Exception as e:
    print(f"❌ Error getting accounts: {e}")
    sys.exit(1)

async def check_and_recreate_session(account):
    """Check if session needs to be recreated and do it if needed"""
    phone = account.get('phone', '')
    account_id = account.get('id', '')
    session_file_path = account.get('session_file', '')
    
    if not session_file_path:
        print(f"⚠️  Account {phone} (ID: {account_id}): No session file path")
        return False
    
    session_file = Path(session_file_path)
    
    if not session_file.exists():
        print(f"⚠️  Account {phone} (ID: {account_id}): Session file not found: {session_file}")
        return False
    
    print(f"📱 Checking account {phone} (ID: {account_id})")
    print(f"   Session file: {session_file.name}")
    
    # Try to connect with correct credentials
    try:
        client = TelegramClient(
            str(session_file.with_suffix('')),
            int(API_ID),
            API_HASH
        )
        
        await client.connect()
        
        if not await client.is_user_authorized():
            print(f"   ⚠️  Session not authorized - needs re-authentication")
            await client.disconnect()
            return False
        
        # Check if we can get account info
        try:
            me = await client.get_me()
            print(f"   ✅ Session is valid and authorized")
            print(f"      User: {me.first_name} {me.last_name or ''} (@{me.username or 'no username'})")
            await client.disconnect()
            return True
        except Exception as e:
            print(f"   ⚠️  Error getting account info: {e}")
            await client.disconnect()
            return False
            
    except Exception as e:
        error_str = str(e).lower()
        print(f"   ❌ Error connecting with correct credentials: {e}")
        
        # Check if it's a credentials mismatch error
        if "auth" in error_str or "unauthorized" in error_str or "session" in error_str:
            print(f"   ⚠️  This might indicate session was created with different credentials")
            print(f"   💡 Recommendation: Delete session file and re-add account")
            return False
        else:
            print(f"   ⚠️  Unexpected error - session might still be valid")
            return False

async def main():
    """Main function"""
    valid_sessions = 0
    invalid_sessions = 0
    needs_recreation = []
    
    for account in accounts:
        phone = account.get('phone', '')
        account_id = account.get('id', '')
        
        is_valid = await check_and_recreate_session(account)
        
        if is_valid:
            valid_sessions += 1
        else:
            invalid_sessions += 1
            needs_recreation.append({
                'phone': phone,
                'account_id': account_id,
                'session_file': account.get('session_file', '')
            })
        print()
    
    print("=" * 80)
    print("  SUMMARY")
    print("=" * 80)
    print()
    print(f"✅ Valid sessions: {valid_sessions}")
    print(f"⚠️  Sessions needing attention: {invalid_sessions}")
    print()
    
    if needs_recreation:
        print("Accounts that may need session recreation:")
        for acc in needs_recreation:
            print(f"   - {acc['phone']} (ID: {acc['account_id']})")
            print(f"     Session: {acc['session_file']}")
        print()
        print("To recreate sessions:")
        print("   1. Delete the session file(s) listed above")
        print("   2. Re-add the account(s) via web interface or CLI")
        print("   3. This will create new session files with correct API credentials")
    else:
        print("✅ All sessions are valid!")
    
    print()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


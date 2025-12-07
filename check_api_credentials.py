#!/usr/bin/env python3
"""
Check API credentials in database and session files
Compares stored credentials with config values
"""

import sqlite3
import os
from pathlib import Path
import sys

# Import config to get API credentials
try:
    from config import API_ID, API_HASH, SESSIONS_DIR
    from database import Database
except ImportError as e:
    print(f"❌ Error importing config: {e}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)

print("=" * 80)
print("  API CREDENTIALS CHECKER")
print("=" * 80)
print()

# Validate API credentials from config
if not API_ID or not API_HASH:
    print("❌ ERROR: API_ID or API_HASH not set in config!")
    print("Please set them in .env file or environment variables")
    sys.exit(1)

print(f"📋 Expected API credentials from config:")
print(f"   API_ID: {API_ID}")
print(f"   API_HASH: {API_HASH[:20]}...")
print()

# Step 1: Check database
print("=" * 80)
print("Step 1: Checking API credentials in DATABASE")
print("=" * 80)
print()

try:
    db = Database()
    accounts = db.get_all_accounts()
    
    print(f"Found {len(accounts)} accounts in database")
    print()
    
    correct_count = 0
    incorrect_count = 0
    missing_count = 0
    
    for acc in accounts:
        phone = acc.get('phone', 'N/A')
        acc_id = acc.get('id', 'N/A')
        db_api_id = acc.get('api_id')
        db_api_hash = acc.get('api_hash')
        
        # Check if credentials match config
        api_id_match = (db_api_id == str(API_ID)) if db_api_id else False
        api_hash_match = (db_api_hash == API_HASH) if db_api_hash else False
        
        if not db_api_id or not db_api_hash:
            missing_count += 1
            status = "❌ MISSING"
            print(f"{status} Account {phone} (ID: {acc_id})")
            print(f"   Database: api_id={db_api_id}, api_hash={db_api_hash or 'None'}")
            print(f"   Expected: api_id={API_ID}, api_hash={API_HASH[:20]}...")
        elif api_id_match and api_hash_match:
            correct_count += 1
            status = "✅ CORRECT"
            print(f"{status} Account {phone} (ID: {acc_id})")
            print(f"   Database: api_id={db_api_id}, api_hash={db_api_hash[:20]}...")
        else:
            incorrect_count += 1
            status = "⚠️  MISMATCH"
            print(f"{status} Account {phone} (ID: {acc_id})")
            print(f"   Database: api_id={db_api_id}, api_hash={db_api_hash[:20] if db_api_hash else 'None'}...")
            print(f"   Expected: api_id={API_ID}, api_hash={API_HASH[:20]}...")
            if not api_id_match:
                print(f"   ⚠️  api_id mismatch!")
            if not api_hash_match:
                print(f"   ⚠️  api_hash mismatch!")
        print()
    
    print(f"Summary:")
    print(f"   ✅ Correct: {correct_count}")
    print(f"   ⚠️  Mismatch: {incorrect_count}")
    print(f"   ❌ Missing: {missing_count}")
    print()
    
except Exception as e:
    print(f"❌ Error checking database: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 2: Check session files
print("=" * 80)
print("Step 2: Checking API credentials in SESSION FILES")
print("=" * 80)
print()

if not SESSIONS_DIR.exists():
    print(f"⚠️  Session directory not found: {SESSIONS_DIR}")
    print(f"   Skipping session file check")
    sys.exit(0)

session_files = list(SESSIONS_DIR.glob("*.session"))
print(f"Found {len(session_files)} session file(s)")
print()

if not session_files:
    print("   No session files found")
    sys.exit(0)

# Telethon stores API credentials in session files
# The session file is a SQLite database
for session_file in session_files:
    phone_from_filename = session_file.stem.replace('_fe2371e4', '').replace('_', '')
    print(f"📁 Session: {session_file.name}")
    print(f"   Phone (from filename): {phone_from_filename}")
    
    try:
        conn = sqlite3.connect(str(session_file))
        cursor = conn.cursor()
        
        # Check if session file has the expected structure
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        # Telethon stores API credentials in the session file metadata
        # However, the exact storage method varies by Telethon version
        # We'll check for common patterns
        
        # Method 1: Check if there's a 'sessions' table with API info
        session_api_id = None
        session_api_hash = None
        
        if 'sessions' in tables:
            try:
                cursor.execute("SELECT api_id, api_hash FROM sessions LIMIT 1")
                row = cursor.fetchone()
                if row:
                    session_api_id, session_api_hash = row
            except:
                pass
        
        # Method 2: Check for auth_key and dc_id (these are always present)
        # API credentials are used when creating the client, not stored in session
        # But we can check the session structure
        
        # Get session info
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        table_count = cursor.fetchone()[0]
        
        # Check for auth_key (indicates session is valid)
        has_auth_key = False
        if 'sessions' in tables:
            try:
                cursor.execute("SELECT COUNT(*) FROM sessions WHERE auth_key IS NOT NULL")
                has_auth_key = cursor.fetchone()[0] > 0
            except:
                pass
        
        conn.close()
        
        # Compare with database
        db_account = next((acc for acc in accounts if phone_from_filename in acc.get('phone', '') or acc.get('phone', '') in phone_from_filename), None)
        
        if db_account:
            db_phone = db_account.get('phone', '')
            db_api_id = db_account.get('api_id')
            db_api_hash = db_account.get('api_hash')
            
            print(f"   Database account: {db_phone}")
            print(f"   Database api_id: {db_api_id}")
            print(f"   Database api_hash: {db_api_hash[:20] if db_api_hash else 'None'}...")
            
            if session_api_id:
                print(f"   Session api_id: {session_api_id}")
                print(f"   Session api_hash: {session_api_hash[:20] if session_api_hash else 'None'}...")
                
                # Compare
                if str(session_api_id) == str(API_ID) and session_api_hash == API_HASH:
                    print(f"   ✅ Session credentials match config")
                else:
                    print(f"   ⚠️  Session credentials DO NOT match config!")
                    print(f"      Expected: api_id={API_ID}, api_hash={API_HASH[:20]}...")
            else:
                print(f"   ℹ️  Session file doesn't store API credentials explicitly")
                print(f"      (Telethon uses credentials from client creation, not stored in session)")
            
            # Check if database credentials match config
            if db_api_id == str(API_ID) and db_api_hash == API_HASH:
                print(f"   ✅ Database credentials match config")
            else:
                print(f"   ⚠️  Database credentials DO NOT match config!")
                print(f"      Expected: api_id={API_ID}, api_hash={API_HASH[:20]}...")
            
            # Check if session has auth_key (is valid)
            if has_auth_key:
                print(f"   ✅ Session has auth_key (valid session)")
            else:
                print(f"   ⚠️  Session may not have auth_key (invalid or new session)")
        else:
            print(f"   ⚠️  No matching account found in database for this session file")
        
        print()
        
    except Exception as e:
        print(f"   ❌ Error reading session file: {e}")
        import traceback
        traceback.print_exc()
        print()

print("=" * 80)
print("  RECOMMENDATIONS")
print("=" * 80)
print()

if incorrect_count > 0 or missing_count > 0:
    print("⚠️  Some accounts have incorrect or missing API credentials!")
    print()
    print("To fix:")
    print("  1. Run the migration script:")
    print("     python3 migrate_api_credentials.py")
    print()
    print("  2. If session files were created with different credentials,")
    print("     you may need to recreate them:")
    print("     - Delete old session files")
    print("     - Re-add accounts using the web interface or CLI")
    print("     - This will create new session files with correct credentials")
    print()
else:
    print("✅ All accounts have correct API credentials in database!")
    print()
    print("Note: Session files don't store API credentials directly.")
    print("They are used when creating the TelegramClient.")
    print("Make sure you're using config.API_ID and config.API_HASH when creating clients.")
    print()

print("=" * 80)


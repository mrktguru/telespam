#!/usr/bin/env python3
"""
Migration script: Update all accounts to use unified API credentials from config
and clean session cache to force Telethon to recreate entities cache with correct credentials.
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

# Determine database path
PROJECT_DIR = Path(__file__).parent
DB_PATH = PROJECT_DIR / "data" / "telespam.db"

# If DB_PATH doesn't exist, try alternative location
if not DB_PATH.exists():
    DB_PATH = PROJECT_DIR / "telespam.db"

if not DB_PATH.exists():
    print(f"❌ Database file not found at {DB_PATH}")
    print("Please ensure the database exists before running this migration")
    sys.exit(1)

print("=" * 70)
print("  MIGRATION: Unified API Credentials")
print("=" * 70)
print()

# Validate API credentials from config
if not API_ID or not API_HASH:
    print("❌ ERROR: API_ID or API_HASH not set in config!")
    print("Please set them in .env file or environment variables")
    print()
    print("Example .env file:")
    print("  API_ID=31278173")
    print("  API_HASH=0cda181618e72e22e29c9da73124a3bf")
    sys.exit(1)

print(f"📋 Using API credentials from config:")
print(f"   API_ID: {API_ID}")
print(f"   API_HASH: {API_HASH[:20]}...")
print()

# Step 1: Update database
print("Step 1: Updating api_id and api_hash in database...")
try:
    db = Database()
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # Get current state
    cursor.execute("SELECT COUNT(*) FROM accounts")
    total_accounts = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM accounts WHERE api_id != ? OR api_hash != ? OR api_id IS NULL OR api_hash IS NULL", 
                   (str(API_ID), API_HASH))
    accounts_to_update = cursor.fetchone()[0]
    
    print(f"   Total accounts: {total_accounts}")
    print(f"   Accounts to update: {accounts_to_update}")
    
    if accounts_to_update > 0:
        # Update all accounts
        cursor.execute("""
            UPDATE accounts 
            SET api_id = ?, api_hash = ?
            WHERE api_id != ? OR api_hash != ? OR api_id IS NULL OR api_hash IS NULL
        """, (str(API_ID), API_HASH, str(API_ID), API_HASH))
        
        affected = cursor.rowcount
        conn.commit()
        print(f"   ✓ Updated {affected} accounts")
    else:
        print(f"   ✓ All accounts already use correct credentials")
    
    conn.close()
except Exception as e:
    print(f"   ❌ Error updating database: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Step 2: Clean session cache
print("Step 2: Cleaning entities cache in session files...")
cleaned = 0
errors = 0

if not SESSIONS_DIR.exists():
    print(f"   ⚠ Session directory not found: {SESSIONS_DIR}")
    print(f"   Skipping session cache cleanup")
else:
    session_files = list(SESSIONS_DIR.glob("*.session"))
    print(f"   Found {len(session_files)} session file(s)")
    
    for session_file in session_files:
        try:
            conn = sqlite3.connect(str(session_file))
            cursor = conn.cursor()
            
            # Check if tables exist before deleting
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            deleted_tables = []
            if 'entities' in tables:
                cursor.execute("DELETE FROM entities")
                deleted_tables.append('entities')
            
            if 'sent_files' in tables:
                cursor.execute("DELETE FROM sent_files")
                deleted_tables.append('sent_files')
            
            if 'update_state' in tables:
                cursor.execute("DELETE FROM update_state")
                deleted_tables.append('update_state')
            
            conn.commit()
            conn.close()
            
            if deleted_tables:
                cleaned += 1
                print(f"   ✓ {session_file.name} (cleaned: {', '.join(deleted_tables)})")
            else:
                print(f"   - {session_file.name} (no cache tables found)")
                
        except Exception as e:
            errors += 1
            print(f"   ✗ {session_file.name}: {e}")

print()
print(f"   ✓ Cleaned {cleaned} session files")
if errors > 0:
    print(f"   ⚠ {errors} errors occurred")

print()
print("=" * 70)
print("  ✓ MIGRATION COMPLETE!")
print("=" * 70)
print()
print("All accounts now use unified API credentials from config")
print("Session cache has been cleaned - Telethon will recreate entities cache")
print("with correct credentials on next connection")
print()
print("⚠ IMPORTANT: Restart the web service to apply changes:")
print("   sudo systemctl restart telespam-web")
print()


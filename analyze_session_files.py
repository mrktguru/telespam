#!/usr/bin/env python3
"""
Analyze session files and their relationship with accounts in database
Shows which session files are used, which are duplicates, and which are orphaned
"""

import sqlite3
from pathlib import Path
from collections import defaultdict
import sys

try:
    from config import SESSIONS_DIR
    from database import Database
except ImportError as e:
    print(f"❌ Error importing modules: {e}")
    sys.exit(1)

print("=" * 80)
print("  SESSION FILES ANALYSIS")
print("=" * 80)
print()

# Get all accounts from database
try:
    db = Database()
    accounts = db.get_all_accounts()
    print(f"📊 Found {len(accounts)} accounts in database")
    print()
except Exception as e:
    print(f"❌ Error getting accounts: {e}")
    sys.exit(1)

# Get all session files
if not SESSIONS_DIR.exists():
    print(f"❌ Session directory not found: {SESSIONS_DIR}")
    sys.exit(1)

session_files = list(SESSIONS_DIR.glob("*.session"))
print(f"📁 Found {len(session_files)} session file(s)")
print()

# Analyze session files
used_sessions = set()
orphaned_sessions = []
duplicate_sessions = defaultdict(list)
phone_to_sessions = defaultdict(list)

# Group session files by phone number (extracted from filename)
for session_file in session_files:
    filename = session_file.name
    
    # Extract phone from filename (remove suffixes like _fe2371e4, _abb3e8ca, etc.)
    # Pattern: phone.session or phone_hash.session
    phone_candidates = []
    
    # Try different patterns
    if '_' in filename:
        # Has hash suffix: phone_hash.session
        base = filename.replace('.session', '')
        parts = base.split('_')
        if len(parts) >= 2:
            # First part is likely the phone
            phone_candidates.append(parts[0])
            # Also try without first underscore
            phone_candidates.append('_'.join(parts[:-1]))
    else:
        # No hash: phone.session
        phone_candidates.append(filename.replace('.session', ''))
    
    # Remove + prefix if present
    for phone in phone_candidates:
        phone_clean = phone.replace('+', '').replace('-', '').replace(' ', '')
        if phone_clean:
            phone_to_sessions[phone_clean].append(session_file)
            break

# Match session files with accounts
account_sessions = {}
for account in accounts:
    phone = account.get('phone', '')
    account_id = account.get('id', '')
    session_file_path = account.get('session_file', '')
    
    if not phone:
        continue
    
    # Normalize phone
    phone_normalized = phone.replace('+', '').replace('-', '').replace(' ', '').strip()
    
    # Find matching session files
    matching_sessions = phone_to_sessions.get(phone_normalized, [])
    
    # Check if the session_file from database exists
    session_from_db = None
    if session_file_path:
        session_from_db = Path(session_file_path)
        if session_from_db.exists():
            used_sessions.add(session_from_db.name)
            account_sessions[account_id] = {
                'phone': phone,
                'session_from_db': session_from_db.name,
                'all_sessions': [s.name for s in matching_sessions],
                'session_count': len(matching_sessions)
            }
        else:
            account_sessions[account_id] = {
                'phone': phone,
                'session_from_db': session_file_path,
                'status': 'NOT FOUND',
                'all_sessions': [s.name for s in matching_sessions],
                'session_count': len(matching_sessions)
            }
    else:
        account_sessions[account_id] = {
            'phone': phone,
            'session_from_db': None,
            'all_sessions': [s.name for s in matching_sessions],
            'session_count': len(matching_sessions)
        }

# Find orphaned sessions (not referenced in database)
all_db_session_names = set()
for acc_data in account_sessions.values():
    if acc_data.get('session_from_db'):
        all_db_session_names.add(Path(acc_data['session_from_db']).name)

orphaned_sessions = [s for s in session_files if s.name not in all_db_session_names]

# Find duplicates (multiple sessions for same phone)
for phone, sessions in phone_to_sessions.items():
    if len(sessions) > 1:
        duplicate_sessions[phone] = [s.name for s in sessions]

# Print results
print("=" * 80)
print("  ACCOUNT SESSION ANALYSIS")
print("=" * 80)
print()

for account_id, data in account_sessions.items():
    phone = data['phone']
    session_from_db = data.get('session_from_db')
    session_count = data.get('session_count', 0)
    all_sessions = data.get('all_sessions', [])
    
    print(f"📱 Account: {phone} (ID: {account_id})")
    
    if session_from_db:
        if Path(SESSIONS_DIR / session_from_db).exists():
            print(f"   ✅ Session from DB: {session_from_db}")
        else:
            print(f"   ❌ Session from DB: {session_from_db} (NOT FOUND)")
    else:
        print(f"   ⚠️  No session file in database")
    
    if session_count > 1:
        print(f"   ⚠️  Found {session_count} session files for this phone:")
        for sess in all_sessions:
            marker = "✅" if sess == session_from_db else "📦"
            print(f"      {marker} {sess}")
    elif session_count == 1:
        print(f"   ✅ 1 session file: {all_sessions[0]}")
    else:
        print(f"   ⚠️  No session files found for this phone")
    
    print()

print("=" * 80)
print("  ORPHANED SESSION FILES")
print("=" * 80)
print()

if orphaned_sessions:
    print(f"Found {len(orphaned_sessions)} orphaned session file(s) (not in database):")
    for sess in sorted(orphaned_sessions, key=lambda x: x.name):
        # Try to extract phone
        phone_guess = sess.stem.split('_')[0].replace('+', '')
        print(f"   📦 {sess.name} (phone guess: {phone_guess})")
    print()
    print("💡 These can be safely deleted if not needed")
else:
    print("✅ No orphaned session files found")
    print()

print("=" * 80)
print("  DUPLICATE SESSION FILES")
print("=" * 80)
print()

if duplicate_sessions:
    print(f"Found {len(duplicate_sessions)} phone(s) with multiple session files:")
    for phone, sessions in duplicate_sessions.items():
        print(f"   📱 Phone: {phone}")
        print(f"      Sessions ({len(sessions)}):")
        for sess in sessions:
            print(f"         - {sess}")
        print()
    print("💡 These are likely old session files with hash suffixes")
    print("   Only the one referenced in database is actively used")
else:
    print("✅ No duplicate session files found")
    print()

print("=" * 80)
print("  SUMMARY")
print("=" * 80)
print()
print(f"Total session files: {len(session_files)}")
print(f"Session files in use: {len(used_sessions)}")
print(f"Orphaned session files: {len(orphaned_sessions)}")
print(f"Phones with duplicates: {len(duplicate_sessions)}")
print()
print("💡 Recommendations:")
print("   1. Keep only session files referenced in database")
print("   2. Delete orphaned session files if not needed")
print("   3. Old session files with hash suffixes can be cleaned up")
print()


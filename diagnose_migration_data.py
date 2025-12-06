#!/usr/bin/env python3
"""
Diagnostic script to check data migration from mock storage to SQLite
Compares data formats and identifies migration issues
"""

import sqlite3
from pathlib import Path
from database import db

def diagnose_campaign_users():
    """Check campaign_users table data"""
    print("=" * 70)
    print("DIAGNOSTIC: Campaign Users Data in SQLite")
    print("=" * 70)
    print()
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # Get all users
    cursor.execute('SELECT * FROM campaign_users LIMIT 10')
    rows = cursor.fetchall()
    
    if not rows:
        print("❌ No users found in campaign_users table")
        print("   This might indicate a migration issue")
        conn.close()
        return
    
    print(f"✓ Found {len(rows)} users (showing first 10)")
    print()
    
    for i, row in enumerate(rows, 1):
        user_dict = dict(row)
        print(f"User #{i}:")
        print(f"  ID (primary key): {user_dict.get('id')} (type: {type(user_dict.get('id'))})")
        print(f"  campaign_id: {user_dict.get('campaign_id')} (type: {type(user_dict.get('campaign_id'))})")
        print(f"  user_id: {user_dict.get('user_id')} (type: {type(user_dict.get('user_id'))})")
        print(f"  username: {user_dict.get('username')} (type: {type(user_dict.get('username'))})")
        print(f"  phone: {user_dict.get('phone')} (type: {type(user_dict.get('phone'))})")
        print(f"  status: {user_dict.get('status')} (type: {type(user_dict.get('status'))})")
        
        # Check for potential issues
        issues = []
        if user_dict.get('user_id') is None:
            issues.append("❌ user_id is NULL")
        elif user_dict.get('user_id') == '':
            issues.append("❌ user_id is empty string")
        elif not str(user_dict.get('user_id')).strip():
            issues.append("❌ user_id is whitespace only")
        else:
            try:
                int(user_dict.get('user_id'))
                print(f"  ✓ user_id can be converted to int")
            except (ValueError, TypeError):
                issues.append(f"❌ user_id '{user_dict.get('user_id')}' cannot be converted to int")
        
        if issues:
            print(f"  ISSUES FOUND:")
            for issue in issues:
                print(f"    {issue}")
        else:
            print(f"  ✓ No obvious issues")
        
        print()
    
    # Check table schema
    print("Table Schema:")
    cursor.execute("PRAGMA table_info(campaign_users)")
    columns = cursor.fetchall()
    for col in columns:
        print(f"  {col[1]} ({col[2]}) - {'NOT NULL' if col[3] else 'NULLABLE'}")
    
    conn.close()
    print()
    print("=" * 70)


def diagnose_specific_user(user_id_to_check):
    """Check specific user_id in database"""
    print("=" * 70)
    print(f"DIAGNOSTIC: Checking specific user_id: {user_id_to_check}")
    print("=" * 70)
    print()
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # Try to find by user_id (as string)
    cursor.execute('SELECT * FROM campaign_users WHERE user_id = ?', (str(user_id_to_check),))
    rows = cursor.fetchall()
    
    if not rows:
        print(f"❌ User with user_id='{user_id_to_check}' not found")
        print("   Trying as integer...")
        cursor.execute('SELECT * FROM campaign_users WHERE CAST(user_id AS INTEGER) = ?', (int(user_id_to_check),))
        rows = cursor.fetchall()
    
    if not rows:
        print(f"❌ User with user_id={user_id_to_check} not found in any format")
        print()
        print("Available user_id values in database:")
        cursor.execute('SELECT DISTINCT user_id FROM campaign_users WHERE user_id IS NOT NULL LIMIT 20')
        available = cursor.fetchall()
        for row in available:
            print(f"  - {row[0]} (type: {type(row[0])})")
        conn.close()
        return
    
    print(f"✓ Found {len(rows)} matching user(s)")
    print()
    
    for row in rows:
        user_dict = dict(row)
        print(f"User data:")
        for key, value in user_dict.items():
            print(f"  {key}: {value} (type: {type(value)})")
        print()
    
    conn.close()


def compare_with_mock():
    """Compare SQLite data with mock storage format (if available)"""
    print("=" * 70)
    print("DIAGNOSTIC: Comparing with Mock Storage Format")
    print("=" * 70)
    print()
    
    print("Expected format from mock storage:")
    print("  user_id: string or int (e.g., '123456789' or 123456789)")
    print("  username: string or None (e.g., 'username' or None)")
    print("  phone: string or None (e.g., '+1234567890' or None)")
    print()
    
    print("Actual format in SQLite:")
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, phone FROM campaign_users LIMIT 5')
    rows = cursor.fetchall()
    
    for row in rows:
        print(f"  user_id: {row[0]} (type: {type(row[0])})")
        print(f"  username: {row[1]} (type: {type(row[1])})")
        print(f"  phone: {row[2]} (type: {type(row[2])})")
        print()
    
    conn.close()


if __name__ == "__main__":
    import sys
    
    print()
    print("=" * 70)
    print("MIGRATION DATA DIAGNOSTIC TOOL")
    print("=" * 70)
    print()
    
    # Run all diagnostics
    diagnose_campaign_users()
    print()
    compare_with_mock()
    
    # If user_id provided, check specific user
    if len(sys.argv) > 1:
        user_id = sys.argv[1]
        print()
        diagnose_specific_user(user_id)
    
    print()
    print("=" * 70)
    print("RECOMMENDATIONS:")
    print("=" * 70)
    print()
    print("1. Check that user_id values are not NULL or empty")
    print("2. Verify user_id can be converted to int")
    print("3. Compare with original mock storage data")
    print("4. If issues found, may need to re-migrate data")
    print()
    print("To check specific user_id, run:")
    print("  python3 diagnose_migration_data.py <user_id>")
    print()


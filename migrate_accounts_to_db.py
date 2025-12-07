#!/usr/bin/env python3
"""
Migration script: Move accounts from mock_sheets (JSON) to SQLite database
"""

import os
os.environ['USE_MOCK_STORAGE'] = 'true'

from mock_sheets import sheets_manager
from database import db
from datetime import datetime

def migrate_accounts():
    """Migrate all accounts from mock_sheets to SQLite database"""
    print("=" * 70)
    print("MIGRATING ACCOUNTS FROM MOCK_SHEETS TO SQLITE DATABASE")
    print("=" * 70)
    print()
    
    # Get all accounts from mock_sheets
    accounts = sheets_manager.get_all_accounts()
    print(f"Found {len(accounts)} accounts in mock_sheets")
    print()
    
    if not accounts:
        print("No accounts to migrate")
        return
    
    migrated = 0
    skipped = 0
    errors = 0
    
    for account in accounts:
        try:
            # Ensure all required fields have defaults
            account_data = {
                'id': account.get('id'),
                'phone': account.get('phone'),
                'username': account.get('username'),
                'first_name': account.get('first_name'),
                'last_name': account.get('last_name'),
                'bio': account.get('bio'),
                'session_file': account.get('session_file'),
                'status': account.get('status', 'checking'),
                'daily_sent': account.get('daily_sent', 0),
                'total_sent': account.get('total_sent', 0),
                'cooldown_until': account.get('cooldown_until'),
                'last_used_at': account.get('last_used_at'),
                'added_at': account.get('added_at', datetime.now().isoformat()),
                'flood_count': account.get('flood_count', 0),
                'use_proxy': account.get('use_proxy', False),
                'proxy': account.get('proxy'),
                'proxy_type': account.get('proxy_type'),
                'proxy_host': account.get('proxy_host'),
                'proxy_port': account.get('proxy_port'),
                'proxy_user': account.get('proxy_user'),
                'proxy_pass': account.get('proxy_pass'),
                'campaign_id': account.get('campaign_id'),
                'notes': account.get('notes'),
                'photo_count': account.get('photo_count', 0)
            }
            
            # Check if account already exists in database
            existing = db.get_account(account_data['id'])
            if existing:
                print(f"⚠ Account {account_data['id']} ({account_data.get('phone')}) already exists in database, skipping")
                skipped += 1
                continue
            
            # Add to database
            success = db.add_account(account_data)
            if success:
                print(f"✓ Migrated: {account_data['id']} - {account_data.get('phone')}")
                migrated += 1
            else:
                print(f"✗ Failed to migrate: {account_data['id']} - {account_data.get('phone')}")
                errors += 1
        except Exception as e:
            print(f"✗ Error migrating account {account.get('id', 'unknown')}: {e}")
            errors += 1
    
    print()
    print("=" * 70)
    print("MIGRATION SUMMARY")
    print("=" * 70)
    print(f"Total accounts in mock_sheets: {len(accounts)}")
    print(f"Migrated: {migrated}")
    print(f"Skipped (already exists): {skipped}")
    print(f"Errors: {errors}")
    print("=" * 70)
    print()
    
    # Verify migration
    db_accounts = db.get_all_accounts()
    print(f"Total accounts in database: {len(db_accounts)}")
    print()
    
    if migrated > 0:
        print("✓ Migration completed successfully!")
        print("⚠ IMPORTANT: After verifying, you can remove accounts from mock_sheets")
    else:
        print("ℹ No new accounts to migrate")

if __name__ == '__main__':
    migrate_accounts()


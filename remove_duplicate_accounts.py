#!/usr/bin/env python3
"""
Script to remove duplicate accounts (same phone number)
Keeps the oldest account (by added_at) and deletes the rest
"""

from database import db
from pathlib import Path

def remove_duplicates():
    """Remove duplicate accounts, keeping the oldest one for each phone"""
    print("=" * 70)
    print("REMOVING DUPLICATE ACCOUNTS")
    print("=" * 70)
    print()
    
    # Get all accounts
    accounts = db.get_all_accounts()
    print(f"Total accounts: {len(accounts)}")
    print()
    
    # Group by phone (normalized)
    phone_groups = {}
    for account in accounts:
        phone = account.get('phone', '')
        if not phone:
            continue
        
        # Normalize phone
        phone_normalized = phone.replace('+', '').replace(' ', '').replace('-', '').strip()
        
        if phone_normalized not in phone_groups:
            phone_groups[phone_normalized] = []
        phone_groups[phone_normalized].append(account)
    
    # Find duplicates
    duplicates_found = 0
    duplicates_to_remove = []
    
    for phone_normalized, group in phone_groups.items():
        if len(group) > 1:
            duplicates_found += len(group) - 1
            print(f"Found {len(group)} accounts with phone {group[0].get('phone')}:")
            for acc in group:
                print(f"  - {acc.get('id')} (added: {acc.get('added_at', 'unknown')})")
            
            # Sort by added_at (oldest first)
            group_sorted = sorted(group, key=lambda x: x.get('added_at', ''))
            
            # Keep the oldest, mark others for deletion
            keep = group_sorted[0]
            to_remove = group_sorted[1:]
            
            print(f"  → Keeping: {keep.get('id')}")
            for acc in to_remove:
                print(f"  → Removing: {acc.get('id')}")
                duplicates_to_remove.append(acc)
            print()
    
    if duplicates_to_remove:
        print(f"Total duplicates to remove: {len(duplicates_to_remove)}")
        print()
        
        confirm = input("Remove these duplicates? (yes/no): ").strip().lower()
        if confirm != 'yes':
            print("Cancelled")
            return
        
        removed = 0
        errors = 0
        
        for account in duplicates_to_remove:
            account_id = account.get('id')
            phone = account.get('phone')
            
            try:
                # Delete session file if exists
                session_file = account.get('session_file')
                if session_file:
                    session_path = Path(session_file)
                    if session_path.exists():
                        try:
                            session_path.unlink()
                            print(f"  ✓ Deleted session file: {session_file}")
                        except Exception as e:
                            print(f"  ⚠ Could not delete session file: {e}")
                
                # Delete from database
                success = db.delete_account(account_id)
                if success:
                    print(f"  ✓ Removed duplicate: {account_id} (phone: {phone})")
                    removed += 1
                else:
                    print(f"  ✗ Failed to remove: {account_id}")
                    errors += 1
            except Exception as e:
                print(f"  ✗ Error removing {account_id}: {e}")
                errors += 1
        
        print()
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Removed: {removed}")
        print(f"Errors: {errors}")
        print()
        
        # Verify
        accounts_after = db.get_all_accounts()
        print(f"Accounts after cleanup: {len(accounts_after)}")
        
    else:
        print("No duplicates found!")
        print()

if __name__ == '__main__':
    remove_duplicates()


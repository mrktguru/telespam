#!/usr/bin/env python3
"""
Migration script: Change user_id column from TEXT to INTEGER in campaign_users table
This fixes the issue where Telethon receives strings instead of integers
"""

import sqlite3
from pathlib import Path
from database import db

def migrate_user_id_to_integer():
    """Migrate user_id column from TEXT to INTEGER"""
    print("=" * 70)
    print("MIGRATION: Converting user_id from TEXT to INTEGER")
    print("=" * 70)
    print()
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        # Step 1: Check current schema
        print("Step 1: Checking current schema...")
        cursor.execute("PRAGMA table_info(campaign_users)")
        columns = cursor.fetchall()
        user_id_col = None
        for col in columns:
            if col[1] == 'user_id':
                user_id_col = col
                print(f"  Found user_id column: {col[1]} ({col[2]})")
                break
        
        if not user_id_col:
            print("  ❌ user_id column not found!")
            conn.close()
            return False
        
        if user_id_col[2].upper() == 'INTEGER':
            print("  ✓ user_id is already INTEGER, no migration needed")
            conn.close()
            return True
        
        print(f"  Current type: {user_id_col[2]} (needs to be INTEGER)")
        print()
        
        # Step 2: Check for invalid data
        print("Step 2: Checking for invalid user_id values...")
        cursor.execute("SELECT COUNT(*) FROM campaign_users WHERE user_id IS NOT NULL AND user_id != ''")
        total = cursor.fetchone()[0]
        print(f"  Total users with user_id: {total}")
        
        # Check for non-numeric values
        cursor.execute("""
            SELECT COUNT(*) FROM campaign_users 
            WHERE user_id IS NOT NULL 
            AND user_id != ''
            AND user_id NOT GLOB '[0-9]*'
        """)
        invalid = cursor.fetchone()[0]
        if invalid > 0:
            print(f"  ⚠ WARNING: Found {invalid} non-numeric user_id values!")
            print("  These will be set to NULL")
            cursor.execute("""
                SELECT id, user_id FROM campaign_users 
                WHERE user_id IS NOT NULL 
                AND user_id != ''
                AND user_id NOT GLOB '[0-9]*'
                LIMIT 10
            """)
            invalid_rows = cursor.fetchall()
            print("  Sample invalid values:")
            for row in invalid_rows:
                print(f"    ID {row[0]}: user_id = '{row[1]}'")
        else:
            print("  ✓ All user_id values are numeric")
        print()
        
        # Step 3: Create backup
        print("Step 3: Creating backup table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS campaign_users_backup AS 
            SELECT * FROM campaign_users
        """)
        print("  ✓ Backup created: campaign_users_backup")
        print()
        
        # Step 4: Create new table with INTEGER user_id
        print("Step 4: Creating new table with INTEGER user_id...")
        cursor.execute("""
            CREATE TABLE campaign_users_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                username TEXT,
                user_id INTEGER,
                phone TEXT,
                priority INTEGER DEFAULT 1,
                status TEXT DEFAULT 'pending',
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                contacted_at TIMESTAMP,
                contacted_by TEXT,
                FOREIGN KEY (campaign_id) REFERENCES campaigns (id) ON DELETE CASCADE
            )
        """)
        print("  ✓ New table created")
        print()
        
        # Step 5: Migrate data
        print("Step 5: Migrating data...")
        cursor.execute("""
            INSERT INTO campaign_users_new 
            (id, campaign_id, username, user_id, phone, priority, status, added_at, contacted_at, contacted_by)
            SELECT 
                id,
                campaign_id,
                username,
                CASE 
                    WHEN user_id IS NULL OR user_id = '' THEN NULL
                    WHEN user_id GLOB '[0-9]*' THEN CAST(user_id AS INTEGER)
                    ELSE NULL
                END as user_id,
                phone,
                priority,
                status,
                added_at,
                contacted_at,
                contacted_by
            FROM campaign_users
        """)
        migrated = cursor.rowcount
        print(f"  ✓ Migrated {migrated} rows")
        print()
        
        # Step 6: Verify migration
        print("Step 6: Verifying migration...")
        cursor.execute("SELECT COUNT(*) FROM campaign_users")
        old_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM campaign_users_new")
        new_count = cursor.fetchone()[0]
        
        if old_count != new_count:
            print(f"  ❌ Row count mismatch: old={old_count}, new={new_count}")
            conn.rollback()
            conn.close()
            return False
        
        print(f"  ✓ Row count matches: {new_count}")
        
        # Check user_id types
        cursor.execute("SELECT user_id FROM campaign_users_new WHERE user_id IS NOT NULL LIMIT 5")
        sample = cursor.fetchall()
        print("  Sample user_id values (should be integers):")
        for row in sample:
            print(f"    {row[0]} (type: {type(row[0])})")
        print()
        
        # Step 7: Replace old table
        print("Step 7: Replacing old table...")
        cursor.execute("DROP TABLE campaign_users")
        cursor.execute("ALTER TABLE campaign_users_new RENAME TO campaign_users")
        print("  ✓ Table replaced")
        print()
        
        # Step 8: Recreate indexes if needed
        print("Step 8: Verifying indexes...")
        cursor.execute("PRAGMA index_list(campaign_users)")
        indexes = cursor.fetchall()
        print(f"  Found {len(indexes)} indexes")
        print()
        
        # Commit
        conn.commit()
        print("=" * 70)
        print("✓ MIGRATION COMPLETED SUCCESSFULLY")
        print("=" * 70)
        print()
        print("The user_id column is now INTEGER type.")
        print("Telethon will now receive integers instead of strings.")
        print()
        print("Backup table 'campaign_users_backup' has been created.")
        print("You can drop it after verifying everything works:")
        print("  DROP TABLE campaign_users_backup;")
        print()
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        conn.close()
        return False


if __name__ == "__main__":
    print()
    success = migrate_user_id_to_integer()
    if success:
        print("Migration completed successfully!")
        exit(0)
    else:
        print("Migration failed!")
        exit(1)


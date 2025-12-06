#!/usr/bin/env python3
"""
Migration script: Add api_id and api_hash columns to accounts table
"""

from database import db
import sqlite3

def migrate():
    """Add api_id and api_hash columns to accounts table if they don't exist"""
    print("=" * 70)
    print("MIGRATING ACCOUNTS TABLE: Adding api_id and api_hash columns")
    print("=" * 70)
    print()
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        # Check if columns exist
        cursor.execute("PRAGMA table_info(accounts)")
        columns = [row[1] for row in cursor.fetchall()]
        
        print(f"Current columns in accounts table: {', '.join(columns)}")
        print()
        
        added_columns = []
        
        if 'api_id' not in columns:
            print("Adding api_id column...")
            cursor.execute('ALTER TABLE accounts ADD COLUMN api_id TEXT')
            added_columns.append('api_id')
            print("✓ api_id column added")
        else:
            print("✓ api_id column already exists")
        
        if 'api_hash' not in columns:
            print("Adding api_hash column...")
            cursor.execute('ALTER TABLE accounts ADD COLUMN api_hash TEXT')
            added_columns.append('api_hash')
            print("✓ api_hash column added")
        else:
            print("✓ api_hash column already exists")
        
        conn.commit()
        
        if added_columns:
            print()
            print("=" * 70)
            print("MIGRATION SUCCESSFUL")
            print("=" * 70)
            print(f"Added columns: {', '.join(added_columns)}")
        else:
            print()
            print("=" * 70)
            print("MIGRATION NOT NEEDED")
            print("=" * 70)
            print("All required columns already exist")
        
    except Exception as e:
        print()
        print("=" * 70)
        print("MIGRATION FAILED")
        print("=" * 70)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        return False
    finally:
        conn.close()
    
    print()
    return True

if __name__ == '__main__':
    success = migrate()
    exit(0 if success else 1)


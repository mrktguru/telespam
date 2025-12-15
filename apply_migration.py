#!/usr/bin/env python3
"""
Apply database migrations
"""

import sqlite3
import sys
from pathlib import Path

def apply_migration(db_path: str, migration_file: str):
    """Apply migration from SQL file"""
    
    # Read migration file
    migration_path = Path(migration_file)
    if not migration_path.exists():
        print(f"❌ Migration file not found: {migration_file}")
        return False
    
    with open(migration_path, 'r') as f:
        migration_sql = f.read()
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        print(f"📦 Applying migration: {migration_path.name}")
        print("=" * 60)
        
        # Split SQL into individual statements
        statements = [s.strip() for s in migration_sql.split(';') if s.strip() and not s.strip().startswith('--')]
        
        for i, statement in enumerate(statements, 1):
            # Skip comments
            if statement.startswith('--'):
                continue
            
            try:
                # Get operation type
                op_type = statement.split()[0].upper() if statement else ""
                
                print(f"  [{i}/{len(statements)}] {op_type}...", end=" ")
                cursor.execute(statement)
                print("✓")
                
            except sqlite3.OperationalError as e:
                error_msg = str(e).lower()
                
                # Handle "duplicate column name" error (column already exists)
                if "duplicate column name" in error_msg:
                    print(f"⚠️  (already exists)")
                    continue
                
                # Handle "table already exists"
                elif "already exists" in error_msg:
                    print(f"⚠️  (already exists)")
                    continue
                
                # Handle "index already exists"
                elif "index" in error_msg and "already exists" in error_msg:
                    print(f"⚠️  (already exists)")
                    continue
                
                # Handle "no such column" - might be trying to update before adding
                elif "no such column" in error_msg:
                    print(f"⚠️  (skipped - column doesn't exist yet)")
                    continue
                
                # Other errors
                else:
                    print(f"❌")
                    print(f"\n  Error: {e}")
                    print(f"  Statement: {statement[:100]}...")
                    raise
        
        conn.commit()
        print("=" * 60)
        print("✅ Migration applied successfully!")
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        conn.close()


def main():
    """Main function"""
    db_path = "telespam.db"
    migration_file = "migrations/001_add_campaign_improvements.sql"
    
    if len(sys.argv) > 1:
        migration_file = sys.argv[1]
    
    if len(sys.argv) > 2:
        db_path = sys.argv[2]
    
    print(f"\n🔧 Database Migration Tool")
    print(f"   Database: {db_path}")
    print(f"   Migration: {migration_file}\n")
    
    success = apply_migration(db_path, migration_file)
    
    if success:
        print(f"\n✅ Done! Database updated.\n")
        sys.exit(0)
    else:
        print(f"\n❌ Migration failed.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()

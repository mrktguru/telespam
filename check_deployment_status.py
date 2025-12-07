#!/usr/bin/env python3
"""
Check deployment status and diagnose issues
"""

import sys
from pathlib import Path
from database import db
import config

print("\n" + "="*70)
print("  DEPLOYMENT STATUS CHECK")
print("="*70)

# 1. Check web_app.py version
print("\n📝 1. CODE VERSION CHECK")
print("-" * 70)

web_app_file = Path(__file__).parent / "web_app.py"
if web_app_file.exists():
    with open(web_app_file, 'r') as f:
        content = f.read()
        
    # Check for the fix
    if 'PRIORITY 1: For username - send directly without trying to get access_hash' in content:
        print("✅ Code version: FIXED (PR #115 applied)")
        print("   Username sending uses direct method (correct)")
    elif 'PRIORITY 1: Try username first' in content:
        print("❌ Code version: OLD (PR #115 NOT applied)")
        print("   Username sending uses complex resolution (wrong)")
        print("\n   ⚠️  YOU NEED TO DEPLOY THE LATEST VERSION!")
    else:
        print("⚠️  Code version: UNKNOWN")
else:
    print("❌ web_app.py not found!")

# 2. Check API credentials in .env
print("\n🔑 2. API CREDENTIALS CHECK (.env)")
print("-" * 70)

if config.API_ID and config.API_HASH:
    print(f"✅ API_ID: {config.API_ID}")
    print(f"✅ API_HASH: {config.API_HASH[:10]}...")
else:
    print("❌ API_ID or API_HASH not set in .env!")
    print("   Add them from https://my.telegram.org")

# 3. Check accounts in database
print("\n👥 3. ACCOUNTS API CREDENTIALS CHECK")
print("-" * 70)

try:
    accounts = db.get_all_accounts()
    
    if not accounts:
        print("⚠️  No accounts found in database")
    else:
        correct_count = 0
        wrong_count = 0
        
        for acc in accounts:
            phone = acc.get('phone', 'Unknown')
            api_id = str(acc.get('api_id', ''))
            api_hash = acc.get('api_hash', '')
            
            # Check for the specific account from error
            if phone == '+12297082263' or '12297082263' in phone:
                print(f"\n🔍 PROBLEM ACCOUNT FOUND: {phone}")
                
            # Check credentials
            if api_id == '611335':
                status = "❌ TELEGRAM DESKTOP (won't work for spam)"
                wrong_count += 1
            elif api_id == str(config.API_ID):
                status = "✅ Correct (from .env)"
                correct_count += 1
            else:
                status = "⚠️  Unknown"
                wrong_count += 1
            
            print(f"  {phone}:")
            print(f"    API ID: {api_id} - {status}")
            print(f"    API Hash: {api_hash[:10]}...")
        
        print("\n" + "-" * 70)
        print(f"Summary: ✅ {correct_count} correct, ❌ {wrong_count} wrong/unknown")
        
        if wrong_count > 0:
            print("\n⚠️  ATTENTION: Some accounts need to be recreated!")
            print("   See SESSION_API_CREDENTIALS_ISSUE.md for instructions")
            
except Exception as e:
    print(f"❌ Error checking accounts: {e}")

# 4. Check git status
print("\n📦 4. GIT STATUS")
print("-" * 70)

import subprocess

try:
    # Get current branch
    result = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], 
                          capture_output=True, text=True, cwd=Path(__file__).parent)
    current_branch = result.stdout.strip()
    
    # Get current commit
    result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], 
                          capture_output=True, text=True, cwd=Path(__file__).parent)
    current_commit = result.stdout.strip()
    
    # Get remote main commit
    result = subprocess.run(['git', 'rev-parse', '--short', 'origin/main'], 
                          capture_output=True, text=True, cwd=Path(__file__).parent)
    remote_commit = result.stdout.strip()
    
    print(f"Current branch: {current_branch}")
    print(f"Current commit: {current_commit}")
    print(f"Remote main commit: {remote_commit}")
    
    if current_commit == remote_commit:
        print("✅ Up to date with remote main")
    else:
        print("❌ NOT up to date with remote main!")
        print("\n   ⚠️  YOU NEED TO RUN: git pull origin main")
        
except Exception as e:
    print(f"⚠️  Could not check git status: {e}")

# 5. Summary and recommendations
print("\n" + "="*70)
print("  SUMMARY & RECOMMENDATIONS")
print("="*70)

print("\n🔴 ERROR: 'Invalid user_id format: None - No user has \"mrgekko\" as username'")
print("\nPossible causes:")
print("\n1. ❌ OLD CODE on production server")
print("   Solution:")
print("     cd /path/to/telespam")
print("     git pull origin main")
print("     sudo systemctl restart telespam-web  # or your restart command")
print("\n2. ❌ Account 12297082263 has WRONG API credentials (Telegram Desktop)")
print("   Solution:")
print("     - Delete account from system")
print("     - Recreate session with correct API credentials")
print("     - See SESSION_API_CREDENTIALS_ISSUE.md")
print("\n3. ❌ Session file corrupted or invalid")
print("   Solution:")
print("     - Delete account and session file")
print("     - Add account again")

print("\n📋 DEPLOYMENT CHECKLIST:")
print("  [ ] 1. Pull latest code: git pull origin main")
print("  [ ] 2. Check code version has the fix (see above)")
print("  [ ] 3. Restart application")
print("  [ ] 4. Check API credentials in .env")
print("  [ ] 5. Verify account credentials (see above)")
print("  [ ] 6. Test sending to unknown user")

print("\n" + "="*70)
print()

#!/usr/bin/env python3
"""
Diagnostic script to check web_app.py for errors
Run this on the server to see what's causing the boot failure
"""

import sys
import traceback

print("=" * 70)
print("  WEB_APP.PY DIAGNOSTIC")
print("=" * 70)
print()

# Step 1: Check Python version
print("Step 1: Python version")
print(f"  Python: {sys.version}")
print()

# Step 2: Check basic imports
print("Step 2: Basic imports")
try:
    import os
    print("  ✓ os")
except Exception as e:
    print(f"  ✗ os: {e}")
    sys.exit(1)

try:
    from pathlib import Path
    print("  ✓ pathlib")
except Exception as e:
    print(f"  ✗ pathlib: {e}")
    sys.exit(1)

try:
    from flask import Flask
    print("  ✓ flask")
except Exception as e:
    print(f"  ✗ flask: {e}")
    sys.exit(1)

try:
    from telethon import TelegramClient
    print("  ✓ telethon")
except Exception as e:
    print(f"  ✗ telethon: {e}")
    sys.exit(1)
print()

# Step 3: Check config
print("Step 3: Config import")
try:
    import config
    print(f"  ✓ config imported")
    print(f"    API_ID: {config.API_ID}")
    print(f"    API_HASH: {'*' * 20 if config.API_HASH else 'None'}")
except Exception as e:
    print(f"  ✗ config: {e}")
    traceback.print_exc()
    sys.exit(1)
print()

# Step 4: Check database
print("Step 4: Database import")
try:
    from database import db
    print("  ✓ database imported")
    print(f"    Database path: {db.db_path}")
    print(f"    Database exists: {db.db_path.exists()}")
except Exception as e:
    print(f"  ✗ database: {e}")
    traceback.print_exc()
    sys.exit(1)
print()

# Step 5: Check other imports
print("Step 5: Other imports")
try:
    from rate_limiter import RateLimiter
    print("  ✓ rate_limiter")
except Exception as e:
    print(f"  ✗ rate_limiter: {e}")
    traceback.print_exc()

try:
    from proxy_manager import ProxyManager
    print("  ✓ proxy_manager")
except Exception as e:
    print(f"  ✗ proxy_manager: {e}")
    traceback.print_exc()
print()

# Step 6: Try to import web_app
print("Step 6: Import web_app")
try:
    import web_app
    print("  ✓ web_app imported successfully")
    print(f"    Flask app: {web_app.app}")
    print(f"    App name: {web_app.app.name}")
except Exception as e:
    print(f"  ✗ web_app: {e}")
    print()
    print("  Full traceback:")
    traceback.print_exc()
    sys.exit(1)
print()

# Step 7: Check if app can be accessed by gunicorn
print("Step 7: Gunicorn compatibility")
try:
    app = web_app.app
    print("  ✓ app object accessible")
    print(f"    App type: {type(app)}")
    print(f"    App name: {app.name}")
except Exception as e:
    print(f"  ✗ app access: {e}")
    traceback.print_exc()
    sys.exit(1)
print()

print("=" * 70)
print("  ✓ ALL CHECKS PASSED")
print("=" * 70)
print()
print("If web_app.py imports successfully here but gunicorn fails,")
print("the issue might be:")
print("  1. Different Python version on server")
print("  2. Missing dependencies")
print("  3. Different working directory")
print("  4. Environment variables not set")
print("  5. File permissions")
print()


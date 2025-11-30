#!/usr/bin/env python3
"""Local development server on port 5001"""

from web_app import app

if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("  WEB INTERFACE STARTING (LOCAL)")
    print("=" * 70)
    print()
    print("  URL: http://127.0.0.1:5001")
    print("  Register a new account to get started")
    print()
    print("=" * 70)
    print()
    
    app.run(host='127.0.0.1', port=5001, debug=True)


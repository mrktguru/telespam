"""Sheets manager loader - selects between real and mock storage"""

import config

if config.USE_MOCK_STORAGE:
    print("✓ Using MOCK storage (in-memory, for testing)")
    from mock_sheets import sheets_manager
else:
    print("✓ Using Google Sheets storage")
    from sheets import sheets_manager

__all__ = ['sheets_manager']

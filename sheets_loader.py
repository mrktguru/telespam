"""Sheets manager loader - deprecated, use database instead"""

# This module is kept for backward compatibility but should not be used
# All data is now stored in SQLite database (database.py)

# Create a dummy sheets_manager for backward compatibility
class DummySheetsManager:
    """Dummy sheets manager - all operations should use database instead"""
    def __getattr__(self, name):
        raise AttributeError(
            f"sheets_manager.{name} is deprecated. "
            f"Please use database (db) instead. "
            f"Import: from database import db"
        )

sheets_manager = DummySheetsManager()

__all__ = ['sheets_manager']

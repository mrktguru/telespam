#!/usr/bin/env python3
"""
Database models for web interface - SQLite
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
import json
import hashlib


class Database:
    """SQLite database manager"""

    def __init__(self, db_path: str = "telespam.db"):
        self.db_path = Path(db_path)
        self.init_db()

    def get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Initialize database tables"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')

        # Campaigns table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                total_users INTEGER DEFAULT 0,
                sent_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                settings TEXT,
                results TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        # Campaign logs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS campaign_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                level TEXT DEFAULT 'info',
                message TEXT NOT NULL,
                details TEXT,
                FOREIGN KEY (campaign_id) REFERENCES campaigns (id)
            )
        ''')

        conn.commit()
        conn.close()

    # ========================================================================
    # USERS
    # ========================================================================

    def create_user(self, email: str, password: str) -> Optional[int]:
        """
        Create new user

        Args:
            email: User email
            password: Plain text password

        Returns:
            User ID or None if exists
        """
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                'INSERT INTO users (email, password_hash) VALUES (?, ?)',
                (email, password_hash)
            )
            conn.commit()
            user_id = cursor.lastrowid
            conn.close()
            return user_id

        except sqlite3.IntegrityError:
            conn.close()
            return None

    def verify_user(self, email: str, password: str) -> Optional[Dict]:
        """
        Verify user credentials

        Args:
            email: User email
            password: Plain text password

        Returns:
            User dict or None
        """
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            'SELECT * FROM users WHERE email = ? AND password_hash = ?',
            (email, password_hash)
        )

        row = cursor.fetchone()

        if row:
            # Update last login
            cursor.execute(
                'UPDATE users SET last_login = ? WHERE id = ?',
                (datetime.now(), row['id'])
            )
            conn.commit()

            user = dict(row)
            conn.close()
            return user

        conn.close()
        return None

    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()

        conn.close()

        if row:
            return dict(row)

        return None

    # ========================================================================
    # CAMPAIGNS
    # ========================================================================

    def create_campaign(
        self,
        user_id: int,
        name: str,
        total_users: int = 0,
        settings: Optional[Dict] = None
    ) -> int:
        """
        Create new campaign

        Args:
            user_id: User ID
            name: Campaign name
            total_users: Total users to contact
            settings: Campaign settings

        Returns:
            Campaign ID
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        settings_json = json.dumps(settings) if settings else None

        cursor.execute(
            '''INSERT INTO campaigns
            (user_id, name, total_users, settings)
            VALUES (?, ?, ?, ?)''',
            (user_id, name, total_users, settings_json)
        )

        conn.commit()
        campaign_id = cursor.lastrowid
        conn.close()

        return campaign_id

    def get_campaign(self, campaign_id: int) -> Optional[Dict]:
        """Get campaign by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM campaigns WHERE id = ?', (campaign_id,))
        row = cursor.fetchone()

        conn.close()

        if row:
            campaign = dict(row)

            # Parse JSON fields
            if campaign.get('settings'):
                campaign['settings'] = json.loads(campaign['settings'])

            if campaign.get('results'):
                campaign['results'] = json.loads(campaign['results'])

            return campaign

        return None

    def get_user_campaigns(self, user_id: int, limit: int = 50) -> List[Dict]:
        """Get user's campaigns"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            '''SELECT * FROM campaigns
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?''',
            (user_id, limit)
        )

        rows = cursor.fetchall()
        conn.close()

        campaigns = []
        for row in rows:
            campaign = dict(row)

            # Parse JSON fields
            if campaign.get('settings'):
                campaign['settings'] = json.loads(campaign['settings'])

            if campaign.get('results'):
                campaign['results'] = json.loads(campaign['results'])

            campaigns.append(campaign)

        return campaigns

    def update_campaign(
        self,
        campaign_id: int,
        status: Optional[str] = None,
        sent_count: Optional[int] = None,
        failed_count: Optional[int] = None,
        results: Optional[Dict] = None
    ):
        """Update campaign"""
        conn = self.get_connection()
        cursor = conn.cursor()

        updates = []
        params = []

        if status:
            updates.append('status = ?')
            params.append(status)

            if status == 'running' and not self.get_campaign(campaign_id).get('started_at'):
                updates.append('started_at = ?')
                params.append(datetime.now())

            if status == 'completed':
                updates.append('completed_at = ?')
                params.append(datetime.now())

        if sent_count is not None:
            updates.append('sent_count = ?')
            params.append(sent_count)

        if failed_count is not None:
            updates.append('failed_count = ?')
            params.append(failed_count)

        if results:
            updates.append('results = ?')
            params.append(json.dumps(results))

        if updates:
            params.append(campaign_id)
            query = f"UPDATE campaigns SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
            conn.commit()

        conn.close()

    def delete_campaign(self, campaign_id: int):
        """Delete campaign"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Delete logs
        cursor.execute('DELETE FROM campaign_logs WHERE campaign_id = ?', (campaign_id,))

        # Delete campaign
        cursor.execute('DELETE FROM campaigns WHERE id = ?', (campaign_id,))

        conn.commit()
        conn.close()

    # ========================================================================
    # CAMPAIGN LOGS
    # ========================================================================

    def add_campaign_log(
        self,
        campaign_id: int,
        message: str,
        level: str = 'info',
        details: Optional[Dict] = None
    ):
        """Add log entry to campaign"""
        conn = self.get_connection()
        cursor = conn.cursor()

        details_json = json.dumps(details) if details else None

        cursor.execute(
            '''INSERT INTO campaign_logs
            (campaign_id, level, message, details)
            VALUES (?, ?, ?, ?)''',
            (campaign_id, level, message, details_json)
        )

        conn.commit()
        conn.close()

    def get_campaign_logs(self, campaign_id: int, limit: int = 100) -> List[Dict]:
        """Get campaign logs"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            '''SELECT * FROM campaign_logs
            WHERE campaign_id = ?
            ORDER BY timestamp DESC
            LIMIT ?''',
            (campaign_id, limit)
        )

        rows = cursor.fetchall()
        conn.close()

        logs = []
        for row in rows:
            log = dict(row)

            if log.get('details'):
                log['details'] = json.loads(log['details'])

            logs.append(log)

        return logs


# Singleton instance
db = Database()


if __name__ == "__main__":
    # Test database
    print("Initializing database...")

    # Create test user
    user_id = db.create_user("test@example.com", "password123")
    print(f"Created user: {user_id}")

    # Verify user
    user = db.verify_user("test@example.com", "password123")
    print(f"Verified user: {user}")

    # Create test campaign
    campaign_id = db.create_campaign(
        user_id=user['id'],
        name="Test Campaign",
        total_users=100,
        settings={'message': 'Hello!'}
    )
    print(f"Created campaign: {campaign_id}")

    # Add log
    db.add_campaign_log(campaign_id, "Campaign started", level="info")

    # Get campaign
    campaign = db.get_campaign(campaign_id)
    print(f"Campaign: {campaign}")

    # Get logs
    logs = db.get_campaign_logs(campaign_id)
    print(f"Logs: {logs}")

    print("\n✅ Database test completed!")

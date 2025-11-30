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
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrency
        conn.execute('PRAGMA journal_mode=WAL')
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

        # Campaign conversations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS campaign_conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                sender_account_id TEXT NOT NULL,
                recipient_user_id TEXT NOT NULL,
                recipient_username TEXT,
                ip_address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_message_at TIMESTAMP,
                FOREIGN KEY (campaign_id) REFERENCES campaigns (id)
            )
        ''')

        # Campaign messages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS campaign_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                direction TEXT NOT NULL,
                message_text TEXT NOT NULL,
                media_path TEXT,
                media_type TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'sent',
                FOREIGN KEY (conversation_id) REFERENCES campaign_conversations (id)
            )
        ''')

        # Campaign users table - links users to specific campaigns
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS campaign_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                username TEXT,
                user_id TEXT,
                phone TEXT,
                priority INTEGER DEFAULT 1,
                status TEXT DEFAULT 'pending',
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                contacted_at TIMESTAMP,
                contacted_by TEXT,
                FOREIGN KEY (campaign_id) REFERENCES campaigns (id) ON DELETE CASCADE
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

    # ========================================================================
    # CAMPAIGN CONVERSATIONS
    # ========================================================================

    def create_conversation(self, campaign_id: int, sender_account_id: str, 
                          recipient_user_id: str, recipient_username: str = None,
                          ip_address: str = None) -> Optional[int]:
        """Create or get conversation for campaign"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Check if conversation already exists
            cursor.execute(
                '''SELECT id FROM campaign_conversations
                WHERE campaign_id = ? AND sender_account_id = ? AND recipient_user_id = ?''',
                (campaign_id, sender_account_id, recipient_user_id)
            )
            
            row = cursor.fetchone()
            if row:
                return row[0]

            # Create new conversation
            cursor.execute(
                '''INSERT INTO campaign_conversations 
                (campaign_id, sender_account_id, recipient_user_id, recipient_username, ip_address, last_message_at)
                VALUES (?, ?, ?, ?, ?, ?)''',
                (campaign_id, sender_account_id, recipient_user_id, recipient_username, 
                 ip_address, datetime.now().isoformat())
            )

            conn.commit()
            conversation_id = cursor.lastrowid
            return conversation_id

        except Exception as e:
            print(f"Error creating conversation: {e}")
            return None
        finally:
            conn.close()

    def add_message(self, conversation_id: int, direction: str, message_text: str) -> bool:
        """Add message to conversation (direction: 'outgoing' or 'incoming')"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                '''INSERT INTO campaign_messages 
                (conversation_id, direction, message_text, sent_at)
                VALUES (?, ?, ?, ?)''',
                (conversation_id, direction, message_text, datetime.now().isoformat())
            )

            # Update last_message_at in conversation
            cursor.execute(
                '''UPDATE campaign_conversations 
                SET last_message_at = ? 
                WHERE id = ?''',
                (datetime.now().isoformat(), conversation_id)
            )

            conn.commit()
            return True

        except Exception as e:
            print(f"Error adding message: {e}")
            return False
        finally:
            conn.close()

    def get_campaign_conversations(self, campaign_id: int) -> List[Dict]:
        """Get all conversations for a campaign"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            '''SELECT * FROM campaign_conversations
            WHERE campaign_id = ?
            ORDER BY last_message_at DESC''',
            (campaign_id,)
        )

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_conversation(self, conversation_id: int) -> Optional[Dict]:
        """Get conversation by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            'SELECT * FROM campaign_conversations WHERE id = ?',
            (conversation_id,)
        )

        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None

    def get_conversation_messages(self, conversation_id: int) -> List[Dict]:
        """Get all messages in a conversation"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            '''SELECT * FROM campaign_messages
            WHERE conversation_id = ?
            ORDER BY sent_at ASC''',
            (conversation_id,)
        )

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def delete_conversation(self, conversation_id: int) -> bool:
        """Delete conversation and all its messages"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Delete messages first
            cursor.execute(
                'DELETE FROM campaign_messages WHERE conversation_id = ?',
                (conversation_id,)
            )

            # Delete conversation
            cursor.execute(
                'DELETE FROM campaign_conversations WHERE id = ?',
                (conversation_id,)
            )

            conn.commit()
            return True

        except Exception as e:
            print(f"Error deleting conversation: {e}")
            return False
        finally:
            conn.close()

    # ========================================================================
    # CAMPAIGN USERS
    # ========================================================================

    def add_campaign_user(self, campaign_id: int, username: str = None, user_id: str = None, 
                         phone: str = None, priority: int = 1) -> Optional[int]:
        """Add user to specific campaign"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                '''INSERT INTO campaign_users 
                   (campaign_id, username, user_id, phone, priority) 
                   VALUES (?, ?, ?, ?, ?)''',
                (campaign_id, username, user_id, phone, priority)
            )
            conn.commit()
            user_record_id = cursor.lastrowid
            return user_record_id
        except Exception as e:
            print(f"Error adding campaign user: {e}")
            return None
        finally:
            conn.close()

    def get_campaign_users(self, campaign_id: int) -> List[Dict]:
        """Get all users for specific campaign"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            '''SELECT * FROM campaign_users 
               WHERE campaign_id = ? 
               ORDER BY priority DESC, added_at ASC''',
            (campaign_id,)
        )

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_all_campaign_users(self) -> List[Dict]:
        """Get all users with campaign information for Users for Outreach"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            '''SELECT cu.*, c.name as campaign_name 
               FROM campaign_users cu
               LEFT JOIN campaigns c ON cu.campaign_id = c.id
               ORDER BY cu.added_at DESC'''
        )

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def bulk_add_campaign_users(self, campaign_id: int, users_data: List[Dict]) -> int:
        """Bulk add users to campaign from CSV/Excel import"""
        conn = self.get_connection()
        cursor = conn.cursor()

        added_count = 0
        try:
            for user_data in users_data:
                cursor.execute(
                    '''INSERT INTO campaign_users 
                       (campaign_id, username, user_id, phone, priority) 
                       VALUES (?, ?, ?, ?, ?)''',
                    (campaign_id, 
                     user_data.get('username'),
                     user_data.get('user_id'), 
                     user_data.get('phone'),
                     user_data.get('priority', 1))
                )
                added_count += 1
            
            conn.commit()
            return added_count
        except Exception as e:
            print(f"Error bulk adding campaign users: {e}")
            conn.rollback()
            return 0
        finally:
            conn.close()

    def delete_campaign_users(self, campaign_id: int, user_ids: List[int]) -> int:
        """Delete selected users from campaign"""
        conn = self.get_connection()
        cursor = conn.cursor()

        deleted_count = 0
        try:
            for user_id in user_ids:
                cursor.execute(
                    'DELETE FROM campaign_users WHERE campaign_id = ? AND id = ?',
                    (campaign_id, user_id)
                )
                deleted_count += cursor.rowcount
            
            conn.commit()
            return deleted_count
        except Exception as e:
            print(f"Error deleting campaign users: {e}")
            conn.rollback()
            return 0
        finally:
            conn.close()

    def update_campaign_user_status(self, user_id: int, campaign_id: int, status: str, contacted_by: str = None):
        """Update campaign user status when contacted"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            if status == 'contacted':
                cursor.execute(
                    '''UPDATE campaign_users 
                       SET status = ?, contacted_at = CURRENT_TIMESTAMP, contacted_by = ?
                       WHERE id = ? AND campaign_id = ?''',
                    (status, contacted_by, user_id, campaign_id)
                )
            else:
                cursor.execute(
                    '''UPDATE campaign_users 
                       SET status = ?
                       WHERE id = ? AND campaign_id = ?''',
                    (status, user_id, campaign_id)
                )
            
            conn.commit()
        except Exception as e:
            print(f"Error updating campaign user status: {e}")
        finally:
            conn.close()


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

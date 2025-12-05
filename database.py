#!/usr/bin/env python3
"""
Database models for web interface - SQLite
"""

import sqlite3
import os
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
        """Get database connection with proper error handling"""
        try:
            # Ensure database file exists and is writable
            if self.db_path.exists():
                # Check if file is writable
                if not os.access(self.db_path, os.W_OK):
                    raise PermissionError(f"Database file {self.db_path} is not writable")
            
            conn = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency
            try:
                conn.execute('PRAGMA journal_mode=WAL')
            except sqlite3.OperationalError:
                # If WAL fails, try DELETE mode
                conn.execute('PRAGMA journal_mode=DELETE')
            return conn
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower():
                raise Exception(f"Database is locked. Please close other processes using the database. Error: {e}")
            elif "readonly" in str(e).lower():
                raise Exception(f"Database is read-only. Check file permissions: {self.db_path}")
            else:
                raise

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

        # Accounts table - for Telegram sender accounts
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                phone TEXT UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                bio TEXT,
                session_file TEXT,
                status TEXT DEFAULT 'checking',
                daily_sent INTEGER DEFAULT 0,
                total_sent INTEGER DEFAULT 0,
                cooldown_until TEXT,
                last_used_at TEXT,
                added_at TEXT,
                flood_count INTEGER DEFAULT 0,
                use_proxy BOOLEAN DEFAULT 0,
                proxy TEXT,
                proxy_type TEXT,
                proxy_host TEXT,
                proxy_port TEXT,
                proxy_user TEXT,
                proxy_pass TEXT,
                campaign_id INTEGER,
                notes TEXT,
                photo_count INTEGER DEFAULT 0,
                rate_limits TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Registration accounts table - for account registration process
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS registration_accounts (
                phone TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'new',
                session_id TEXT,
                check_status TEXT,
                check_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                registered_at TIMESTAMP,
                tdata_path TEXT,
                session_path TEXT,
                error_message TEXT,
                proxy_id INTEGER,
                proxy_ip TEXT,
                device_model TEXT,
                system_version TEXT,
                app_version TEXT,
                lang_code TEXT,
                FOREIGN KEY (proxy_id) REFERENCES registration_proxies (id)
            )
        ''')

        # Registration proxies table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS registration_proxies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                provider TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                protocol TEXT DEFAULT 'socks5',
                session_type TEXT DEFAULT 'rotating',
                rotation_interval INTEGER DEFAULT 20,
                country TEXT,
                exclude_countries TEXT,
                total_gb_purchased FLOAT DEFAULT 0,
                total_gb_used FLOAT DEFAULT 0,
                registrations_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                last_used DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                notes TEXT
            )
        ''')

        # Registration logs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS registration_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL,
                session_id TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                level TEXT DEFAULT 'info',
                message TEXT NOT NULL,
                details TEXT,
                FOREIGN KEY (phone) REFERENCES registration_accounts (phone) ON DELETE CASCADE
            )
        ''')

        # Device presets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS device_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                device_model TEXT NOT NULL,
                system_type TEXT NOT NULL,
                system_version TEXT NOT NULL,
                app_version TEXT NOT NULL,
                lang_code TEXT NOT NULL,
                system_lang_code TEXT NOT NULL,
                enabled BOOLEAN DEFAULT TRUE,
                popularity_weight INTEGER DEFAULT 1
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
        
        # Initialize device presets if table is empty
        self.init_device_presets()

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

    def get_all_campaigns(self) -> List[Dict]:
        """Get all campaigns"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM campaigns ORDER BY created_at DESC')
        rows = cursor.fetchall()

        conn.close()

        return [dict(row) for row in rows]

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

    def delete_campaign(self, campaign_id: int) -> bool:
        """Delete campaign and all related data"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Delete related data first (CASCADE should handle this, but we do it explicitly)
            # Delete campaign users
            cursor.execute('DELETE FROM campaign_users WHERE campaign_id = ?', (campaign_id,))
            
            # Delete campaign conversations and their messages
            # First get conversation IDs
            cursor.execute('SELECT id FROM campaign_conversations WHERE campaign_id = ?', (campaign_id,))
            conversation_ids = [row[0] for row in cursor.fetchall()]
            
            # Delete messages for these conversations
            for conv_id in conversation_ids:
                cursor.execute('DELETE FROM campaign_messages WHERE conversation_id = ?', (conv_id,))
            
            # Delete conversations
            cursor.execute('DELETE FROM campaign_conversations WHERE campaign_id = ?', (campaign_id,))
            
            # Delete logs
            cursor.execute('DELETE FROM campaign_logs WHERE campaign_id = ?', (campaign_id,))

            # Delete campaign
            cursor.execute('DELETE FROM campaigns WHERE id = ?', (campaign_id,))

            conn.commit()
            return True
        except Exception as e:
            print(f"Error deleting campaign: {e}")
            conn.rollback()
            return False
        finally:
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

    def add_message(self, conversation_id: int, direction: str, message_text: str, message_date: str = None) -> bool:
        """Add message to conversation (direction: 'outgoing' or 'incoming')
        
        Args:
            conversation_id: Conversation ID
            direction: 'outgoing' or 'incoming'
            message_text: Message text
            message_date: Optional message date from Telegram (ISO format). If not provided, uses current time.
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Use provided message date (from Telegram) or current time
            sent_at = message_date if message_date else datetime.now().isoformat()
            
            cursor.execute(
                '''INSERT INTO campaign_messages 
                (conversation_id, direction, message_text, sent_at)
                VALUES (?, ?, ?, ?)''',
                (conversation_id, direction, message_text, sent_at)
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
                # Process user_id - convert to string if it's a number, or None if empty
                user_id = user_data.get('user_id')
                if user_id is not None and user_id != '':
                    user_id = str(user_id)
                else:
                    user_id = None
                
                # Process username - None if empty
                username = user_data.get('username')
                if username == '':
                    username = None
                
                # Process phone - None if empty
                phone = user_data.get('phone')
                if phone == '':
                    phone = None
                
                cursor.execute(
                    '''INSERT INTO campaign_users 
                       (campaign_id, username, user_id, phone, priority) 
                       VALUES (?, ?, ?, ?, ?)''',
                    (campaign_id, 
                     username,
                     user_id, 
                     phone,
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

    # Registration logs operations
    def add_registration_log(self, phone: str, message: str, level: str = 'info', session_id: str = None, details: str = None):
        """Add log entry for registration process"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO registration_logs (phone, session_id, level, message, details)
                VALUES (?, ?, ?, ?, ?)
            ''', (phone, session_id, level, message, details))
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            print(f"Error adding registration log: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    def get_registration_logs(self, phone: str, session_id: str = None, limit: int = 100) -> List[Dict]:
        """Get registration logs for a phone number"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            if session_id:
                cursor.execute('''
                    SELECT * FROM registration_logs 
                    WHERE phone = ? AND session_id = ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                ''', (phone, session_id, limit))
            else:
                cursor.execute('''
                    SELECT * FROM registration_logs 
                    WHERE phone = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (phone, limit))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"Error getting registration logs: {e}")
            return []
        finally:
            conn.close()

    # Registration accounts operations
    def add_registration_account(self, phone: str) -> bool:
        """Add new phone number for registration"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                '''INSERT OR IGNORE INTO registration_accounts (phone, status)
                   VALUES (?, 'new')''',
                (phone,)
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Error adding registration account: {e}")
            return False
        finally:
            conn.close()

    def get_registration_account(self, phone: str) -> Optional[Dict]:
        """Get registration account by phone"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT * FROM registration_accounts WHERE phone = ?',
                (phone,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            print(f"Error getting registration account: {e}")
            return None
        finally:
            conn.close()

    def get_all_registration_accounts(self) -> List[Dict]:
        """Get all registration accounts"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT * FROM registration_accounts ORDER BY created_at DESC'
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"Error getting registration accounts: {e}")
            return []
        finally:
            conn.close()

    def update_registration_account(self, phone: str, updates: Dict) -> bool:
        """Update registration account"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
            values = list(updates.values()) + [phone]
            cursor.execute(
                f'UPDATE registration_accounts SET {set_clause} WHERE phone = ?',
                values
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Error updating registration account: {e}")
            return False
        finally:
            conn.close()

    def delete_registration_account(self, phone: str) -> bool:
        """Delete registration account"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'DELETE FROM registration_accounts WHERE phone = ?',
                (phone,)
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Error deleting registration account: {e}")
            return False
        finally:
            conn.close()

    # Registration proxies operations
    def add_registration_proxy(self, proxy_data: Dict) -> Optional[int]:
        """Add new registration proxy"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO registration_proxies 
                (name, type, provider, host, port, username, password, protocol, 
                 session_type, rotation_interval, country, exclude_countries, 
                 total_gb_purchased, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                proxy_data.get('name'),
                proxy_data.get('type'),
                proxy_data.get('provider'),
                proxy_data.get('host'),
                proxy_data.get('port'),
                proxy_data.get('username'),
                proxy_data.get('password'),
                proxy_data.get('protocol', 'socks5'),
                proxy_data.get('session_type', 'rotating'),
                proxy_data.get('rotation_interval', 20),
                proxy_data.get('country'),
                json.dumps(proxy_data.get('exclude_countries', [])) if proxy_data.get('exclude_countries') else None,
                proxy_data.get('total_gb_purchased', 0),
                proxy_data.get('notes')
            ))
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            print(f"Error adding registration proxy: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    def get_all_registration_proxies(self) -> List[Dict]:
        """Get all registration proxies"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT * FROM registration_proxies ORDER BY created_at DESC')
            rows = cursor.fetchall()
            result = []
            for row in rows:
                proxy = dict(row)
                if proxy.get('exclude_countries'):
                    try:
                        proxy['exclude_countries'] = json.loads(proxy['exclude_countries'])
                    except:
                        proxy['exclude_countries'] = []
                else:
                    proxy['exclude_countries'] = []
                result.append(proxy)
            return result
        except Exception as e:
            print(f"Error getting registration proxies: {e}")
            return []
        finally:
            conn.close()

    def get_registration_proxy(self, proxy_id: int) -> Optional[Dict]:
        """Get registration proxy by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT * FROM registration_proxies WHERE id = ?', (proxy_id,))
            row = cursor.fetchone()
            if row:
                proxy = dict(row)
                if proxy.get('exclude_countries'):
                    try:
                        proxy['exclude_countries'] = json.loads(proxy['exclude_countries'])
                    except:
                        proxy['exclude_countries'] = []
                else:
                    proxy['exclude_countries'] = []
                return proxy
            return None
        except Exception as e:
            print(f"Error getting registration proxy: {e}")
            return None
        finally:
            conn.close()

    def update_registration_proxy(self, proxy_id: int, updates: Dict) -> bool:
        """Update registration proxy"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            if 'exclude_countries' in updates and isinstance(updates['exclude_countries'], list):
                updates['exclude_countries'] = json.dumps(updates['exclude_countries'])
            
            set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
            values = list(updates.values()) + [proxy_id]
            cursor.execute(
                f'UPDATE registration_proxies SET {set_clause} WHERE id = ?',
                values
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Error updating registration proxy: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    def delete_registration_proxy(self, proxy_id: int) -> bool:
        """Delete registration proxy"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM registration_proxies WHERE id = ?', (proxy_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Error deleting registration proxy: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    # Device presets operations
    def add_device_preset(self, device_data: Dict) -> Optional[int]:
        """Add new device preset"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO device_presets 
                (name, device_model, system_type, system_version, app_version, 
                 lang_code, system_lang_code, enabled, popularity_weight)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                device_data.get('name'),
                device_data.get('device_model'),
                device_data.get('system_type'),
                device_data.get('system_version'),
                device_data.get('app_version'),
                device_data.get('lang_code'),
                device_data.get('system_lang_code'),
                device_data.get('enabled', True),
                device_data.get('popularity_weight', 1)
            ))
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            print(f"Error adding device preset: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    def get_all_device_presets(self, enabled_only: bool = False) -> List[Dict]:
        """Get all device presets"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            query = 'SELECT * FROM device_presets'
            if enabled_only:
                query += ' WHERE enabled = TRUE'
            query += ' ORDER BY popularity_weight DESC, name ASC'
            cursor.execute(query)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"Error getting device presets: {e}")
            return []
        finally:
            conn.close()

    def get_random_device_preset(self, system_type: Optional[str] = None) -> Optional[Dict]:
        """Get random device preset with weighted selection"""
        import random
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            query = 'SELECT * FROM device_presets WHERE enabled = TRUE'
            params = []
            if system_type:
                query += ' AND system_type = ?'
                params.append(system_type)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            devices = [dict(row) for row in rows]
            
            if not devices:
                return None
            
            # Weighted random selection
            weights = [d.get('popularity_weight', 1) for d in devices]
            selected = random.choices(devices, weights=weights, k=1)[0]
            return selected
        except Exception as e:
            print(f"Error getting random device preset: {e}")
            return None
        finally:
            conn.close()

    def init_device_presets(self):
        """Initialize device presets with top 20 devices"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # Check if presets already exist
            cursor.execute('SELECT COUNT(*) FROM device_presets')
            count = cursor.fetchone()[0]
            if count > 0:
                return  # Already initialized
            
            # Android devices
            android_devices = [
                ('Samsung Galaxy S21', 'SM-G991B', 'android', 'Android 12', '9.4.2', 'en', 'en-US', 10),
                ('Samsung Galaxy S22', 'SM-S901B', 'android', 'Android 13', '9.4.3', 'en', 'en-US', 9),
                ('Samsung Galaxy A52', 'SM-A525F', 'android', 'Android 11', '9.3.5', 'ru', 'ru-RU', 8),
                ('Samsung Galaxy S20', 'SM-G980F', 'android', 'Android 12', '9.4.1', 'de', 'de-DE', 7),
                ('Xiaomi Mi 11', 'M2011K2G', 'android', 'Android 11', '9.4.0', 'en', 'en-US', 9),
                ('Xiaomi Redmi Note 10', 'M2101K7AG', 'android', 'Android 11', '9.3.8', 'ru', 'ru-RU', 8),
                ('Xiaomi Mi 10T Pro', 'M2007J3SG', 'android', 'Android 12', '9.4.2', 'en', 'en-GB', 7),
                ('OnePlus 9 Pro', 'LE2121', 'android', 'Android 12', '9.4.2', 'en', 'en-US', 7),
                ('OnePlus Nord', 'AC2003', 'android', 'Android 11', '9.3.9', 'de', 'de-DE', 6),
                ('Google Pixel 6', 'PIXEL6', 'android', 'Android 13', '9.4.3', 'en', 'en-US', 8),
                ('Google Pixel 5', 'PIXEL5', 'android', 'Android 13', '9.4.2', 'en', 'en-GB', 7),
                ('Huawei P40 Pro', 'ELS-NX9', 'android', 'Android 10', '9.2.5', 'ru', 'ru-RU', 5),
                ('Motorola Edge 20', 'XT2143', 'android', 'Android 11', '9.3.7', 'en', 'en-US', 5),
            ]
            
            # iOS devices
            ios_devices = [
                ('iPhone 13 Pro', 'iPhone14,2', 'ios', 'iOS 16.3', '9.4.0', 'en', 'en-US', 10),
                ('iPhone 13', 'iPhone14,5', 'ios', 'iOS 16.2', '9.4.0', 'en', 'en-US', 9),
                ('iPhone 12 Pro', 'iPhone13,3', 'ios', 'iOS 15.7', '9.3.9', 'en', 'en-GB', 8),
                ('iPhone 12', 'iPhone13,2', 'ios', 'iOS 16.1', '9.4.1', 'ru', 'ru-RU', 8),
                ('iPhone 11', 'iPhone12,1', 'ios', 'iOS 15.7', '9.3.8', 'de', 'de-DE', 7),
                ('iPhone SE (2022)', 'iPhone14,6', 'ios', 'iOS 16.3', '9.4.0', 'en', 'en-US', 6),
                ('iPhone XR', 'iPhone11,8', 'ios', 'iOS 15.6', '9.3.5', 'ru', 'ru-RU', 5),
            ]
            
            all_devices = android_devices + ios_devices
            
            cursor.executemany('''
                INSERT INTO device_presets 
                (name, device_model, system_type, system_version, app_version, 
                 lang_code, system_lang_code, enabled, popularity_weight)
                VALUES (?, ?, ?, ?, ?, ?, ?, TRUE, ?)
            ''', all_devices)
            
            conn.commit()
            print(f"✓ Initialized {len(all_devices)} device presets")
        except Exception as e:
            print(f"Error initializing device presets: {e}")
            conn.rollback()
        finally:
            conn.close()

    # ============================================================================
    # ACCOUNTS OPERATIONS
    # ============================================================================

    def add_account(self, account: Dict) -> bool:
        """Add new account to database"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO accounts (
                    id, phone, username, first_name, last_name, bio, session_file,
                    status, daily_sent, total_sent, cooldown_until, last_used_at,
                    added_at, flood_count, use_proxy, proxy, proxy_type, proxy_host,
                    proxy_port, proxy_user, proxy_pass, campaign_id, notes, photo_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                account.get('id'),
                account.get('phone'),
                account.get('username'),
                account.get('first_name'),
                account.get('last_name'),
                account.get('bio'),
                account.get('session_file'),
                account.get('status', 'checking'),
                account.get('daily_sent', 0),
                account.get('total_sent', 0),
                account.get('cooldown_until'),
                account.get('last_used_at'),
                account.get('added_at'),
                account.get('flood_count', 0),
                1 if account.get('use_proxy') else 0,
                account.get('proxy'),
                account.get('proxy_type'),
                account.get('proxy_host'),
                account.get('proxy_port'),
                account.get('proxy_user'),
                account.get('proxy_pass'),
                account.get('campaign_id'),
                account.get('notes'),
                account.get('photo_count', 0)
            ))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            print(f"Error adding account: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            conn.close()

    def get_account(self, account_id: str) -> Optional[Dict]:
        """Get account by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT * FROM accounts WHERE id = ?', (account_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_dict(row, cursor.description)
            return None
        except Exception as e:
            print(f"Error getting account: {e}")
            return None
        finally:
            conn.close()

    def get_all_accounts(self) -> List[Dict]:
        """Get all accounts"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT * FROM accounts ORDER BY created_at DESC')
            rows = cursor.fetchall()
            accounts = []
            for row in rows:
                account = self._row_to_dict(row, cursor.description)
                # Convert boolean fields
                if account.get('use_proxy') is not None:
                    account['use_proxy'] = bool(account.get('use_proxy'))
                accounts.append(account)
            return accounts
        except Exception as e:
            print(f"Error getting all accounts: {e}")
            import traceback
            traceback.print_exc()
            return []
        finally:
            conn.close()

    def update_account(self, account_id: str, updates: Dict) -> bool:
        """Update account fields"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # Handle ID change if requested
            if 'new_id' in updates:
                new_id = updates.pop('new_id')
                cursor.execute('UPDATE accounts SET id = ? WHERE id = ?', (new_id, account_id))
                account_id = new_id
            
            # Build update query dynamically
            if updates:
                set_clause = ', '.join([f"{key} = ?" for key in updates.keys()])
                set_clause += ', updated_at = CURRENT_TIMESTAMP'
                values = list(updates.values()) + [account_id]
                
                # Convert boolean to int for use_proxy
                if 'use_proxy' in updates:
                    idx = list(updates.keys()).index('use_proxy')
                    values[idx] = 1 if values[idx] else 0
                
                cursor.execute(f'UPDATE accounts SET {set_clause} WHERE id = ?', values)
                conn.commit()
                return True
            return False
        except Exception as e:
            conn.rollback()
            print(f"Error updating account: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            conn.close()

    def delete_account(self, account_id: str) -> bool:
        """Delete account by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM accounts WHERE id = ?', (account_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            print(f"Error deleting account: {e}")
            return False
        finally:
            conn.close()

    def _row_to_dict(self, row, description) -> Dict:
        """Convert database row to dictionary"""
        if row is None:
            return {}
        return {desc[0]: row[i] for i, desc in enumerate(description)}


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

"""
Patch to add methods to Database class in database.py

These methods should be added inside the Database class (with proper indentation).
"""

# Copy these methods into Database class in database.py:

def init_account_campaign_limit(self, campaign_id: int, account_phone: str, messages_limit: int = 3):
    """Initialize account limit tracking for campaign"""
    conn = self.get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            '''INSERT OR IGNORE INTO account_campaign_limits 
               (campaign_id, account_phone, messages_sent, messages_limit, status)
               VALUES (?, ?, 0, ?, 'active')''',
            (campaign_id, account_phone, messages_limit)
        )
        conn.commit()
    finally:
        conn.close()

def get_account_campaign_limit(self, campaign_id: int, account_phone: str):
    """Get account limit status for campaign"""
    conn = self.get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        'SELECT * FROM account_campaign_limits WHERE campaign_id = ? AND account_phone = ?',
        (campaign_id, account_phone)
    )
    
    row = cursor.fetchone()
    conn.close()
    
    return dict(row) if row else None

def update_account_campaign_limit(self, campaign_id: int, account_phone: str, updates: dict):
    """Update account limit tracking"""
    conn = self.get_connection()
    cursor = conn.cursor()
    
    try:
        update_fields = []
        values = []
        
        for key, value in updates.items():
            update_fields.append(f"{key} = ?")
            values.append(value)
        
        if update_fields:
            values.extend([campaign_id, account_phone])
            query = f"UPDATE account_campaign_limits SET {', '.join(update_fields)} WHERE campaign_id = ? AND account_phone = ?"
            cursor.execute(query, values)
            conn.commit()
    finally:
        conn.close()

def reset_account_campaign_limits(self, campaign_id: int):
    """Reset all account limits for campaign (for Restart operation)"""
    conn = self.get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            '''UPDATE account_campaign_limits 
               SET messages_sent = 0, status = 'active', last_sent_at = NULL
               WHERE campaign_id = ?''',
            (campaign_id,)
        )
        conn.commit()
    finally:
        conn.close()

def get_campaign_account_limits(self, campaign_id: int):
    """Get all account limits for campaign"""
    conn = self.get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        'SELECT * FROM account_campaign_limits WHERE campaign_id = ? ORDER BY account_phone',
        (campaign_id,)
    )
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def get_next_campaign_user(self, campaign_id: int):
    """Get next user to send message to (for worker)"""
    conn = self.get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            '''SELECT * FROM campaign_users 
               WHERE campaign_id = ? AND status = 'new'
               ORDER BY priority DESC, added_at ASC
               LIMIT 1''',
            (campaign_id,)
        )
        
        row = cursor.fetchone()
        
        if row:
            user = dict(row)
            cursor.execute(
                'UPDATE campaign_users SET status = ? WHERE id = ?',
                ('processing', user['id'])
            )
            conn.commit()
            return user
        
        return None
    finally:
        conn.close()

def count_campaign_users_by_status(self, campaign_id: int, status: str):
    """Count users with specific status in campaign"""
    conn = self.get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        'SELECT COUNT(*) as count FROM campaign_users WHERE campaign_id = ? AND status = ?',
        (campaign_id, status)
    )
    
    row = cursor.fetchone()
    conn.close()
    
    return row['count'] if row else 0

def get_account_by_phone(self, phone: str):
    """Get account by phone number"""
    conn = self.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM accounts WHERE phone = ?', (phone,))
    
    row = cursor.fetchone()
    conn.close()
    
    return dict(row) if row else None

def update_campaign_user(self, user_id: int, updates: dict):
    """Update campaign user"""
    conn = self.get_connection()
    cursor = conn.cursor()
    
    try:
        update_fields = []
        values = []
        
        for key, value in updates.items():
            update_fields.append(f"{key} = ?")
            values.append(value)
        
        if update_fields:
            values.append(user_id)
            query = f"UPDATE campaign_users SET {', '.join(update_fields)} WHERE id = ?"
            cursor.execute(query, values)
            conn.commit()
    finally:
        conn.close()

def reset_campaign_users_for_restart(self, campaign_id: int):
    """Reset all 'sent' users to 'new' for Restart operation"""
    conn = self.get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            '''UPDATE campaign_users 
               SET status = 'new', contacted_at = NULL, contacted_by = NULL, error_message = NULL
               WHERE campaign_id = ? AND status = 'sent' ''',
            (campaign_id,)
        )
        affected = cursor.rowcount
        conn.commit()
        return affected
    finally:
        conn.close()

def delete_campaign_user_by_id(self, user_id: int):
    """Delete single campaign user by ID"""
    conn = self.get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('DELETE FROM campaign_users WHERE id = ?', (user_id,))
        affected = cursor.rowcount
        conn.commit()
        return affected > 0
    finally:
        conn.close()

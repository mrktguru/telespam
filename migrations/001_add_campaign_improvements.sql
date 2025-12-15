-- Migration: Campaign Improvements (Parallel Sending, Limits, Proxy Rotation)
-- Date: 2025-12-15
-- Description: Add account limits, campaign settings, proxy rotation support

-- Step 1: Add new columns to campaigns table
ALTER TABLE campaigns ADD COLUMN message_text TEXT;

ALTER TABLE campaigns ADD COLUMN media_path TEXT;

ALTER TABLE campaigns ADD COLUMN media_type TEXT;

-- Step 2: Create account_campaign_limits table
CREATE TABLE IF NOT EXISTS account_campaign_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    account_phone TEXT NOT NULL,
    messages_sent INTEGER DEFAULT 0,
    messages_limit INTEGER DEFAULT 3,
    last_sent_at TIMESTAMP,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (campaign_id) REFERENCES campaigns (id) ON DELETE CASCADE,
    UNIQUE(campaign_id, account_phone)
);

-- Step 3: Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_account_limits_campaign 
    ON account_campaign_limits(campaign_id, account_phone);

CREATE INDEX IF NOT EXISTS idx_account_limits_status 
    ON account_campaign_limits(campaign_id, status);

CREATE INDEX IF NOT EXISTS idx_campaign_users_status 
    ON campaign_users(campaign_id, status);

-- Step 4: Add columns to campaign_users table
ALTER TABLE campaign_users ADD COLUMN contacted_by TEXT;

ALTER TABLE campaign_users ADD COLUMN error_message TEXT;

-- Notes:
-- - campaigns.settings (JSON) will store:
--   {
--     "accounts": ["phone1", "phone2", ...],
--     "proxies": ["proxy_id1", "proxy_id2", ...],
--     "messages_per_account": 3,
--     "delay_min": 100,
--     "delay_max": 600,
--     "rotate_ip_per_message": true
--   }
-- - campaign_users.status values: 'new' | 'processing' | 'sent' | 'failed'
--   (previously was 'pending' | 'contacted' - we'll migrate this)

-- Step 5: Migrate existing status values
-- 'pending' -> 'new', 'contacted' -> 'sent'
UPDATE campaign_users SET status = 'new' WHERE status = 'pending';
UPDATE campaign_users SET status = 'sent' WHERE status = 'contacted';

-- Step 6: Update campaigns.status values if needed
-- 'pending' -> 'draft', keep 'running', 'completed', 'paused'
UPDATE campaigns SET status = 'draft' WHERE status = 'pending';

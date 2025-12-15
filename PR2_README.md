# PR #2: Campaign Backend Integration

## Overview

This PR adds backend integration for the campaign improvements foundation (PR #1).

## Changes

### 1. Continue/Restart API Endpoints

Added two new REST API endpoints in `web_app.py`:

#### `/campaigns/<id>/continue` (POST)
- Continues a stopped, paused, or failed campaign
- Resumes from where it left off
- Only processes users with `status='new'`
- Returns JSON: `{success: true, message: '...'}`

#### `/campaigns/<id>/restart` (POST)
- Restarts a campaign from the beginning
- Resets all account limits (`reset_account_campaign_limits`)
- Resets all 'sent' users back to 'new' status (`reset_campaign_users_for_restart`)
- Resets campaign counters (sent_count, failed_count)
- Returns JSON: `{success: true, affected_users: N}`

### 2. Campaign Runner V2

New module: `campaign_runner_v2.py`

**Main Functions:**
- `run_campaign_with_worker_pool()` - Async campaign runner using `CampaignCoordinator`
- `run_campaign_task_v2()` - Sync wrapper for threading compatibility

**Features:**
- ✅ Parallel account sending (worker pool)
- ✅ Account limit tracking per campaign
- ✅ Proxy rotation (round-robin from pool)
- ✅ Random delays between messages (30-90 seconds default)
- ✅ Stop check callback integration
- ✅ Account status handling (unauthorized, limited, active)
- ✅ Auto-restore limited accounts after 24 hours
- ✅ Thread-safe user distribution via `db.get_next_campaign_user()`
- ✅ Comprehensive logging to campaign_logs

**Architecture:**
```
Campaign
  ↓
CampaignCoordinator
  ↓
[Worker1, Worker2, Worker3, ...]
  ↓         ↓         ↓
Account1  Account2  Account3
  ↓         ↓         ↓
[Users]   [Users]   [Users]
```

## Usage

### Continue Campaign
```bash
curl -X POST http://localhost:5000/campaigns/123/continue \
  -H "Cookie: session=..." \
  -H "Content-Type: application/json"
```

### Restart Campaign
```bash
curl -X POST http://localhost:5000/campaigns/123/restart \
  -H "Cookie: session=..." \
  -H "Content-Type: application/json"
```

### Using Runner V2 (for developers)
```python
from campaign_runner_v2 import run_campaign_task_v2
import threading

# Start campaign with worker pool
thread = threading.Thread(
    target=run_campaign_task_v2,
    args=(campaign_id, campaign_stop_flags, get_all_accounts, update_account),
    daemon=True
)
thread.start()
```

## Configuration

Worker pool settings can be configured in campaign settings:

```json
{
  "message": "Hello!",
  "accounts": ["+1234567890", "+0987654321"],
  "proxies": [1, 2, 3],
  "messages_per_account": 50,  // Max messages per account
  "delay_min": 30,              // Min delay in seconds
  "delay_max": 90               // Max delay in seconds
}
```

## Database Methods Used

From PR #1 (foundation):
- `db.reset_account_campaign_limits(campaign_id)` - Reset all account limits
- `db.reset_campaign_users_for_restart(campaign_id)` - Reset users to 'new'
- `db.get_next_campaign_user(campaign_id)` - Thread-safe user fetching
- `db.init_account_campaign_limit(campaign_id, phone, limit)` - Initialize limits
- `db.update_account_campaign_limit(campaign_id, phone, updates)` - Update limits
- `db.update_campaign_user(user_id, updates)` - Update user status

## Testing

### Syntax Validation
```bash
python3 -m py_compile web_app.py campaign_runner_v2.py
# ✅ PASSED
```

### Import Test
```bash
python3 -c "from campaign_runner_v2 import run_campaign_task_v2; print('OK')"
# ✅ PASSED
```

## Integration

To integrate Runner V2 into existing campaign execution:

1. Import the new runner:
```python
from campaign_runner_v2 import run_campaign_task_v2
```

2. Replace `run_campaign_task` with `run_campaign_task_v2` in start/continue/restart endpoints:
```python
thread = threading.Thread(
    target=run_campaign_task_v2,  # Changed from run_campaign_task
    args=(campaign_id, campaign_stop_flags, get_all_accounts, update_account),
    daemon=True
)
thread.start()
```

## Benefits

### vs Old System (Simple Round-Robin)
| Feature | Old System | New System (PR #2) |
|---------|-----------|-------------------|
| **Account sending** | Sequential | Parallel (worker pool) |
| **Account limits** | None | Per-campaign tracking |
| **Proxy rotation** | Static | Dynamic (reconnect support) |
| **Continue support** | ❌ | ✅ (resumes from 'new' users) |
| **Restart support** | ❌ | ✅ (full reset) |
| **Thread safety** | ⚠️ | ✅ (get_next_campaign_user) |
| **Delays** | Fixed 2s | Random 30-90s (configurable) |
| **Performance** | Slow (sequential) | Fast (parallel) |

## Next Steps (PR #3: Frontend)

- [ ] Campaign creation UI with account/proxy selection
- [ ] Worker pool settings (messages_per_account, delays)
- [ ] Continue/Restart buttons in campaign detail page
- [ ] Account limits display
- [ ] User management (delete users from campaign)
- [ ] Campaign status indicators

## Files Changed

```
 web_app.py              |  74 +++++++++++++++++
 campaign_runner_v2.py   | 213 +++++++++++++++++++++++++++++++++++++++++++
 PR2_README.md           |  (this file)
 3 files changed, 287 insertions(+)
```

## Dependencies

- Requires PR #1 (Campaign Improvements Foundation) to be merged first
- Uses `CampaignCoordinator` from `campaign_worker.py`
- Uses new Database methods from `database.py`

## Compatibility

- ✅ Backwards compatible with existing campaigns
- ✅ Old `run_campaign_task` still available
- ✅ Can be deployed incrementally (switch campaigns one by one)

## Known Limitations

- Frontend UI not included (PR #3)
- Worker pool settings not configurable via UI yet
- No live progress updates (polling still uses old format)

---

**Droid-assisted PR** - Campaign Backend Integration

#!/usr/bin/env python3
"""
Web Interface - Flask application for Telegram Outreach System
"""

import os
os.environ['USE_MOCK_STORAGE'] = 'true'

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_file
from functools import wraps
from datetime import datetime
import asyncio
import threading
import time
import json
from pathlib import Path
from telethon import TelegramClient
from telethon.errors import FloodWaitError, UserPrivacyRestrictedError, PeerFloodError, PhoneNumberInvalidError, PhoneCodeInvalidError, PhoneCodeExpiredError, SessionPasswordNeededError
from telethon.tl.functions.users import GetFullUserRequest

from database import db
from rate_limiter import RateLimiter
from proxy_manager import ProxyManager
import config

# Account management - use database instead of mock_sheets
def get_all_accounts():
    """Get all accounts from database"""
    return db.get_all_accounts()

def get_account(account_id: str):
    """Get account by ID from database"""
    return db.get_account(account_id)

def add_account(account: dict) -> bool:
    """Add account to database"""
    return db.add_account(account)

def update_account(account_id: str, updates: dict) -> bool:
    """Update account in database"""
    return db.update_account(account_id, updates)

def delete_account(account_id: str) -> bool:
    """Delete account from database"""
    return db.delete_account(account_id)

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Global dictionary to track campaign stop flags
campaign_stop_flags = {}

# Global dictionary to store active registration sessions (phone -> TelegramClient)
registration_sessions = {}

# Initialize managers
rate_limiter = RateLimiter()
proxy_manager = ProxyManager()


# ============================================================================
# CAMPAIGN RUNNER
# ============================================================================

async def send_message_to_user(account, user, message_text, media_path=None, media_type=None, campaign_proxies=None):
    """Send message to user via Telegram with optional media

    Args:
        account: Account dictionary
        user: User dictionary
        message_text: Message text
        media_path: Optional media file path
        media_type: Optional media type
        campaign_proxies: Optional list of proxy IDs from campaign settings (takes priority over account proxy)

    Returns: (success: bool, error_msg: str)
    """
    phone = account.get('phone')
    session_file = Path(__file__).parent / 'sessions' / f'{phone.replace("+", "")}.session'

    if not session_file.exists():
        return False, f'Session file not found: {session_file}'

    # Get proxy - priority: campaign_proxies > account proxy
    proxy = None
    proxy_id = None
    
    # First, try campaign proxies (round-robin)
    if campaign_proxies and len(campaign_proxies) > 0:
        # Use round-robin: select proxy based on account phone hash
        import hashlib
        account_hash = int(hashlib.md5(phone.encode()).hexdigest(), 16)
        proxy_id = campaign_proxies[account_hash % len(campaign_proxies)]
        proxy_data = proxy_manager.get_proxy(proxy_id)
        if proxy_data:
            import socks
            proxy_type_map = {
                'socks5': socks.SOCKS5,
                'http': socks.HTTP
            }
            proxy = (
                proxy_type_map.get(proxy_data['type'], socks.SOCKS5),
                proxy_data['host'],
                proxy_data['port'],
                True,  # rdns
                proxy_data.get('username'),
                proxy_data.get('password')
            )
            print(f"DEBUG: Using campaign proxy {proxy_id} for account {phone}")
    
    # Fallback to account proxy if no campaign proxy
    if not proxy and account.get('use_proxy') and account.get('proxy'):
        proxy_id = account['proxy']
        proxy_data = proxy_manager.get_proxy(proxy_id)
        if proxy_data:
            import socks
            proxy_type_map = {
                'socks5': socks.SOCKS5,
                'http': socks.HTTP
            }
            proxy = (
                proxy_type_map.get(proxy_data['type'], socks.SOCKS5),
                proxy_data['host'],
                proxy_data['port'],
                True,  # rdns
                proxy_data.get('username'),
                proxy_data.get('password')
            )
            print(f"DEBUG: Using account proxy {proxy_id} for account {phone}")

    client = TelegramClient(
        str(session_file),
        config.API_ID,
        config.API_HASH,
        proxy=proxy
    )

    try:
        await client.connect()

        if not await client.is_user_authorized():
            await client.disconnect()
            # Mark account as unauthorized so it's not used in future campaigns
            account_id = account.get('id')
            if account_id:
                update_account(account_id, {
                    'status': 'unauthorized',
                    'last_used_at': datetime.now().isoformat()
                })
                print(f"⚠ Account {account.get('phone')} ({account_id}) marked as unauthorized")
            return False, 'Account not authorized - session expired or invalid'

        # Find user by ID only (from XLS table)
        target = None
        
        if not user.get('user_id'):
            await client.disconnect()
            return False, 'User ID is required'
        
        try:
            # Convert user_id to int (can be string from DB)
            user_id_str = str(user['user_id']).strip()
            if not user_id_str:
                await client.disconnect()
                return False, 'User ID is empty'
            
            user_id_value = int(user_id_str)
            print(f"DEBUG: Attempting to find user by ID: {user_id_value} (original: {user.get('user_id')})")
            
            # Try to get entity by ID - this works if user is in contacts or was contacted before
            try:
                target = await client.get_entity(user_id_value)
                print(f"DEBUG: ✓ Found user by ID using get_entity: {user_id_value}")
            except (ValueError, TypeError) as ve:
                # If get_entity fails with ValueError (user not found), try other methods
                print(f"DEBUG: get_entity failed for ID {user_id_value}: {ve}, trying alternative methods...")
                try:
                    from telethon.tl.types import InputPeerUser
                    from telethon.tl.functions.users import GetUsersRequest
                    
                    # Try to get user info to get access_hash
                    users_result = await client(GetUsersRequest([user_id_value]))
                    if users_result and len(users_result) > 0:
                        user_obj = users_result[0]
                        target = InputPeerUser(user_id=user_obj.id, access_hash=user_obj.access_hash)
                        print(f"DEBUG: ✓ Found user by ID using GetUsersRequest: {user_id_value}")
                    else:
                        # Can't get access_hash
                        print(f"DEBUG: GetUsersRequest returned empty for ID {user_id_value}")
                        await client.disconnect()
                        return False, f'User not found by ID: {user_id_value}'
                except Exception as e2:
                    print(f"DEBUG: GetUsersRequest failed for ID {user_id_value}: {e2}")
                    await client.disconnect()
                    return False, f'User not found by ID: {user_id_value} ({str(e2)})'
        except (ValueError, TypeError) as e:
            await client.disconnect()
            return False, f'Invalid user_id format: {user.get("user_id")} - {str(e)}'
            except Exception as e:
            await client.disconnect()
            return False, f'Failed to process user_id {user.get("user_id")}: {str(e)}'

        if not target:
            await client.disconnect()
            return False, f'User not found by ID: {user.get("user_id")}'

        # Send message with or without media, using HTML parsing
        try:
        if media_path and media_type:
            media_file = Path(media_path)
            if media_file.exists():
                print(f"DEBUG: Sending media file: {media_path} (exists: {media_file.exists()}, size: {media_file.stat().st_size} bytes)")
                # Send with media - use file path directly
                if media_type == 'photo':
                    await client.send_file(target, media_file, caption=message_text if message_text else None, parse_mode='html' if message_text else None)
                elif media_type == 'video':
                    await client.send_file(target, media_file, caption=message_text if message_text else None, parse_mode='html' if message_text else None)
                elif media_type == 'audio':
                    await client.send_file(target, media_file, caption=message_text if message_text else None, parse_mode='html' if message_text else None)
            else:
                print(f"DEBUG: Media file not found: {media_path}")
                # File doesn't exist, send text only
                await client.send_message(target, message_text, parse_mode='html')
        else:
            # Send text only with HTML formatting
            await client.send_message(target, message_text, parse_mode='html')
            
        await client.disconnect()
        return True, None
        except ValueError as ve:
            # Handle "Could not find the input entity" error
            error_str = str(ve)
            if "Could not find the input entity" in error_str or "PeerUser" in error_str:
                await client.disconnect()
                return False, f'Could not find the input entity for user ID: {user.get("user_id")}. User may not be accessible or may have blocked the account.'
            else:
                # Other ValueError, re-raise
                await client.disconnect()
                raise

    except FloodWaitError as e:
        await client.disconnect()
        return False, f'FloodWait: {e.seconds} seconds'
    except UserPrivacyRestrictedError:
        await client.disconnect()
        return False, 'User privacy settings prevent messaging'
    except PeerFloodError:
        await client.disconnect()
        return False, 'Peer flood - account limited'
    except Exception as e:
        await client.disconnect()
        return False, str(e)


def run_campaign_task(campaign_id):
    """Run campaign in background thread"""
    try:
        # Initialize stop flag for this campaign
        campaign_stop_flags[campaign_id] = False
        
        campaign = db.get_campaign(campaign_id)
        if not campaign:
            return

        settings = campaign.get('settings', {})
        message = settings.get('message', '')
        media_path = settings.get('media_path')
        media_type = settings.get('media_type')
        account_phones = settings.get('accounts', [])
        campaign_proxies = settings.get('proxies', [])  # Get proxy IDs from campaign settings

        # Normalize phone numbers for comparison (remove +, spaces, etc.)
        def normalize_phone(phone):
            if not phone:
                return ''
            return str(phone).replace('+', '').replace(' ', '').replace('-', '').strip()

        normalized_saved_phones = [normalize_phone(p) for p in account_phones]
        
        # Get accounts (exclude limited and unauthorized accounts, but check if they can be restored)
        # Don't reload from file - use in-memory state which is always up-to-date
        all_accounts = get_all_accounts()
        print(f"DEBUG Campaign {campaign_id}: Found {len(all_accounts)} total accounts in memory")
        accounts = []
        for acc in all_accounts:
            acc_phone = normalize_phone(acc.get('phone'))
            
            # Skip unauthorized accounts (session expired)
            if acc.get('status') == 'unauthorized':
                db.add_campaign_log(
                    campaign_id,
                    f'Account {acc_phone} is unauthorized (session expired), skipping',
                    level='warning'
                )
                continue
            
            # Check if limited account can be restored (after 24 hours)
            if acc.get('status') == 'limited':
                last_used = acc.get('last_used_at')
                if last_used:
                    try:
                        last_used_time = datetime.fromisoformat(last_used)
                        hours_since_limit = (datetime.now() - last_used_time).total_seconds() / 3600
                        # Restore account after 24 hours
                        if hours_since_limit >= 24:
                            db.add_campaign_log(
                                campaign_id,
                                f'Account {acc_phone} limited status cleared after {hours_since_limit:.1f} hours, restoring to active',
                                level='info'
                            )
                            update_account(acc.get('id'), {
                                'status': 'active',
                                'last_used_at': datetime.now().isoformat()
                            })
                            acc['status'] = 'active'  # Update local copy
                        else:
                            # Still limited, skip
                            continue
                    except:
                        # If can't parse date, skip limited account
                        continue
                else:
                    # No last_used_at, skip limited account
                    continue
            
            if acc_phone and acc_phone in normalized_saved_phones:
                accounts.append(acc)

        # Debug logging
        db.add_campaign_log(
            campaign_id, 
            f'Looking for accounts: {account_phones} (normalized: {normalized_saved_phones})', 
            level='info'
        )
        db.add_campaign_log(
            campaign_id, 
            f'Found {len(accounts)} accounts out of {len(all_accounts)} total', 
            level='info'
        )

        # Get users from campaign_users table (new system)
        campaign_users = db.get_campaign_users(campaign_id)
        # Filter only pending users
        users = [cu for cu in campaign_users if cu.get('status', 'pending') == 'pending']

        if not accounts:
            db.add_campaign_log(
                campaign_id, 
                f'No accounts available. Saved phones: {account_phones}, Available accounts: {[a.get("phone") for a in all_accounts]}', 
                level='error'
            )
            db.update_campaign(campaign_id, status='failed')
            return

        if not users:
            db.add_campaign_log(campaign_id, 'No users to contact', level='error')
            db.update_campaign(campaign_id, status='failed')
            return

        db.add_campaign_log(campaign_id, f'Starting campaign: {len(accounts)} accounts, {len(users)} users', level='info')

        sent_count = 0
        failed_count = 0

        # Simple round-robin sending
        account_idx = 0
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        for user in users:
            # Check if campaign should be stopped
            if campaign_stop_flags.get(campaign_id, False):
                db.add_campaign_log(campaign_id, 'Campaign stopped by user', level='warning')
                db.update_campaign(campaign_id, status='stopped')
                return
            
            account = accounts[account_idx % len(accounts)]
            account_phone = account.get('phone', 'unknown')

            # Get user identifier with priority: ID -> Username -> Phone
            # Ensure user_id is properly formatted (can be string or int from DB)
            user_id_value = user.get('user_id')
            if user_id_value:
                # Convert to string for display, but keep original for sending
                try:
                    user_id_value = int(user_id_value) if str(user_id_value).isdigit() else user_id_value
                except:
                    pass
            
            user_identifier = user_id_value or user.get('username') or user.get('phone') or 'unknown'
            identifier_type = 'ID' if user_id_value else ('Username' if user.get('username') else 'Phone')
            
            # Debug: log what we're trying to send
            print(f"DEBUG Campaign {campaign_id}: Sending to user - ID: {user_id_value}, Username: {user.get('username')}, Phone: {user.get('phone')}")

            # Check rate limit
            if not rate_limiter.can_send(account_phone):
                db.add_campaign_log(
                    campaign_id,
                    f'Rate limit exceeded for {account_phone}',
                    level='warning'
                )
                account_idx += 1
                continue

            # Send message via Telegram
            try:
                success, error_msg = loop.run_until_complete(
                    send_message_to_user(account, user, message, media_path, media_type, campaign_proxies)
                )

                if success:
                    sent_count += 1
                    rate_limiter.record_sent(account_phone)

                    db.add_campaign_log(
                        campaign_id,
                        f'✓ Sent to {user_identifier} ({identifier_type}) from {account_phone}',
                        level='success'
                    )

                    # Add delay between messages to avoid rate limits
                    # Random delay between 30-90 seconds to appear more natural
                    import random
                    delay = random.randint(30, 90)
                    db.add_campaign_log(
                        campaign_id,
                        f'Waiting {delay} seconds before next message to avoid rate limits...',
                        level='info'
                    )
                    # Check for stop flag during delay (check every 5 seconds)
                    for _ in range(delay // 5):
                        if campaign_stop_flags.get(campaign_id, False):
                            db.add_campaign_log(campaign_id, 'Campaign stopped by user during delay', level='warning')
                            db.update_campaign(campaign_id, status='stopped')
                            return
                        time.sleep(5)
                    # Sleep remaining time
                    remaining = delay % 5
                    if remaining > 0:
                        time.sleep(remaining)

                    # Save conversation to database
                    try:
                        # Get IP address (proxy or current)
                        ip_address = account.get('proxy_host') if account.get('use_proxy') else 'current'
                        
                        # Create or get conversation
                        conv_id = db.create_conversation(
                            campaign_id=campaign_id,
                            sender_account_id=account.get('id'),
                            recipient_user_id=str(user.get('user_id', user_identifier)),
                            recipient_username=user.get('username'),
                            ip_address=ip_address
                        )
                        
                        # Add outgoing message
                        if conv_id:
                            db.add_message(conv_id, 'outgoing', message)
                    except Exception as conv_error:
                        print(f"Warning: Could not save conversation: {conv_error}")

                    # Update campaign user status in database
                    if user.get('id'):  # id is the campaign_users table record ID
                        db.update_campaign_user_status(
                            user_id=user['id'],  # campaign_users.id
                            campaign_id=campaign_id,
                            status='contacted',
                            contacted_by=account_phone
                        )

                    # Update account stats
                    daily_sent = int(account.get('daily_sent', 0)) + 1
                    total_sent = int(account.get('total_sent', 0)) + 1
                    update_account(account.get('id'), {
                        'daily_sent': daily_sent,
                        'total_sent': total_sent,
                        'last_used_at': datetime.now().isoformat()
                    })
                else:
                    failed_count += 1
                    db.add_campaign_log(
                        campaign_id,
                        f'✗ Failed to send to {user_identifier} ({identifier_type}) from {account_phone}: {error_msg}',
                        level='error'
                    )

                    # Handle flood wait
                    if 'FloodWait' in str(error_msg):
                        db.add_campaign_log(
                            campaign_id,
                            f'Account {account_phone} hit flood wait, switching to next account',
                            level='warning'
                        )
                        # Move to next account
                        account_idx += 1
                        # Skip this user and continue with next
                        continue
                    
                    # Handle peer flood (account limited by Telegram)
                    elif 'Peer flood' in str(error_msg) or 'account limited' in str(error_msg).lower():
                        db.add_campaign_log(
                            campaign_id,
                            f'Account {account_phone} limited by Telegram (Peer flood), switching to next account',
                            level='warning'
                        )
                        # Mark account as limited and move to next account
                        update_account(account.get('id'), {
                            'status': 'limited',
                            'last_used_at': datetime.now().isoformat()
                        })
                        # Move to next account
                        account_idx += 1
                        # Skip this user and continue with next
                        continue
                    
                    # Handle peer flood (account limited)
                    elif 'Peer flood' in str(error_msg) or 'account limited' in str(error_msg).lower():
                        db.add_campaign_log(
                            campaign_id,
                            f'Account {account_phone} limited by Telegram (Peer flood), switching to next account',
                            level='warning'
                        )
                        # Mark account as limited and move to next account
                        update_account(account.get('id'), {
                            'status': 'limited',
                            'last_used_at': datetime.now().isoformat()
                        })
                        # Move to next account
                        account_idx += 1
                        # Skip this user and continue with next
                        continue

            except Exception as e:
                failed_count += 1
                db.add_campaign_log(
                    campaign_id,
                    f'Exception sending to {user_identifier} ({identifier_type}): {str(e)}',
                    level='error'
                )

            # Update progress
            db.update_campaign(
                campaign_id,
                sent_count=sent_count,
                failed_count=failed_count
            )

            # Delay between messages
            time.sleep(2)

            account_idx += 1

        loop.close()

        # Check if stopped before marking as completed
        if campaign_stop_flags.get(campaign_id, False):
            db.add_campaign_log(campaign_id, f'Campaign stopped: {sent_count} sent, {failed_count} failed', level='warning')
            db.update_campaign(campaign_id, status='stopped')
        else:
        # Mark as completed
        db.update_campaign(campaign_id, status='completed')
        db.add_campaign_log(campaign_id, f'Campaign completed: {sent_count} sent, {failed_count} failed', level='info')
    except Exception as e:
        db.add_campaign_log(campaign_id, f'Campaign error: {str(e)}', level='error')
        db.update_campaign(campaign_id, status='failed')
    finally:
        # Clean up stop flag
        campaign_stop_flags.pop(campaign_id, None)


# ============================================================================
# AUTH DECORATORS
# ============================================================================

def login_required(f):
    """Require login for route"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# AUTH ROUTES
# ============================================================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Register new user"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        confirm = request.form.get('confirm_password')

        if not email or not password:
            flash('Email and password are required', 'danger')
            return render_template('register.html')

        if password != confirm:
            flash('Passwords do not match', 'danger')
            return render_template('register.html')

        user_id = db.create_user(email, password)

        if user_id:
            flash('Account created! Please login.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Email already exists', 'danger')

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login user"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = db.verify_user(email, password)

        if user:
            session['user_id'] = user['id']
            session['email'] = user['email']
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    return redirect(url_for('login'))


# ============================================================================
# MAIN ROUTES
# ============================================================================

@app.route('/')
@login_required
def dashboard():
    """Main dashboard"""
    user_id = session['user_id']

    # Get accounts
    accounts = get_all_accounts()

    # Get users for outreach from database
    users = db.get_all_campaign_users()

    # Get recent campaigns
    campaigns = db.get_user_campaigns(user_id, limit=10)

    # Stats
    stats = {
        'accounts': len(accounts),
        'active_accounts': len([a for a in accounts if a.get('status') == 'active']),
        'users': len(users),
        'pending_users': len([u for u in users if u.get('status') == 'pending']),
        'total_campaigns': len(campaigns),
        'running_campaigns': len([c for c in campaigns if c['status'] == 'running'])
    }

    return render_template('dashboard.html',
                         stats=stats,
                         accounts=accounts,
                         users=users[:10],
                         campaigns=campaigns)


# ============================================================================
# CAMPAIGN ROUTES
# ============================================================================

@app.route('/campaigns')
@login_required
def campaigns():
    """List all campaigns"""
    user_id = session['user_id']
    campaigns_list = db.get_user_campaigns(user_id, limit=100)

    return render_template('campaigns.html', campaigns=campaigns_list)


@app.route('/campaigns/new', methods=['GET', 'POST'])
@login_required
def new_campaign():
    """Create new campaign"""
    if request.method == 'POST':
        name = request.form.get('name')
        message = request.form.get('message', '').strip()

        # Handle media upload
        media_path = None
        media_type = None
        if 'media' in request.files:
            media_file = request.files['media']
            if media_file and media_file.filename:
                # Create uploads directory
                upload_dir = Path(__file__).parent / 'uploads' / 'campaigns'
                upload_dir.mkdir(parents=True, exist_ok=True)
                
                # Save file with unique name
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{timestamp}_{media_file.filename}"
                media_path = str(upload_dir / filename)
                media_file.save(media_path)
                
                print(f"DEBUG Campaign: Saved media to {media_path}, size: {Path(media_path).stat().st_size} bytes")
                
                # Determine media type
                ext = media_file.filename.lower().rsplit('.', 1)[-1]
                if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                    media_type = 'photo'
                elif ext in ['mp4', 'avi', 'mov', 'mkv']:
                    media_type = 'video'
                elif ext in ['mp3', 'ogg', 'wav', 'm4a']:
                    media_type = 'audio'
                
                print(f"DEBUG Campaign: media_type={media_type}")
        
        # Validate: at least text or media must be provided
        if not message and not media_path:
            flash('Please provide either a message or media file', 'warning')
            # Get accounts and users for form
            accounts = get_all_accounts()
            users = db.get_all_campaign_users()
            return render_template('new_campaign.html', accounts=accounts, users=users)

        # Get selected accounts (form sends phone numbers, not IDs)
        account_phones = request.form.getlist('accounts')
        print(f"DEBUG: Selected account phones from form: {account_phones}")
        
        # Validate that phones exist in available accounts
        all_accounts = get_all_accounts()
        print(f"DEBUG: Total accounts available: {len(all_accounts)}")
        valid_account_phones = []
        for phone in account_phones:
            # Check if phone exists in any account
            account = next((acc for acc in all_accounts if acc.get('phone') == phone), None)
            if account:
                valid_account_phones.append(phone)
                print(f"DEBUG: Valid account phone: {phone}")
            else:
                print(f"DEBUG: Account with phone {phone} not found!")
        
        account_phones = valid_account_phones
        print(f"DEBUG: Final account phones to save: {account_phones}")
        
        # Get campaign users from JSON (sent by JavaScript)
        campaign_users_json = request.form.get('campaign_users_data', '[]')
        try:
            campaign_users = json.loads(campaign_users_json)
        except:
            campaign_users = []

        settings = {
            'message': message if message else None,
            'media_path': media_path,
            'media_type': media_type,
            'accounts': account_phones  # Store phones, not IDs
        }
        
        print(f"DEBUG Campaign settings: message={bool(message)}, media_path={media_path}, media_type={media_type}")
        print(f"DEBUG Campaign users count: {len(campaign_users)}")
        print(f"DEBUG Campaign accounts count: {len(account_phones)}")

        campaign_id = db.create_campaign(
            user_id=session['user_id'],
            name=name,
            total_users=len(campaign_users),
            settings=settings
        )
        
        # Add campaign users to database
        if campaign_users:
            db.bulk_add_campaign_users(campaign_id, campaign_users)
            print(f"DEBUG: Added {len(campaign_users)} users to campaign {campaign_id}")

        # Assign campaign_id to selected accounts and update their IDs
        for phone in account_phones:
            # Find account by phone
            account = next((acc for acc in all_accounts if acc.get('phone') == phone), None)
            if account:
                account_id = account.get('id')
                    # Generate new ID: acc_{phone}_{campaign_id}
                    phone_clean = phone.replace('+', '').replace(' ', '').replace('-', '')
                    new_account_id = f"acc_{phone_clean}_{campaign_id}"
                    
                    # Update account with new ID and campaign_id
                update_account(account_id, {
                        'new_id': new_account_id,
                        'campaign_id': campaign_id
                    })
        flash('Campaign created! Starting...', 'success')
        return redirect(url_for('campaign_detail', campaign_id=campaign_id))

    # Get accounts and users for form
    accounts = get_all_accounts()
    users = db.get_all_campaign_users()
    proxies = proxy_manager.get_all_proxies()

    # Debug: log all accounts being sent to template
    print(f"DEBUG new_campaign: Found {len(accounts)} accounts to display")
    for i, acc in enumerate(accounts):
        print(f"DEBUG new_campaign: Account {i+1}: id={acc.get('id')}, phone={acc.get('phone')}, status={acc.get('status')}")
    
    # Filter out limited and unauthorized accounts for campaign selection
    # But keep all accounts for display (user can see which ones are not available)
    available_accounts = [acc for acc in accounts if acc.get('status') not in ['limited', 'unauthorized']]
    print(f"DEBUG new_campaign: {len(available_accounts)} accounts available (excluding limited/unauthorized)")
    
    # Pass both all accounts and available accounts to template
    return render_template('new_campaign.html', accounts=accounts, available_accounts=available_accounts, users=users, proxies=proxies)


@app.route('/campaigns/<int:campaign_id>')
@login_required
def campaign_detail(campaign_id):
    """View campaign details"""
    campaign = db.get_campaign(campaign_id)

    if not campaign:
        flash('Campaign not found', 'danger')
        return redirect(url_for('campaigns'))

    # Get logs
    logs = db.get_campaign_logs(campaign_id, limit=100)
    
    # Get conversations
    conversations = db.get_campaign_conversations(campaign_id)

    return render_template('campaign_detail.html', campaign=campaign, logs=logs, conversations=conversations)


@app.route('/campaigns/<int:campaign_id>/start', methods=['POST'])
@login_required
def start_campaign(campaign_id):
    """Start campaign (async)"""
    campaign = db.get_campaign(campaign_id)

    if not campaign:
        return jsonify({'error': 'Campaign not found'}), 404

    # Reset stop flag
    campaign_stop_flags[campaign_id] = False

    # Update status
    db.update_campaign(campaign_id, status='running')
    db.add_campaign_log(campaign_id, 'Campaign started', level='info')

    # Start campaign in background thread
    thread = threading.Thread(target=run_campaign_task, args=(campaign_id,), daemon=True)
    thread.start()

    return jsonify({'success': True, 'message': 'Campaign started'})


@app.route('/campaigns/<int:campaign_id>/stop', methods=['POST'])
@login_required
def stop_campaign(campaign_id):
    """Stop running campaign"""
    campaign = db.get_campaign(campaign_id)

    if not campaign:
        return jsonify({'error': 'Campaign not found'}), 404

    if campaign['status'] != 'running':
        return jsonify({'error': 'Campaign is not running'}), 400

    # Set stop flag
    campaign_stop_flags[campaign_id] = True
    db.add_campaign_log(campaign_id, 'Stop request received', level='warning')

    return jsonify({'success': True, 'message': 'Campaign stop requested'})


@app.route('/campaigns/<int:campaign_id>/progress')
@login_required
def campaign_progress(campaign_id):
    """Get campaign progress (for AJAX polling)"""
    campaign = db.get_campaign(campaign_id)

    if not campaign:
        return jsonify({'error': 'Campaign not found'}), 404

    progress = {
        'status': campaign['status'],
        'total': campaign['total_users'],
        'sent': campaign['sent_count'],
        'failed': campaign['failed_count'],
        'percent': int((campaign['sent_count'] / campaign['total_users']) * 100) if campaign['total_users'] > 0 else 0
    }

    return jsonify(progress)


@app.route('/campaigns/<int:campaign_id>/delete', methods=['POST'])
@login_required
def delete_campaign(campaign_id):
    """Delete a campaign"""
    try:
        campaign = db.get_campaign(campaign_id)
        
        if not campaign:
            flash('Campaign not found', 'danger')
            return redirect(url_for('campaigns'))
        
        # Check if user owns this campaign
        if campaign['user_id'] != session['user_id']:
            flash('Unauthorized', 'danger')
            return redirect(url_for('campaigns'))
        
        # Delete campaign from database
        success = db.delete_campaign(campaign_id)
        
        if success:
            flash(f'Campaign "{campaign["name"]}" deleted successfully', 'success')
        else:
            flash('Error deleting campaign', 'danger')
    
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        import traceback
        traceback.print_exc()
    
    return redirect(url_for('campaigns'))


# ============================================================================
# CONVERSATION ROUTES
# ============================================================================

@app.route('/conversations/<int:conversation_id>')
@login_required
def view_conversation(conversation_id):
    """View conversation history and send new messages"""
    conversation = db.get_conversation(conversation_id)
    
    if not conversation:
        flash('Conversation not found', 'danger')
        return redirect(url_for('campaigns'))
    
    # Get messages
    messages = db.get_conversation_messages(conversation_id)
    
    # Get campaign info
    campaign = db.get_campaign(conversation['campaign_id'])
    
    return render_template('conversation.html', 
                         conversation=conversation, 
                         messages=messages,
                         campaign=campaign)


def find_account_by_id_or_phone(account_id: str):
    """
    Find account by ID, or if not found, try to find by phone extracted from ID.
    This handles cases where account ID was changed (e.g., acc_{phone}_{campaign_id})
    """
    # First try to find by exact ID
    account = get_account(account_id)
    if account:
        return account
    
    # If not found, try to extract phone from ID format: acc_{phone}_{campaign_id}
    # or find among all accounts by matching phone
        all_accounts = get_all_accounts()
    
    # Try to extract phone from ID if it follows the pattern acc_{phone}_{campaign_id}
    if account_id.startswith('acc_'):
        parts = account_id.split('_')
        if len(parts) >= 2:
            # Phone might be in parts[1] (for format acc_phone_campaign)
            # Or we need to find account with phone that matches part of the ID
            for acc in all_accounts:
                acc_phone = acc.get('phone', '')
                if acc_phone:
                    # Normalize phone for comparison
                    phone_clean = acc_phone.replace('+', '').replace(' ', '').replace('-', '')
                    # Check if phone is in the account_id
                    if phone_clean in account_id.replace('+', '').replace(' ', '').replace('-', ''):
                        return acc
    
    # Last resort: try to find by matching any part of ID
    for acc in all_accounts:
        if acc.get('id') == account_id:
            return acc
    
    return None


@app.route('/conversations/<int:conversation_id>/send', methods=['POST'])
@login_required
def send_conversation_message(conversation_id):
    """Send a new message in the conversation with optional media"""
    conversation = db.get_conversation(conversation_id)
    
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404
    
    message_text = request.form.get('message', '').strip()
    
    # Handle media upload
    media_path = None
    media_type = None
    if 'media' in request.files:
        media_file = request.files['media']
        if media_file and media_file.filename:
            # Create uploads directory
            upload_dir = Path(__file__).parent / 'uploads' / 'conversations'
            upload_dir.mkdir(parents=True, exist_ok=True)
            
            # Save file with unique name
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{media_file.filename}"
            media_path = str(upload_dir / filename)
            media_file.save(media_path)
            
            # Determine media type
            ext = media_file.filename.lower().rsplit('.', 1)[-1]
            if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                media_type = 'photo'
            elif ext in ['mp4', 'avi', 'mov', 'mkv']:
                media_type = 'video'
            elif ext in ['mp3', 'ogg', 'wav', 'm4a']:
                media_type = 'audio'
    
    # Validate: at least text or media must be provided
    if not message_text and not media_path:
        flash('Please provide either a message or media file', 'warning')
        return redirect(url_for('view_conversation', conversation_id=conversation_id))
    
    # Get account (try to find even if ID changed)
    account = find_account_by_id_or_phone(conversation['sender_account_id'])
    if not account:
        flash('Sender account not found', 'danger')
        return redirect(url_for('view_conversation', conversation_id=conversation_id))
    
    # Send message via Telegram
    try:
        import asyncio
        
        phone = account.get('phone')
        session_file = Path(__file__).parent / 'sessions' / f'{phone.replace("+", "")}.session'
        
        if not session_file.exists():
            flash('Session file not found', 'danger')
            return redirect(url_for('view_conversation', conversation_id=conversation_id))
        
        # Create user object
        user_id = int(conversation['recipient_user_id'])
        
        async def send_msg():
            """Send message via Telegram with media and HTML formatting"""
            client = TelegramClient(
                str(session_file.with_suffix('')),
                config.API_ID,
                config.API_HASH
            )
            
            try:
                await client.connect()
                
                if not await client.is_user_authorized():
                    return False, 'Account not authorized'
                
                # Send message with or without media, using HTML parsing
                if media_path and media_type:
                    media_file_path = Path(media_path)
                    if media_file_path.exists():
                        print(f"DEBUG: Sending conversation media: {media_path} (size: {media_file_path.stat().st_size} bytes)")
                        # Send with media
                        if media_type == 'photo':
                            await client.send_file(user_id, media_file_path, caption=message_text if message_text else None, parse_mode='html' if message_text else None)
                        elif media_type == 'video':
                            await client.send_file(user_id, media_file_path, caption=message_text if message_text else None, parse_mode='html' if message_text else None)
                        elif media_type == 'audio':
                            await client.send_file(user_id, media_file_path, caption=message_text if message_text else None, parse_mode='html' if message_text else None)
                    else:
                        print(f"DEBUG: Conversation media file not found: {media_path}")
                        # Send text only if file doesn't exist
                        await client.send_message(user_id, message_text, parse_mode='html')
                else:
                    # Send text only with HTML formatting
                    await client.send_message(user_id, message_text, parse_mode='html')
                
                return True, None
            except Exception as e:
                return False, str(e)
            finally:
                try:
                    await client.disconnect()
                except:
                    pass
        
        # Send message
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success, error = loop.run_until_complete(send_msg())
        loop.close()
        
        if success:
            # Save message to database (use media info if no text)
            msg_to_save = message_text if message_text else f'[Media: {media_type}]' if media_type else 'Message sent'
            db.add_message(conversation_id, 'outgoing', msg_to_save)
            flash('Message sent successfully', 'success')
        else:
            flash(f'Failed to send message: {error}', 'danger')
            
    except Exception as e:
        flash(f'Error sending message: {str(e)}', 'danger')
    
    return redirect(url_for('view_conversation', conversation_id=conversation_id))


@app.route('/conversations/<int:conversation_id>/fetch-messages', methods=['POST'])
@login_required
def fetch_conversation_messages(conversation_id):
    """Fetch incoming messages from conversation"""
    conversation = db.get_conversation(conversation_id)
    
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404
    
    # Get account (try to find even if ID changed)
    account = find_account_by_id_or_phone(conversation['sender_account_id'])
    if not account:
        return jsonify({'error': 'Sender account not found'}), 404
    
    try:
        import asyncio
        from pathlib import Path
        
        phone = account.get('phone')
        session_file = Path(__file__).parent / 'sessions' / f'{phone.replace("+", "")}.session'
        
        if not session_file.exists():
            return jsonify({'error': 'Session file not found'}), 404
        
        user_id = int(conversation['recipient_user_id'])
        
        async def fetch_msgs():
            """Fetch messages from Telegram"""
            client = TelegramClient(
                str(session_file.with_suffix('')),
                config.API_ID,
                config.API_HASH
            )
            
            try:
                await client.connect()
                
                if not await client.is_user_authorized():
                    return [], 'Account not authorized'
                
                # Get conversation history
                messages = []
                async for message in client.iter_messages(user_id, limit=100):
                    messages.append({
                        'id': message.id,  # Telegram message ID for duplicate detection
                        'text': message.text or '',
                        'is_out': message.out,  # True if sent by us, False if received
                        'date': message.date.isoformat() if message.date else None
                    })
                
                return list(reversed(messages)), None
            except Exception as e:
                return [], str(e)
            finally:
                try:
                    await client.disconnect()
                except:
                    pass
        
        # Fetch messages
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        messages, error = loop.run_until_complete(fetch_msgs())
        loop.close()
        
        if error:
            return jsonify({'error': error}), 400
        
        # Get already saved messages to avoid duplicates
        # We'll use a combination of text and date to identify duplicates
        saved_msgs = db.get_conversation_messages(conversation_id)
        # Create set of (text, date) pairs from saved messages
        # Normalize dates to first 19 chars (YYYY-MM-DDTHH:MM:SS) for comparison
        saved_set = set()
        for saved_msg in saved_msgs:
            if saved_msg.get('message_text') and saved_msg.get('sent_at'):
                text = saved_msg['message_text'].strip()
                date = saved_msg['sent_at'][:19]  # First 19 chars: YYYY-MM-DDTHH:MM:SS
                saved_set.add((text, date))
        
        # Save new messages
        new_count = 0
        for msg in messages:
            text = msg.get('text', '').strip()
            if text:  # Only process messages with text
                # Normalize date to first 19 chars for comparison
                msg_date = msg.get('date', '')[:19] if msg.get('date') else None
                msg_key = (text, msg_date)
                
                # Only add if not already in database
                if msg_key not in saved_set:
                    direction = 'outgoing' if msg.get('is_out') else 'incoming'
                    # Pass original message date from Telegram to preserve it
                    db.add_message(conversation_id, direction, text, message_date=msg.get('date'))
                    new_count += 1
                    # Add to saved_set to avoid duplicates in the same batch
                    saved_set.add(msg_key)
        
        return jsonify({'success': True, 'new_messages': new_count, 'total': len(messages)})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/conversations/<int:conversation_id>/delete', methods=['POST'])
@login_required
def delete_conversation(conversation_id):
    """Delete a conversation"""
    conversation = db.get_conversation(conversation_id)
    
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404
    
    campaign_id = conversation['campaign_id']
    
    if db.delete_conversation(conversation_id):
        flash('Conversation deleted successfully', 'success')
    else:
        flash('Failed to delete conversation', 'danger')
    
    return redirect(url_for('campaign_detail', campaign_id=campaign_id))


# ============================================================================
# ACCOUNT ROUTES
# ============================================================================

@app.route('/accounts')
@login_required
def accounts_list():
    """List all accounts"""
    # Don't reload from file here - it overwrites in-memory changes
    # Only load on startup, changes are saved immediately
    accounts = get_all_accounts()

    print(f"DEBUG: Found {len(accounts)} accounts in storage")
    for i, acc in enumerate(accounts):
        acc_id = acc.get('id', 'MISSING')
        acc_phone = acc.get('phone', 'MISSING')
        acc_status = acc.get('status', 'MISSING')
        acc_first_name = acc.get('first_name', 'MISSING')
        print(f"DEBUG: Account {i+1}: id={acc_id}, phone={acc_phone}, status={acc_status}, first_name={acc_first_name}")
        print(f"DEBUG: Account {i+1} full data: {acc}")

    # Don't filter - show all accounts, even if they have missing fields
    # The template handles missing fields with 'or' operators
    filtered_accounts = accounts
    
    print(f"DEBUG: After processing: {len(filtered_accounts)} accounts to display")

    # Add rate limit stats (handle errors gracefully)
    for acc in filtered_accounts:
        try:
            acc_id = acc.get('id', '')
            if acc_id:
                stats = rate_limiter.get_stats(acc_id)
        acc['rate_limits'] = stats
            else:
                acc['rate_limits'] = None
        except Exception as e:
            print(f"Warning: Could not get rate limits for account {acc.get('id')}: {e}")
            acc['rate_limits'] = None

    print(f"DEBUG: Returning {len(filtered_accounts)} accounts to template")
    return render_template('accounts.html', accounts=filtered_accounts)


@app.route('/accounts/delete/<account_id>', methods=['POST'])
@login_required
def delete_account(account_id):
    """Delete account"""
    try:
        success = delete_account(account_id)
        
        if success:
            flash(f'Account {account_id} deleted successfully', 'success')
        else:
            flash(f'Account {account_id} not found', 'warning')
    except Exception as e:
        flash(f'Error deleting account: {str(e)}', 'danger')
    
    return redirect(url_for('accounts_list'))


@app.route('/accounts/<account_id>/profile-photo')
@login_required
def get_account_profile_photo(account_id):
    """Get account profile photo"""
    try:
        account = get_account(account_id)
        if not account:
            # Return 1x1 transparent pixel as placeholder
            from io import BytesIO
            import base64
            transparent = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
            return send_file(BytesIO(transparent), mimetype='image/gif')
        
        # Check if account has photos
        photo_count = account.get('photo_count', 0)
        if photo_count and photo_count > 0:
            # Try to get photo from Telegram
            import asyncio
            from pathlib import Path
            from telethon import TelegramClient
            import config
            
            phone = account.get('phone', '')
            session_file = Path(__file__).parent / 'sessions' / f'{phone.replace("+", "")}.session'
            
            if session_file.exists():
                async def get_photo():
                    client = TelegramClient(
                        str(session_file.with_suffix('')),
                        config.API_ID,
                        config.API_HASH
                    )
                    try:
                        await client.connect()
                        if await client.is_user_authorized():
                            me = await client.get_me()
                            # Download profile photo
                            photo_bytes = await client.download_profile_photo(me, file=bytes)
                            if photo_bytes:
                                return photo_bytes
                        return None
                    except Exception as e:
                        print(f"Error getting profile photo: {e}")
                        return None
                    finally:
                        try:
                            await client.disconnect()
                        except:
                            pass
                
                photo_data = asyncio.run(get_photo())
                if photo_data:
                    from io import BytesIO
                    return send_file(BytesIO(photo_data), mimetype='image/jpeg')
        
        # Return 1x1 transparent pixel as placeholder
        from io import BytesIO
        import base64
        transparent = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
        return send_file(BytesIO(transparent), mimetype='image/gif')
        
    except Exception as e:
        print(f"Error in get_account_profile_photo: {e}")
        # Return 1x1 transparent pixel as placeholder
        from io import BytesIO
        import base64
        transparent = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
        return send_file(BytesIO(transparent), mimetype='image/gif')


@app.route('/accounts/edit/<account_id>', methods=['GET', 'POST'])
@login_required
def edit_account(account_id):
    """Edit account profile"""
    account = get_account(account_id)
    
    if not account:
        flash('Account not found', 'danger')
        return redirect(url_for('accounts_list'))
    
    if request.method == 'POST':
        try:
            # Import account manager functions
            import asyncio
            from pathlib import Path
            from telethon import TelegramClient
            from account_manager import update_full_profile, get_account_info
            
            # Get form data
            first_name = request.form.get('first_name', '').strip()
            last_name = request.form.get('last_name', '').strip()
            bio = request.form.get('bio', '').strip()
            
            # Handle file uploads
            photos = request.files.getlist('photos')
            photo_paths = []
            
            print(f"DEBUG: Received {len(photos)} photo(s)")
            
            for photo in photos:
                if photo and photo.filename:
                    upload_dir = Path(__file__).parent / 'uploads' / 'profile_photos'
                    upload_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Generate unique filename
                    import time
                    timestamp = int(time.time())
                    filename = f"{account_id}_{timestamp}_{photo.filename}"
                    filepath = upload_dir / filename
                    
                    # Save file
                    photo.save(str(filepath))
                    photo_paths.append(str(filepath))
                    print(f"DEBUG: Saved photo to {filepath}")
            
            # Get session file
            phone = account.get('phone', '')
            session_file = Path(__file__).parent / 'sessions' / f'{phone.replace("+", "")}.session'
            
            if not session_file.exists():
                flash('Session file not found', 'danger')
                return redirect(url_for('accounts_list'))
            
            # Update profile via Telegram API
            async def update_profile():
                client = TelegramClient(
                    str(session_file.with_suffix('')),
                    config.API_ID,
                    config.API_HASH
                )
                
                try:
                    await client.connect()
                    
                    if not await client.is_user_authorized():
                        return False, 'Account not authorized'
                    
                    print(f"DEBUG: Calling update_full_profile with:")
                    print(f"  - first_name: {first_name or None}")
                    print(f"  - last_name: {last_name or None}")
                    print(f"  - bio: {bio or None}")
                    print(f"  - photo_paths: {photo_paths if photo_paths else None}")
                    
                    result = await update_full_profile(
                        client,
                        first_name=first_name or None,
                        last_name=last_name or None,
                        bio=bio or None,
                        photo_paths=photo_paths if photo_paths else None
                    )
                    
                    print(f"DEBUG: update_full_profile returned: {result}")
                    
                    # Get updated info
                    info = await get_account_info(client)
                    
                    print(f"DEBUG: Account info after update: {info}")
                    
                    return True, info
                
                except Exception as e:
                    import traceback
                    print("DEBUG: Exception occurred:")
                    traceback.print_exc()
                    return False, str(e)
                
                finally:
                    try:
                        await client.disconnect()
                    except:
                        pass
            
            # Run update
            success, result = asyncio.run(update_profile())
            
            if success:
                # Update local storage with all updated fields
                update_data = {
                    'first_name': result.get('first_name', ''),
                    'last_name': result.get('last_name', ''),
                }
                
                # Add bio if available
                if 'bio' in result:
                    update_data['bio'] = result['bio']
                elif 'about' in result:
                    update_data['bio'] = result['about']
                
                # Add username if available
                if 'username' in result:
                    update_data['username'] = result.get('username', '')
                
                # Add photo count if available
                if 'photo_count' in result:
                    update_data['photo_count'] = result.get('photo_count', 0)
                
                print(f"DEBUG: Updating account with data: {update_data}")
                update_account(account_id, update_data)
                
                flash('Profile updated successfully!', 'success')
            else:
                flash(f'Error updating profile: {result}', 'danger')
        
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
            import traceback
            traceback.print_exc()
        
        return redirect(url_for('accounts_list'))
    
    # GET request - show form
    return render_template('edit_account.html', account=account)


@app.route('/accounts/add/tdata', methods=['POST'])
@login_required
def add_account_tdata():
    """Add account from TDATA/SESSION/JSON file"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        if not file or not file.filename:
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        notes = request.form.get('notes', '')
        
        # Save uploaded file
        upload_dir = Path(__file__).parent / 'uploads' / 'accounts'
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{file.filename}"
        filepath = upload_dir / filename
        file.save(str(filepath))
        
        # Import converter functions
        from converter import detect_and_process
        from accounts import add_account
        import asyncio
        
        # Process file based on extension
        file_ext = Path(file.filename).suffix.lower()
        
        async def process():
            if file_ext == '.json':
                # JSON credentials - need to create session
                import json
                from telethon import TelegramClient
                
                with open(filepath, 'r') as f:
                    creds = json.load(f)
                
                phone = creds.get('phone')
                api_id = int(creds.get('api_id'))
                api_hash = creds.get('api_hash')
                password = creds.get('password')
                
                sessions_dir = Path(__file__).parent / 'sessions'
                sessions_dir.mkdir(exist_ok=True)
                session_file = sessions_dir / f"{phone.replace('+', '')}.session"
                
                client = TelegramClient(str(session_file.with_suffix('')), api_id, api_hash)
                
                try:
                    await client.connect()
                    if not await client.is_user_authorized():
                        return {'success': False, 'error': 'Session not authorized. Please use manual method with code.'}
                    
                    me = await client.get_me()
                    await client.disconnect()
                    
                    account_data = {
                        'phone': me.phone,
                        'username': me.username or '',
                        'first_name': me.first_name,
                        'last_name': me.last_name or '',
                        'session_file': str(session_file),
                        'status': 'active',
                        'notes': notes or 'Web added from JSON'
                    }
                    
                    add_result = await add_account(account_data)
                    return add_result
                except Exception as e:
                    await client.disconnect()
                    return {'success': False, 'error': str(e)}
            else:
                # TDATA or SESSION file
                result = await detect_and_process(str(filepath), notes or 'Web added account')
                
                if result['success']:
                    account_data = result['account']
                    add_result = await add_account(account_data)
                    return add_result
                else:
                    return {'success': False, 'error': result.get('error', 'Processing failed')}
        
        result = asyncio.run(process())
        
        # Verify account was added (don't reload - in-memory state is correct)
        if result.get('success'):
            accounts_after = get_all_accounts()
            print(f"DEBUG: Accounts after addition: {len(accounts_after)}")
            result['accounts_count'] = len(accounts_after)
        
        # Clean up uploaded file
        try:
            filepath.unlink()
        except:
            pass
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/accounts/add/manual', methods=['POST'])
@login_required
def add_account_manual():
    """Add account manually with phone and API credentials"""
    try:
        phone = request.form.get('phone', '').strip()
        api_id = request.form.get('api_id', '').strip()
        api_hash = request.form.get('api_hash', '').strip()
        password = request.form.get('password', '').strip()
        notes = request.form.get('notes', '').strip()
        
        if not phone or not api_id or not api_hash:
            return jsonify({'success': False, 'error': 'Phone, API ID, and API Hash are required'}), 400
        
        try:
            api_id = int(api_id)
        except ValueError:
            return jsonify({'success': False, 'error': 'API ID must be a number'}), 400
        
        if len(api_hash) != 32:
            return jsonify({'success': False, 'error': 'API Hash must be exactly 32 characters'}), 400
        
        from telethon import TelegramClient
        from accounts import add_account
        import asyncio
        
        async def process():
            # Normalize phone (remove +, spaces, etc.)
            phone_normalized = phone.replace('+', '').replace(' ', '').replace('-', '').strip()
            session_name = phone_normalized
            
            sessions_dir = Path(__file__).parent / 'sessions'
            sessions_dir.mkdir(exist_ok=True)
            session_file = sessions_dir / f"{session_name}.session"
            
            client = TelegramClient(str(session_file.with_suffix('')), api_id, api_hash)
            
            try:
                await client.connect()
                
                if not await client.is_user_authorized():
                    # Send code
                    await client.send_code_request(phone_normalized)
                    return {'success': False, 'error': 'AUTH_CODE_REQUIRED', 'message': 'Please check your phone for the authentication code and submit it via the form'}
                
                me = await client.get_me()
                await client.disconnect()
                
                account_data = {
                    'phone': me.phone,
                    'username': me.username or '',
                    'first_name': me.first_name,
                    'last_name': me.last_name or '',
                    'session_file': str(session_file),
                    'status': 'active',
                    'notes': notes or 'Web added manually'
                }
                
                add_result = await add_account(account_data)
                return add_result
                
            except Exception as e:
                try:
                    await client.disconnect()
                except:
                    pass
                return {'success': False, 'error': str(e)}
        
        result = asyncio.run(process())
        
        # Verify account was added (don't reload - in-memory state is correct)
        if result.get('success'):
            accounts_after = get_all_accounts()
            print(f"DEBUG: Accounts after manual addition: {len(accounts_after)}")
            result['accounts_count'] = len(accounts_after)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/accounts/add/authkey', methods=['POST'])
@login_required
def add_account_authkey():
    """Add account from AUTH KEY and DC ID"""
    try:
        phone = request.form.get('phone', '').strip()
        auth_key_hex = request.form.get('auth_key', '').strip()
        dc_id = request.form.get('dc_id', '').strip()
        user_id = request.form.get('user_id', '').strip()
        notes = request.form.get('notes', '').strip()
        
        if not phone or not auth_key_hex or not dc_id:
            return jsonify({'success': False, 'error': 'Phone, AUTH KEY, and DC ID are required'}), 400
        
        try:
            auth_key = bytes.fromhex(auth_key_hex.replace(' ', ''))
            if len(auth_key) != 256:
                return jsonify({'success': False, 'error': 'AUTH KEY must be 256 bytes (512 hex characters)'}), 400
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid AUTH KEY format (must be hex)'}), 400
        
        try:
            dc_id = int(dc_id)
            if dc_id < 1 or dc_id > 5:
                return jsonify({'success': False, 'error': 'DC ID must be between 1 and 5'}), 400
        except ValueError:
            return jsonify({'success': False, 'error': 'DC ID must be a number'}), 400
        
        from add_account_from_session_data import create_session_file
        from accounts import add_account
        import asyncio
        
        async def process():
            # Normalize phone (remove +, spaces, etc.)
            phone_normalized = phone.replace('+', '').replace(' ', '').replace('-', '').strip()
            session_name = phone_normalized
            
            sessions_dir = Path(__file__).parent / 'sessions'
            sessions_dir.mkdir(exist_ok=True)
            session_file = sessions_dir / f"{session_name}.session"
            
            # Create session file
            await create_session_file(str(session_file.with_suffix('')), auth_key, dc_id)
            
            # Try to get account info
            from telethon import TelegramClient
            import config
            
            client = TelegramClient(str(session_file.with_suffix('')), config.API_ID, config.API_HASH)
            
            try:
                await client.connect()
                
                if await client.is_user_authorized():
                    me = await client.get_me()
                    account_data = {
                        'phone': me.phone,
                        'username': me.username or '',
                        'first_name': me.first_name,
                        'last_name': me.last_name or '',
                        'session_file': str(session_file),
                        'status': 'active',
                        'notes': notes or 'Web added from AUTH KEY'
                    }
                else:
                    # Use provided user_id or phone
                    account_data = {
                        'phone': phone_normalized,
                        'username': '',
                        'first_name': '',
                        'last_name': '',
                        'session_file': str(session_file),
                        'status': 'active',
                        'notes': notes or 'Web added from AUTH KEY'
                    }
                
                await client.disconnect()
                
                add_result = await add_account(account_data)
                return add_result
                
            except Exception as e:
                try:
                    await client.disconnect()
                except:
                    pass
                return {'success': False, 'error': str(e)}
        
        result = asyncio.run(process())
        
        # Verify account was added
        if result.get('success'):
            accounts_after = get_all_accounts()
            print(f"DEBUG: Accounts after authkey addition: {len(accounts_after)}")
            result['accounts_count'] = len(accounts_after)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/accounts/delete-photos/<account_id>', methods=['POST'])
@login_required
def delete_account_photos(account_id):
    """Delete all profile photos from account"""
    try:
        account = get_account(account_id)
        
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        # Import required modules
        import asyncio
        from pathlib import Path
        from telethon import TelegramClient
        from account_manager import delete_all_profile_photos
        
        # Get session file
        phone = account.get('phone', '')
        session_file = Path(__file__).parent / 'sessions' / f'{phone.replace("+", "")}.session'
        
        if not session_file.exists():
            return jsonify({'success': False, 'error': 'Session file not found'})
        
        # Delete photos via Telegram API
        async def delete_photos():
            client = TelegramClient(
                str(session_file.with_suffix('')),
                config.API_ID,
                config.API_HASH
            )
            
            try:
                await client.connect()
                
                if not await client.is_user_authorized():
                    return False, 'Account not authorized'
                
                result = await delete_all_profile_photos(client)
                
                return True, result
            
            except Exception as e:
                import traceback
                traceback.print_exc()
                return False, str(e)
            
            finally:
                try:
                    await client.disconnect()
                except:
                    pass
        
        # Run deletion
        success, result = asyncio.run(delete_photos())
        
        if success:
            return jsonify({'success': True, 'message': 'All photos deleted'})
        else:
            return jsonify({'success': False, 'error': result})
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


# ============================================================================
# USER ROUTES (for outreach)
# ============================================================================

@app.route('/users')
@login_required
def users_list():
    """List all users for outreach"""
    # Get campaign-specific users from database
    campaign_users = db.get_all_campaign_users()
    
    # Get all campaigns for filter dropdown
    user_id = session['user_id']
    campaigns_list = db.get_user_campaigns(user_id, limit=100)
    campaigns = [(c['id'], c['name']) for c in campaigns_list]

    return render_template('users.html', users=campaign_users, campaigns=campaigns)


@app.route('/users/add', methods=['POST'])
@login_required
def add_user():
    """Add user for outreach"""
    username = request.form.get('username', '').strip()
    user_id = request.form.get('user_id', '').strip()
    phone = request.form.get('phone', '').strip()
    priority = request.form.get('priority', '1').strip()

    # Convert user_id to int if provided and valid
    user_id_int = None
    if user_id:
        try:
            user_id_int = int(user_id)
        except ValueError:
            flash('Invalid user ID format', 'danger')
            return redirect(url_for('users_list'))

    # Convert priority to int
    try:
        priority_int = int(priority) if priority else 1
    except ValueError:
        priority_int = 1

    # At least one identifier must be provided
    if not username and not user_id_int and not phone:
        flash('Please provide at least username, user ID, or phone number', 'danger')
        return redirect(url_for('users_list'))

    # For users added without campaign, we need to create a default campaign or use existing
    # For now, we'll add to a default campaign (campaign_id = 0 means "general users")
    # Or we can create a special "General Users" campaign
    user_id = session['user_id']
    
    # Get or create a default campaign for general users
    default_campaign = None
    campaigns = db.get_user_campaigns(user_id)
    for campaign in campaigns:
        if campaign.get('name') == 'General Users':
            default_campaign = campaign
            break
    
    if not default_campaign:
        # Create default campaign
        campaign_id = db.create_campaign(
            user_id=user_id,
            name='General Users',
            total_users=0
        )
    else:
        campaign_id = default_campaign['id']
    
    # Add user to campaign
    db.add_campaign_user(
        campaign_id=campaign_id,
        username=username if username else None,
        user_id=str(user_id_int) if user_id_int else None,
        phone=phone if phone else None,
        priority=priority_int
    )

    flash('User added successfully', 'success')
    return redirect(url_for('users_list'))


@app.route('/users/bulk-delete', methods=['POST'])
@login_required
def bulk_delete_users():
    """Delete multiple users"""
    try:
        data = request.get_json()
        user_ids = data.get('user_ids', [])
        
        if not user_ids:
            return jsonify({'success': False, 'error': 'No users selected'})
        
        # Delete users from all campaigns
        conn = db.get_connection()
        cursor = conn.cursor()
        count = 0
        try:
            for user_id in user_ids:
                cursor.execute('DELETE FROM campaign_users WHERE id = ?', (user_id,))
                if cursor.rowcount > 0:
                    count += 1
            conn.commit()
        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'error': str(e)})
        finally:
            conn.close()
        
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/users/import-csv', methods=['POST'])
@login_required
def import_csv_users():
    """Import users from CSV/Excel file"""
    print("=" * 60)
    print("CSV IMPORT REQUEST RECEIVED")
    print("=" * 60)
    try:
        print(f"Files in request: {list(request.files.keys())}")
        if 'file' not in request.files:
            print("ERROR: No file in request")
            return jsonify({'success': False, 'error': 'No file provided'})

        file = request.files['file']
        print(f"File received: {file.filename}")
        if file.filename == '':
            print("ERROR: Empty filename")
            return jsonify({'success': False, 'error': 'No file selected'})

        # Check file extension
        filename_lower = file.filename.lower()
        print(f"File extension check: {filename_lower}")
        if not (filename_lower.endswith('.csv') or filename_lower.endswith('.xlsx') or filename_lower.endswith('.xls')):
            print(f"ERROR: Invalid extension")
            return jsonify({'success': False, 'error': 'Unsupported file format. Use CSV, XLS, or XLSX.'})

        # Import pandas
        try:
            import pandas as pd
            print(f"✓ Pandas imported successfully (v{pd.__version__})")
        except ImportError as e:
            print(f"ERROR: Failed to import pandas: {e}")
            return jsonify({
                'success': False,
                'error': 'Required libraries not installed. Please install: pip install pandas openpyxl xlrd'
            })

        # Read file based on extension
        print(f"Attempting to read file...")
        try:
            if filename_lower.endswith('.csv'):
                # Try different encodings for CSV
                try:
                    df = pd.read_csv(file, encoding='utf-8')
                    print(f"✓ CSV read with UTF-8 encoding")
                except UnicodeDecodeError:
                    file.seek(0)
                    df = pd.read_csv(file, encoding='latin-1')
                    print(f"✓ CSV read with Latin-1 encoding")
            elif filename_lower.endswith('.xlsx'):
                df = pd.read_excel(file, engine='openpyxl')
                print(f"✓ XLSX read with openpyxl")
            elif filename_lower.endswith('.xls'):
                df = pd.read_excel(file, engine='xlrd')
                print(f"✓ XLS read with xlrd")
            print(f"DataFrame shape: {df.shape} (rows: {len(df)}, columns: {len(df.columns)})")
            print(f"Columns: {list(df.columns)}")
        except Exception as e:
            print(f"ERROR reading file: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'error': f'Failed to read file: {str(e)}'})

        # Validate that file has data
        if df.empty:
            print("ERROR: DataFrame is empty")
            return jsonify({'success': False, 'error': 'File is empty'})

        # Expected columns: username, user_id, phone, priority (all optional)
        print(f"Processing {len(df)} rows...")
        count = 0
        skipped = 0

        for idx, row in df.iterrows():
            user_data = {}

            if 'username' in df.columns and pd.notna(row['username']):
                user_data['username'] = str(row['username']).strip().lstrip('@')

            if 'user_id' in df.columns and pd.notna(row['user_id']):
                try:
                    user_data['user_id'] = int(float(row['user_id']))
                except (ValueError, TypeError):
                    skipped += 1
                    continue

            if 'phone' in df.columns and pd.notna(row['phone']):
                phone_str = str(row['phone']).strip()
                # Handle phone numbers that might be parsed as floats
                if '.' in phone_str:
                    phone_str = phone_str.split('.')[0]
                user_data['phone'] = phone_str

            if 'priority' in df.columns and pd.notna(row['priority']):
                try:
                    user_data['priority'] = int(float(row['priority']))
                except (ValueError, TypeError):
                    user_data['priority'] = 1
            else:
                user_data['priority'] = 1

            # Skip if no identifiers
            if not user_data.get('username') and not user_data.get('user_id') and not user_data.get('phone'):
                skipped += 1
                continue

            # Get or create default campaign for general users
            user_id = session['user_id']
            default_campaign = None
            campaigns = db.get_user_campaigns(user_id)
            for campaign in campaigns:
                if campaign.get('name') == 'General Users':
                    default_campaign = campaign
                    break
            
            if not default_campaign:
                campaign_id = db.create_campaign(
                    user_id=user_id,
                    name='General Users',
                    total_users=0
                )
            else:
                campaign_id = default_campaign['id']
            
            # Add user to campaign
            db.add_campaign_user(
                campaign_id=campaign_id,
                username=user_data.get('username'),
                user_id=str(user_data.get('user_id')) if user_data.get('user_id') else None,
                phone=user_data.get('phone'),
                priority=user_data.get('priority', 1)
            )
            count += 1

        print(f"✓ Import complete: {count} users imported, {skipped} skipped")
        print("=" * 60)

        result = {'success': True, 'count': count}
        if skipped > 0:
            result['skipped'] = skipped

        return jsonify(result)

    except Exception as e:
        print(f"EXCEPTION in import_csv_users: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 60)
        return jsonify({'success': False, 'error': f'Unexpected error: {str(e)}'})


# ============================================================================
# PROXY ROUTES
# ============================================================================

@app.route('/proxies', methods=['GET', 'POST'])
@login_required
def proxies_list():
    """List all proxies and handle testing"""
    if request.method == 'POST':
        action = request.form.get('action')
        proxy_id = request.form.get('proxy_id')

        if action == 'test' and proxy_id:
            # Test proxy
            result = proxy_manager.test_proxy(proxy_id)

            if result:
                flash(f'Proxy {proxy_id} is working!', 'success')
            else:
                proxy = proxy_manager.get_proxy(proxy_id)
                error_msg = proxy.get('error', 'Unknown error') if proxy else 'Proxy not found'
                flash(f'Proxy {proxy_id} failed test: {error_msg}', 'danger')

            return redirect(url_for('proxies_list'))

    proxies = proxy_manager.get_all_proxies()
    return render_template('proxies.html', proxies=proxies)


@app.route('/proxies/add', methods=['POST'])
@login_required
def add_proxy():
    """Add proxy"""
    proxy_id = request.form.get('proxy_id')
    proxy_string = request.form.get('proxy_string')

    try:
        components = proxy_manager.parse_proxy_string(proxy_string)
        proxy_manager.add_proxy(
            proxy_id,
            components['type'],
            components['host'],
            components['port'],
            components.get('username'),
            components.get('password')
        )

        flash('Proxy added successfully', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')

    return redirect(url_for('proxies_list'))


@app.route('/api/campaign/check-proxy-ips', methods=['POST'])
def check_proxy_ips():
    """Check IP addresses through selected proxies"""
    # Check authentication manually to return JSON error instead of HTML redirect
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401
    
    try:
        data = request.get_json()
        proxy_ids = data.get('proxy_ids', [])
        
        if not proxy_ids:
            return jsonify({'success': False, 'error': 'No proxy IDs provided'}), 400
        
        import asyncio
        import aiohttp
        
        async def check_all_proxies():
            results = {}
            
            for proxy_id in proxy_ids:
                proxy = proxy_manager.get_proxy(proxy_id)
                if not proxy:
                    results[proxy_id] = {'ip': None, 'error': 'Proxy not found'}
                    continue
                
                try:
                    # Prepare proxy URL
                    if proxy.get('username') and proxy.get('password'):
                        proxy_url = f"{proxy['type']}://{proxy['username']}:{proxy['password']}@{proxy['host']}:{proxy['port']}"
                    else:
                        proxy_url = f"{proxy['type']}://{proxy['host']}:{proxy['port']}"
                    
                    # Check IP through proxy
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            'https://api.ipify.org?format=json',
                            proxy=proxy_url,
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as response:
                            if response.status == 200:
                                ip_data = await response.json()
                                # Try to get country info
                                try:
                                    async with session.get(
                                        f"https://ipapi.co/{ip_data['ip']}/json/",
                                        proxy=proxy_url,
                                        timeout=aiohttp.ClientTimeout(total=5)
                                    ) as geo_response:
                                        if geo_response.status == 200:
                                            geo_data = await geo_response.json()
                                            results[proxy_id] = {
                                                'ip': ip_data.get('ip'),
                                                'country': geo_data.get('country_name') or geo_data.get('country_code', 'Unknown')
                                            }
                                        else:
                                            results[proxy_id] = {'ip': ip_data.get('ip'), 'country': None}
                                except:
                                    results[proxy_id] = {'ip': ip_data.get('ip'), 'country': None}
                            else:
                                results[proxy_id] = {'ip': None, 'error': f'HTTP {response.status}'}
                except Exception as e:
                    results[proxy_id] = {'ip': None, 'error': str(e)}
            
            return results
        
        ips = asyncio.run(check_all_proxies())
        return jsonify({'success': True, 'ips': ips})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ============================================================================
# API ROUTES
# ============================================================================

@app.route('/api/stats')
@login_required
def api_stats():
    """Get system stats (JSON)"""
    accounts = get_all_accounts()
    users = db.get_all_campaign_users()
    user_id = session['user_id']
    campaigns = db.get_user_campaigns(user_id)

    stats = {
        'accounts': {
            'total': len(accounts),
            'active': len([a for a in accounts if a.get('status') == 'active']),
            'warming': len([a for a in accounts if a.get('status') == 'warming']),
        },
        'users': {
            'total': len(users),
            'pending': len([u for u in users if u.get('status') == 'pending']),
            'contacted': len([u for u in users if u.get('status') == 'contacted']),
        },
        'campaigns': {
            'total': len(campaigns),
            'running': len([c for c in campaigns if c['status'] == 'running']),
            'completed': len([c for c in campaigns if c['status'] == 'completed']),
        }
    }

    return jsonify(stats)


# ============================================================================
# ERROR HANDLERS
# ============================================================================

# ============================================================================
# ACCOUNT REGISTRATION ROUTES
# ============================================================================

@app.route('/create-accounts')
@login_required
def create_accounts():
    """Account registration management page"""
    return render_template('create_accounts.html')


@app.route('/api/registration/accounts')
@login_required
def get_registration_accounts():
    """Get all registration accounts"""
    accounts = db.get_all_registration_accounts()
    
    # Add file existence flags
    for acc in accounts:
        phone_clean = acc['phone'].replace('+', '').replace(' ', '').replace('-', '')
        storage_dir = Path(__file__).parent / 'storage' / phone_clean
        
        acc['has_tdata'] = (storage_dir / 'tdata.zip').exists() if storage_dir.exists() else False
        acc['has_session'] = (storage_dir / 'session.session').exists() if storage_dir.exists() else False
    
    return jsonify(accounts)


@app.route('/api/registration/add-phone', methods=['POST'])
@login_required
def add_registration_phone():
    """Add new phone number for registration"""
    try:
        data = request.get_json()
        phone = data.get('phone', '').strip()
        
        if not phone:
            return jsonify({'success': False, 'error': 'Phone number is required'}), 400
        
        # Validate phone format
        if not phone.startswith('+'):
            return jsonify({'success': False, 'error': 'Phone number must start with +'}), 400
        
        success = db.add_registration_account(phone)
        if success:
            return jsonify({'success': True, 'message': 'Phone added successfully'})
        else:
            return jsonify({'success': False, 'error': 'Phone already exists or failed to add'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/registration/start', methods=['POST'])
@login_required
def start_registration():
    """Start registration - send code to phone"""
    try:
        data = request.get_json()
        phone = data.get('phone', '').strip()
        proxy_id = data.get('proxy_id')  # Optional: specific proxy ID
        device_preset_id = data.get('device_preset_id')  # Optional: specific device preset ID
        country_preference = data.get('country_preference')  # Optional: country preference
        
        if not phone:
            return jsonify({'success': False, 'error': 'Phone number is required'}), 400
        
        account = db.get_registration_account(phone)
        if not account:
            return jsonify({'success': False, 'error': 'Phone not found'}), 404
        
        import asyncio
        from telethon import TelegramClient
        from telethon.errors import PhoneNumberInvalidError, FloodWaitError
        from telethon.tl.types import InputClientProxy
        import config
        import uuid
        
        # Select proxy (round-robin)
        proxy = None
        if proxy_id:
            proxy = db.get_registration_proxy(proxy_id)
        else:
            # Auto-select proxy using round-robin (least recently used)
            proxies = db.get_all_registration_proxies()
            available = [
                p for p in proxies 
                if p.get('status') == 'active'
            ]
            
            if available:
                # Sort by last_used (NULL first, then by datetime) - round-robin
                available.sort(key=lambda x: (
                    x.get('last_used') is None,  # NULL values first
                    x.get('last_used') or ''  # Then by datetime
                ))
                proxy = available[0]
        
        # Select device preset
        device = None
        if device_preset_id:
            presets = db.get_all_device_presets()
            device = next((p for p in presets if p.get('id') == device_preset_id), None)
        else:
            # Auto-select random device
            device = db.get_random_device_preset()
        
        if not device:
            device = {
                'device_model': 'Unknown',
                'system_version': 'Unknown',
                'app_version': '9.4.0',
                'lang_code': 'en',
                'system_lang_code': 'en-US'
            }
        
        async def send_code():
            # Create temporary session for registration
            session_id = str(uuid.uuid4())
            phone_clean = phone.replace('+', '').replace(' ', '').replace('-', '')
            storage_dir = Path(__file__).parent / 'storage' / phone_clean
            storage_dir.mkdir(parents=True, exist_ok=True)
            session_file = storage_dir / f'temp_{session_id}'
            
            # Log: Starting registration
            db.add_registration_log(phone, 'Starting registration process...', 'info', session_id)
            
            # Prepare proxy config if available
            proxy_config = None
            proxy_info = None
            if proxy:
                proxy_info = f"{proxy['host']}:{proxy['port']}"
                db.add_registration_log(phone, f'Selected proxy: {proxy.get("name", "Unknown")} ({proxy_info})', 'info', session_id)
                
                import socks
                if proxy['protocol'] == 'socks5':
                    proxy_config = (
                        socks.SOCKS5,
                        proxy['host'],
                        proxy['port'],
                        True,  # rdns
                        proxy['username'],
                        proxy['password']
                    )
                else:
                    # HTTP/HTTPS proxy
                    proxy_config = (
                        socks.HTTP,
                        proxy['host'],
                        proxy['port'],
                        True,  # rdns
                        proxy['username'],
                        proxy['password']
                    )
            else:
                db.add_registration_log(phone, 'No proxy configured, using direct connection', 'warning', session_id)
            
            # Log: Creating Telegram client
            device_info = f"{device.get('device_model', 'Unknown')} ({device.get('system_version', 'Unknown')})"
            db.add_registration_log(phone, f'Creating Telegram client with device: {device_info}', 'info', session_id)
            
            # Create client with device fingerprint and proxy
            client = TelegramClient(
                str(session_file.with_suffix('')),
                config.API_ID,
                config.API_HASH,
                device_model=device.get('device_model', 'Unknown'),
                system_version=device.get('system_version', 'Unknown'),
                app_version=device.get('app_version', '9.4.0'),
                lang_code=device.get('lang_code', 'en'),
                system_lang_code=device.get('system_lang_code', 'en-US'),
                proxy=proxy_config
            )
            
            try:
                # Log: Connecting to Telegram
                if proxy:
                    db.add_registration_log(phone, f'Connecting to Telegram via proxy {proxy_info}...', 'info', session_id)
                else:
                    db.add_registration_log(phone, 'Connecting to Telegram...', 'info', session_id)
                
                await client.connect()
                
                if proxy:
                    db.add_registration_log(phone, f'✓ Connected via proxy {proxy_info}', 'success', session_id)
                else:
                    db.add_registration_log(phone, '✓ Connected to Telegram', 'success', session_id)
                
                # Check if already authorized
                db.add_registration_log(phone, 'Checking account authorization status...', 'info', session_id)
                if await client.is_user_authorized():
                    await client.disconnect()
                    db.add_registration_log(phone, '✗ Account already registered', 'error', session_id)
                    return {'success': False, 'error': 'Account already registered'}
                
                db.add_registration_log(phone, '✓ Account not registered, proceeding...', 'success', session_id)
                
                # Send code with force_sms=True to ensure SMS delivery (not Telegram app)
                # ВАЖНО: force_sms=True заставляет отправить SMS вместо кода в Telegram приложение
                db.add_registration_log(phone, f'Sending SMS code request to {phone} (force_sms=True)...', 'info', session_id)
                result = await client.send_code_request(phone, force_sms=True)
                phone_code_hash = result.phone_code_hash
                
                db.add_registration_log(phone, '✓ SMS code sent successfully! Please check your phone for the SMS message (not Telegram app).', 'success', session_id)
                
                # Store session info
                registration_sessions[phone] = {
                    'client': client,
                    'session_file': session_file,
                    'phone_code_hash': phone_code_hash,
                    'session_id': session_id
                }
                
                # Update status with proxy and device info
                updates = {
                    'status': 'code_sent',
                    'session_id': session_id
                }
                if proxy:
                    updates['proxy_id'] = proxy['id']
                    # Update proxy last_used timestamp for round-robin
                    from datetime import datetime
                    db.update_registration_proxy(proxy['id'], {
                        'last_used': datetime.now().isoformat()
                    })
                if device:
                    updates['device_model'] = device.get('device_model')
                    updates['system_version'] = device.get('system_version')
                    updates['app_version'] = device.get('app_version')
                    updates['lang_code'] = device.get('lang_code')
                
                db.update_registration_account(phone, updates)
                
                return {
                    'success': True,
                    'session_id': session_id,
                    'message': 'Code sent to phone',
                    'proxy_used': {
                        'id': proxy['id'],
                        'name': proxy['name'],
                        'type': proxy['type']
                    } if proxy else None,
                    'device_used': {
                        'id': device.get('id'),
                        'name': device.get('name'),
                        'model': device.get('device_model'),
                        'system': device.get('system_version')
                    } if device else None
                }
                
            except PhoneNumberInvalidError:
                await client.disconnect()
                db.add_registration_log(phone, '✗ Invalid phone number', 'error', session_id)
                return {'success': False, 'error': 'Invalid phone number'}
            except FloodWaitError as e:
                await client.disconnect()
                error_msg = f'Flood wait: please try again after {e.seconds} seconds'
                db.add_registration_log(phone, f'✗ {error_msg}', 'error', session_id)
                return {'success': False, 'error': error_msg}
            except Exception as e:
                await client.disconnect()
                error_msg = str(e)
                db.add_registration_log(phone, f'✗ Error: {error_msg}', 'error', session_id)
                return {'success': False, 'error': error_msg}
        
        result = asyncio.run(send_code())
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/registration/resend-code', methods=['POST'])
@login_required
def resend_registration_code():
    """Resend verification code to phone"""
    try:
        data = request.get_json()
        phone = data.get('phone', '').strip()
        
        if not phone:
            return jsonify({'success': False, 'error': 'Phone number is required'}), 400
        
        account = db.get_registration_account(phone)
        if not account:
            return jsonify({'success': False, 'error': 'Phone not found'}), 404
        
        # Check if account is in a state where resend is possible
        # Allow resend for new, code_sent, waiting_code, and error statuses
        if account['status'] not in ['new', 'code_sent', 'waiting_code', 'error']:
            return jsonify({'success': False, 'error': 'Cannot resend code for this account status'}), 400
        
        import asyncio
        from telethon import TelegramClient
        from telethon.errors import PhoneNumberInvalidError, FloodWaitError
        import config
        import uuid
        
        async def resend_code():
            phone_clean = phone.replace('+', '').replace(' ', '').replace('-', '')
            storage_dir = Path(__file__).parent / 'storage' / phone_clean
            storage_dir.mkdir(parents=True, exist_ok=True)
            
            # If session exists, disconnect it first
            if phone in registration_sessions:
                try:
                    old_client = registration_sessions[phone]['client']
                    await old_client.disconnect()
                except:
                    pass
                del registration_sessions[phone]
            
            # Get proxy and device from account if available
            proxy = None
            device = None
            if account.get('proxy_id'):
                proxy = db.get_registration_proxy(account['proxy_id'])
            if account.get('device_model'):
                device = {
                    'device_model': account.get('device_model'),
                    'system_version': account.get('system_version', 'Unknown'),
                    'app_version': account.get('app_version', '9.4.0'),
                    'lang_code': account.get('lang_code', 'en'),
                    'system_lang_code': account.get('lang_code', 'en') + '-US'
                }
            else:
                # Auto-select device if not set
                device = db.get_random_device_preset()
                if not device:
                    device = {
                        'device_model': 'Unknown',
                        'system_version': 'Unknown',
                        'app_version': '9.4.0',
                        'lang_code': 'en',
                        'system_lang_code': 'en-US'
                    }
            
            # Prepare proxy config if available
            proxy_config = None
            if proxy:
                import socks
                if proxy['protocol'] == 'socks5':
                    proxy_config = (
                        socks.SOCKS5,
                        proxy['host'],
                        proxy['port'],
                        True,  # rdns
                        proxy['username'],
                        proxy['password']
                    )
                else:
                    proxy_config = (
                        socks.HTTP,
                        proxy['host'],
                        proxy['port'],
                        True,  # rdns
                        proxy['username'],
                        proxy['password']
                    )
            
            # Create new temporary session for registration
            session_id = str(uuid.uuid4())
            session_file = storage_dir / f'temp_{session_id}'
            
            client = TelegramClient(
                str(session_file.with_suffix('')),
                config.API_ID,
                config.API_HASH,
                device_model=device.get('device_model', 'Unknown'),
                system_version=device.get('system_version', 'Unknown'),
                app_version=device.get('app_version', '9.4.0'),
                lang_code=device.get('lang_code', 'en'),
                system_lang_code=device.get('system_lang_code', 'en-US'),
                proxy=proxy_config
            )
            
            try:
                await client.connect()
                
                # Check if already authorized
                if await client.is_user_authorized():
                    await client.disconnect()
                    return {'success': False, 'error': 'Account already registered'}
                
                # Send code with force_sms=True to ensure SMS delivery (not Telegram app)
                # ВАЖНО: force_sms=True заставляет отправить SMS вместо кода в Telegram приложение
                result = await client.send_code_request(phone, force_sms=True)
                phone_code_hash = result.phone_code_hash
                
                # Store session info
                registration_sessions[phone] = {
                    'client': client,
                    'session_file': session_file,
                    'phone_code_hash': phone_code_hash,
                    'session_id': session_id
                }
                
                # Update status
                db.update_registration_account(phone, {
                    'status': 'code_sent',
                    'session_id': session_id,
                    'error_message': None  # Clear any previous errors
                })
                
                return {'success': True, 'session_id': session_id, 'message': 'Code resent to phone'}
                
            except PhoneNumberInvalidError:
                await client.disconnect()
                return {'success': False, 'error': 'Invalid phone number'}
            except FloodWaitError as e:
                await client.disconnect()
                return {'success': False, 'error': f'Flood wait: please try again after {e.seconds} seconds'}
            except Exception as e:
                await client.disconnect()
                return {'success': False, 'error': str(e)}
        
        result = asyncio.run(resend_code())
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/registration/submit-code', methods=['POST'])
@login_required
def submit_registration_code():
    """Submit verification code"""
    try:
        data = request.get_json()
        phone = data.get('phone', '').strip()
        code = data.get('code', '').strip()
        
        if not phone or not code:
            return jsonify({'success': False, 'error': 'Phone and code are required'}), 400
        
        if phone not in registration_sessions:
            return jsonify({'success': False, 'error': 'Registration session not found. Please start registration again.'}), 400
        
        session_data = registration_sessions[phone]
        client = session_data['client']
        phone_code_hash = session_data['phone_code_hash']
        
        import asyncio
        
        async def sign_in():
            try:
                # Sign in with code
                await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
                
                # Get account info
                me = await client.get_me()
                
                # Generate files
                phone_clean = phone.replace('+', '').replace(' ', '').replace('-', '')
                storage_dir = Path(__file__).parent / 'storage' / phone_clean
                storage_dir.mkdir(parents=True, exist_ok=True)
                
                # Copy session file
                temp_session = session_data['session_file']
                final_session = storage_dir / 'session.session'
                import shutil
                shutil.copy2(f"{temp_session}.session", str(final_session))
                
                # Generate tdata (if opentele available)
                tdata_path = None
                try:
                    from opentele.td import TDesktop
                    tdesk = await TDesktop.from_telethon_file(str(final_session))
                    tdata_dir = storage_dir / 'tdata'
                    await tdesk.to_tdata_folder(str(tdata_dir))
                    
                    # Create zip
                    import zipfile
                    tdata_zip = storage_dir / 'tdata.zip'
                    with zipfile.ZipFile(tdata_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for file_path in tdata_dir.rglob('*'):
                            if file_path.is_file():
                                zipf.write(file_path, file_path.relative_to(tdata_dir))
                    
                    tdata_path = str(tdata_zip)
                except ImportError:
                    print("opentele not available, skipping tdata generation")
                except Exception as e:
                    print(f"Error generating tdata: {e}")
                
                # Update database
                db.update_registration_account(phone, {
                    'status': 'registered',
                    'registered_at': datetime.now().isoformat(),
                    'session_path': str(final_session),
                    'tdata_path': tdata_path
                })
                
                # Update proxy statistics
                account = db.get_registration_account(phone)
                if account and account.get('proxy_id'):
                    proxy = db.get_registration_proxy(account['proxy_id'])
                    if proxy:
                        # Estimate traffic used: ~0.09 MB per registration
                        traffic_used_mb = 0.09
                        traffic_used_gb = traffic_used_mb / 1024
                        
                        db.update_registration_proxy(account['proxy_id'], {
                            'total_gb_used': proxy.get('total_gb_used', 0) + traffic_used_gb,
                            'registrations_count': proxy.get('registrations_count', 0) + 1,
                            'last_used': datetime.now().isoformat()
                        })
                
                # Clean up temp session
                try:
                    Path(f"{temp_session}.session").unlink()
                except:
                    pass
                
                # Remove from active sessions but keep client for status check
                # Don't disconnect yet - need for status check
                
                # Start account check in background
                import threading
                def check_status():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(check_registration_account_status(phone, client))
                    loop.close()
                
                thread = threading.Thread(target=check_status, daemon=True)
                thread.start()
                
                return {'success': True, 'message': 'Registration successful'}
                
            except PhoneCodeInvalidError:
                return {'success': False, 'error': 'PhoneCodeInvalidError', 'message': 'Invalid verification code'}
            except PhoneCodeExpiredError:
                return {'success': False, 'error': 'PhoneCodeExpiredError', 'message': 'Code expired. Please request a new code.'}
            except SessionPasswordNeededError:
                return {'success': False, 'error': 'SessionPasswordNeededError', 'message': '2FA password required (not yet supported)'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
        
        result = asyncio.run(sign_in())
        
        # Update status if error
        if not result.get('success'):
            db.update_registration_account(phone, {
                'status': 'error',
                'error_message': result.get('message', result.get('error', 'Unknown error'))
            })
            # Clean up session on error
            if phone in registration_sessions:
                try:
                    asyncio.run(registration_sessions[phone]['client'].disconnect())
                except:
                    pass
                del registration_sessions[phone]
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


async def check_registration_account_status(phone: str, client: TelegramClient):
    """Check account status after registration"""
    try:
        db.update_registration_account(phone, {
            'check_status': 'checking',
            'check_message': 'Checking account status...'
        })
        
        # Basic check - get account info
        me = await client.get_me()
        
        # Try to send a test message to self
        try:
            await client.send_message('me', 'Test')
            check_status = 'active'
            check_message = 'Account is fully functional'
        except PeerFloodError:
            check_status = 'limited'
            check_message = 'Peer flood - account has limitations'
        except FloodWaitError as e:
            check_status = 'limited'
            check_message = f'Flood wait - retry after {e.seconds}s'
        except Exception as e:
            check_status = 'limited'
            check_message = f'Limited: {str(e)}'
        
        db.update_registration_account(phone, {
            'check_status': check_status,
            'check_message': check_message
        })
        
        await client.disconnect()
        
    except Exception as e:
        db.update_registration_account(phone, {
            'check_status': 'error',
            'check_message': f'Check error: {str(e)}'
        })


@app.route('/api/registration/check-account', methods=['POST'])
@login_required
def check_registration_account():
    """Check single account status"""
    try:
        data = request.get_json()
        phone = data.get('phone', '').strip()
        
        if not phone:
            return jsonify({'success': False, 'error': 'Phone number is required'}), 400
        
        account = db.get_registration_account(phone)
        if not account or account['status'] != 'registered':
            return jsonify({'success': False, 'error': 'Account not registered'}), 400
        
        import asyncio
        from telethon import TelegramClient
        import config
        
        session_path = account.get('session_path')
        if not session_path or not Path(session_path).exists():
            return jsonify({'success': False, 'error': 'Session file not found'}), 400
        
        async def check():
            client = TelegramClient(str(Path(session_path).with_suffix('')), config.API_ID, config.API_HASH)
            try:
                await client.connect()
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'Account not authorized'}
                
                await check_registration_account_status(phone, client)
                return {'success': True}
            finally:
                try:
                    await client.disconnect()
                except:
                    pass
        
        asyncio.run(check())
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/registration/check-all', methods=['POST'])
@login_required
def check_all_registration_accounts():
    """Check all registered accounts"""
    try:
        accounts = db.get_all_registration_accounts()
        registered = [acc for acc in accounts if acc['status'] == 'registered']
        
        import asyncio
        from telethon import TelegramClient
        import config
        
        results = {'active': 0, 'limited': 0, 'banned': 0}
        
        async def check_all():
            for acc in registered:
                session_path = acc.get('session_path')
                if not session_path or not Path(session_path).exists():
                    continue
                
                try:
                    client = TelegramClient(str(Path(session_path).with_suffix('')), config.API_ID, config.API_HASH)
                    await client.connect()
                    
                    if await client.is_user_authorized():
                        await check_registration_account_status(acc['phone'], client)
                        # Get updated status
                        updated = db.get_registration_account(acc['phone'])
                        if updated:
                            status = updated.get('check_status', 'unknown')
                            if status == 'active':
                                results['active'] += 1
                            elif status == 'limited':
                                results['limited'] += 1
                            elif status == 'banned':
                                results['banned'] += 1
                    
                    await client.disconnect()
                except Exception as e:
                    print(f"Error checking {acc['phone']}: {e}")
        
        asyncio.run(check_all())
        
        return jsonify({
            'success': True,
            'checked': len(registered),
            'results': results
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/registration/download-tdata/<phone>')
@login_required
def download_registration_tdata(phone):
    """Download tdata.zip file"""
    try:
        account = db.get_registration_account(phone)
        if not account or not account.get('tdata_path'):
            flash('tdata file not found', 'danger')
            return redirect(url_for('create_accounts'))
        
        tdata_path = Path(account['tdata_path'])
        if not tdata_path.exists():
            flash('tdata file not found', 'danger')
            return redirect(url_for('create_accounts'))
        
        return send_file(str(tdata_path), as_attachment=True, download_name=f'tdata_{phone.replace("+", "")}.zip')
        
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('create_accounts'))


@app.route('/api/registration/download-session/<phone>')
@login_required
def download_registration_session(phone):
    """Download session file"""
    try:
        account = db.get_registration_account(phone)
        if not account or not account.get('session_path'):
            flash('Session file not found', 'danger')
            return redirect(url_for('create_accounts'))
        
        session_path = Path(account['session_path'])
        if not session_path.exists():
            flash('Session file not found', 'danger')
            return redirect(url_for('create_accounts'))
        
        return send_file(str(session_path), as_attachment=True, download_name=f'session_{phone.replace("+", "")}.session')
        
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('create_accounts'))


# ============================================================================
# PROXY MANAGEMENT API
# ============================================================================

@app.route('/api/registration/proxies')
@login_required
def get_registration_proxies():
    """Get all registration proxies"""
    proxies = db.get_all_registration_proxies()
    # Calculate remaining traffic
    for proxy in proxies:
        proxy['traffic_remaining_gb'] = proxy.get('total_gb_purchased', 0) - proxy.get('total_gb_used', 0)
    return jsonify(proxies)


@app.route('/api/registration/proxies/add', methods=['POST'])
@login_required
def add_registration_proxy():
    """Add new registration proxy"""
    try:
        data = request.get_json()
        proxy_id = db.add_registration_proxy(data)
        if proxy_id:
            return jsonify({'success': True, 'proxy_id': proxy_id, 'message': 'Proxy added successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to add proxy'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/registration/proxies/add-bulk', methods=['POST'])
@login_required
def add_registration_proxies_bulk():
    """Add multiple registration proxies at once"""
    try:
        data = request.get_json()
        proxies = data.get('proxies', [])
        
        if not proxies:
            return jsonify({'success': False, 'error': 'No proxies provided'}), 400
        
        added_count = db.add_registration_proxies_bulk(proxies)
        
        if added_count > 0:
            return jsonify({
                'success': True,
                'added_count': added_count,
                'message': f'Successfully added {added_count} proxy/proxies'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to add proxies'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/registration/proxies/<int:proxy_id>', methods=['PUT'])
@login_required
def update_registration_proxy(proxy_id):
    """Update registration proxy"""
    try:
        data = request.get_json()
        success = db.update_registration_proxy(proxy_id, data)
        if success:
            return jsonify({'success': True, 'message': 'Proxy updated successfully'})
        else:
            return jsonify({'success': False, 'error': 'Proxy not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/registration/proxies/<int:proxy_id>', methods=['DELETE'])
@login_required
def delete_registration_proxy(proxy_id):
    """Delete registration proxy"""
    try:
        success = db.delete_registration_proxy(proxy_id)
        if success:
            return jsonify({'success': True, 'message': 'Proxy deleted successfully'})
        else:
            return jsonify({'success': False, 'error': 'Proxy not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/registration/proxies/test', methods=['POST'])
@login_required
def test_registration_proxy():
    """Test proxy connection"""
    try:
        data = request.get_json()
        proxy_id = data.get('proxy_id')
        
        if not proxy_id:
            return jsonify({'success': False, 'error': 'Proxy ID is required'}), 400
        
        proxy = db.get_registration_proxy(proxy_id)
        if not proxy:
            return jsonify({'success': False, 'error': 'Proxy not found'}), 404
        
        import asyncio
        import aiohttp
        
        async def test_connection():
            try:
                # Prepare proxy URL
                if proxy['protocol'] == 'socks5':
                    proxy_url = f"socks5://{proxy['username']}:{proxy['password']}@{proxy['host']}:{proxy['port']}"
                else:
                    proxy_url = f"{proxy['protocol']}://{proxy['username']}:{proxy['password']}@{proxy['host']}:{proxy['port']}"
                
                # Test connection
                async with aiohttp.ClientSession() as session:
                    async with session.get('https://api.ipify.org?format=json', proxy=proxy_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            ip_data = await response.json()
                            return {
                                'success': True,
                                'test_results': {
                                    'connection': 'OK',
                                    'ip_address': ip_data.get('ip', 'Unknown'),
                                    'country': 'Unknown',  # Would need geoip service
                                    'type': proxy['type'],
                                    'speed_mbps': None,
                                    'latency_ms': None
                                }
                            }
                        else:
                            return {'success': False, 'error': f'HTTP {response.status}'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
        
        result = asyncio.run(test_connection())
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/registration/proxies/select', methods=['POST'])
@login_required
def select_proxy_for_registration():
    """Select optimal proxy for registration"""
    try:
        data = request.get_json()
        country_preference = data.get('country_preference')
        type_preference = data.get('type_preference')
        
        proxies = db.get_all_registration_proxies()
        
        # Filter active proxies with traffic
        available = [
            p for p in proxies 
            if p.get('status') == 'active' 
            and (p.get('total_gb_purchased', 0) - p.get('total_gb_used', 0)) > 0.1
        ]
        
        if not available:
            return jsonify({'success': False, 'error': 'No available proxies'}), 400
        
        # Filter by type preference
        if type_preference:
            available = [p for p in available if p.get('type') == type_preference]
        
        # Filter by country preference
        if country_preference:
            available = [p for p in available if p.get('country') == country_preference or p.get('country') is None]
        
        if not available:
            return jsonify({'success': False, 'error': 'No proxies match preferences'}), 400
        
        # Sort by type priority (mobile > residential > datacenter) and registrations count
        type_priority = {'mobile': 1, 'residential': 2, 'datacenter': 3}
        available.sort(key=lambda x: (
            type_priority.get(x.get('type', 'datacenter'), 3),
            x.get('registrations_count', 0)
        ))
        
        selected = available[0]
        return jsonify({
            'success': True,
            'proxy_id': selected['id'],
            'proxy_name': selected['name'],
            'estimated_ip': 'rotating' if selected.get('session_type') == 'rotating' else 'sticky',
            'traffic_remaining_gb': selected.get('total_gb_purchased', 0) - selected.get('total_gb_used', 0)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ============================================================================
# DEVICE PRESETS API
# ============================================================================

@app.route('/api/registration/device-presets')
@login_required
def get_device_presets():
    """Get all device presets"""
    enabled_only = request.args.get('enabled_only', 'false').lower() == 'true'
    presets = db.get_all_device_presets(enabled_only=enabled_only)
    return jsonify(presets)


@app.route('/api/registration/device-presets/random', methods=['POST'])
@login_required
def get_random_device_preset():
    """Get random device preset"""
    try:
        data = request.get_json() or {}
        system_type = data.get('system_type')
        
        device = db.get_random_device_preset(system_type=system_type)
        if device:
            return jsonify({'success': True, 'device': device})
        else:
            return jsonify({'success': False, 'error': 'No device presets available'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/registration/device-presets/add', methods=['POST'])
@login_required
def add_device_preset():
    """Add custom device preset"""
    try:
        data = request.get_json()
        device_id = db.add_device_preset(data)
        if device_id:
            return jsonify({'success': True, 'device_id': device_id, 'message': 'Device preset added successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to add device preset'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/registration/logs/<phone>')
@login_required
def get_registration_logs(phone):
    """Get registration logs for a phone number"""
    try:
        session_id = request.args.get('session_id')
        logs = db.get_registration_logs(phone, session_id=session_id)
        return jsonify(logs)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/registration/delete-account/<phone>', methods=['DELETE'])
@login_required
def delete_registration_account(phone):
    """Delete registration account"""
    try:
        # Clean up session if exists
        if phone in registration_sessions:
            try:
                session_data = registration_sessions[phone]
                client = session_data['client']
                asyncio.run(client.disconnect())
            except:
                pass
            del registration_sessions[phone]
        
        # Delete files
        phone_clean = phone.replace('+', '').replace(' ', '').replace('-', '')
        storage_dir = Path(__file__).parent / 'storage' / phone_clean
        if storage_dir.exists():
            import shutil
            shutil.rmtree(storage_dir, ignore_errors=True)
        
        # Delete from database
        success = db.delete_registration_account(phone)
        
        if success:
            return jsonify({'success': True, 'message': 'Account deleted'})
        else:
            return jsonify({'success': False, 'error': 'Account not found'}), 404
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(error):
    return render_template('500.html'), 500


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("  WEB INTERFACE STARTING")
    print("=" * 70)
    print()
    print("  URL: http://localhost:5000")
    print("  Register a new account to get started")
    print()
    print("=" * 70)
    print()

    app.run(host='0.0.0.0', port=5000, debug=True)

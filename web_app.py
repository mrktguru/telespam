#!/usr/bin/env python3
"""
Web Interface - Flask application for Telegram Outreach System
"""

import os
os.environ['USE_MOCK_STORAGE'] = 'true'

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from functools import wraps
from datetime import datetime
import asyncio
import threading
import time
import json
from pathlib import Path
from telethon import TelegramClient
from telethon.errors import FloodWaitError, UserPrivacyRestrictedError, PeerFloodError
from telethon.tl.functions.users import GetFullUserRequest

from database import db
from mock_sheets import sheets_manager
from rate_limiter import RateLimiter
from proxy_manager import ProxyManager
import config

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Initialize managers
rate_limiter = RateLimiter()
proxy_manager = ProxyManager()


# ============================================================================
# CAMPAIGN RUNNER
# ============================================================================

async def send_message_to_user(account, user, message_text, media_path=None, media_type=None):
    """Send message to user via Telegram with optional media

    Returns: (success: bool, error_msg: str)
    """
    phone = account.get('phone')
    session_file = Path(__file__).parent / 'sessions' / f'{phone.replace("+", "")}.session'

    if not session_file.exists():
        return False, f'Session file not found: {session_file}'

    # Get proxy if assigned to account
    proxy = None
    if account.get('use_proxy') and account.get('proxy'):
        proxy_id = account['proxy']
        proxy_data = proxy_manager.get_proxy(proxy_id)
        if proxy_data:
            proxy = {
                'proxy_type': proxy_data['type'],
                'addr': proxy_data['host'],
                'port': proxy_data['port'],
                'username': proxy_data.get('username'),
                'password': proxy_data.get('password')
            }

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
            return False, 'Account not authorized'

        # Find user by username, user_id or phone
        target = None
        if user.get('username'):
            username = user['username'].lstrip('@')
            try:
                target = await client.get_entity(username)
            except Exception as e:
                pass

        if not target and user.get('user_id'):
            try:
                target = await client.get_entity(int(user['user_id']))
            except Exception as e:
                pass

        if not target and user.get('phone'):
            phone_num = user['phone']
            try:
                target = await client.get_entity(phone_num)
            except Exception as e:
                pass

        if not target:
            await client.disconnect()
            return False, 'User not found'

        # Send message with or without media, using HTML parsing
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
        campaign = db.get_campaign(campaign_id)
        if not campaign:
            return

        settings = campaign.get('settings', {})
        message = settings.get('message', '')
        media_path = settings.get('media_path')
        media_type = settings.get('media_type')
        account_phones = settings.get('accounts', [])

        # Get accounts
        all_accounts = sheets_manager.get_all_accounts()
        accounts = [acc for acc in all_accounts if acc.get('phone') in account_phones]

        # Get users from campaign_users table (new system)
        campaign_users = db.get_campaign_users(campaign_id)
        # Filter only pending users
        users = [cu for cu in campaign_users if cu.get('status', 'pending') == 'pending']

        if not accounts:
            db.add_campaign_log(campaign_id, 'No accounts available', level='error')
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
            account = accounts[account_idx % len(accounts)]
            account_phone = account.get('phone', 'unknown')

            # Get user identifier
            user_identifier = user.get('username') or user.get('user_id') or user.get('phone') or 'unknown'

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
                    send_message_to_user(account, user, message, media_path, media_type)
                )

                if success:
                    sent_count += 1
                    rate_limiter.record_sent(account_phone)

                    db.add_campaign_log(
                        campaign_id,
                        f'✓ Sent to {user_identifier} from {account_phone}',
                        level='success'
                    )

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
                    sheets_manager.update_account(account.get('id'), {
                        'daily_sent': daily_sent,
                        'total_sent': total_sent,
                        'last_used_at': datetime.now().isoformat()
                    })
                else:
                    failed_count += 1
                    db.add_campaign_log(
                        campaign_id,
                        f'✗ Failed to send to {user_identifier} from {account_phone}: {error_msg}',
                        level='error'
                    )

                    # Handle flood wait
                    if 'FloodWait' in str(error_msg):
                        db.add_campaign_log(
                            campaign_id,
                            f'Account {account_phone} hit flood wait, skipping',
                            level='warning'
                        )
                        # Move to next account
                        account_idx += 1

            except Exception as e:
                failed_count += 1
                db.add_campaign_log(
                    campaign_id,
                    f'Exception sending to {user_identifier}: {str(e)}',
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

        # Mark as completed
        db.update_campaign(campaign_id, status='completed')
        db.add_campaign_log(campaign_id, f'Campaign completed: {sent_count} sent, {failed_count} failed', level='info')

    except Exception as e:
        db.add_campaign_log(campaign_id, f'Campaign error: {str(e)}', level='error')
        db.update_campaign(campaign_id, status='failed')


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
    accounts = sheets_manager.get_all_accounts()

    # Get users for outreach
    users = sheets_manager.users

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
            accounts = sheets_manager.get_all_accounts()
            users = sheets_manager.users
            return render_template('new_campaign.html', accounts=accounts, users=users)

        # Get selected accounts
        account_ids = request.form.getlist('accounts')
        
        # Get account phones from account IDs
        all_accounts = sheets_manager.get_all_accounts()
        account_phones = []
        for acc_id in account_ids:
            account = next((acc for acc in all_accounts if acc.get('id') == acc_id), None)
            if account and account.get('phone'):
                account_phones.append(account['phone'])
        
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
        for account_id in account_ids:
            account = sheets_manager.get_account(account_id)
            if account:
                phone = account.get('phone', '')
                if phone:
                    # Generate new ID: acc_{phone}_{campaign_id}
                    phone_clean = phone.replace('+', '').replace(' ', '')
                    new_account_id = f"acc_{phone_clean}_{campaign_id}"
                    
                    # Update account with new ID and campaign_id
                    sheets_manager.update_account(account_id, {
                        'new_id': new_account_id,
                        'campaign_id': campaign_id
                    })
                    print(f"✓ Assigned campaign {campaign_id} to account {account_id} → {new_account_id}")

        flash('Campaign created! Starting...', 'success')
        return redirect(url_for('campaign_detail', campaign_id=campaign_id))

    # Get accounts and users for form
    accounts = sheets_manager.get_all_accounts()
    users = sheets_manager.users

    return render_template('new_campaign.html', accounts=accounts, users=users)


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

    # Update status
    db.update_campaign(campaign_id, status='running')
    db.add_campaign_log(campaign_id, 'Campaign started', level='info')

    # Start campaign in background thread
    thread = threading.Thread(target=run_campaign_task, args=(campaign_id,), daemon=True)
    thread.start()

    return jsonify({'success': True, 'message': 'Campaign started'})


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
    
    # Get account
    account = sheets_manager.get_account(conversation['sender_account_id'])
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
    
    # Get account
    account = sheets_manager.get_account(conversation['sender_account_id'])
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
                        'text': message.text,
                        'is_out': message.out,  # True if sent by us, False if received
                        'date': message.date.isoformat()
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
        
        # Get already saved messages to avoid duplicates (text + date combination)
        saved_msgs = db.get_conversation_messages(conversation_id)
        saved_set = {(msg['message_text'], msg['sent_at'][:19]) for msg in saved_msgs if msg.get('message_text')}
        
        # Save new messages
        new_count = 0
        for msg in messages:
            if msg['text']:
                # Create unique key from text and date
                msg_key = (msg['text'], msg['date'][:19])
                
                # Only add if not already in database
                if msg_key not in saved_set:
                    direction = 'outgoing' if msg['is_out'] else 'incoming'
                    db.add_message(conversation_id, direction, msg['text'])
                    new_count += 1
        
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
    accounts = sheets_manager.get_all_accounts()

    # Add rate limit stats
    for acc in accounts:
        stats = rate_limiter.get_stats(acc['id'])
        acc['rate_limits'] = stats

    return render_template('accounts.html', accounts=accounts)


@app.route('/accounts/delete/<account_id>', methods=['POST'])
@login_required
def delete_account(account_id):
    """Delete account"""
    try:
        success = sheets_manager.delete_account(account_id)
        
        if success:
            flash(f'Account {account_id} deleted successfully', 'success')
        else:
            flash(f'Account {account_id} not found', 'warning')
    except Exception as e:
        flash(f'Error deleting account: {str(e)}', 'danger')
    
    return redirect(url_for('accounts_list'))


@app.route('/accounts/edit/<account_id>', methods=['GET', 'POST'])
@login_required
def edit_account(account_id):
    """Edit account profile"""
    account = sheets_manager.get_account(account_id)
    
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
                # Update local storage
                sheets_manager.update_account(account_id, {
                    'first_name': result['first_name'],
                    'last_name': result['last_name']
                })
                
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


@app.route('/accounts/delete-photos/<account_id>', methods=['POST'])
@login_required
def delete_account_photos(account_id):
    """Delete all profile photos from account"""
    try:
        account = sheets_manager.get_account(account_id)
        
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

    user_data = {
        'username': username if username else None,
        'user_id': user_id_int,
        'phone': phone if phone else None,
        'priority': priority_int,
        'status': 'pending'
    }

    sheets_manager.add_user(user_data)

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
        
        count = sheets_manager.delete_users(user_ids)
        
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

            user_data['status'] = 'pending'
            sheets_manager.add_user(user_data)
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
            import asyncio
            result = asyncio.run(proxy_manager.test_proxy(proxy_id))

            if result:
                flash(f'Proxy {proxy_id} is working!', 'success')
            else:
                flash(f'Proxy {proxy_id} failed test', 'danger')

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


# ============================================================================
# API ROUTES
# ============================================================================

@app.route('/api/stats')
@login_required
def api_stats():
    """Get system stats (JSON)"""
    accounts = sheets_manager.get_all_accounts()
    users = sheets_manager.users
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

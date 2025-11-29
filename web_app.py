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

async def send_message_to_user(account, user, message_text):
    """Send message to user via Telegram

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

        # Send message
        await client.send_message(target, message_text)
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
        account_phones = settings.get('accounts', [])
        user_indices = settings.get('users', [])

        # Get accounts
        all_accounts = sheets_manager.get_all_accounts()
        accounts = [acc for acc in all_accounts if acc.get('phone') in account_phones]

        # Get users
        all_users = sheets_manager.users
        users = [all_users[int(idx)] for idx in user_indices if int(idx) < len(all_users)]

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
                    send_message_to_user(account, user, message)
                )

                if success:
                    sent_count += 1
                    rate_limiter.record_send(account_phone)

                    db.add_campaign_log(
                        campaign_id,
                        f'✓ Sent to {user_identifier} from {account_phone}',
                        level='success'
                    )

                    # Update user status
                    if user.get('user_id'):
                        sheets_manager.update_user_status(user['user_id'], 'contacted', account_phone)

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
        message = request.form.get('message')

        # Get selected accounts and users
        account_ids = request.form.getlist('accounts')
        user_ids = request.form.getlist('users')

        settings = {
            'message': message,
            'accounts': account_ids,
            'users': user_ids
        }

        campaign_id = db.create_campaign(
            user_id=session['user_id'],
            name=name,
            total_users=len(user_ids),
            settings=settings
        )

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

    return render_template('campaign_detail.html', campaign=campaign, logs=logs)


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


# ============================================================================
# USER ROUTES (for outreach)
# ============================================================================

@app.route('/users')
@login_required
def users_list():
    """List all users for outreach"""
    users = sheets_manager.users

    return render_template('users.html', users=users)


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

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
from pathlib import Path

from database import db
from mock_sheets import sheets_manager
from rate_limiter import RateLimiter
from proxy_manager import ProxyManager

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Initialize managers
rate_limiter = RateLimiter()
proxy_manager = ProxyManager()


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
    db.add_campaign_log(campaign_id, 'Campaign started')

    # TODO: Start async task to run campaign

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
    username = request.form.get('username')
    user_id = request.form.get('user_id')
    phone = request.form.get('phone')
    priority = int(request.form.get('priority', 1))

    user_data = {
        'username': username,
        'user_id': int(user_id) if user_id else None,
        'phone': phone,
        'priority': priority,
        'status': 'pending'
    }

    sheets_manager.add_user(user_data)

    flash('User added successfully', 'success')
    return redirect(url_for('users_list'))


# ============================================================================
# PROXY ROUTES
# ============================================================================

@app.route('/proxies')
@login_required
def proxies_list():
    """List all proxies"""
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

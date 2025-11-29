#!/usr/bin/env python3
"""
Web Interface - FastAPI backend for Telegram Outreach System
"""

import os
os.environ['USE_MOCK_STORAGE'] = 'true'

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, List
import secrets

from mock_sheets import sheets_manager
from rate_limiter import RateLimiter
from proxy_manager import ProxyManager

app = FastAPI(title="Telegram Outreach System")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple auth
security = HTTPBasic()

# Single user credentials (можно вынести в .env)
USERNAME = os.getenv("WEB_USERNAME", "admin")
PASSWORD = os.getenv("WEB_PASSWORD", "admin123")


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Verify HTTP Basic Auth"""
    correct_username = secrets.compare_digest(credentials.username, USERNAME)
    correct_password = secrets.compare_digest(credentials.password, PASSWORD)

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials.username


# Pydantic models
class AccountCreate(BaseModel):
    phone: str
    username: Optional[str] = None
    first_name: str
    session_file: str


class UserCreate(BaseModel):
    username: Optional[str] = None
    user_id: Optional[int] = None
    phone: Optional[str] = None
    priority: int = 1


class ProxyCreate(BaseModel):
    proxy_id: str
    proxy_type: str
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None


class RateLimitSet(BaseModel):
    account_id: str
    per_hour: Optional[int] = None
    per_day: Optional[int] = None


# Initialize managers
rate_limiter = RateLimiter()
proxy_manager = ProxyManager()


# ============================================================================
# ACCOUNTS
# ============================================================================

@app.get("/api/accounts")
def get_accounts(username: str = Depends(verify_credentials)):
    """Get all accounts"""
    accounts = sheets_manager.get_all_accounts()
    return {"accounts": accounts}


@app.get("/api/accounts/{account_id}")
def get_account(account_id: str, username: str = Depends(verify_credentials)):
    """Get specific account"""
    accounts = sheets_manager.get_all_accounts()

    for acc in accounts:
        if acc['id'] == account_id:
            # Add rate limit info
            stats = rate_limiter.get_stats(account_id)
            acc['rate_limits'] = stats

            return acc

    raise HTTPException(status_code=404, detail="Account not found")


@app.delete("/api/accounts/{account_id}")
def delete_account(account_id: str, username: str = Depends(verify_credentials)):
    """Delete account"""
    accounts = sheets_manager.get_all_accounts()

    for i, acc in enumerate(accounts):
        if acc['id'] == account_id:
            sheets_manager.accounts.pop(i)
            sheets_manager.save()
            return {"message": "Account deleted"}

    raise HTTPException(status_code=404, detail="Account not found")


# ============================================================================
# USERS (for outreach)
# ============================================================================

@app.get("/api/users")
def get_users(username: str = Depends(verify_credentials)):
    """Get all users"""
    return {"users": sheets_manager.users}


@app.post("/api/users")
def add_user(user: UserCreate, username: str = Depends(verify_credentials)):
    """Add user for outreach"""
    user_data = {
        'username': user.username,
        'user_id': user.user_id,
        'phone': user.phone,
        'priority': user.priority,
        'status': 'pending',
        'contacted_at': None,
        'account_used': None
    }

    sheets_manager.add_user(user_data)

    return {"message": "User added", "user": user_data}


@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, username: str = Depends(verify_credentials)):
    """Delete user"""
    users = sheets_manager.users

    for i, user in enumerate(users):
        if user.get('user_id') == user_id:
            sheets_manager.users.pop(i)
            sheets_manager.save()
            return {"message": "User deleted"}

    raise HTTPException(status_code=404, detail="User not found")


# ============================================================================
# RATE LIMITS
# ============================================================================

@app.get("/api/rate-limits")
def get_rate_limits(username: str = Depends(verify_credentials)):
    """Get all rate limits"""
    accounts = sheets_manager.get_all_accounts()

    limits = []
    for acc in accounts:
        stats = rate_limiter.get_stats(acc['id'])
        limits.append({
            'account_id': acc['id'],
            'phone': acc.get('phone'),
            'stats': stats
        })

    return {"limits": limits}


@app.post("/api/rate-limits")
def set_rate_limit(limit: RateLimitSet, username: str = Depends(verify_credentials)):
    """Set rate limits for account"""
    rate_limiter.set_limits(limit.account_id, per_hour=limit.per_hour, per_day=limit.per_day)

    return {"message": "Rate limits set", "account_id": limit.account_id}


# ============================================================================
# PROXIES
# ============================================================================

@app.get("/api/proxies")
def get_proxies(username: str = Depends(verify_credentials)):
    """Get all proxies"""
    proxies = proxy_manager.get_all_proxies()
    return {"proxies": proxies}


@app.post("/api/proxies")
def add_proxy(proxy: ProxyCreate, username: str = Depends(verify_credentials)):
    """Add proxy"""
    proxy_manager.add_proxy(
        proxy.proxy_id,
        proxy.proxy_type,
        proxy.host,
        proxy.port,
        proxy.username,
        proxy.password
    )

    return {"message": "Proxy added", "proxy_id": proxy.proxy_id}


@app.delete("/api/proxies/{proxy_id}")
def delete_proxy(proxy_id: str, username: str = Depends(verify_credentials)):
    """Delete proxy"""
    proxy_manager.remove_proxy(proxy_id)
    return {"message": "Proxy deleted"}


@app.post("/api/proxies/{proxy_id}/test")
async def test_proxy(proxy_id: str, username: str = Depends(verify_credentials)):
    """Test proxy"""
    result = await proxy_manager.test_proxy(proxy_id)

    return {
        "proxy_id": proxy_id,
        "working": result
    }


@app.post("/api/accounts/{account_id}/proxy/{proxy_id}")
def assign_proxy(account_id: str, proxy_id: str, username: str = Depends(verify_credentials)):
    """Assign proxy to account"""
    proxy_manager.assign_proxy_to_account(account_id, proxy_id)

    return {"message": "Proxy assigned"}


# ============================================================================
# STATISTICS
# ============================================================================

@app.get("/api/stats")
def get_stats(username: str = Depends(verify_credentials)):
    """Get system statistics"""
    accounts = sheets_manager.get_all_accounts()
    users = sheets_manager.users
    dialogs = sheets_manager.dialogs
    logs = sheets_manager.logs

    return {
        "accounts": {
            "total": len(accounts),
            "active": len([a for a in accounts if a.get('status') == 'active']),
            "warming": len([a for a in accounts if a.get('status') == 'warming']),
        },
        "users": {
            "total": len(users),
            "pending": len([u for u in users if u.get('status') == 'pending']),
            "contacted": len([u for u in users if u.get('status') == 'contacted']),
            "completed": len([u for u in users if u.get('status') == 'completed']),
        },
        "dialogs": len(dialogs),
        "logs": len(logs),
        "recent_logs": logs[-10:]
    }


# ============================================================================
# LOGS
# ============================================================================

@app.get("/api/logs")
def get_logs(limit: int = 100, username: str = Depends(verify_credentials)):
    """Get recent logs"""
    logs = sheets_manager.logs[-limit:]
    return {"logs": logs}


# ============================================================================
# FRONTEND
# ============================================================================

@app.get("/", response_class=HTMLResponse)
def index():
    """Serve frontend"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Telegram Outreach System</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: system-ui, -apple-system, sans-serif; background: #f5f5f5; }
            .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
            header { background: #2563eb; color: white; padding: 20px; margin-bottom: 30px; border-radius: 8px; }
            header h1 { font-size: 24px; }
            .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }
            .stat-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
            .stat-card h3 { color: #64748b; font-size: 14px; margin-bottom: 10px; }
            .stat-card .number { font-size: 32px; font-weight: bold; color: #1e293b; }
            .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
            .tab { padding: 12px 24px; background: white; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; }
            .tab.active { background: #2563eb; color: white; }
            .tab-content { display: none; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
            .tab-content.active { display: block; }
            table { width: 100%; border-collapse: collapse; }
            th, td { padding: 12px; text-align: left; border-bottom: 1px solid #e2e8f0; }
            th { background: #f8fafc; font-weight: 600; color: #475569; }
            button { padding: 8px 16px; background: #2563eb; color: white; border: none; border-radius: 6px; cursor: pointer; }
            button:hover { background: #1d4ed8; }
            .status { display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 500; }
            .status.active { background: #dcfce7; color: #166534; }
            .status.warming { background: #fef3c7; color: #92400e; }
            .status.pending { background: #e0e7ff; color: #3730a3; }
            .login-container { max-width: 400px; margin: 100px auto; }
            .login-box { background: white; padding: 40px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
            .form-group { margin-bottom: 20px; }
            .form-group label { display: block; margin-bottom: 8px; font-weight: 500; }
            .form-group input { width: 100%; padding: 12px; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 14px; }
        </style>
    </head>
    <body>
        <div id="app"></div>

        <script>
            // Simple auth state
            let auth = localStorage.getItem('auth');

            // API helper
            async function api(endpoint, options = {}) {
                const headers = { 'Content-Type': 'application/json' };
                if (auth) {
                    headers['Authorization'] = 'Basic ' + auth;
                }

                const response = await fetch('/api' + endpoint, { ...options, headers });

                if (response.status === 401) {
                    localStorage.removeItem('auth');
                    location.reload();
                    return;
                }

                return response.json();
            }

            // Login
            function showLogin() {
                document.getElementById('app').innerHTML = `
                    <div class="login-container">
                        <div class="login-box">
                            <h1 style="margin-bottom: 30px; text-align: center;">Telegram Outreach</h1>
                            <form id="loginForm">
                                <div class="form-group">
                                    <label>Username</label>
                                    <input type="text" id="username" value="admin">
                                </div>
                                <div class="form-group">
                                    <label>Password</label>
                                    <input type="password" id="password" value="admin123">
                                </div>
                                <button type="submit" style="width: 100%;">Login</button>
                            </form>
                        </div>
                    </div>
                `;

                document.getElementById('loginForm').onsubmit = async (e) => {
                    e.preventDefault();
                    const username = document.getElementById('username').value;
                    const password = document.getElementById('password').value;

                    auth = btoa(username + ':' + password);
                    localStorage.setItem('auth', auth);

                    try {
                        await api('/stats');
                        showDashboard();
                    } catch {
                        alert('Invalid credentials');
                        localStorage.removeItem('auth');
                    }
                };
            }

            // Dashboard
            async function showDashboard() {
                const stats = await api('/stats');
                const accounts = await api('/accounts');
                const users = await api('/users');

                document.getElementById('app').innerHTML = `
                    <div class="container">
                        <header>
                            <h1>🚀 Telegram Outreach System</h1>
                            <p style="margin-top: 5px; opacity: 0.9;">Manage accounts, users, and campaigns</p>
                        </header>

                        <div class="stats-grid">
                            <div class="stat-card">
                                <h3>Total Accounts</h3>
                                <div class="number">${stats.accounts.total}</div>
                            </div>
                            <div class="stat-card">
                                <h3>Active Accounts</h3>
                                <div class="number">${stats.accounts.active}</div>
                            </div>
                            <div class="stat-card">
                                <h3>Total Users</h3>
                                <div class="number">${stats.users.total}</div>
                            </div>
                            <div class="stat-card">
                                <h3>Pending</h3>
                                <div class="number">${stats.users.pending}</div>
                            </div>
                        </div>

                        <div class="tabs">
                            <button class="tab active" onclick="switchTab('accounts')">Accounts</button>
                            <button class="tab" onclick="switchTab('users')">Users</button>
                            <button class="tab" onclick="switchTab('proxies')">Proxies</button>
                            <button class="tab" onclick="switchTab('logs')">Logs</button>
                        </div>

                        <div id="accounts" class="tab-content active">
                            <h2 style="margin-bottom: 20px;">Accounts</h2>
                            <table>
                                <thead>
                                    <tr>
                                        <th>Phone</th>
                                        <th>Name</th>
                                        <th>Status</th>
                                        <th>Daily Sent</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${accounts.accounts.map(a => `
                                        <tr>
                                            <td>${a.phone || 'N/A'}</td>
                                            <td>${a.first_name || 'N/A'}</td>
                                            <td><span class="status ${a.status}">${a.status}</span></td>
                                            <td>${a.daily_sent || 0}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>

                        <div id="users" class="tab-content">
                            <h2 style="margin-bottom: 20px;">Users for Outreach</h2>
                            <table>
                                <thead>
                                    <tr>
                                        <th>Username</th>
                                        <th>User ID</th>
                                        <th>Status</th>
                                        <th>Priority</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${users.users.map(u => `
                                        <tr>
                                            <td>@${u.username || 'N/A'}</td>
                                            <td>${u.user_id || 'N/A'}</td>
                                            <td><span class="status ${u.status}">${u.status}</span></td>
                                            <td>${u.priority || 1}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>

                        <div id="proxies" class="tab-content">
                            <h2 style="margin-bottom: 20px;">Proxies</h2>
                            <p>Proxy management coming soon...</p>
                        </div>

                        <div id="logs" class="tab-content">
                            <h2 style="margin-bottom: 20px;">Recent Logs</h2>
                            <table>
                                <thead>
                                    <tr>
                                        <th>Action</th>
                                        <th>Account</th>
                                        <th>User</th>
                                        <th>Result</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${stats.recent_logs.map(log => `
                                        <tr>
                                            <td>${log.action || 'N/A'}</td>
                                            <td>${log.account_id || 'N/A'}</td>
                                            <td>${log.user_id || 'N/A'}</td>
                                            <td>${log.result || 'N/A'}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                `;
            }

            function switchTab(tab) {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

                event.target.classList.add('active');
                document.getElementById(tab).classList.add('active');
            }

            // Init
            if (auth) {
                showDashboard();
            } else {
                showLogin();
            }
        </script>
    </body>
    </html>
    """


if __name__ == "__main__":
    import uvicorn

    print("\n" + "=" * 70)
    print("  WEB INTERFACE STARTING")
    print("=" * 70)
    print()
    print("  URL: http://localhost:8000")
    print("  Username: admin")
    print("  Password: admin123")
    print()
    print("=" * 70)
    print()

    uvicorn.run(app, host="0.0.0.0", port=8000)

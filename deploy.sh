#!/bin/bash

# Deployment script for Telegram Outreach Web Interface
# Domain: tgspam.mrktgu.ru

set -e

echo "=== Deploying Telegram Outreach Web Interface ==="
echo ""

# 1. Install gunicorn if not installed
echo "[1/6] Checking gunicorn installation..."
if ! command -v gunicorn &> /dev/null; then
    echo "Installing gunicorn..."
    pip install gunicorn
else
    echo "Gunicorn already installed at $(which gunicorn)"
fi

# 2. Install Flask if not installed
echo ""
echo "[2/6] Checking Flask installation..."
pip install flask==3.0.0 --quiet

# 3. Copy systemd service file
echo ""
echo "[3/6] Installing systemd service..."
cp telespam-web.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable telespam-web
echo "Systemd service installed"

# 4. Copy Nginx configuration
echo ""
echo "[4/6] Installing Nginx configuration..."
cp nginx-tgspam.conf /etc/nginx/sites-available/tgspam.mrktgu.ru
ln -sf /etc/nginx/sites-available/tgspam.mrktgu.ru /etc/nginx/sites-enabled/
nginx -t
echo "Nginx configuration installed"

# 5. Start services
echo ""
echo "[5/6] Starting services..."
systemctl start telespam-web
systemctl restart nginx
echo "Services started"

# 6. Check status
echo ""
echo "[6/6] Checking service status..."
systemctl status telespam-web --no-pager -l

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Web interface should be accessible at: http://tgspam.mrktgu.ru"
echo ""
echo "To set up SSL (recommended):"
echo "  sudo certbot --nginx -d tgspam.mrktgu.ru"
echo ""
echo "To view logs:"
echo "  sudo journalctl -u telespam-web -f"
echo ""
echo "To restart service:"
echo "  sudo systemctl restart telespam-web"

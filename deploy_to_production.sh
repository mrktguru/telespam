#!/bin/bash
# Deployment script for production server
# Run this script on the production server to update the code

set -e  # Exit on error

echo "=== Deploying telespam to production ==="
echo ""

# Navigate to project directory
cd ~/telespam/telespam || cd /root/telespam/telespam

echo "Current branch:"
git branch

echo ""
echo "Fetching latest changes..."
git fetch origin claude/audit-project-changes-01RhbB1KccoAFLjDsmGAnVR9

echo ""
echo "Checking out the feature branch..."
git checkout claude/audit-project-changes-01RhbB1KccoAFLjDsmGAnVR9

echo ""
echo "Pulling latest changes..."
git pull origin claude/audit-project-changes-01RhbB1KccoAFLjDsmGAnVR9

echo ""
echo "Checking for syntax errors..."
python3 -m py_compile web_app.py
if [ $? -eq 0 ]; then
    echo "✓ No syntax errors found in web_app.py"
else
    echo "✗ Syntax errors detected! Deployment aborted."
    exit 1
fi

echo ""
echo "Restarting telespam-web service..."
sudo systemctl restart telespam-web

echo ""
echo "Waiting for service to start..."
sleep 3

echo ""
echo "Checking service status..."
sudo systemctl status telespam-web --no-pager -l

echo ""
echo "=== Deployment complete ==="
echo "Check logs with: sudo journalctl -u telespam-web -f"

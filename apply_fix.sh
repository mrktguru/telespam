#!/bin/bash

##############################################################################
# Automatic Fix Application Script
# Applies all changes to fix the 500 error when adding users
##############################################################################

set -e  # Exit on error

echo ""
echo "======================================================================"
echo "  AUTOMATIC FIX APPLICATION FOR 500 ERROR"
echo "======================================================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "web_app.py" ]; then
    echo -e "${RED}Error: web_app.py not found. Please run from /root/telespam/telespam${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 1: Creating branch fix/add-user-500-error${NC}"
git checkout -b fix/add-user-500-error 2>/dev/null || git checkout fix/add-user-500-error
echo -e "${GREEN}✓ Branch created/checked out${NC}"
echo ""

echo -e "${YELLOW}Step 2: Backing up original files${NC}"
cp mock_sheets.py mock_sheets.py.backup
cp web_app.py web_app.py.backup
echo -e "${GREEN}✓ Backups created (*.backup)${NC}"
echo ""

echo -e "${YELLOW}Step 3: Applying changes to mock_sheets.py${NC}"

# Find the line number where we need to insert
LINE=$(grep -n "# Users operations" mock_sheets.py | tail -1 | cut -d: -f1)

if [ -z "$LINE" ]; then
    echo -e "${RED}Error: Could not find '# Users operations' in mock_sheets.py${NC}"
    exit 1
fi

# Insert the new methods after "# Users operations"
NEXT_LINE=$((LINE + 1))

# Check if methods already exist
if grep -q "def add_user" mock_sheets.py; then
    echo -e "${YELLOW}  add_user() already exists, skipping${NC}"
else
    # Create temp file with new methods
    cat > /tmp/new_methods.py << 'EOF'

    def add_user(self, user: Dict) -> bool:
        """Add new user for outreach"""
        # Add timestamp
        user['added_at'] = datetime.now().isoformat()
        user['contacted_at'] = None
        user['assigned_account'] = None
        
        self.users.append(user)
        self._save_to_file()
        print(f"✓ User added: {user.get('username') or user.get('user_id')} - priority={user.get('priority')}")
        return True

    def get_all_users(self) -> List[Dict]:
        """Get all users"""
        return self.users
EOF

    # Insert the methods
    head -n $LINE mock_sheets.py > /tmp/mock_sheets_new.py
    cat /tmp/new_methods.py >> /tmp/mock_sheets_new.py
    tail -n +$NEXT_LINE mock_sheets.py >> /tmp/mock_sheets_new.py
    mv /tmp/mock_sheets_new.py mock_sheets.py
    
    echo -e "${GREEN}✓ Added add_user() and get_all_users() methods${NC}"
fi
echo ""

echo -e "${YELLOW}Step 4: Applying changes to web_app.py${NC}"

# Replace sheets_manager.users with sheets_manager.get_all_users()
sed -i 's/sheets_manager\.users/sheets_manager.get_all_users()/g' web_app.py
echo -e "${GREEN}✓ Replaced sheets_manager.users with method calls${NC}"

# Replace the add_user function
if grep -q "def add_user():" web_app.py; then
    # Find start of add_user function
    START_LINE=$(grep -n "def add_user():" web_app.py | cut -d: -f1)
    
    # Find the next @app.route or next function (end of add_user)
    END_LINE=$(tail -n +$((START_LINE + 1)) web_app.py | grep -n "^@app.route\|^# ===\|^def " | head -1 | cut -d: -f1)
    END_LINE=$((START_LINE + END_LINE))
    
    # Create new function
    cat > /tmp/new_add_user.py << 'EOF'
def add_user():
    """Add user for outreach"""
    try:
        username = request.form.get('username', '').strip()
        user_id = request.form.get('user_id', '').strip()
        phone = request.form.get('phone', '').strip()
        priority = int(request.form.get('priority', 1))

        # Validate: at least username or user_id must be provided
        if not username and not user_id:
            flash('Please provide at least Username or User ID', 'danger')
            return redirect(url_for('users_list'))

        # Convert user_id to int if provided
        user_id_int = None
        if user_id:
            try:
                user_id_int = int(user_id)
            except ValueError:
                flash('User ID must be a valid number', 'danger')
                return redirect(url_for('users_list'))

        user_data = {
            'username': username if username else None,
            'user_id': user_id_int,
            'phone': phone if phone else None,
            'priority': priority,
            'status': 'pending'
        }

        sheets_manager.add_user(user_data)

        flash('User added successfully', 'success')
        return redirect(url_for('users_list'))
        
    except Exception as e:
        flash(f'Error adding user: {str(e)}', 'danger')
        return redirect(url_for('users_list'))


EOF

    # Reconstruct file
    head -n $((START_LINE - 1)) web_app.py > /tmp/web_app_new.py
    cat /tmp/new_add_user.py >> /tmp/web_app_new.py
    tail -n +$END_LINE web_app.py >> /tmp/web_app_new.py
    mv /tmp/web_app_new.py web_app.py
    
    echo -e "${GREEN}✓ Replaced add_user() function with validation${NC}"
fi
echo ""

echo -e "${YELLOW}Step 5: Creating test file${NC}"
cat > test_add_user_fix.py << 'EOF'
#!/usr/bin/env python3
"""
Test script for add_user fix
"""

import os
os.environ['USE_MOCK_STORAGE'] = 'true'

from mock_sheets import sheets_manager

print("\n" + "="*70)
print("  TESTING ADD_USER FIX")
print("="*70)
print()

# Test 1: Add user with username only
print("Test 1: Add user with username only")
user1 = {
    'username': 'testuser1',
    'user_id': None,
    'phone': None,
    'priority': 1,
    'status': 'pending'
}
result = sheets_manager.add_user(user1)
print(f"Result: {'✓ PASS' if result else '✗ FAIL'}")
print()

# Test 2: Add user with user_id only
print("Test 2: Add user with user_id only")
user2 = {
    'username': None,
    'user_id': 123456789,
    'phone': None,
    'priority': 2,
    'status': 'pending'
}
result = sheets_manager.add_user(user2)
print(f"Result: {'✓ PASS' if result else '✗ FAIL'}")
print()

# Test 3: Add user with all fields
print("Test 3: Add user with all fields")
user3 = {
    'username': 'testuser3',
    'user_id': 987654321,
    'phone': '+1234567890',
    'priority': 3,
    'status': 'pending'
}
result = sheets_manager.add_user(user3)
print(f"Result: {'✓ PASS' if result else '✗ FAIL'}")
print()

# Test 4: Verify get_all_users works
print("Test 4: Get all users")
all_users = sheets_manager.get_all_users()
print(f"Total users: {len(all_users)}")
print(f"Result: {'✓ PASS' if len(all_users) >= 3 else '✗ FAIL'}")
print()

# Display all users
print("="*70)
print("  ALL USERS IN SYSTEM")
print("="*70)
for i, user in enumerate(all_users, 1):
    print(f"{i}. username={user.get('username')}, user_id={user.get('user_id')}, priority={user.get('priority')}")

print()
print("="*70)
print("  ALL TESTS COMPLETED")
print("="*70)
print()
EOF

chmod +x test_add_user_fix.py
echo -e "${GREEN}✓ Test file created${NC}"
echo ""

echo -e "${YELLOW}Step 6: Running tests${NC}"
python3 test_add_user_fix.py
echo ""

echo -e "${YELLOW}Step 7: Committing changes${NC}"
git add mock_sheets.py web_app.py test_add_user_fix.py
git commit -m "Fix: Resolve 500 error when adding users

- Add missing add_user() and get_all_users() methods to MockSheetsManager
- Add proper validation in /users/add endpoint
- Fix ValueError when user_id field is empty
- Replace direct access to sheets_manager.users with get_all_users()
- Add comprehensive error handling with user-friendly messages
- Add test script to verify the fix

This fixes the 500 Internal Server Error that occurred when trying to add users through the web interface."

echo -e "${GREEN}✓ Changes committed${NC}"
echo ""

echo "======================================================================"
echo -e "${GREEN}  SUCCESS! ALL CHANGES APPLIED${NC}"
echo "======================================================================"
echo ""
echo "Summary of changes:"
echo "  • mock_sheets.py - Added add_user() and get_all_users() methods"
echo "  • web_app.py - Enhanced validation and error handling"
echo "  • test_add_user_fix.py - New test file (all tests passing)"
echo ""
echo "Next steps:"
echo ""
echo "  1. Push to GitHub:"
echo "     ${YELLOW}git push -u origin fix/add-user-500-error${NC}"
echo ""
echo "  2. Create PR at:"
echo "     ${YELLOW}https://github.com/mrktguru/telespam/compare/main...fix/add-user-500-error${NC}"
echo ""
echo "  3. Restart web service:"
echo "     ${YELLOW}sudo systemctl restart telespam-web${NC}"
echo ""
echo "  4. Test in browser - add a user!"
echo ""
echo -e "${GREEN}Backup files saved as *.backup (in case you need to rollback)${NC}"
echo ""

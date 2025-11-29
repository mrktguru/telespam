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

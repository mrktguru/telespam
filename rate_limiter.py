#!/usr/bin/env python3
"""
Rate Limiter - Control message sending rate per account
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
from pathlib import Path


class RateLimiter:
    """
    Rate limiter for message sending

    Supports:
    - Messages per hour limit
    - Messages per day limit
    - Even distribution of messages
    """

    def __init__(self, storage_file: str = "rate_limits.json"):
        self.storage_file = Path(storage_file)
        self.limits: Dict[str, Dict] = {}
        self.history: Dict[str, List[datetime]] = {}
        self.load()

    def load(self):
        """Load rate limits from storage"""
        if self.storage_file.exists():
            with open(self.storage_file, 'r') as f:
                data = json.load(f)
                self.limits = data.get('limits', {})

                # Convert history timestamps back to datetime
                history = data.get('history', {})
                self.history = {}
                for account_id, timestamps in history.items():
                    self.history[account_id] = [
                        datetime.fromisoformat(ts) for ts in timestamps
                    ]

    def save(self):
        """Save rate limits to storage"""
        # Convert datetime to ISO format for JSON
        history_json = {}
        for account_id, timestamps in self.history.items():
            history_json[account_id] = [
                ts.isoformat() for ts in timestamps
            ]

        data = {
            'limits': self.limits,
            'history': history_json
        }

        with open(self.storage_file, 'w') as f:
            json.dump(data, f, indent=2)

    def set_limits(self, account_id: str, per_hour: Optional[int] = None, per_day: Optional[int] = None):
        """
        Set rate limits for an account

        Args:
            account_id: Account identifier
            per_hour: Messages per hour (None = unlimited)
            per_day: Messages per day (None = unlimited)
        """
        if account_id not in self.limits:
            self.limits[account_id] = {}

        if per_hour is not None:
            self.limits[account_id]['per_hour'] = per_hour

        if per_day is not None:
            self.limits[account_id]['per_day'] = per_day

        self.save()

    def get_limits(self, account_id: str) -> Dict:
        """Get rate limits for an account"""
        return self.limits.get(account_id, {
            'per_hour': None,
            'per_day': None
        })

    def _cleanup_history(self, account_id: str):
        """Remove old history entries (older than 24 hours)"""
        if account_id not in self.history:
            return

        cutoff = datetime.now() - timedelta(days=1)
        self.history[account_id] = [
            ts for ts in self.history[account_id]
            if ts > cutoff
        ]

    def get_sent_count(self, account_id: str, window: str = 'hour') -> int:
        """
        Get number of messages sent in the given window

        Args:
            account_id: Account identifier
            window: 'hour' or 'day'

        Returns:
            Number of messages sent
        """
        if account_id not in self.history:
            return 0

        self._cleanup_history(account_id)

        now = datetime.now()

        if window == 'hour':
            cutoff = now - timedelta(hours=1)
        elif window == 'day':
            cutoff = now - timedelta(days=1)
        else:
            raise ValueError(f"Invalid window: {window}")

        count = sum(1 for ts in self.history[account_id] if ts > cutoff)
        return count

    def can_send(self, account_id: str) -> bool:
        """
        Check if account can send a message now

        Args:
            account_id: Account identifier

        Returns:
            True if can send, False otherwise
        """
        limits = self.get_limits(account_id)

        # Check hourly limit
        if limits.get('per_hour'):
            sent_hour = self.get_sent_count(account_id, 'hour')
            if sent_hour >= limits['per_hour']:
                return False

        # Check daily limit
        if limits.get('per_day'):
            sent_day = self.get_sent_count(account_id, 'day')
            if sent_day >= limits['per_day']:
                return False

        return True

    def record_sent(self, account_id: str):
        """
        Record that a message was sent

        Args:
            account_id: Account identifier
        """
        if account_id not in self.history:
            self.history[account_id] = []

        self.history[account_id].append(datetime.now())
        self._cleanup_history(account_id)
        self.save()

    def get_next_available_time(self, account_id: str) -> Optional[datetime]:
        """
        Get the next time when account can send a message

        Args:
            account_id: Account identifier

        Returns:
            datetime of next available time, or None if can send now
        """
        if self.can_send(account_id):
            return None

        limits = self.get_limits(account_id)
        now = datetime.now()
        next_times = []

        # Check hourly limit
        if limits.get('per_hour'):
            sent_hour = self.get_sent_count(account_id, 'hour')
            if sent_hour >= limits['per_hour']:
                # Find oldest message in the hour
                hour_ago = now - timedelta(hours=1)
                hour_messages = [ts for ts in self.history[account_id] if ts > hour_ago]
                if hour_messages:
                    oldest = min(hour_messages)
                    next_times.append(oldest + timedelta(hours=1))

        # Check daily limit
        if limits.get('per_day'):
            sent_day = self.get_sent_count(account_id, 'day')
            if sent_day >= limits['per_day']:
                # Find oldest message in the day
                day_ago = now - timedelta(days=1)
                day_messages = [ts for ts in self.history[account_id] if ts > day_ago]
                if day_messages:
                    oldest = min(day_messages)
                    next_times.append(oldest + timedelta(days=1))

        if next_times:
            return max(next_times)

        return None

    def calculate_even_distribution(self, account_id: str, total_messages: int) -> List[datetime]:
        """
        Calculate evenly distributed send times for messages

        Args:
            account_id: Account identifier
            total_messages: Number of messages to send

        Returns:
            List of datetime objects when to send each message
        """
        limits = self.get_limits(account_id)

        # Use daily limit for distribution if set
        if limits.get('per_day'):
            messages_per_day = limits['per_day']
        else:
            messages_per_day = total_messages

        # Calculate time between messages
        day_in_seconds = 24 * 60 * 60
        interval_seconds = day_in_seconds / messages_per_day

        send_times = []
        now = datetime.now()

        for i in range(total_messages):
            # Distribute evenly throughout the day
            send_time = now + timedelta(seconds=interval_seconds * i)
            send_times.append(send_time)

        return send_times

    def get_stats(self, account_id: str) -> Dict:
        """
        Get statistics for an account

        Args:
            account_id: Account identifier

        Returns:
            Dict with stats
        """
        limits = self.get_limits(account_id)
        sent_hour = self.get_sent_count(account_id, 'hour')
        sent_day = self.get_sent_count(account_id, 'day')

        can_send_now = self.can_send(account_id)
        next_available = self.get_next_available_time(account_id)

        return {
            'limits': limits,
            'sent_hour': sent_hour,
            'sent_day': sent_day,
            'remaining_hour': (limits.get('per_hour') - sent_hour) if limits.get('per_hour') else None,
            'remaining_day': (limits.get('per_day') - sent_day) if limits.get('per_day') else None,
            'can_send': can_send_now,
            'next_available': next_available.isoformat() if next_available else None
        }


# CLI interface
def rate_limiter_cli():
    """Interactive CLI for rate limiter management"""

    print("\n" + "=" * 70)
    print("  RATE LIMITER MANAGEMENT")
    print("=" * 70)
    print()

    limiter = RateLimiter()

    # Load accounts
    import os
    os.environ['USE_MOCK_STORAGE'] = 'true'
    from mock_sheets import sheets_manager

    accounts = sheets_manager.get_all_accounts()

    if not accounts:
        print("❌ No accounts found!")
        return 1

    while True:
        print()
        print("=" * 70)
        print("  ACCOUNTS & LIMITS")
        print("=" * 70)
        print()

        for acc in accounts:
            account_id = acc['id']
            limits = limiter.get_limits(account_id)
            stats = limiter.get_stats(account_id)

            print(f"📱 {account_id} ({acc.get('phone', 'N/A')})")
            print(f"   Limits: {limits.get('per_hour', '∞')}/hour, {limits.get('per_day', '∞')}/day")
            print(f"   Sent: {stats['sent_hour']}/hour, {stats['sent_day']}/day")

            if stats['can_send']:
                print(f"   Status: ✅ Can send")
            else:
                print(f"   Status: ⏸️  Rate limited (next: {stats['next_available']})")

            print()

        print("=" * 70)
        print()
        print("Options:")
        print("  1. Set limits for account")
        print("  2. View account stats")
        print("  3. Test send (record message)")
        print("  4. Reset limits for account")
        print("  0. Exit")
        print()

        choice = input("Select option: ").strip()

        if choice == "1":
            # Set limits
            print()
            for i, acc in enumerate(accounts, 1):
                print(f"  {i}. {acc['id']} ({acc.get('phone', 'N/A')})")

            acc_choice = input(f"\nSelect account (1-{len(accounts)}): ").strip()

            try:
                account = accounts[int(acc_choice) - 1]
                account_id = account['id']

                print()
                per_hour = input("Messages per hour (Enter for unlimited): ").strip()
                per_day = input("Messages per day (Enter for unlimited): ").strip()

                per_hour = int(per_hour) if per_hour else None
                per_day = int(per_day) if per_day else None

                limiter.set_limits(account_id, per_hour=per_hour, per_day=per_day)
                print(f"\n✅ Limits set for {account_id}")

            except Exception as e:
                print(f"\n❌ Error: {e}")

        elif choice == "2":
            # View stats
            print()
            for i, acc in enumerate(accounts, 1):
                print(f"  {i}. {acc['id']} ({acc.get('phone', 'N/A')})")

            acc_choice = input(f"\nSelect account (1-{len(accounts)}): ").strip()

            try:
                account = accounts[int(acc_choice) - 1]
                account_id = account['id']

                stats = limiter.get_stats(account_id)

                print()
                print("=" * 70)
                print(f"  STATS: {account_id}")
                print("=" * 70)
                print(json.dumps(stats, indent=2))

            except Exception as e:
                print(f"\n❌ Error: {e}")

        elif choice == "3":
            # Test send
            print()
            for i, acc in enumerate(accounts, 1):
                print(f"  {i}. {acc['id']} ({acc.get('phone', 'N/A')})")

            acc_choice = input(f"\nSelect account (1-{len(accounts)}): ").strip()

            try:
                account = accounts[int(acc_choice) - 1]
                account_id = account['id']

                if limiter.can_send(account_id):
                    limiter.record_sent(account_id)
                    print(f"\n✅ Message recorded for {account_id}")
                else:
                    next_time = limiter.get_next_available_time(account_id)
                    print(f"\n❌ Rate limited! Next available: {next_time}")

            except Exception as e:
                print(f"\n❌ Error: {e}")

        elif choice == "4":
            # Reset limits
            print()
            for i, acc in enumerate(accounts, 1):
                print(f"  {i}. {acc['id']} ({acc.get('phone', 'N/A')})")

            acc_choice = input(f"\nSelect account (1-{len(accounts)}): ").strip()

            try:
                account = accounts[int(acc_choice) - 1]
                account_id = account['id']

                limiter.set_limits(account_id, per_hour=None, per_day=None)
                if account_id in limiter.history:
                    limiter.history[account_id] = []
                    limiter.save()

                print(f"\n✅ Limits reset for {account_id}")

            except Exception as e:
                print(f"\n❌ Error: {e}")

        elif choice == "0":
            break

        else:
            print("\n❌ Invalid option")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(rate_limiter_cli())

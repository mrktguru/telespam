#!/usr/bin/env python3
"""
Proxy Manager - Add, remove, test, and assign proxies to accounts
"""

import asyncio
import socket
import json
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse


class ProxyManager:
    """
    Proxy management system

    Supports:
    - SOCKS5 and HTTP proxies
    - Testing proxy connectivity
    - Assigning proxies to accounts
    """

    def __init__(self, storage_file: str = "proxies.json"):
        self.storage_file = Path(storage_file)
        self.proxies: Dict[str, Dict] = {}
        self.load()

    def load(self):
        """Load proxies from storage"""
        if self.storage_file.exists():
            with open(self.storage_file, 'r') as f:
                self.proxies = json.load(f)

    def save(self):
        """Save proxies to storage"""
        with open(self.storage_file, 'w') as f:
            json.dump(self.proxies, f, indent=2)

    def add_proxy(
        self,
        proxy_id: str,
        proxy_type: str,
        host: str,
        port: int,
        username: Optional[str] = None,
        password: Optional[str] = None
    ):
        """
        Add a proxy

        Args:
            proxy_id: Unique ID for proxy
            proxy_type: 'socks5' or 'http'
            host: Proxy host
            port: Proxy port
            username: Optional username
            password: Optional password
        """
        if proxy_type not in ['socks5', 'http']:
            raise ValueError("proxy_type must be 'socks5' or 'http'")

        self.proxies[proxy_id] = {
            'type': proxy_type,
            'host': host,
            'port': port,
            'username': username,
            'password': password,
            'status': 'untested'
        }

        self.save()

    def remove_proxy(self, proxy_id: str):
        """Remove a proxy"""
        if proxy_id in self.proxies:
            del self.proxies[proxy_id]
            self.save()

    def get_proxy(self, proxy_id: str) -> Optional[Dict]:
        """Get proxy details"""
        return self.proxies.get(proxy_id)

    def get_all_proxies(self) -> Dict[str, Dict]:
        """Get all proxies"""
        return self.proxies

    async def test_proxy(self, proxy_id: str) -> bool:
        """
        Test proxy connectivity

        Args:
            proxy_id: Proxy ID

        Returns:
            True if working, False otherwise
        """
        proxy = self.get_proxy(proxy_id)

        if not proxy:
            return False

        try:
            # Simple socket connection test
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)

            result = sock.connect_ex((proxy['host'], proxy['port']))

            sock.close()

            if result == 0:
                self.proxies[proxy_id]['status'] = 'working'
                self.save()
                return True
            else:
                self.proxies[proxy_id]['status'] = 'failed'
                self.save()
                return False

        except Exception as e:
            self.proxies[proxy_id]['status'] = 'failed'
            self.proxies[proxy_id]['error'] = str(e)
            self.save()
            return False

    def format_proxy_url(self, proxy_id: str) -> Optional[str]:
        """
        Format proxy as URL for Telethon

        Args:
            proxy_id: Proxy ID

        Returns:
            Proxy URL (e.g., socks5://user:pass@host:port)
        """
        proxy = self.get_proxy(proxy_id)

        if not proxy:
            return None

        auth = ""
        if proxy.get('username') and proxy.get('password'):
            auth = f"{proxy['username']}:{proxy['password']}@"

        return f"{proxy['type']}://{auth}{proxy['host']}:{proxy['port']}"

    def get_proxy_for_telethon(self, proxy_id: str) -> Optional[tuple]:
        """
        Get proxy in Telethon format

        Args:
            proxy_id: Proxy ID

        Returns:
            Tuple (proxy_type, host, port, username, password) or None
        """
        proxy = self.get_proxy(proxy_id)

        if not proxy:
            return None

        import socks

        proxy_type_map = {
            'socks5': socks.SOCKS5,
            'http': socks.HTTP
        }

        return (
            proxy_type_map.get(proxy['type']),
            proxy['host'],
            proxy['port'],
            True,  # rdns
            proxy.get('username'),
            proxy.get('password')
        )

    def assign_proxy_to_account(self, account_id: str, proxy_id: Optional[str]):
        """
        Assign proxy to account in mock storage

        Args:
            account_id: Account ID
            proxy_id: Proxy ID (None to remove proxy)
        """
        import os
        os.environ['USE_MOCK_STORAGE'] = 'true'
        from mock_sheets import sheets_manager

        accounts = sheets_manager.get_all_accounts()

        for acc in accounts:
            if acc['id'] == account_id:
                if proxy_id:
                    proxy = self.get_proxy(proxy_id)
                    if proxy:
                        acc['proxy'] = proxy_id
                        acc['proxy_type'] = proxy['type']
                        acc['proxy_host'] = proxy['host']
                        acc['proxy_port'] = proxy['port']
                        acc['proxy_user'] = proxy.get('username', '')
                        acc['proxy_pass'] = proxy.get('password', '')
                        acc['use_proxy'] = True
                else:
                    acc['proxy'] = None
                    acc['use_proxy'] = False

                # Update in storage
                sheets_manager.accounts = [acc if a['id'] == account_id else a for a in accounts]
                sheets_manager.save()

                break

    def parse_proxy_string(self, proxy_string: str) -> Dict:
        """
        Parse proxy string to components

        Supports formats:
        - host:port
        - type://host:port
        - type://user:pass@host:port

        Args:
            proxy_string: Proxy string

        Returns:
            Dict with proxy components
        """
        # Default type
        proxy_type = 'socks5'
        username = None
        password = None

        # Parse URL if has protocol
        if '://' in proxy_string:
            parsed = urlparse(proxy_string)

            proxy_type = parsed.scheme
            host = parsed.hostname
            port = parsed.port
            username = parsed.username
            password = parsed.password

        else:
            # Simple host:port format
            parts = proxy_string.split(':')

            if len(parts) != 2:
                raise ValueError("Invalid proxy format. Use host:port or type://host:port")

            host = parts[0]
            port = int(parts[1])

        return {
            'type': proxy_type,
            'host': host,
            'port': port,
            'username': username,
            'password': password
        }


# CLI interface
def proxy_manager_cli():
    """Interactive CLI for proxy management"""

    print("\n" + "=" * 70)
    print("  PROXY MANAGER")
    print("=" * 70)
    print()

    manager = ProxyManager()

    while True:
        print()
        print("=" * 70)
        print("  PROXIES")
        print("=" * 70)
        print()

        proxies = manager.get_all_proxies()

        if proxies:
            for proxy_id, proxy in proxies.items():
                status_icon = "✅" if proxy.get('status') == 'working' else "❌" if proxy.get('status') == 'failed' else "❓"
                auth = f" (auth: {proxy.get('username')})" if proxy.get('username') else ""

                print(f"{status_icon} {proxy_id}")
                print(f"   {proxy['type']}://{proxy['host']}:{proxy['port']}{auth}")
                print()
        else:
            print("No proxies configured")
            print()

        print("=" * 70)
        print()
        print("Options:")
        print("  1. Add proxy")
        print("  2. Add proxy from string")
        print("  3. Remove proxy")
        print("  4. Test proxy")
        print("  5. Test all proxies")
        print("  6. Assign proxy to account")
        print("  7. View account proxies")
        print("  0. Exit")
        print()

        choice = input("Select option: ").strip()

        if choice == "1":
            # Add proxy manually
            print()
            proxy_id = input("Proxy ID (e.g., proxy1): ").strip()
            proxy_type = input("Type (socks5/http): ").strip().lower()
            host = input("Host: ").strip()
            port = input("Port: ").strip()
            username = input("Username (optional): ").strip() or None
            password = input("Password (optional): ").strip() or None

            try:
                manager.add_proxy(proxy_id, proxy_type, host, int(port), username, password)
                print(f"\n✅ Proxy {proxy_id} added!")
            except Exception as e:
                print(f"\n❌ Error: {e}")

        elif choice == "2":
            # Add from string
            print()
            print("Examples:")
            print("  123.45.67.89:1080")
            print("  socks5://123.45.67.89:1080")
            print("  socks5://user:pass@123.45.67.89:1080")
            print()

            proxy_string = input("Proxy string: ").strip()
            proxy_id = input("Proxy ID: ").strip()

            try:
                components = manager.parse_proxy_string(proxy_string)
                manager.add_proxy(
                    proxy_id,
                    components['type'],
                    components['host'],
                    components['port'],
                    components.get('username'),
                    components.get('password')
                )
                print(f"\n✅ Proxy {proxy_id} added!")
            except Exception as e:
                print(f"\n❌ Error: {e}")

        elif choice == "3":
            # Remove proxy
            print()
            proxy_id = input("Proxy ID to remove: ").strip()

            manager.remove_proxy(proxy_id)
            print(f"\n✅ Proxy {proxy_id} removed!")

        elif choice == "4":
            # Test single proxy
            print()
            proxy_id = input("Proxy ID to test: ").strip()

            print(f"Testing {proxy_id}...")
            result = asyncio.run(manager.test_proxy(proxy_id))

            if result:
                print(f"✅ Proxy {proxy_id} is working!")
            else:
                print(f"❌ Proxy {proxy_id} failed!")

        elif choice == "5":
            # Test all proxies
            print()
            print("Testing all proxies...")

            async def test_all():
                tasks = [manager.test_proxy(pid) for pid in proxies.keys()]
                results = await asyncio.gather(*tasks)
                return results

            results = asyncio.run(test_all())

            for i, (proxy_id, result) in enumerate(zip(proxies.keys(), results)):
                status = "✅ Working" if result else "❌ Failed"
                print(f"{proxy_id}: {status}")

        elif choice == "6":
            # Assign proxy to account
            import os
            os.environ['USE_MOCK_STORAGE'] = 'true'
            from mock_sheets import sheets_manager

            accounts = sheets_manager.get_all_accounts()

            if not accounts:
                print("\n❌ No accounts found!")
                continue

            print()
            for i, acc in enumerate(accounts, 1):
                current_proxy = acc.get('proxy', 'None')
                print(f"  {i}. {acc['id']} ({acc.get('phone', 'N/A')}) - Proxy: {current_proxy}")

            acc_choice = input(f"\nSelect account (1-{len(accounts)}): ").strip()

            try:
                account = accounts[int(acc_choice) - 1]

                print()
                print("Available proxies:")
                for i, proxy_id in enumerate(proxies.keys(), 1):
                    print(f"  {i}. {proxy_id}")
                print(f"  0. Remove proxy")

                proxy_choice = input(f"\nSelect proxy (0-{len(proxies)}): ").strip()

                if proxy_choice == "0":
                    manager.assign_proxy_to_account(account['id'], None)
                    print(f"\n✅ Proxy removed from {account['id']}")
                else:
                    proxy_id = list(proxies.keys())[int(proxy_choice) - 1]
                    manager.assign_proxy_to_account(account['id'], proxy_id)
                    print(f"\n✅ Proxy {proxy_id} assigned to {account['id']}")

            except Exception as e:
                print(f"\n❌ Error: {e}")

        elif choice == "7":
            # View account proxies
            import os
            os.environ['USE_MOCK_STORAGE'] = 'true'
            from mock_sheets import sheets_manager

            accounts = sheets_manager.get_all_accounts()

            print()
            print("=" * 70)
            print("  ACCOUNT PROXIES")
            print("=" * 70)
            print()

            for acc in accounts:
                proxy_id = acc.get('proxy', 'None')
                use_proxy = acc.get('use_proxy', False)

                print(f"📱 {acc['id']} ({acc.get('phone', 'N/A')})")
                print(f"   Proxy: {proxy_id} ({'enabled' if use_proxy else 'disabled'})")
                print()

        elif choice == "0":
            break

        else:
            print("\n❌ Invalid option")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(proxy_manager_cli())

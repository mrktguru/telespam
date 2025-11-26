"""Proxy management for Telegram accounts"""

import socks
from typing import Dict, Optional
from telethon import TelegramClient
import config


def get_proxy_config(account: Dict, settings: Dict) -> Optional[Dict]:
    """
    Determine proxy configuration for an account

    Args:
        account: Account dictionary with proxy settings
        settings: Global settings dictionary

    Returns:
        Proxy configuration dict or None if proxy is disabled
    """

    # Check if proxy is globally enabled
    proxy_enabled = settings.get('proxy_enabled', config.PROXY_ENABLED)
    if isinstance(proxy_enabled, str):
        proxy_enabled = proxy_enabled.lower() in ['true', '1', 'yes']

    if not proxy_enabled:
        return None

    # Check if proxy is enabled for this account
    use_proxy = account.get('use_proxy', False)
    if isinstance(use_proxy, str):
        use_proxy = use_proxy.lower() in ['true', '1', 'yes']

    if not use_proxy:
        return None

    # Get proxy host and port (account-specific or default)
    host = account.get('proxy_host') or settings.get('default_proxy_host') or config.DEFAULT_PROXY_HOST
    port = account.get('proxy_port') or settings.get('default_proxy_port') or config.DEFAULT_PROXY_PORT

    if not host or not port:
        return None

    # Get proxy type
    proxy_type_str = (
        account.get('proxy_type') or
        settings.get('default_proxy_type') or
        config.DEFAULT_PROXY_TYPE or
        'socks5'
    )

    # Map proxy type string to socks constant
    proxy_type_map = {
        'socks5': socks.SOCKS5,
        'socks4': socks.SOCKS4,
        'http': socks.HTTP,
        'https': socks.HTTP
    }

    proxy_type = proxy_type_map.get(proxy_type_str.lower(), socks.SOCKS5)

    # Build proxy config
    proxy = {
        'proxy_type': proxy_type,
        'addr': host,
        'port': int(port),
    }

    # Add authentication if provided
    user = account.get('proxy_user') or settings.get('default_proxy_user') or config.DEFAULT_PROXY_USER
    password = account.get('proxy_pass') or settings.get('default_proxy_pass') or config.DEFAULT_PROXY_PASS

    if user:
        proxy['username'] = user
        if password:
            proxy['password'] = password

    return proxy


async def get_client(
    account: Dict,
    settings: Dict,
    api_id: Optional[int] = None,
    api_hash: Optional[str] = None
) -> TelegramClient:
    """
    Create Telegram client with proxy support

    Args:
        account: Account dictionary with session file and proxy settings
        settings: Global settings dictionary
        api_id: Telegram API ID (from config if not provided)
        api_hash: Telegram API hash (from config if not provided)

    Returns:
        TelegramClient instance
    """

    # Get API credentials
    if not api_id:
        api_id = settings.get('api_id') or config.API_ID
    if not api_hash:
        api_hash = settings.get('api_hash') or config.API_HASH

    if not api_id or not api_hash:
        raise ValueError("API_ID and API_HASH must be set")

    # Get proxy config
    proxy = get_proxy_config(account, settings)

    # Get session file
    session_file = account.get('session_file')
    if not session_file:
        raise ValueError("Account session_file not set")

    # Create client
    client = TelegramClient(
        session_file,
        int(api_id),
        api_hash,
        proxy=proxy
    )

    return client


def test_proxy(proxy_config: Dict) -> bool:
    """
    Test if proxy is working

    Args:
        proxy_config: Proxy configuration dict

    Returns:
        True if proxy is working, False otherwise
    """

    try:
        import socket
        import socks as pysocks

        # Create a socket through the proxy
        sock = pysocks.socksocket()
        sock.set_proxy(
            proxy_type=proxy_config['proxy_type'],
            addr=proxy_config['addr'],
            port=proxy_config['port'],
            username=proxy_config.get('username'),
            password=proxy_config.get('password')
        )

        # Try to connect to Telegram server
        sock.settimeout(10)
        sock.connect(('149.154.167.51', 443))  # Telegram DC1
        sock.close()

        return True

    except Exception as e:
        print(f"Proxy test failed: {e}")
        return False


def format_proxy_display(proxy_config: Optional[Dict]) -> str:
    """
    Format proxy config for display

    Args:
        proxy_config: Proxy configuration dict or None

    Returns:
        Human-readable proxy string
    """

    if not proxy_config:
        return "No proxy"

    proxy_type_map = {
        socks.SOCKS5: "SOCKS5",
        socks.SOCKS4: "SOCKS4",
        socks.HTTP: "HTTP"
    }

    proxy_type = proxy_type_map.get(proxy_config.get('proxy_type'), "Unknown")
    addr = proxy_config.get('addr', 'unknown')
    port = proxy_config.get('port', 0)
    user = proxy_config.get('username', '')

    if user:
        return f"{proxy_type}://{user}@{addr}:{port}"
    else:
        return f"{proxy_type}://{addr}:{port}"

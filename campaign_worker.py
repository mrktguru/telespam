#!/usr/bin/env python3
"""
Campaign Worker Pool - Parallel message sending with account limits
"""

import asyncio
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError, UserPrivacyRestrictedError, PeerFloodError,
    UserBannedInChannelError, ChatWriteForbiddenError
)

from database import Database
from proxy_manager import ProxyManager
import config

logger = logging.getLogger(__name__)


class CampaignWorker:
    """Worker that sends messages for a campaign using one account"""
    
    def __init__(
        self,
        campaign_id: int,
        account_phone: str,
        campaign_settings: dict,
        db: Database,
        proxy_manager: ProxyManager,
        stop_flag: asyncio.Event
    ):
        self.campaign_id = campaign_id
        self.account_phone = account_phone
        self.campaign_settings = campaign_settings
        self.db = db
        self.proxy_manager = proxy_manager
        self.stop_flag = stop_flag
        
        # Settings
        self.messages_limit = campaign_settings.get('messages_per_account', 3)
        self.delay_min = campaign_settings.get('delay_min', 100)
        self.delay_max = campaign_settings.get('delay_max', 600)
        self.rotate_ip = campaign_settings.get('rotate_ip_per_message', True)
        self.proxies = campaign_settings.get('proxies', [])
        
        # State
        self.messages_sent = 0
        self.errors = 0
        
        # Proxy rotation state
        self.current_proxy_index = 0
        
    async def run(self):
        """Main worker loop"""
        logger.info(f"Worker started for account {self.account_phone} in campaign {self.campaign_id}")
        
        try:
            # Check account limit from database
            limit_status = self.db.get_account_campaign_limit(self.campaign_id, self.account_phone)
            
            if limit_status and limit_status['status'] == 'limit_reached':
                logger.info(f"Account {self.account_phone} already reached limit")
                return
            
            if limit_status:
                self.messages_sent = limit_status['messages_sent']
            else:
                # Initialize limit tracking
                self.db.init_account_campaign_limit(
                    self.campaign_id,
                    self.account_phone,
                    self.messages_limit
                )
            
            # Main sending loop
            while not self.stop_flag.is_set():
                # Check if limit reached
                if self.messages_sent >= self.messages_limit:
                    logger.info(f"Account {self.account_phone} reached limit ({self.messages_limit})")
                    self.db.update_account_campaign_limit(
                        self.campaign_id,
                        self.account_phone,
                        {'status': 'limit_reached'}
                    )
                    break
                
                # Get next user to send to
                user = self.db.get_next_campaign_user(self.campaign_id)
                
                if not user:
                    logger.info(f"No more users for account {self.account_phone}")
                    break
                
                # Mark user as processing
                self.db.update_campaign_user(
                    user['id'],
                    {'status': 'processing'}
                )
                
                # Send message
                success, error_msg = await self.send_message_to_user(user)
                
                if success:
                    # Mark as sent
                    self.db.update_campaign_user(user['id'], {
                        'status': 'sent',
                        'contacted_at': datetime.now().isoformat(),
                        'contacted_by': self.account_phone
                    })
                    
                    # Update counter
                    self.messages_sent += 1
                    self.db.update_account_campaign_limit(
                        self.campaign_id,
                        self.account_phone,
                        {
                            'messages_sent': self.messages_sent,
                            'last_sent_at': datetime.now().isoformat()
                        }
                    )
                    
                    # Update campaign stats
                    campaign = self.db.get_campaign(self.campaign_id)
                    if campaign:
                        self.db.update_campaign(self.campaign_id, {
                            'sent_count': (campaign.get('sent_count', 0) or 0) + 1
                        })
                    
                    logger.info(f"✓ Sent to {user.get('username') or user.get('user_id')} "
                               f"({self.messages_sent}/{self.messages_limit})")
                else:
                    # Mark as failed
                    self.db.update_campaign_user(user['id'], {
                        'status': 'failed',
                        'error_message': error_msg
                    })
                    
                    # Update campaign stats
                    campaign = self.db.get_campaign(self.campaign_id)
                    if campaign:
                        self.db.update_campaign(self.campaign_id, {
                            'failed_count': (campaign.get('failed_count', 0) or 0) + 1
                        })
                    
                    self.errors += 1
                    logger.error(f"✗ Failed to send to {user.get('username')}: {error_msg}")
                
                # Random delay between messages
                if self.messages_sent < self.messages_limit and not self.stop_flag.is_set():
                    delay = random.randint(self.delay_min, self.delay_max)
                    logger.info(f"Waiting {delay}s before next message...")
                    await asyncio.sleep(delay)
        
        except Exception as e:
            logger.exception(f"Worker error for {self.account_phone}: {e}")
        finally:
            logger.info(f"Worker finished for {self.account_phone}: "
                       f"{self.messages_sent} sent, {self.errors} errors")
    
    async def send_message_to_user(self, user: dict) -> Tuple[bool, Optional[str]]:
        """Send message to one user with proxy rotation"""
        
        # Get account
        account = self.db.get_account_by_phone(self.account_phone)
        if not account:
            return False, f"Account {self.account_phone} not found"
        
        # Get session file
        session_file = Path(__file__).parent / 'sessions' / f'{self.account_phone.replace("+", "")}.session'
        if not session_file.exists():
            return False, f"Session file not found"
        
        # Get campaign
        campaign = self.db.get_campaign(self.campaign_id)
        if not campaign:
            return False, "Campaign not found"
        
        message_text = campaign.get('message_text')
        media_path = campaign.get('media_path')
        media_type = campaign.get('media_type')
        
        if not message_text:
            return False, "No message text in campaign"
        
        # Select proxy (round-robin)
        proxy = None
        proxy_config = None
        
        if self.proxies:
            proxy_id = self.proxies[self.current_proxy_index % len(self.proxies)]
            proxy = self.proxy_manager.get_proxy(proxy_id)
            
            if proxy:
                # Rotate proxy IP before sending (for mobile proxies)
                if self.rotate_ip:
                    await self.rotate_proxy_ip(proxy)
                
                # Prepare proxy config for Telethon
                import socks
                if proxy['type'] == 'socks5':
                    proxy_config = (
                        socks.SOCKS5,
                        proxy['host'],
                        proxy['port'],
                        True,  # rdns
                        proxy.get('username'),
                        proxy.get('password')
                    )
                elif proxy['type'] in ['http', 'https']:
                    proxy_config = (
                        socks.HTTP,
                        proxy['host'],
                        proxy['port'],
                        True,
                        proxy.get('username'),
                        proxy.get('password')
                    )
            
            # Move to next proxy for round-robin
            self.current_proxy_index += 1
        
        # Get API credentials (account-specific or default)
        api_id = account.get('api_id') or config.API_ID
        api_hash = account.get('api_hash') or config.API_HASH
        
        # Create Telegram client
        client = TelegramClient(
            str(session_file.with_suffix('')),
            api_id,
            api_hash,
            proxy=proxy_config
        )
        
        try:
            await client.connect()
            
            if not await client.is_user_authorized():
                return False, "Account not authorized"
            
            # Determine recipient identifier
            recipient = None
            if user.get('username'):
                recipient = user['username']
                if not recipient.startswith('@'):
                    recipient = '@' + recipient
            elif user.get('user_id'):
                try:
                    recipient = int(user['user_id'])
                except (ValueError, TypeError):
                    return False, "Invalid user_id format"
            elif user.get('phone'):
                recipient = user['phone']
            else:
                return False, "No valid recipient identifier"
            
            # Send message
            if media_path and Path(media_path).exists():
                await client.send_file(
                    recipient,
                    media_path,
                    caption=message_text
                )
            else:
                await client.send_message(recipient, message_text)
            
            return True, None
        
        except FloodWaitError as e:
            return False, f"Flood wait: {e.seconds}s"
        
        except UserPrivacyRestrictedError:
            return False, "User privacy restricted"
        
        except PeerFloodError:
            return False, "Peer flood - account limited"
        
        except UserBannedInChannelError:
            return False, "Account banned"
        
        except ChatWriteForbiddenError:
            return False, "Chat write forbidden"
        
        except ValueError as e:
            error_str = str(e).lower()
            if 'no user' in error_str or 'could not find' in error_str:
                return False, f"User not found: {recipient}"
            return False, str(e)
        
        except Exception as e:
            return False, str(e)
        
        finally:
            try:
                await client.disconnect()
            except:
                pass
    
    async def rotate_proxy_ip(self, proxy: dict):
        """Rotate proxy IP (for mobile proxies) by reconnecting"""
        try:
            # For DataImpulse and similar mobile proxies:
            # Simply disconnecting and reconnecting triggers IP rotation
            
            # Wait a moment to allow IP rotation
            await asyncio.sleep(2)
            
            logger.debug(f"Rotated IP for proxy {proxy.get('proxy_id', 'unknown')}")
        except Exception as e:
            logger.warning(f"Failed to rotate proxy IP: {e}")


class CampaignCoordinator:
    """Coordinates multiple workers for a campaign"""
    
    def __init__(self, campaign_id: int, db: Database, proxy_manager: ProxyManager):
        self.campaign_id = campaign_id
        self.db = db
        self.proxy_manager = proxy_manager
        
        self.workers: List[asyncio.Task] = []
        self.stop_flag = asyncio.Event()
        
    async def start(self):
        """Start campaign with parallel workers"""
        
        # Get campaign
        campaign = self.db.get_campaign(self.campaign_id)
        if not campaign:
            raise ValueError(f"Campaign {self.campaign_id} not found")
        
        # Parse settings
        settings = {}
        if campaign.get('settings'):
            import json
            try:
                settings = json.loads(campaign['settings'])
            except:
                settings = {}
        
        accounts = settings.get('accounts', [])
        if not accounts:
            raise ValueError("No accounts configured for campaign")
        
        # Update campaign status
        self.db.update_campaign(self.campaign_id, {
            'status': 'running',
            'started_at': datetime.now().isoformat()
        })
        
        # Create worker for each account
        for account_phone in accounts:
            worker = CampaignWorker(
                campaign_id=self.campaign_id,
                account_phone=account_phone,
                campaign_settings=settings,
                db=self.db,
                proxy_manager=self.proxy_manager,
                stop_flag=self.stop_flag
            )
            
            task = asyncio.create_task(worker.run())
            self.workers.append(task)
        
        logger.info(f"Started {len(self.workers)} workers for campaign {self.campaign_id}")
        
        # Wait for all workers to complete
        await asyncio.gather(*self.workers, return_exceptions=True)
        
        # Update campaign status
        remaining = self.db.count_campaign_users_by_status(self.campaign_id, 'new')
        
        if remaining == 0:
            self.db.update_campaign(self.campaign_id, {
                'status': 'completed',
                'completed_at': datetime.now().isoformat()
            })
            logger.info(f"Campaign {self.campaign_id} completed")
        else:
            self.db.update_campaign(self.campaign_id, {
                'status': 'paused'
            })
            logger.info(f"Campaign {self.campaign_id} paused (workers stopped)")
    
    async def stop(self):
        """Stop all workers"""
        logger.info(f"Stopping campaign {self.campaign_id}")
        self.stop_flag.set()
        
        # Wait for workers to finish (with timeout)
        if self.workers:
            await asyncio.wait(self.workers, timeout=30)
        
        # Update campaign status
        self.db.update_campaign(self.campaign_id, {
            'status': 'paused'
        })

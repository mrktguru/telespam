"""Message listener for incoming Telegram messages"""

import asyncio
import aiohttp
from typing import Dict, List
from telethon import events, TelegramClient
from datetime import datetime
import config
from database import db
from proxy import get_client


class MessageListener:
    """Listener for incoming messages from all accounts"""

    def __init__(self):
        self.clients: Dict[str, TelegramClient] = {}
        self.running = False

    async def start_listening(self):
        """Start listening for messages on all active accounts"""

        self.running = True

        # Get all active accounts
        accounts = db.get_all_accounts()
        active_accounts = [
            acc for acc in accounts
            if acc.get('status') in [
                config.AccountStatus.ACTIVE,
                config.AccountStatus.WARMING,
                config.AccountStatus.COOLDOWN
            ]
        ]

        # Get settings from config
        settings = {
            "proxy_enabled": config.PROXY_ENABLED,
            "default_proxy_type": config.DEFAULT_PROXY_TYPE,
            "default_proxy_host": config.DEFAULT_PROXY_HOST,
            "default_proxy_port": config.DEFAULT_PROXY_PORT,
            "default_proxy_user": config.DEFAULT_PROXY_USER,
            "default_proxy_pass": config.DEFAULT_PROXY_PASS,
            "api_id": config.API_ID,
            "api_hash": config.API_HASH
        }

        # Create clients for each account
        for account in active_accounts:
            try:
                account_id = account.get('id')

                # Create client
                client = await get_client(account, settings)

                # Add event handler
                @client.on(events.NewMessage(incoming=True))
                async def handler(event):
                    await self.handle_incoming_message(event, account_id)

                # Connect
                await client.connect()

                # Store client
                self.clients[account_id] = client

                print(f"Listening for messages on account {account_id} ({account.get('phone')})")

            except Exception as e:
                print(f"Failed to start listener for account {account.get('id')}: {e}")

        # Keep running
        while self.running:
            await asyncio.sleep(1)

    async def handle_incoming_message(self, event, account_id: str):
        """
        Handle incoming message

        Args:
            event: Telethon message event
            account_id: Account ID that received the message
        """

        try:
            message = event.message
            sender = await event.get_sender()

            # Get account info
            account = db.get_account(account_id)

            # Prepare message data
            message_data = {
                "user_id": sender.id,
                "username": sender.username,
                "first_name": sender.first_name,
                "account_id": account_id,
                "account_phone": account.get('phone') if account else '',
                "message": {
                    "id": message.id,
                    "text": message.text or '',
                    "date": message.date.isoformat(),
                    "type": "text"
                }
            }

            # Determine message type
            if message.photo:
                message_data["message"]["type"] = "photo"
                message_data["message"]["file_id"] = str(message.photo.id)
            elif message.voice:
                message_data["message"]["type"] = "voice"
                message_data["message"]["file_id"] = str(message.voice.id)
            elif message.video:
                message_data["message"]["type"] = "video"
                message_data["message"]["file_id"] = str(message.video.id)
            elif message.document:
                message_data["message"]["type"] = "document"
                message_data["message"]["file_id"] = str(message.document.id)

            if message.text and (message.photo or message.video or message.document):
                message_data["message"]["caption"] = message.text

            # Update conversation in database (if exists)
            conversation = db.get_conversation_by_user_id(str(sender.id))
            if conversation:
                # Update last_message_at timestamp
                # Note: We don't have update_conversation method, so we'll just log it
                pass

            # Log the received message to campaign logs (if conversation exists)
            if conversation:
                try:
                    campaigns = db.get_all_campaigns()
                    for campaign in campaigns:
                        db.add_campaign_log(
                            campaign['id'],
                            f"Received message from {sender.id}",
                            level='info',
                            details=f"Message type: {message_data['message']['type']}"
                        )
                except:
                    pass

            # Send to n8n webhook
            await self.send_to_webhook(message_data)

        except Exception as e:
            print(f"Error handling incoming message: {e}")

    async def send_to_webhook(self, message_data: Dict):
        """
        Send message data to n8n webhook

        Args:
            message_data: Message data to send
        """

        if not config.N8N_WEBHOOK_INCOMING:
            print("N8N_WEBHOOK_INCOMING not configured, skipping webhook")
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    config.N8N_WEBHOOK_INCOMING,
                    json=message_data,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        print(f"Webhook sent successfully for user {message_data['user_id']}")
                    else:
                        print(f"Webhook failed with status {response.status}")

        except Exception as e:
            print(f"Error sending webhook: {e}")

    async def stop_listening(self):
        """Stop all listeners"""

        self.running = False

        # Disconnect all clients
        for account_id, client in self.clients.items():
            try:
                await client.disconnect()
                print(f"Disconnected listener for account {account_id}")
            except Exception as e:
                print(f"Error disconnecting {account_id}: {e}")

        self.clients.clear()

    def is_running(self) -> bool:
        """Check if listener is running"""
        return self.running

    def get_active_accounts(self) -> List[str]:
        """Get list of account IDs currently being listened to"""
        return list(self.clients.keys())


# Global listener instance
message_listener = MessageListener()

"""Message sending logic for Telegram Outreach System"""

from typing import Dict, Optional
from pathlib import Path
import aiohttp
import base64
from telethon.errors import (
    FloodWaitError,
    UserBannedInChannelError,
    UserIsBlockedError,
    PeerIdInvalidError
)
import config
from sheets import sheets_manager
from proxy import get_client, get_proxy_config
from accounts import (
    select_account_for_user,
    increment_account_usage,
    set_account_cooldown
)


async def download_file(url: str, destination: Path) -> bool:
    """
    Download file from URL

    Args:
        url: File URL
        destination: Destination path

    Returns:
        True if successful
    """

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    content = await response.read()
                    destination.write_bytes(content)
                    return True
        return False
    except Exception as e:
        print(f"Error downloading file: {e}")
        return False


async def send_message(
    user_id: int,
    message_type: str,
    content: Optional[str] = None,
    file_url: Optional[str] = None,
    file_base64: Optional[str] = None,
    file_path: Optional[str] = None,
    caption: Optional[str] = None,
    filename: Optional[str] = None,
    account_id: Optional[str] = None
) -> Dict:
    """
    Send message to user

    Args:
        user_id: Target user ID
        message_type: Type of message (text, photo, video_note, voice, video, document)
        content: Text content for text messages
        file_url: URL to download file from
        file_base64: Base64 encoded file
        file_path: Local file path
        caption: Caption for media
        filename: Filename for documents
        account_id: Specific account to use (optional)

    Returns:
        Dict with success status and message info
    """

    client = None
    selected_account = None

    try:
        # Select account
        selected_account = await select_account_for_user(user_id, account_id)

        if not selected_account:
            return {
                "success": False,
                "error": "No available accounts",
                "error_code": config.ErrorCode.NO_AVAILABLE_ACCOUNTS
            }

        # Get settings
        settings = sheets_manager.get_settings()

        # Create client
        client = await get_client(selected_account, settings)
        await client.connect()

        # Get proxy info
        proxy_config = get_proxy_config(selected_account, settings)
        proxy_used = proxy_config is not None

        # Prepare file if needed
        file_to_send = None

        if message_type != config.MessageType.TEXT:
            # Handle file source
            if file_path:
                file_to_send = file_path
            elif file_base64:
                # Decode base64 and save to temp
                temp_file = config.TEMP_DIR / f"temp_{user_id}_{message_type}"
                temp_file.write_bytes(base64.b64decode(file_base64))
                file_to_send = str(temp_file)
            elif file_url:
                # Download file
                temp_file = config.TEMP_DIR / f"temp_{user_id}_{message_type}"
                if await download_file(file_url, temp_file):
                    file_to_send = str(temp_file)
                else:
                    return {
                        "success": False,
                        "error": "Failed to download file"
                    }

            if not file_to_send:
                return {
                    "success": False,
                    "error": "No file provided for media message"
                }

        # Send message based on type
        sent_message = None

        if message_type == config.MessageType.TEXT:
            sent_message = await client.send_message(user_id, content)

        elif message_type == config.MessageType.PHOTO:
            sent_message = await client.send_file(
                user_id,
                file_to_send,
                caption=caption
            )

        elif message_type == config.MessageType.VIDEO_NOTE:
            sent_message = await client.send_file(
                user_id,
                file_to_send,
                video_note=True
            )

        elif message_type == config.MessageType.VOICE:
            sent_message = await client.send_file(
                user_id,
                file_to_send,
                voice_note=True
            )

        elif message_type == config.MessageType.VIDEO:
            sent_message = await client.send_file(
                user_id,
                file_to_send,
                caption=caption
            )

        elif message_type == config.MessageType.DOCUMENT:
            sent_message = await client.send_file(
                user_id,
                file_to_send,
                caption=caption,
                force_document=True,
                attributes=[filename] if filename else None
            )

        # Cleanup temp file if created
        if file_to_send and file_to_send.startswith(str(config.TEMP_DIR)):
            Path(file_to_send).unlink(missing_ok=True)

        # Update account usage
        increment_account_usage(selected_account['id'])

        # Log success
        sheets_manager.add_log({
            "account_id": selected_account['id'],
            "user_id": user_id,
            "action": "send",
            "message_type": message_type,
            "result": "success",
            "proxy_used": proxy_used,
            "details": f"Message sent successfully"
        })

        await client.disconnect()

        return {
            "success": True,
            "message_id": sent_message.id,
            "account_id": selected_account['id'],
            "account_phone": selected_account.get('phone'),
            "proxy_used": proxy_used
        }

    except FloodWaitError as e:
        # Flood wait error - set account to cooldown
        if selected_account:
            set_account_cooldown(selected_account['id'], hours=e.seconds // 3600 + 1)

            sheets_manager.add_log({
                "account_id": selected_account['id'],
                "user_id": user_id,
                "action": "send",
                "message_type": message_type,
                "result": "error",
                "error": f"Flood wait: {e.seconds} seconds",
                "details": f"Account set to cooldown"
            })

        if client:
            await client.disconnect()

        return {
            "success": False,
            "error": "Flood wait",
            "error_code": config.ErrorCode.FLOOD_WAIT,
            "retry_after": e.seconds
        }

    except (UserBannedInChannelError, UserIsBlockedError):
        # User blocked the account
        if selected_account:
            sheets_manager.add_log({
                "account_id": selected_account['id'],
                "user_id": user_id,
                "action": "send",
                "message_type": message_type,
                "result": "error",
                "error": "User blocked",
                "details": "User has blocked this account"
            })

        if client:
            await client.disconnect()

        return {
            "success": False,
            "error": "User has blocked the account",
            "error_code": config.ErrorCode.USER_BLOCKED
        }

    except PeerIdInvalidError:
        # Invalid user ID
        if selected_account:
            sheets_manager.add_log({
                "account_id": selected_account['id'],
                "user_id": user_id,
                "action": "send",
                "message_type": message_type,
                "result": "error",
                "error": "Invalid user ID",
                "details": "PeerIdInvalidError"
            })

        if client:
            await client.disconnect()

        return {
            "success": False,
            "error": "Invalid user ID"
        }

    except Exception as e:
        # General error
        if selected_account:
            sheets_manager.add_log({
                "account_id": selected_account['id'],
                "user_id": user_id,
                "action": "send",
                "message_type": message_type,
                "result": "error",
                "error": str(e),
                "details": f"Unexpected error: {type(e).__name__}"
            })

        if client:
            await client.disconnect()

        return {
            "success": False,
            "error": str(e)
        }


async def get_dialog_history(user_id: int, limit: int = 50) -> Dict:
    """
    Get message history with a user

    Args:
        user_id: User ID
        limit: Maximum number of messages to retrieve

    Returns:
        Dict with messages
    """

    try:
        # Find which account has dialog with this user
        dialog = sheets_manager.get_dialog(user_id)

        if not dialog:
            return {
                "success": False,
                "error": "No dialog found with this user"
            }

        account_id = dialog.get('account_id')
        account = sheets_manager.get_account(account_id)

        if not account:
            return {
                "success": False,
                "error": "Account not found"
            }

        # Get settings
        settings = sheets_manager.get_settings()

        # Create client
        client = await get_client(account, settings)
        await client.connect()

        # Get messages
        messages = []
        async for message in client.iter_messages(user_id, limit=limit):
            messages.append({
                "id": message.id,
                "text": message.text,
                "date": message.date.isoformat(),
                "out": message.out,  # True if sent by us
                "type": "text" if message.text else "media"
            })

        await client.disconnect()

        return {
            "success": True,
            "user_id": user_id,
            "account_id": account_id,
            "messages": messages
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

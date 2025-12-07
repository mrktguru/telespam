"""Converter for tdata to Telethon session files"""

import zipfile
import shutil
from pathlib import Path
from uuid import uuid4
from typing import Dict, Optional
from opentele.td import TDesktop
from opentele.api import API
import config


def find_tdata_folder(base_path: Path) -> Optional[Path]:
    """Search for tdata folder in unpacked archive"""

    # Directly in root
    if (base_path / "tdata").exists():
        return base_path / "tdata"

    # In subfolder
    for item in base_path.iterdir():
        if item.is_dir():
            if (item / "tdata").exists():
                return item / "tdata"
            if item.name == "tdata":
                return item

    return None


async def process_tdata(zip_path: str, notes: str = "") -> Dict:
    """
    Process ZIP with tdata and convert to Telethon session

    Args:
        zip_path: Path to ZIP file with tdata
        notes: Optional notes about the account

    Returns:
        Dict with success status and account info or error
    """

    temp_dir = config.TEMP_DIR / f"processing_{uuid4()}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Extract ZIP
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)

        # 2. Find tdata folder
        tdata_path = find_tdata_folder(temp_dir)
        if not tdata_path:
            raise ValueError("tdata folder not found in archive")

        # 3. Convert via opentele
        tdesk = TDesktop(str(tdata_path))
        session_path = config.SESSIONS_DIR / f"{uuid4()}"

        # Convert to Telethon (flag parameter not needed for tdata)
        telethon_client = await tdesk.ToTelethon(
            session=str(session_path)
        )

        # 4. Check and get account info
        await telethon_client.connect()
        me = await telethon_client.get_me()

        if not me:
            raise ValueError("Failed to get account information")

        # 5. Rename session file to phone number
        final_session = config.SESSIONS_DIR / f"{me.phone}.session"

        # If session already exists, add suffix
        if final_session.exists():
            final_session = config.SESSIONS_DIR / f"{me.phone}_{uuid4().hex[:8]}.session"

        shutil.move(f"{session_path}.session", final_session)

        # 6. Backup original
        backup_path = config.BACKUPS_DIR / f"{me.phone}_tdata.zip"
        if backup_path.exists():
            backup_path = config.BACKUPS_DIR / f"{me.phone}_{uuid4().hex[:8]}_tdata.zip"
        shutil.copy(zip_path, backup_path)

        # 7. Delete from incoming
        Path(zip_path).unlink(missing_ok=True)

        await telethon_client.disconnect()

        return {
            "success": True,
            "account": {
                "phone": me.phone,
                "username": me.username,
                "first_name": me.first_name,
                "last_name": me.last_name,
                "session_file": str(final_session),
                "status": config.AccountStatus.WARMING,
                "notes": notes,
                "api_id": config.API_ID,  # Store API credentials used to create session
                "api_hash": config.API_HASH  # Store API credentials used to create session
            }
        }

    except Exception as e:
        error_msg = str(e)

        # Better error messages
        if "TDesktopUnauthorized" in error_msg or "unauthorized" in error_msg.lower():
            error_msg = "TDATA account is not authorized. The account was never logged in or session expired. Use an authorized Telegram Desktop tdata."
        elif "LoginFlagInvalid" in error_msg:
            error_msg = "Invalid login flag. This is a code issue, please report."
        elif "tdata folder not found" in error_msg:
            error_msg = "No tdata folder found in the archive. Make sure you're uploading the correct Telegram Desktop data."

        return {
            "success": False,
            "error": error_msg,
            "error_code": config.ErrorCode.CONVERSION_FAILED
        }

    finally:
        # Cleanup temp
        shutil.rmtree(temp_dir, ignore_errors=True)


async def process_session_file(session_path: str, notes: str = "") -> Dict:
    """
    Process existing .session file

    Args:
        session_path: Path to .session file
        notes: Optional notes about the account

    Returns:
        Dict with success status and account info or error
    """

    try:
        from telethon import TelegramClient

        # Get API credentials from config
        if not config.API_ID or not config.API_HASH:
            raise ValueError("API_ID and API_HASH must be set in environment")

        # Create client
        client = TelegramClient(
            session_path,
            int(config.API_ID),
            config.API_HASH
        )

        # Connect and get info
        await client.connect()
        me = await client.get_me()

        if not me:
            raise ValueError("Failed to get account information")

        # Copy to sessions directory with phone number
        final_session = config.SESSIONS_DIR / f"{me.phone}.session"

        if final_session.exists():
            final_session = config.SESSIONS_DIR / f"{me.phone}_{uuid4().hex[:8]}.session"

        shutil.copy(session_path, final_session)

        # Backup original if it's from incoming
        if Path(session_path).parent == config.INCOMING_DIR:
            backup_path = config.BACKUPS_DIR / f"{me.phone}_session.backup"
            if backup_path.exists():
                backup_path = config.BACKUPS_DIR / f"{me.phone}_{uuid4().hex[:8]}_session.backup"
            shutil.copy(session_path, backup_path)
            Path(session_path).unlink(missing_ok=True)

        await client.disconnect()

        return {
            "success": True,
            "account": {
                "phone": me.phone,
                "username": me.username,
                "first_name": me.first_name,
                "last_name": me.last_name,
                "session_file": str(final_session),
                "status": config.AccountStatus.WARMING,
                "notes": notes,
                "api_id": config.API_ID,  # Store API credentials used to create session
                "api_hash": config.API_HASH  # Store API credentials used to create session
            }
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_code": config.ErrorCode.CONVERSION_FAILED
        }


async def detect_and_process(file_path: str, notes: str = "") -> Dict:
    """
    Auto-detect file type and process accordingly

    Args:
        file_path: Path to file (ZIP, session, etc.)
        notes: Optional notes about the account

    Returns:
        Dict with success status and account info or error
    """

    path = Path(file_path)

    if not path.exists():
        return {
            "success": False,
            "error": f"File not found: {file_path}",
            "error_code": config.ErrorCode.INVALID_TDATA
        }

    # Check file extension
    if path.suffix.lower() == '.zip':
        return await process_tdata(file_path, notes)
    elif path.suffix.lower() == '.session':
        return await process_session_file(file_path, notes)
    elif path.is_dir() and (path / 'tdata').exists():
        # Directory with tdata - create temp zip
        temp_zip = config.TEMP_DIR / f"{uuid4()}.zip"
        shutil.make_archive(
            str(temp_zip.with_suffix('')),
            'zip',
            path
        )
        result = await process_tdata(str(temp_zip), notes)
        temp_zip.unlink(missing_ok=True)
        return result
    else:
        return {
            "success": False,
            "error": f"Unsupported file type: {path.suffix}",
            "error_code": config.ErrorCode.INVALID_TDATA
        }

#!/usr/bin/env python3
"""
Account Profile Manager - Update account name, photo, bio
"""

import asyncio
from pathlib import Path
from typing import Optional, List
from telethon import TelegramClient
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest


async def update_account_name(client: TelegramClient, first_name: str, last_name: str = ""):
    """
    Update account first name and last name

    Args:
        client: Connected TelegramClient
        first_name: New first name
        last_name: New last name (optional)

    Returns:
        Updated user object
    """
    result = await client(UpdateProfileRequest(
        first_name=first_name,
        last_name=last_name
    ))
    return result


async def update_account_bio(client: TelegramClient, bio: str):
    """
    Update account bio/about

    Args:
        client: Connected TelegramClient
        bio: New bio text (max 70 characters)

    Returns:
        Updated user object
    """
    if len(bio) > 70:
        raise ValueError("Bio must be 70 characters or less")

    result = await client(UpdateProfileRequest(about=bio))
    return result


async def get_profile_photos(client: TelegramClient):
    """
    Get all profile photos

    Args:
        client: Connected TelegramClient

    Returns:
        List of profile photo objects
    """
    photos = await client.get_profile_photos('me')
    return photos


async def delete_all_profile_photos(client: TelegramClient):
    """
    Delete all profile photos

    Args:
        client: Connected TelegramClient

    Returns:
        Result of delete operation
    """
    photos = await client.get_profile_photos('me')
    
    if not photos:
        print("No photos to delete")
        return None
    
    # Extract photo IDs
    from telethon.tl.types import InputPhoto
    photo_ids = [InputPhoto(
        id=photo.id,
        access_hash=photo.access_hash,
        file_reference=photo.file_reference
    ) for photo in photos]
    
    result = await client(DeletePhotosRequest(id=photo_ids))
    print(f"Deleted {len(photo_ids)} profile photo(s)")
    return result


async def update_account_photo(client: TelegramClient, photo_path: str, replace_all: bool = False):
    """
    Update account profile photo

    Args:
        client: Connected TelegramClient
        photo_path: Path to photo file
        replace_all: If True, delete all existing photos before uploading

    Returns:
        Updated photo object
    """
    photo_file = Path(photo_path)

    if not photo_file.exists():
        raise FileNotFoundError(f"Photo not found: {photo_path}")

    # Delete existing photos if requested
    if replace_all:
        await delete_all_profile_photos(client)
        await asyncio.sleep(1)

    # Upload photo
    file = await client.upload_file(photo_file)
    result = await client(UploadProfilePhotoRequest(file=file))

    return result


async def delete_account_photos(client: TelegramClient, photo_ids: Optional[List] = None):
    """
    Delete account profile photos

    Args:
        client: Connected TelegramClient
        photo_ids: List of photo IDs to delete (if None, deletes current photo)

    Returns:
        Result of deletion
    """
    if photo_ids is None:
        # Get current photos
        photos = await client.get_profile_photos('me')
        if photos:
            photo_ids = [photos[0]]

    if photo_ids:
        result = await client(DeletePhotosRequest(id=photo_ids))
        return result

    return None


async def upload_multiple_photos(client: TelegramClient, photo_paths: List[str], replace_existing: bool = True):
    """
    Upload multiple photos to account (carousel)

    Args:
        client: Connected TelegramClient
        photo_paths: List of paths to photo files
        replace_existing: If True, first photo replaces all existing photos

    Returns:
        List of uploaded photo objects
    """
    results = []
    
    print(f"DEBUG upload_multiple_photos: Received {len(photo_paths)} photos")

    for i, photo_path in enumerate(photo_paths):
        try:
            print(f"DEBUG: Uploading photo {i+1}/{len(photo_paths)}: {photo_path}")
            result = await update_account_photo(client, photo_path)
            results.append(result)
            print(f"DEBUG: Successfully uploaded photo {i+1}")
            await asyncio.sleep(2)  # Delay between uploads
        except Exception as e:
            print(f"ERROR: Failed to upload {photo_path}: {e}")
            import traceback
            traceback.print_exc()

    print(f"DEBUG: Uploaded {len(results)} photos successfully")
    return results


async def get_account_info(client: TelegramClient):
    """
    Get current account information

    Args:
        client: Connected TelegramClient

    Returns:
        Dict with account info
    """
    me = await client.get_me()
    full = await client.get_entity('me')

    return {
        'phone': me.phone,
        'username': me.username,
        'first_name': me.first_name,
        'last_name': me.last_name or '',
        'bio': full.about if hasattr(full, 'about') else '',
        'user_id': me.id,
        'photo_count': len(await client.get_profile_photos('me'))
    }


async def update_full_profile(
    client: TelegramClient,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    bio: Optional[str] = None,
    photo_path: Optional[str] = None,
    photo_paths: Optional[List[str]] = None
):
    """
    Update full account profile in one call

    Args:
        client: Connected TelegramClient
        first_name: New first name
        last_name: New last name
        bio: New bio
        photo_path: Single photo path
        photo_paths: Multiple photo paths (carousel)

    Returns:
        Dict with update results
    """
    results = {}

    # Update name
    if first_name or last_name:
        current = await client.get_me()
        fname = first_name if first_name else current.first_name
        lname = last_name if last_name else (current.last_name or "")

        results['name'] = await update_account_name(client, fname, lname)

    # Update bio
    if bio:
        results['bio'] = await update_account_bio(client, bio)

    # Upload single photo
    if photo_path:
        results['photo'] = await update_account_photo(client, photo_path)

    # Upload multiple photos (carousel)
    if photo_paths:
        results['photos'] = await upload_multiple_photos(client, photo_paths)

    return results


# CLI interface
async def profile_manager_cli():
    """Interactive CLI for profile management"""

    print("\n" + "=" * 70)
    print("  ACCOUNT PROFILE MANAGER")
    print("=" * 70)
    print()

    # Load session
    from phone_utils import filename_to_phone

    sessions_dir = Path(__file__).parent / "sessions"
    session_files = list(sessions_dir.glob("*.session"))

    if not session_files:
        print("❌ No session files found!")
        return 1

    print("Available accounts:")
    for i, session_file in enumerate(session_files, 1):
        phone = filename_to_phone(session_file.stem)
        print(f"  {i}. {phone}")

    print()
    choice = input(f"Select account (1-{len(session_files)}): ").strip()

    try:
        selected_session = session_files[int(choice) - 1]
    except:
        print("❌ Invalid choice")
        return 1

    # Load API credentials (use Telegram Desktop by default)
    TELEGRAM_DESKTOP_API_ID = 611335
    TELEGRAM_DESKTOP_API_HASH = "d524b414d21f4d37f08684c1df41ac9c"

    client = TelegramClient(
        str(selected_session.with_suffix('')),
        api_id=TELEGRAM_DESKTOP_API_ID,
        api_hash=TELEGRAM_DESKTOP_API_HASH
    )

    await client.connect()

    if not await client.is_user_authorized():
        print("❌ Session not authorized!")
        await client.disconnect()
        return 1

    # Show current info
    info = await get_account_info(client)

    print()
    print("=" * 70)
    print("  CURRENT PROFILE")
    print("=" * 70)
    print(f"Name: {info['first_name']} {info['last_name']}")
    print(f"Username: @{info['username']}" if info['username'] else "Username: (not set)")
    print(f"Bio: {info['bio']}" if info['bio'] else "Bio: (not set)")
    print(f"Photos: {info['photo_count']}")
    print()

    # Update menu
    print("What do you want to update?")
    print("  1. Name")
    print("  2. Bio")
    print("  3. Photo (single)")
    print("  4. Photos (carousel)")
    print("  5. All of the above")
    print("  0. Cancel")
    print()

    option = input("Select option: ").strip()

    try:
        if option == "1":
            first_name = input("New first name: ").strip()
            last_name = input("New last name (optional): ").strip()
            await update_account_name(client, first_name, last_name)
            print("✅ Name updated!")

        elif option == "2":
            bio = input("New bio (max 70 chars): ").strip()
            await update_account_bio(client, bio)
            print("✅ Bio updated!")

        elif option == "3":
            photo_path = input("Photo path: ").strip()
            await update_account_photo(client, photo_path)
            print("✅ Photo uploaded!")

        elif option == "4":
            print("Enter photo paths (one per line, empty line to finish):")
            photo_paths = []
            while True:
                path = input().strip()
                if not path:
                    break
                photo_paths.append(path)

            if photo_paths:
                await upload_multiple_photos(client, photo_paths)
                print(f"✅ {len(photo_paths)} photos uploaded!")

        elif option == "5":
            first_name = input("New first name (or Enter to skip): ").strip() or None
            last_name = input("New last name (or Enter to skip): ").strip() or None
            bio = input("New bio (or Enter to skip): ").strip() or None

            photo_option = input("Add photo? (single/carousel/no): ").strip().lower()

            photo_path = None
            photo_paths = None

            if photo_option == "single":
                photo_path = input("Photo path: ").strip()
            elif photo_option == "carousel":
                print("Enter photo paths (one per line, empty line to finish):")
                photo_paths = []
                while True:
                    path = input().strip()
                    if not path:
                        break
                    photo_paths.append(path)

            await update_full_profile(
                client,
                first_name=first_name,
                last_name=last_name,
                bio=bio,
                photo_path=photo_path,
                photo_paths=photo_paths
            )

            print("✅ Profile updated!")

        elif option == "0":
            print("Cancelled")

        else:
            print("❌ Invalid option")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    await client.disconnect()

    # Show updated info
    await client.connect()
    info = await get_account_info(client)

    print()
    print("=" * 70)
    print("  UPDATED PROFILE")
    print("=" * 70)
    print(f"Name: {info['first_name']} {info['last_name']}")
    print(f"Username: @{info['username']}" if info['username'] else "Username: (not set)")
    print(f"Bio: {info['bio']}" if info['bio'] else "Bio: (not set)")
    print(f"Photos: {info['photo_count']}")
    print()

    await client.disconnect()

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(profile_manager_cli()))

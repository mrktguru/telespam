#!/usr/bin/env python3
"""
TDATA Checker - Scan and validate TDATA archives
"""

import asyncio
import sys
from pathlib import Path
import zipfile
from uuid import uuid4
import shutil
from datetime import datetime


async def check_single_tdata(tdata_path: Path, quiet: bool = False) -> dict:
    """
    Check if tdata is authorized

    Returns:
        dict with keys: success (bool), account_info (dict or None), error (str or None)
    """

    if not quiet:
        print(f"\n{'='*60}")
        print(f"  Checking: {tdata_path.name}")
        print(f"{'='*60}")

    try:
        from opentele.td import TDesktop

        # Extract ZIP if needed
        temp_dir = None

        if tdata_path.suffix.lower() == '.zip':
            if not quiet:
                print(f"📦 Extracting ZIP...")

            temp_dir = Path(f"/tmp/tdata_check_{uuid4()}")
            temp_dir.mkdir(exist_ok=True)

            with zipfile.ZipFile(tdata_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            # Find tdata folder
            tdata_folder = None
            if (temp_dir / "tdata").exists():
                tdata_folder = temp_dir / "tdata"
            else:
                for item in temp_dir.iterdir():
                    if item.is_dir() and (item / "tdata").exists():
                        tdata_folder = item / "tdata"
                        break
                    if item.is_dir() and item.name == "tdata":
                        tdata_folder = item
                        break

            if not tdata_folder:
                return {
                    'success': False,
                    'account_info': None,
                    'error': 'No tdata folder found in archive'
                }

            tdata_str = str(tdata_folder)
        else:
            tdata_str = str(tdata_path)

        if not quiet:
            print(f"📁 Loading TDATA...")

        # Try to load
        tdesk = TDesktop(tdata_str)

        if not quiet:
            print("✓ TDATA loaded")

        # Check if authorized
        try:
            session_path = f"/tmp/test_session_{uuid4()}"
            client = await tdesk.ToTelethon(session=session_path)

            await client.connect()
            me = await client.get_me()

            if me:
                account_info = {
                    'phone': me.phone,
                    'username': me.username,
                    'first_name': me.first_name,
                    'last_name': me.last_name or '',
                    'user_id': me.id
                }

                if not quiet:
                    print(f"\n✅ AUTHORIZED!")
                    print(f"   Phone: {me.phone}")
                    print(f"   Username: @{me.username}" if me.username else "   Username: (not set)")
                    print(f"   Name: {me.first_name} {me.last_name or ''}")

                await client.disconnect()

                # Cleanup temp session
                Path(f"{session_path}.session").unlink(missing_ok=True)

                return {
                    'success': True,
                    'account_info': account_info,
                    'error': None
                }
            else:
                await client.disconnect()
                return {
                    'success': False,
                    'account_info': None,
                    'error': 'Could not get account info'
                }

        except Exception as e:
            error = str(e)

            if not quiet:
                print(f"\n❌ NOT AUTHORIZED")
                print(f"   Error: {error}")

            return {
                'success': False,
                'account_info': None,
                'error': error
            }

    except Exception as e:
        return {
            'success': False,
            'account_info': None,
            'error': str(e)
        }

    finally:
        # Cleanup
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def scan_tdata_folder(base_path: Path) -> list:
    """Scan for ZIP archives in uploads/tdata"""

    archives = []

    if not base_path.exists():
        return archives

    # Find all ZIP files in the root of tdata folder (not in subdirs)
    for item in base_path.iterdir():
        if item.is_file() and item.suffix.lower() == '.zip':
            archives.append(item)

    return sorted(archives, key=lambda x: x.name)


def move_archive(archive: Path, destination: str):
    """Move archive to valid/ or failed/ subfolder"""

    base_dir = archive.parent
    dest_dir = base_dir / destination
    dest_dir.mkdir(exist_ok=True)

    dest_path = dest_dir / archive.name

    # If file already exists, add timestamp
    if dest_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = dest_path.stem
        dest_path = dest_dir / f"{stem}_{timestamp}{dest_path.suffix}"

    shutil.move(str(archive), str(dest_path))
    return dest_path


def print_menu(archives: list):
    """Print CLI menu"""

    print("\n" + "="*60)
    print("  TDATA CHECKER - Batch Validator")
    print("="*60)
    print()

    if not archives:
        print("❌ No ZIP archives found in uploads/tdata/")
        print()
        print("Place your TDATA archives (.zip) in uploads/tdata/ folder")
        return False

    print(f"Found {len(archives)} archive(s):\n")

    for idx, archive in enumerate(archives, 1):
        size = archive.stat().st_size / (1024 * 1024)  # MB
        print(f"  [{idx}] {archive.name} ({size:.2f} MB)")

    print(f"\n  [0] Check ALL archives")
    print(f"  [q] Quit")
    print()

    return True


async def check_and_move(archive: Path):
    """Check archive and move to valid/ or failed/"""

    result = await check_single_tdata(archive, quiet=False)

    if result['success']:
        dest = move_archive(archive, 'valid')
        print(f"✅ Moved to: {dest.relative_to(Path.cwd())}")
        return 'valid', result['account_info']
    else:
        dest = move_archive(archive, 'failed')
        print(f"❌ Moved to: {dest.relative_to(Path.cwd())}")
        print(f"   Reason: {result['error']}")
        return 'failed', None


async def main():
    """Main CLI interface"""

    # Determine base path
    script_dir = Path(__file__).parent
    tdata_dir = script_dir / "uploads" / "tdata"

    # Scan for archives
    archives = scan_tdata_folder(tdata_dir)

    # Show menu
    if not print_menu(archives):
        return 1

    # Get user choice
    try:
        choice = input("Select number: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled")
        return 0

    if choice.lower() == 'q':
        print("Bye!")
        return 0

    try:
        choice_num = int(choice)
    except ValueError:
        print("❌ Invalid choice")
        return 1

    # Process choice
    results = {
        'valid': [],
        'failed': []
    }

    if choice_num == 0:
        # Check all
        print(f"\n🔄 Checking all {len(archives)} archives...\n")

        for archive in archives:
            status, info = await check_and_move(archive)
            results[status].append((archive.name, info))

        # Print summary
        print("\n" + "="*60)
        print("  SUMMARY")
        print("="*60)
        print(f"\n✅ Valid: {len(results['valid'])}")
        for name, info in results['valid']:
            if info:
                print(f"   - {name} (@{info['username'] or 'no username'})")

        print(f"\n❌ Failed: {len(results['failed'])}")
        for name, _ in results['failed']:
            print(f"   - {name}")

        print()

    elif 1 <= choice_num <= len(archives):
        # Check single
        archive = archives[choice_num - 1]
        status, info = await check_and_move(archive)

        if status == 'valid':
            print("\n🎉 Success! Archive is valid and ready to use.")
            print(f"   Next step: python add_account_cli.py uploads/tdata/valid/{archive.name}")
        else:
            print("\n💡 This TDATA is not authorized.")
            print("   You need authorized TDATA from logged-in Telegram Desktop")
    else:
        print("❌ Invalid choice")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

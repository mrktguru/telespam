#!/usr/bin/env python3
"""
Check TDATA authorization status
"""

import asyncio
import sys
from pathlib import Path
import zipfile
from uuid import uuid4


async def check_tdata(tdata_path: str):
    """Check if tdata is authorized"""

    print("=" * 60)
    print("  TDATA CHECKER")
    print("=" * 60)
    print()

    try:
        from opentele.td import TDesktop

        # If ZIP, extract first
        path = Path(tdata_path)
        temp_dir = None

        if path.suffix.lower() == '.zip':
            print(f"📦 Extracting ZIP: {path}")
            temp_dir = Path(f"/tmp/tdata_check_{uuid4()}")
            temp_dir.mkdir(exist_ok=True)

            with zipfile.ZipFile(path, 'r') as zip_ref:
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
                print("❌ No tdata folder found in archive")
                return False

            tdata_path = str(tdata_folder)

        print(f"📁 Checking TDATA: {tdata_path}")
        print()

        # Try to load
        tdesk = TDesktop(tdata_path)

        print("✓ TDATA loaded successfully")
        print()

        # Check if authorized
        try:
            # Try to convert (will fail if not authorized)
            session_path = f"/tmp/test_session_{uuid4()}"
            client = await tdesk.ToTelethon(session=session_path)

            await client.connect()
            me = await client.get_me()

            if me:
                print("=" * 60)
                print("✅ TDATA IS AUTHORIZED!")
                print("=" * 60)
                print()
                print(f"Phone: {me.phone}")
                print(f"Username: @{me.username}" if me.username else "Username: (not set)")
                print(f"Name: {me.first_name} {me.last_name or ''}")
                print(f"User ID: {me.id}")
                print()
                print("✅ You can use this TDATA without phone access!")

                await client.disconnect()

                # Cleanup temp session
                Path(f"{session_path}.session").unlink(missing_ok=True)

                return True
            else:
                print("❌ Could not get account info")
                await client.disconnect()
                return False

        except Exception as e:
            error = str(e)

            print("=" * 60)
            print("❌ TDATA IS NOT AUTHORIZED")
            print("=" * 60)
            print()
            print(f"Error: {error}")
            print()

            if "unauthorized" in error.lower():
                print("This TDATA was never logged in or session expired.")
                print()
                print("⚠️  WITHOUT PHONE ACCESS:")
                print("   - You CANNOT use this TDATA")
                print("   - You NEED either:")
                print("     1. Authorized TDATA from logged-in Telegram Desktop")
                print("     2. Access to the phone number to create new session")
                print("     3. Working .session file")
                print()
                print("💡 OPTIONS:")
                print("   - Get TDATA from LOGGED-IN Telegram Desktop")
                print("   - Buy authorized session from provider")
                print("   - Get access to phone number temporarily")

            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

    finally:
        # Cleanup
        if temp_dir and temp_dir.exists():
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    if len(sys.argv) < 2:
        print("Usage: python check_tdata.py <path_to_tdata_or_zip>")
        print()
        print("Examples:")
        print("  python check_tdata.py tg36.zip")
        print("  python check_tdata.py /path/to/tdata/")
        return 1

    tdata_path = sys.argv[1]
    result = asyncio.run(check_tdata(tdata_path))

    print()
    if result:
        print("🎉 Next step: Add this account to the system")
        print("   python add_account_cli.py " + tdata_path)
    else:
        print("💡 You need authorized TDATA or phone access")

    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())

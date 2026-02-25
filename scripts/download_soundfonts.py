"""Download free SoundFont files for music synthesis."""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOUNDFONTS_DIR = PROJECT_ROOT / "soundfonts"

# Free SoundFont download sources
SOUNDFONTS = {
    "FluidR3_GM": {
        "url": "https://keymusician01.s3.amazonaws.com/FluidR3_GM.sf2",
        "filename": "FluidR3_GM.sf2",
        "size_mb": 148,
        "description": "General MIDI SoundFont, good quality, widely used",
    },
    "MuseScore_General": {
        "url": "https://ftp.osuosl.org/pub/musescore/soundfont/MuseScore_General/MuseScore_General.sf2",
        "filename": "MuseScore_General.sf2",
        "size_mb": 208,
        "description": "MuseScore's default SoundFont, high quality",
    },
}


def download_file(url: str, dest: Path, description: str = "") -> bool:
    """Download a file with progress reporting."""
    print(f"\n📥 Downloading: {description or url}")
    print(f"   Destination: {dest}")

    try:
        def progress_hook(block_num, block_size, total_size):
            downloaded = block_num * block_size
            if total_size > 0:
                percent = min(100, downloaded * 100 // total_size)
                mb_down = downloaded / (1024 * 1024)
                mb_total = total_size / (1024 * 1024)
                sys.stdout.write(
                    f"\r   Progress: {mb_down:.1f}/{mb_total:.1f} MB ({percent}%)"
                )
                sys.stdout.flush()

        urllib.request.urlretrieve(url, str(dest), reporthook=progress_hook)
        print(f"\n   ✅ Download complete: {dest.name}")
        return True

    except Exception as e:
        print(f"\n   ❌ Download failed: {e}")
        if dest.exists():
            dest.unlink()
        return False


def main():
    SOUNDFONTS_DIR.mkdir(parents=True, exist_ok=True)

    print("🎹 Hachimi Music - SoundFont Downloader")
    print(f"   Directory: {SOUNDFONTS_DIR}")
    print()

    # Check what's already downloaded
    existing = list(SOUNDFONTS_DIR.glob("*.sf2")) + list(SOUNDFONTS_DIR.glob("*.sf3"))
    if existing:
        print(f"   Found {len(existing)} existing SoundFont(s):")
        for sf in existing:
            size_mb = sf.stat().st_size / (1024 * 1024)
            print(f"   - {sf.name} ({size_mb:.1f} MB)")
        print()

    # Show available downloads
    print("Available SoundFonts:")
    for i, (name, info) in enumerate(SOUNDFONTS.items(), 1):
        dest = SOUNDFONTS_DIR / info["filename"]
        status = "✅ already downloaded" if dest.exists() else f"~{info['size_mb']} MB"
        print(f"  {i}. {name} ({status})")
        print(f"     {info['description']}")

    print()
    print("Which SoundFont would you like to download?")
    print("  Enter number (1-2), 'all', or 'skip': ", end="")

    choice = input().strip().lower()

    if choice == "skip":
        print("Skipping download.")
        return

    to_download = []
    if choice == "all":
        to_download = list(SOUNDFONTS.items())
    elif choice.isdigit():
        idx = int(choice) - 1
        items = list(SOUNDFONTS.items())
        if 0 <= idx < len(items):
            to_download = [items[idx]]
        else:
            print("Invalid selection.")
            return
    else:
        print("Invalid input.")
        return

    success_count = 0
    for name, info in to_download:
        dest = SOUNDFONTS_DIR / info["filename"]
        if dest.exists():
            print(f"\n⏩ {info['filename']} already exists, skipping.")
            success_count += 1
            continue

        if download_file(info["url"], dest, f"{name} - {info['description']}"):
            success_count += 1

    print(f"\n{'='*50}")
    print(f"Downloaded {success_count}/{len(to_download)} SoundFont(s).")

    if success_count > 0:
        # Update config to point to first available SoundFont
        sf_files = list(SOUNDFONTS_DIR.glob("*.sf2"))
        if sf_files:
            print(f"\nDefault SoundFont: {sf_files[0].name}")
            print("You can change this in config/settings.yaml")


if __name__ == "__main__":
    main()

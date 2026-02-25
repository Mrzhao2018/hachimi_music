"""Install FluidSynth binary for Windows (automated download)."""

from __future__ import annotations

import logging
import platform
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
FLUIDSYNTH_DIR = _PROJECT_ROOT / "fluidsynth"

# FluidSynth releases for Windows
FLUIDSYNTH_RELEASES = {
    "win64": {
        "url": "https://github.com/FluidSynth/fluidsynth/releases/download/v2.4.0/fluidsynth-2.4.0-win10-x64.zip",
        "zip_name": "fluidsynth-2.4.0-win10-x64",
        "version": "2.4.0",
    },
}


def is_fluidsynth_installed() -> dict:
    """Check if FluidSynth is available."""
    # Check our local install
    local_exe = FLUIDSYNTH_DIR / "bin" / "fluidsynth.exe"
    if local_exe.exists():
        return {"installed": True, "path": str(local_exe), "source": "local"}

    # Check system PATH
    system_exe = shutil.which("fluidsynth")
    if system_exe:
        return {"installed": True, "path": system_exe, "source": "system"}

    return {"installed": False, "path": None, "source": None}


def install_fluidsynth(progress_callback=None) -> dict:
    """Download and install FluidSynth for Windows."""
    if platform.system() != "Windows":
        return {
            "success": False,
            "message": "Auto-install only supports Windows. Install FluidSynth via your package manager.",
        }

    arch = "win64"
    info = FLUIDSYNTH_RELEASES[arch]

    if progress_callback:
        progress_callback("downloading", f"Downloading FluidSynth {info['version']}...")

    FLUIDSYNTH_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # Download zip
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        def _hook(block_num, block_size, total_size):
            if progress_callback and total_size > 0:
                pct = min(100, block_num * block_size * 100 // total_size)
                progress_callback("downloading", f"Downloading... {pct}%")

        logger.info("Downloading FluidSynth from %s", info["url"])
        urllib.request.urlretrieve(info["url"], str(tmp_path), reporthook=_hook)

        if progress_callback:
            progress_callback("extracting", "Extracting FluidSynth...")

        # Extract directly into FLUIDSYNTH_DIR
        with zipfile.ZipFile(str(tmp_path), "r") as zf:
            zf.extractall(str(FLUIDSYNTH_DIR))

        # Clean up temp file
        tmp_path.unlink(missing_ok=True)

        # Verify
        exe = FLUIDSYNTH_DIR / "bin" / "fluidsynth.exe"
        if exe.exists():
            # Add to system PATH for this process
            bin_dir = str(FLUIDSYNTH_DIR / "bin")
            import os
            if bin_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")

            if progress_callback:
                progress_callback("done", "FluidSynth installed successfully!")

            return {
                "success": True,
                "message": f"FluidSynth {info['version']} installed to {FLUIDSYNTH_DIR}",
                "path": str(exe),
            }
        else:
            return {"success": False, "message": "Installation failed: executable not found after extraction"}

    except Exception as e:
        logger.error("FluidSynth installation failed: %s", e)
        return {"success": False, "message": f"Installation failed: {e}"}


def ensure_fluidsynth_path():
    """Add local FluidSynth to PATH if installed locally."""
    import os
    bin_dir = str(FLUIDSYNTH_DIR / "bin")
    if (FLUIDSYNTH_DIR / "bin" / "fluidsynth.exe").exists():
        if bin_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = install_fluidsynth(lambda stage, msg: print(f"  [{stage}] {msg}"))
    print(result)

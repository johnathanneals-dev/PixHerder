"""
DupeFinder configuration and settings management.
Handles settings persistence, directory paths, and defaults.
"""

import json
import os
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
SETTINGS_PATH = PROJECT_ROOT / "settings.json"
SCANS_DIR = PROJECT_ROOT / "scans"
LOGS_DIR = PROJECT_ROOT / "logs"
CHECKPOINTS_DIR = PROJECT_ROOT / "checkpoints"
ACTIVITY_LOG = LOGS_DIR / "activity.log"

# Canonical image extension list -- import this everywhere, do not duplicate
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp",
    ".tiff", ".tif", ".webp", ".heic", ".heif",
}

DEFAULTS = {
    "threshold": 5,
    "move_destination": os.path.join(tempfile.gettempdir(), "DupeFinder_dupes"),
    "keep_strategy": "largest",
    "extensions": [
        ".jpg", ".jpeg", ".png", ".gif", ".bmp",
        ".tiff", ".tif", ".webp", ".heic", ".heif",
    ],
    "recursive": True,
    "port": 8787,
    "hash_size": 16,
    "staging_dir": os.path.join(tempfile.gettempdir(), "DupeFinder_Staging"),
    "keepers_dir": os.path.join(tempfile.gettempdir(), "DupeFinder_Keepers"),
    "onedrive_safe_mode": True,
    "scan_batch_size": 2000,
    "show_hints": True,
    "show_tooltips": True,
}


def default_pictures_path():
    """Return the likely OneDrive Pictures path for the current user."""
    userprofile = os.environ.get("USERPROFILE", "")
    onedrive_pics = os.path.join(userprofile, "OneDrive", "Pictures")
    if os.path.isdir(onedrive_pics):
        return onedrive_pics
    # Fallback to regular Pictures folder
    pics = os.path.join(userprofile, "Pictures")
    if os.path.isdir(pics):
        return pics
    return ""


def ensure_dirs():
    """Create scans/ and logs/ directories if they do not exist."""
    for d in (SCANS_DIR, LOGS_DIR, CHECKPOINTS_DIR):
        try:
            os.makedirs(str(d), exist_ok=True)
        except OSError:
            pass  # CFA may block; _check_write_access() handles warning


def load_settings():
    """Load settings from disk, merging with defaults for missing keys."""
    settings = dict(DEFAULTS)
    if SETTINGS_PATH.exists():
        try:
            with open(str(SETTINGS_PATH), "r") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                settings.update(saved)
        except Exception:
            pass
    return settings


def _is_system_path(path_str):
    """Check if a path points to a protected system directory."""
    if not path_str or not isinstance(path_str, str):
        return False
    lower = os.path.normpath(path_str).lower()
    windir = os.environ.get("WINDIR", "C:\\Windows").lower()
    blocked = [
        windir,
        os.path.join(windir, "system32"),
        os.environ.get("PROGRAMFILES", "C:\\Program Files").lower(),
        os.environ.get("PROGRAMFILES(X86)",
                        "C:\\Program Files (x86)").lower(),
    ]
    return any(lower == b or lower.startswith(b + os.sep) for b in blocked)


def save_settings(data):
    """Validate and write settings to disk."""
    # Merge with defaults to ensure all keys exist
    settings = dict(DEFAULTS)
    if isinstance(data, dict):
        for key in DEFAULTS:
            if key in data:
                settings[key] = data[key]

    # Validate path settings -- reject system directories
    path_keys = ["move_destination", "staging_dir", "keepers_dir"]
    for pk in path_keys:
        if pk in settings and _is_system_path(settings[pk]):
            settings[pk] = DEFAULTS[pk]

    with open(str(SETTINGS_PATH), "w") as f:
        json.dump(settings, f, indent=2)
    return settings


def verify_copy(source, destination):
    """Verify a copy succeeded by comparing file sizes.

    Returns True if destination exists and matches source size.
    """
    try:
        src_size = os.path.getsize(str(source))
        dst_size = os.path.getsize(str(destination))
        return src_size == dst_size
    except OSError:
        return False

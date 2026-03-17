"""
DupeFinder configuration and settings management.
Handles settings persistence, directory paths, and defaults.
"""

import json
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
SETTINGS_PATH = PROJECT_ROOT / "settings.json"
SCANS_DIR = PROJECT_ROOT / "scans"
LOGS_DIR = PROJECT_ROOT / "logs"

DEFAULTS = {
    "threshold": 5,
    "move_destination": "C:\\Temp\\dupes",
    "keep_strategy": "largest",
    "extensions": [
        ".jpg", ".jpeg", ".png", ".gif", ".bmp",
        ".tiff", ".tif", ".webp", ".heic", ".heif",
    ],
    "recursive": True,
    "port": 8787,
    "hash_size": 16,
}


def ensure_dirs():
    """Create scans/ and logs/ directories if they do not exist."""
    os.makedirs(str(SCANS_DIR), exist_ok=True)
    os.makedirs(str(LOGS_DIR), exist_ok=True)


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


def save_settings(data):
    """Validate and write settings to disk."""
    # Merge with defaults to ensure all keys exist
    settings = dict(DEFAULTS)
    if isinstance(data, dict):
        for key in DEFAULTS:
            if key in data:
                settings[key] = data[key]
    with open(str(SETTINGS_PATH), "w") as f:
        json.dump(settings, f, indent=2)
    return settings

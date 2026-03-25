"""
PixHerder configuration and settings management.
Handles settings persistence, directory paths, and defaults.
"""

import json
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).parent.parent
SETTINGS_PATH = PROJECT_ROOT / "settings.json"
SCANS_DIR = PROJECT_ROOT / "scans"
LOGS_DIR = PROJECT_ROOT / "logs"
CHECKPOINTS_DIR = PROJECT_ROOT / "checkpoints"
ACTIVITY_LOG = LOGS_DIR / "activity.log"
SYSTEM_RECOVERY_DIR = PROJECT_ROOT / "_system_recovery"

# ---- System Recovery: backup-before-write for critical files ----

def _ensure_system_recovery_dir():
    """Create the _system_recovery folder if it doesn't exist."""
    SYSTEM_RECOVERY_DIR.mkdir(exist_ok=True)


def backup_before_write(filepath):
    """Copy a critical file to _system_recovery before overwriting.

    Keeps only the most recent backup of each file.
    Silent on failure -- backup is best-effort, never blocks the write.
    """
    try:
        src = Path(filepath)
        if not src.exists():
            return
        _ensure_system_recovery_dir()
        dest = SYSTEM_RECOVERY_DIR / src.name
        import shutil
        shutil.copy2(str(src), str(dest))
    except Exception:
        pass  # Best-effort -- never block the actual write


def restore_from_backup(filepath):
    """Restore a critical file from _system_recovery if the primary is missing/corrupt.

    Returns True if restored, False if no backup available.
    """
    try:
        src = Path(filepath)
        backup = SYSTEM_RECOVERY_DIR / src.name
        if backup.exists() and backup.stat().st_size > 0:
            import shutil
            shutil.copy2(str(backup), str(src))
            logger.info("Restored %s from system recovery backup", src.name)
            return True
    except Exception:
        pass
    return False


def safe_json_write(filepath, data):
    """Atomic JSON write: backup existing, write to temp, replace.

    Combines backup-before-write with atomic temp+replace pattern.
    """
    filepath = Path(filepath)
    backup_before_write(filepath)
    tmp_path = str(filepath) + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, str(filepath))
    except Exception:
        # Clean up temp file on failure
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def cleanup_system_recovery():
    """Remove all files from the _system_recovery folder.

    Called during session finish / cleanup operations.
    """
    try:
        if SYSTEM_RECOVERY_DIR.is_dir():
            import shutil
            shutil.rmtree(str(SYSTEM_RECOVERY_DIR), ignore_errors=True)
            logger.info("System recovery folder cleaned up")
    except Exception:
        pass


# Canonical image extension list -- import this everywhere, do not duplicate
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp",
    ".tiff", ".tif", ".webp", ".heic", ".heif",
}

DEFAULTS = {
    "threshold": 5,
    "move_destination": os.path.join(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()), "PixHerder", "Dupes"),
    "keep_strategy": "largest",
    "extensions": [
        ".jpg", ".jpeg", ".png", ".gif", ".bmp",
        ".tiff", ".tif", ".webp", ".heic", ".heif",
    ],
    "recursive": True,
    "port": 8787,
    "hash_size": 16,
    "staging_dir": os.path.join(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()), "PixHerder", "Staging"),
    "keepers_dir": os.path.join(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()), "PixHerder", "Keepers"),
    "onedrive_safe_mode": True,
    "show_onedrive_prompts": True,
    "scan_batch_size": 2000,
    "show_hints": True,
    "show_kbd_shortcuts": True,
    "show_tooltips": True,
    "show_explanations": True,
    "persistent_logging": False,
    "debug_mode": False,
    "workflow_mode": "",
    "show_welcome": True,
    "show_tour": True,
    "open_fullscreen": True,
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
            logger.warning("CFA may be blocking: %s", d)


def load_settings():
    """Load settings from disk, merging with defaults for missing keys.

    If settings.json is missing or corrupt, tries to restore from system recovery.
    """
    settings = dict(DEFAULTS)
    loaded = False
    if SETTINGS_PATH.exists():
        try:
            with open(str(SETTINGS_PATH), "r") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                settings.update(saved)
                loaded = True
            logger.info("Settings loaded from %s", SETTINGS_PATH)
        except Exception:
            logger.warning("Settings file corrupt, attempting recovery")
            if restore_from_backup(SETTINGS_PATH):
                try:
                    with open(str(SETTINGS_PATH), "r") as f:
                        saved = json.load(f)
                    if isinstance(saved, dict):
                        settings.update(saved)
                        loaded = True
                except Exception:
                    pass
    elif not loaded:
        # File missing entirely -- try restore
        if restore_from_backup(SETTINGS_PATH):
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

    safe_json_write(SETTINGS_PATH, settings)
    logger.info("Settings saved to %s", SETTINGS_PATH)
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

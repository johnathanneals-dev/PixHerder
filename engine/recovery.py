"""
PixHerder Recovery Archive.
Maintains a rolling 2-slot archive of recycled files for undo capability.
Each slot holds files from one recycle operation. When a 3rd operation
starts, the oldest slot is purged. Archive is cleared on session finish.
"""

import json
import logging
import os
import shutil
import tempfile
from datetime import datetime

logger = logging.getLogger(__name__)


def _recovery_base():
    """Return the recovery archive base directory."""
    return os.path.join(tempfile.gettempdir(), "PixHerder_Recovery")


def _slot_path(slot_num):
    """Return path for a specific slot (1 or 2)."""
    return os.path.join(_recovery_base(), "slot_" + str(slot_num))


def _manifest_path(slot_num):
    """Return manifest file path for a slot."""
    return os.path.join(_slot_path(slot_num), "manifest.json")


def _files_path(slot_num):
    """Return files directory path for a slot."""
    return os.path.join(_slot_path(slot_num), "files")


def start_new_operation(operation_name="recycle"):
    """Prepare a new archive slot for an incoming recycle operation.

    If both slots are full, purge slot 1, shift slot 2 to slot 1,
    and use slot 2 for the new operation.

    Returns the slot number to archive into.
    """
    base = _recovery_base()
    os.makedirs(base, exist_ok=True)

    slot1_exists = os.path.isdir(_slot_path(1))
    slot2_exists = os.path.isdir(_slot_path(2))

    if slot1_exists and slot2_exists:
        # Both full — purge slot 1, shift slot 2 to slot 1
        shutil.rmtree(_slot_path(1), ignore_errors=True)
        os.rename(_slot_path(2), _slot_path(1))

    # Use slot 2 if slot 1 exists, otherwise slot 1
    active_slot = 2 if os.path.isdir(_slot_path(1)) else 1
    logger.info("Recovery: starting new operation slot %d (%s)", active_slot, operation_name)
    os.makedirs(_files_path(active_slot), exist_ok=True)

    # Write initial manifest
    manifest = {
        "operation": operation_name,
        "started": datetime.now().isoformat(),
        "files": [],
    }
    with open(_manifest_path(active_slot), "w") as f:
        json.dump(manifest, f, indent=2)

    return active_slot


def archive_file(slot_num, filepath):
    """Copy a file to the recovery archive before recycling.

    Args:
        slot_num: Active slot number from start_new_operation().
        filepath: Path to the file being recycled.

    Returns:
        True if archived successfully, False otherwise.
    """
    try:
        files_dir = _files_path(slot_num)
        filename = os.path.basename(filepath)

        # Collision avoidance
        dest = os.path.join(files_dir, filename)
        if os.path.exists(dest):
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(dest):
                dest = os.path.join(files_dir, base + "_" + str(counter) + ext)
                counter += 1

        logger.debug("Recovery: archiving %s", filepath)
        shutil.copy2(filepath, dest)

        # Update manifest
        manifest_file = _manifest_path(slot_num)
        try:
            with open(manifest_file, "r") as f:
                manifest = json.load(f)
        except Exception:
            manifest = {"files": []}

        manifest["files"].append({
            "original_path": filepath,
            "archived_as": os.path.basename(dest),
            "timestamp": datetime.now().isoformat(),
        })

        with open(manifest_file, "w") as f:
            json.dump(manifest, f, indent=2)

        return True
    except Exception:
        return False


def get_archive_status():
    """Get current archive status (slot count, file counts, total size).

    Returns:
        Dict with slots info and totals.
    """
    base = _recovery_base()
    slots = []
    total_files = 0
    total_bytes = 0

    for slot_num in (1, 2):
        slot_dir = _slot_path(slot_num)
        if not os.path.isdir(slot_dir):
            continue

        files_dir = _files_path(slot_num)
        file_count = 0
        slot_bytes = 0

        if os.path.isdir(files_dir):
            for f in os.listdir(files_dir):
                fp = os.path.join(files_dir, f)
                if os.path.isfile(fp):
                    file_count += 1
                    try:
                        slot_bytes += os.path.getsize(fp)
                    except Exception:
                        pass

        # Read manifest for operation info
        operation = "unknown"
        started = ""
        try:
            with open(_manifest_path(slot_num), "r") as f:
                manifest = json.load(f)
            operation = manifest.get("operation", "unknown")
            started = manifest.get("started", "")
        except Exception:
            pass

        slots.append({
            "slot": slot_num,
            "operation": operation,
            "started": started,
            "file_count": file_count,
            "size_bytes": slot_bytes,
        })

        total_files += file_count
        total_bytes += slot_bytes

    return {
        "slots": slots,
        "total_files": total_files,
        "total_bytes": total_bytes,
        "exists": len(slots) > 0,
    }


def list_archived_files(slot_num=None):
    """List all archived files with their original paths.

    Args:
        slot_num: Specific slot to list, or None for all.

    Returns:
        List of dicts with original_path, archived_path, slot, timestamp.
    """
    files = []
    slot_range = [slot_num] if slot_num else [1, 2]

    for sn in slot_range:
        manifest_file = _manifest_path(sn)
        if not os.path.isfile(manifest_file):
            continue

        try:
            with open(manifest_file, "r") as f:
                manifest = json.load(f)
        except Exception:
            continue

        files_dir = _files_path(sn)
        for entry in manifest.get("files", []):
            archived_name = entry.get("archived_as", "")
            archived_path = os.path.join(files_dir, archived_name)
            if os.path.isfile(archived_path):
                files.append({
                    "original_path": entry.get("original_path", ""),
                    "archived_path": archived_path,
                    "archived_name": archived_name,
                    "slot": sn,
                    "timestamp": entry.get("timestamp", ""),
                })

    return files


def restore_file(archived_path, destination_dir):
    """Restore a file from the archive to a destination directory.

    Args:
        archived_path: Path to the archived file.
        destination_dir: Directory to restore to (e.g., Staging).

    Returns:
        Dict with success, destination path, or error.
    """
    if not os.path.isfile(archived_path):
        return {"success": False, "error": "Archived file not found"}

    os.makedirs(destination_dir, exist_ok=True)
    filename = os.path.basename(archived_path)
    dest = os.path.join(destination_dir, filename)

    # Collision avoidance
    if os.path.exists(dest):
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(dest):
            dest = os.path.join(destination_dir, base + "_" + str(counter) + ext)
            counter += 1

    try:
        shutil.copy2(archived_path, dest)
        # Remove from archive after successful restore
        os.remove(archived_path)
        logger.info("Recovery: restored %s to %s", archived_path, dest)
        return {"success": True, "destination": dest}
    except Exception as e:
        return {"success": False, "error": str(e)}


def clear_archive():
    """Clear the entire recovery archive."""
    base = _recovery_base()
    if os.path.isdir(base):
        shutil.rmtree(base, ignore_errors=True)
    return {"success": True}

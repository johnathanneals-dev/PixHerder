"""
PixHerder file actions.
Move, delete, and rescue operations with per-file error handling.
Uses copy+delete instead of shutil.move for OneDrive compatibility.
"""

import json
import logging
import os
import stat
import shutil
from datetime import datetime
from pathlib import Path

from engine.comparator import pick_original
from engine.config import LOGS_DIR, verify_copy

logger = logging.getLogger(__name__)


def log_action(action_type, details):
    """Append an action log entry to the daily log file.
    Non-critical -- if logging fails, the action still proceeds.
    """
    try:
        today = datetime.now().strftime("%Y%m%d")
        log_path = LOGS_DIR / ("actions_" + today + ".log")
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action_type,
        }
        entry.update(details)
        with open(str(log_path), "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def move_files(groups, move_dir, keep_strategy="largest",
               progress_cb=None, cancel_event=None, scan_dir=None):
    """Move duplicate files to a destination directory.

    Uses copy+delete for OneDrive compatibility. Per-file error handling
    ensures one failure does not stop the batch.

    Args:
        groups: List of dicts with "keep" and "duplicates" keys,
                or list of lists of paths.
        move_dir: Destination directory path string.
        keep_strategy: Strategy for pick_original if groups are path lists.
        progress_cb: Optional callback(current, total, stage).
        cancel_event: Optional threading.Event for cancellation.

    Returns:
        Dict with moved (int), errors (list of dicts), cancelled (bool).
    """
    move_dir = Path(move_dir)
    os.makedirs(str(move_dir), exist_ok=True)
    logger.info("Moving %d files to %s", len(groups), move_dir)

    moved = 0
    skipped = 0
    error_list = []
    cancelled = False
    moved_sources = []  # Track staging paths of successfully moved files

    # Count total unique files to process (dedup across groups)
    all_dupe_paths = set()
    for group in groups:
        if isinstance(group, dict):
            for p in group.get("duplicates", []):
                all_dupe_paths.add(os.path.normpath(p))
        else:
            orig = pick_original(group, strategy=keep_strategy)
            if orig is not None:
                for p in group:
                    if str(p) != str(orig):
                        all_dupe_paths.add(os.path.normpath(str(p)))
    total = len(all_dupe_paths)

    current = 0
    processed_paths = set()

    for group in groups:
        if cancel_event and cancel_event.is_set():
            cancelled = True
            break

        # Normalize group format
        if isinstance(group, dict):
            keep = group.get("keep")
            dupes = group.get("duplicates", [])
        else:
            original = pick_original(group, strategy=keep_strategy)
            if original is None:
                continue
            keep = str(original)
            dupes = [str(p) for p in group if str(p) != keep]

        for dupe_path_str in dupes:
            norm_path = os.path.normpath(dupe_path_str)
            if norm_path in processed_paths:
                continue
            processed_paths.add(norm_path)
            if cancel_event and cancel_event.is_set():
                cancelled = True
                break

            current += 1
            dupe_path = Path(dupe_path_str)

            if not dupe_path.exists():
                skipped += 1
                if progress_cb:
                    progress_cb(current, total, "move")
                continue

            # Determine destination preserving subfolder structure
            if scan_dir:
                try:
                    rel = dupe_path.relative_to(scan_dir)
                    dest = move_dir / rel
                except ValueError:
                    dest = move_dir / dupe_path.name
            else:
                dest = move_dir / dupe_path.name
            # Collision avoidance
            if dest.exists():
                stem = dest.stem
                suffix = dest.suffix
                counter = 1
                while dest.exists():
                    dest = dest.parent / (stem + "_" + str(counter) + suffix)
                    counter += 1
            os.makedirs(str(dest.parent), exist_ok=True)

            try:
                logger.debug("Copying %s -> %s", dupe_path, dest)
                shutil.copy2(str(dupe_path), str(dest))
                if not verify_copy(dupe_path, dest):
                    error_list.append({
                        "path": dupe_path_str,
                        "error": "copy verification failed",
                    })
                    continue
                # Clear read-only flag if set (common with OneDrive staged files)
                if not os.access(str(dupe_path), os.W_OK):
                    os.chmod(str(dupe_path), stat.S_IWRITE | stat.S_IREAD)
                os.remove(str(dupe_path))
                moved += 1
                moved_sources.append(dupe_path_str)
                log_action("move", {
                    "source": dupe_path_str,
                    "destination": str(dest),
                    "keep": keep,
                    "success": True,
                })
            except Exception as e:
                logger.error("Failed to move %s: %s", dupe_path_str, e)
                error_list.append({
                    "path": dupe_path_str,
                    "error": str(e),
                })
                log_action("move", {
                    "source": dupe_path_str,
                    "success": False,
                    "error": str(e),
                })

            if progress_cb:
                progress_cb(current, total, "move")

        if cancelled:
            break

    return {"moved": moved, "skipped": skipped, "errors": error_list,
            "cancelled": cancelled, "moved_sources": moved_sources}


def delete_files(groups, keep_strategy="largest",
                 progress_cb=None, cancel_event=None,
                 archive_slot=None):
    """Delete duplicate files with per-file error handling.

    Args:
        groups: List of dicts with "keep" and "duplicates" keys,
                or list of lists of paths.
        keep_strategy: Strategy for pick_original if groups are path lists.
        progress_cb: Optional callback(current, total, stage).
        cancel_event: Optional threading.Event for cancellation.
        archive_slot: Optional recovery archive slot number for backup.

    Returns:
        Dict with deleted (int), errors (list of dicts), cancelled (bool).
    """
    deleted = 0
    skipped = 0
    error_list = []
    cancelled = False

    # Count total unique files to process (dedup across groups)
    all_dupe_paths = set()
    for group in groups:
        if isinstance(group, dict):
            for p in group.get("duplicates", []):
                all_dupe_paths.add(os.path.normpath(p))
        else:
            orig = pick_original(group, strategy=keep_strategy)
            if orig is not None:
                for p in group:
                    if str(p) != str(orig):
                        all_dupe_paths.add(os.path.normpath(str(p)))
    total = len(all_dupe_paths)
    logger.info("Recycling %d files", total)

    current = 0
    processed_paths = set()

    for group in groups:
        if cancel_event and cancel_event.is_set():
            cancelled = True
            break

        if isinstance(group, dict):
            keep = group.get("keep")
            dupes = group.get("duplicates", [])
        else:
            original = pick_original(group, strategy=keep_strategy)
            if original is None:
                continue
            keep = str(original)
            dupes = [str(p) for p in group if str(p) != keep]

        for dupe_path_str in dupes:
            norm_path = os.path.normpath(dupe_path_str)
            if norm_path in processed_paths:
                continue
            processed_paths.add(norm_path)
            if cancel_event and cancel_event.is_set():
                cancelled = True
                break

            current += 1

            if not os.path.exists(dupe_path_str):
                skipped += 1
                if progress_cb:
                    progress_cb(current, total, "delete")
                continue

            try:
                logger.debug("Recycling %s", dupe_path_str)
                # Clear read-only flag if set (common with OneDrive staged files)
                if not os.access(dupe_path_str, os.W_OK):
                    os.chmod(dupe_path_str, stat.S_IWRITE | stat.S_IREAD)
                # Send to Recycle Bin -- leave in place if recycling fails
                from engine.staging import _recycle_file_powershell
                _recycle_file_powershell(dupe_path_str, archive_slot=archive_slot)
                deleted += 1
                log_action("delete", {
                    "path": dupe_path_str,
                    "keep": keep,
                    "success": True,
                })
            except Exception as e:
                logger.error("Failed to recycle %s: %s", dupe_path_str, e)
                error_list.append({
                    "path": dupe_path_str,
                    "error": str(e),
                })
                log_action("delete", {
                    "path": dupe_path_str,
                    "success": False,
                    "error": str(e),
                })

            if progress_cb:
                progress_cb(current, total, "delete")

        if cancelled:
            break

    return {"deleted": deleted, "skipped": skipped, "errors": error_list, "cancelled": cancelled}


def rescue_file(source_path, original_path):
    """Copy a file back from the dupes folder to its original location.

    Uses copy+delete for OneDrive compatibility.

    Args:
        source_path: Current path of the file (in dupes folder).
        original_path: Where to restore it to.

    Returns:
        Dict with success (bool) and error (str or None).
    """
    try:
        source = Path(source_path)
        dest = Path(original_path)

        if not source.exists():
            return {"success": False, "error": "Source file not found"}

        # Ensure destination directory exists
        os.makedirs(str(dest.parent), exist_ok=True)

        shutil.copy2(str(source), str(dest))
        if not verify_copy(source, dest):
            return {"success": False, "error": "Copy verification failed"}
        os.remove(str(source))

        log_action("rescue", {
            "source": source_path,
            "destination": original_path,
            "success": True,
        })

        return {"success": True, "error": None}
    except Exception as e:
        log_action("rescue", {
            "source": source_path,
            "destination": original_path,
            "success": False,
            "error": str(e),
        })
        return {"success": False, "error": str(e)}

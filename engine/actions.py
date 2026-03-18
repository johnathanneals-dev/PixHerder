"""
DupeFinder file actions.
Move, delete, and rescue operations with per-file error handling.
Uses copy+delete instead of shutil.move for OneDrive compatibility.
"""

import json
import os
import stat
import shutil
from datetime import datetime
from pathlib import Path

from engine.comparator import pick_original
from engine.config import LOGS_DIR


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
               progress_cb=None, cancel_event=None):
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

    moved = 0
    skipped = 0
    error_list = []
    cancelled = False

    # Count total files to process
    total = 0
    for group in groups:
        if isinstance(group, dict):
            total += len(group.get("duplicates", []))
        else:
            total += max(0, len(group) - 1)

    current = 0

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
                current += max(0, len(group) - 1)
                if progress_cb:
                    progress_cb(current, total, "move")
                continue
            keep = str(original)
            dupes = [str(p) for p in group if str(p) != keep]

        for dupe_path_str in dupes:
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

            # Determine destination with collision avoidance
            dest = move_dir / dupe_path.name
            if dest.exists():
                stem = dest.stem
                suffix = dest.suffix
                counter = 1
                while dest.exists():
                    dest = move_dir / (stem + "_" + str(counter) + suffix)
                    counter += 1

            try:
                shutil.copy2(str(dupe_path), str(dest))
                # Clear read-only flag if set (common with OneDrive staged files)
                if not os.access(str(dupe_path), os.W_OK):
                    os.chmod(str(dupe_path), stat.S_IWRITE | stat.S_IREAD)
                os.remove(str(dupe_path))
                moved += 1
                log_action("move", {
                    "source": dupe_path_str,
                    "destination": str(dest),
                    "keep": keep,
                    "success": True,
                })
            except Exception as e:
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

    return {"moved": moved, "skipped": skipped, "errors": error_list, "cancelled": cancelled}


def delete_files(groups, keep_strategy="largest",
                 progress_cb=None, cancel_event=None):
    """Delete duplicate files with per-file error handling.

    Args:
        groups: List of dicts with "keep" and "duplicates" keys,
                or list of lists of paths.
        keep_strategy: Strategy for pick_original if groups are path lists.
        progress_cb: Optional callback(current, total, stage).
        cancel_event: Optional threading.Event for cancellation.

    Returns:
        Dict with deleted (int), errors (list of dicts), cancelled (bool).
    """
    deleted = 0
    skipped = 0
    error_list = []
    cancelled = False

    total = 0
    for group in groups:
        if isinstance(group, dict):
            total += len(group.get("duplicates", []))
        else:
            total += max(0, len(group) - 1)

    current = 0

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
                current += max(0, len(group) - 1)
                if progress_cb:
                    progress_cb(current, total, "delete")
                continue
            keep = str(original)
            dupes = [str(p) for p in group if str(p) != keep]

        for dupe_path_str in dupes:
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
                # Clear read-only flag if set (common with OneDrive staged files)
                if not os.access(dupe_path_str, os.W_OK):
                    os.chmod(dupe_path_str, stat.S_IWRITE | stat.S_IREAD)
                os.remove(dupe_path_str)
                deleted += 1
                log_action("delete", {
                    "path": dupe_path_str,
                    "keep": keep,
                    "success": True,
                })
            except Exception as e:
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

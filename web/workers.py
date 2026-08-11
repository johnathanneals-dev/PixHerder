"""
PixHerder background worker state and lifecycle.
Owns all background threads, cancel events, and progress dicts.
"""

import json
import logging
import os
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

from engine.config import (
    SCANS_DIR, ACTIVITY_LOG, DEFAULTS, IMAGE_EXTENSIONS,
    load_settings,
)
from engine.scanner import find_images
from engine.comparator import (
    find_exact_duplicates, find_perceptual_duplicates, pick_original,
)
from engine.actions import move_files, delete_files
from engine.oddball import verify_pairs, filter_oddballs
from engine.checkpoint import (
    checkpoint_path, save_checkpoint, delete_checkpoint, validate_checkpoint,
)
from engine.staging import (
    start_staging, sync_back_deletions, cleanup_staging,
)


# ---- Activity Log ----

def _log_activity(event, details=None):
    """Append an activity entry to the log file."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event": event,
        "details": details or {},
    }
    try:
        with open(str(ACTIVITY_LOG), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _read_activity(limit=50):
    """Read recent activity entries (newest first)."""
    entries = []
    try:
        with open(str(ACTIVITY_LOG), "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
    except FileNotFoundError:
        pass
    entries.reverse()
    if limit > 0:
        entries = entries[:limit]
    return entries


# ---- WorkerManager ----

class WorkerManager:
    """Owns all background worker state: threads, cancel events, progress dicts."""

    def __init__(self):
        # Guards the check-and-start sequence for every worker thread below.
        # The HTTP routes and the pywebview bridge share this one instance,
        # so without it two callers can both pass an is_alive() check and
        # both launch a worker against the same files.
        self._thread_lock = threading.RLock()

        self.scan_thread = None
        self.scan_cancel = threading.Event()
        self.scan_progress = {
            "status": "idle",
            "stage": "",
            "current": 0,
            "total": 0,
            "elapsed": 0,
            "errors": 0,
            "message": "",
            "result_file": None,
        }

        self.action_thread = None
        self.action_cancel = threading.Event()
        self.action_progress = {
            "status": "idle",
            "current": 0,
            "total": 0,
            "result": None,
        }

        self.oddball_thread = None
        self.oddball_cancel = threading.Event()
        self.oddball_progress = {
            "status": "idle",
            "current": 0,
            "total": 0,
            "result": None,
        }

        self.staging_thread = None
        self.staging_cancel = threading.Event()
        self.staging_progress = {
            "status": "idle",
            "current": 0,
            "total": 0,
            "bytes_copied": 0,
            "bytes_total": 0,
            "copied": 0,
            "skipped": 0,
            "failed": 0,
            "message": "",
            "staging_dir": None,
            "source_dir": None,
            "manifest_path": None,
        }

        self.syncback_thread = None
        self.syncback_cancel = threading.Event()
        self.syncback_progress = {
            "status": "idle",
            "current": 0,
            "total": 0,
            "deleted": 0,
            "errors": 0,
            "message": "",
        }

        self.restore_thread = None
        self.restore_progress = {
            "status": "idle",
            "current": 0,
            "total": 0,
            "copied": 0,
            "skipped": 0,
            "errors": 0,
            "message": "",
            "phase": "",
        }

    def start_worker(self, thread_attr, target, args=(), cancel_attr=None,
                     before_start=None):
        """Atomically check the "already running" guard and start a worker.

        Returns True if this caller started the worker, False if one was
        already running. Checking and starting under a single lock is what
        makes the guard sound: callers arriving from the HTTP routes and the
        pywebview bridge share one WorkerManager, and a bare
        `if thread and thread.is_alive()` test lets both of them through.

        `cancel_attr` names a cancel Event to replace with a fresh one for
        the new worker. `before_start` is a callable for priming state the
        worker depends on, such as seeding a progress dict. Both run only
        after the guard has been passed and before the thread starts, so a
        refused start can neither hand a running worker a cancel Event that
        nothing is watching nor advertise a run that never began.
        """
        with self._thread_lock:
            existing = getattr(self, thread_attr, None)
            if existing is not None and existing.is_alive():
                return False
            if cancel_attr is not None:
                setattr(self, cancel_attr, threading.Event())
            if before_start is not None:
                before_start()
            thread = threading.Thread(target=target, args=args, daemon=True)
            setattr(self, thread_attr, thread)
            thread.start()
            return True

    def reset_all_progress(self):
        """Clear all in-memory progress dicts to prevent stale state."""
        self.scan_progress.update({
            "status": "idle", "stage": "", "current": 0, "total": 0,
            "elapsed": 0, "errors": 0, "message": "", "result_file": None,
        })
        self.action_progress.update({
            "status": "idle", "current": 0, "total": 0, "result": None,
        })
        self.oddball_progress.update({
            "status": "idle", "current": 0, "total": 0, "result": None,
        })
        self.staging_progress.update({
            "status": "idle", "current": 0, "total": 0,
            "bytes_copied": 0, "bytes_total": 0, "copied": 0,
            "skipped": 0, "failed": 0, "message": "",
            "staging_dir": None, "source_dir": None, "manifest_path": None,
        })
        self.syncback_progress.update({
            "status": "idle", "current": 0, "total": 0,
            "deleted": 0, "errors": 0, "message": "",
        })
        self.restore_progress.update({
            "status": "idle", "current": 0, "total": 0,
            "copied": 0, "skipped": 0, "errors": 0,
            "message": "", "phase": "",
        })
        map_path = SCANS_DIR / "source_dupes.json"
        if map_path.exists():
            try:
                map_path.unlink()
            except Exception:
                pass


# Module-level singleton
worker_manager = WorkerManager()

# Module-level aliases — these are the SAME objects as on the instance,
# so mutations via either name are visible everywhere. Preserves backward
# compatibility for bridge.py imports.
scan_progress = worker_manager.scan_progress
scan_cancel = worker_manager.scan_cancel
action_progress = worker_manager.action_progress
action_cancel = worker_manager.action_cancel
oddball_progress = worker_manager.oddball_progress
oddball_cancel = worker_manager.oddball_cancel
staging_progress = worker_manager.staging_progress
staging_cancel = worker_manager.staging_cancel
syncback_progress = worker_manager.syncback_progress
syncback_cancel = worker_manager.syncback_cancel
restore_progress = worker_manager.restore_progress

# Backward-compat alias
_reset_all_progress = worker_manager.reset_all_progress


# ---- Progress Callbacks ----

def _update_scan_progress(current, total, stage):
    scan_progress["current"] = current
    scan_progress["total"] = total
    scan_progress["stage"] = stage


def _update_action_progress(current, total, stage):
    action_progress["current"] = current
    action_progress["total"] = total


def _update_oddball_progress(current, total, stage):
    oddball_progress["current"] = current
    oddball_progress["total"] = total


def _update_staging_progress(current, total, bytes_copied, bytes_total, stage):
    staging_progress["current"] = current
    staging_progress["total"] = total
    staging_progress["bytes_copied"] = bytes_copied
    staging_progress["bytes_total"] = bytes_total
    staging_progress["stage"] = stage
    mb_copied = bytes_copied / (1024 * 1024)
    mb_total = bytes_total / (1024 * 1024)
    staging_progress["message"] = (
        "Staging: " + str(current) + "/" + str(total) + " files ("
        + str(round(mb_copied, 1)) + " / "
        + str(round(mb_total, 1)) + " MB)"
    )


def _update_syncback_progress(current, total, stage):
    syncback_progress["current"] = current
    syncback_progress["total"] = total
    syncback_progress["message"] = (
        "Syncing: " + str(current) + "/" + str(total) + " files"
    )


# ---- Helpers ----

def _find_staging_subfolder():
    """Find the active staging subfolder reliably.

    Checks in-memory session first, then falls back to the subfolder
    with the most files. Returns the path or empty string.
    """
    mem_dir = staging_progress.get("staging_dir", "")
    if mem_dir and os.path.isdir(mem_dir):
        return mem_dir

    settings = load_settings()
    staging_base = settings.get("staging_dir", DEFAULTS["staging_dir"])
    search_paths = [staging_base]
    alt_base = os.path.join("C:\\Temp", "PixHerder_Staging")
    if alt_base != staging_base and os.path.isdir(alt_base):
        search_paths.append(alt_base)
    import tempfile as _tf
    temp_base = os.path.join(_tf.gettempdir(), "PixHerder_Staging")
    if temp_base != staging_base and temp_base != alt_base and os.path.isdir(temp_base):
        search_paths.append(temp_base)

    best_path = ""
    best_count = 0
    for base in search_paths:
        if not os.path.isdir(base):
            continue
        for d in os.listdir(base):
            candidate = os.path.join(base, d)
            if not os.path.isdir(candidate):
                continue
            count = sum(
                1 for _, _, files in os.walk(candidate)
                for f in files
                if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS
            )
            if count > best_count:
                best_count = count
                best_path = candidate

    return best_path


def _save_source_dupe_map(moved_staging_paths):
    """Save staging paths of moved duplicates so finalize can recycle source originals."""
    map_path = SCANS_DIR / "source_dupes.json"
    existing = []
    if map_path.exists():
        try:
            with open(str(map_path), "r", encoding="utf-8") as f:
                data = json.load(f)
            existing = data.get("staging_paths", [])
        except Exception:
            pass
    all_paths = list(set(existing + moved_staging_paths))
    try:
        from engine.config import safe_json_write
        safe_json_write(str(map_path), {"staging_paths": all_paths})
        logger.info("Saved %d source dupe paths to %s", len(all_paths), map_path)
    except Exception as e:
        logger.error("Failed to save source dupe map: %s", e)


def recycle_source_dupes(staging_dir, source_dir):
    """Recycle original duplicate files from the source folder."""
    map_path = SCANS_DIR / "source_dupes.json"
    if not map_path.exists():
        logger.info("No source_dupes.json found, nothing to recycle from source")
        return {"recycled": 0, "errors": [], "source_paths": []}

    try:
        with open(str(map_path), "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error("Failed to read source dupe map: %s", e)
        return {"recycled": 0, "errors": [str(e)], "source_paths": []}

    staging_paths = data.get("staging_paths", [])
    if not staging_paths:
        return {"recycled": 0, "errors": [], "source_paths": []}

    source_files = []
    for sp in staging_paths:
        try:
            rel = os.path.relpath(sp, staging_dir)
            source_path = os.path.join(source_dir, rel)
            if os.path.isfile(source_path):
                source_files.append(source_path)
            else:
                logger.debug("Source original not found (already gone?): %s",
                            source_path)
        except Exception as e:
            logger.warning("Failed to map staging path %s: %s", sp, e)

    if not source_files:
        logger.info("No source originals found to recycle")
        return {"recycled": 0, "errors": [], "source_paths": []}

    logger.info("Recycling %d source originals", len(source_files))
    from engine.staging import _recycle_files_batch_powershell
    total_recycled = 0
    all_errors = []
    chunk_size = 50
    for i in range(0, len(source_files), chunk_size):
        chunk = source_files[i:i + chunk_size]
        result = _recycle_files_batch_powershell(chunk)
        total_recycled += result.get("recycled", 0)
        all_errors.extend(result.get("errors", []))
    result = {"recycled": total_recycled, "errors": all_errors}

    try:
        map_path.unlink()
    except Exception:
        pass

    return {
        "recycled": result.get("recycled", 0),
        "errors": result.get("errors", []),
        "source_paths": source_files,
    }


def move_dupes_to_folder(staging_dir, source_dir):
    """Move duplicates into PixHerder_Duplicates folder in source directory."""
    from engine.dupe_folder import (
        create_dupe_folder, move_workspace_dupes, move_source_dupes
    )
    from engine.config import load_settings, DEFAULTS

    folders = create_dupe_folder(source_dir)

    settings = load_settings()
    dupes_dir = settings.get("move_destination", DEFAULTS["move_destination"])
    workspace_result = move_workspace_dupes(dupes_dir, folders["found_dir"])

    source_result = move_source_dupes(
        staging_dir, source_dir, folders["source_of_dir"]
    )

    total_moved = workspace_result["moved"] + source_result["moved"]
    all_errors = workspace_result["errors"] + source_result["errors"]

    logger.info("Moved %d files to %s (%d errors)",
                total_moved, folders["base_dir"], len(all_errors))

    return {
        "folder": folders["base_dir"],
        "workspace_moved": workspace_result["moved"],
        "source_moved": source_result["moved"],
        "total_moved": total_moved,
        "errors": all_errors,
    }


# ---- Background Worker Functions ----

def _run_scan(directory, mode, threshold, recursive, hash_size,
              keep_strategy, extensions, resume_data=None,
              auto_recycle=False, scan_limit=0):
    """Background scan thread target."""
    start_time = time.time()
    settings = load_settings()
    batch_size = settings.get("scan_batch_size", DEFAULTS.get("scan_batch_size", 500))

    scan_progress.update({
        "status": "running",
        "stage": "discovering",
        "mode": mode,
        "current": 0,
        "total": 0,
        "elapsed": 0,
        "errors": 0,
        "message": "Discovering images...",
        "result_file": None,
    })

    ckpt_path = checkpoint_path(directory, mode)

    try:
        ext_set = set(extensions) if extensions else None
        image_paths = list(find_images(directory, recursive, ext_set))
        total_found = len(image_paths)

        scan_limit = int(scan_limit or 0)
        if scan_limit > 0 and total_found > scan_limit:
            image_paths = image_paths[:scan_limit]

        total_images = len(image_paths)

        batch_msg = "Found " + str(total_images) + " images"
        if scan_limit > 0 and total_found > scan_limit:
            batch_msg = ("Scanning batch: " + str(total_images) + " of "
                        + str(total_found) + " total images")

        scan_progress["total"] = total_images
        scan_progress["message"] = batch_msg

        if total_images < 2:
            scan_progress.update({
                "status": "complete",
                "message": "Not enough images to compare ("
                           + str(total_images) + " found)",
            })
            return

        md5_precomputed = {}
        phash_precomputed = {}
        file_info = {}
        if resume_data:
            resume_data = validate_checkpoint(resume_data, image_paths)
            md5_precomputed = resume_data.get("md5_hashes", {})
            phash_precomputed = resume_data.get("phash_hashes", {})
            file_info = resume_data.get("file_info", {})
            skipped = len(md5_precomputed) + len(phash_precomputed)
            _log_activity("scan_resumed", {
                "directory": directory,
                "mode": mode,
                "cached_hashes": skipped,
                "stale_removed": resume_data.get("stale_removed", 0),
            })
        else:
            _log_activity("scan_started", {
                "directory": directory,
                "mode": mode,
                "total_images": total_images,
            })

        all_errors = []
        exact_groups_data = []
        perceptual_groups_data = []

        def _ckpt_md5(hashes, finfo):
            file_info.update(finfo)
            save_checkpoint(ckpt_path, {
                "directory": directory,
                "mode": mode,
                "threshold": threshold,
                "recursive": recursive,
                "hash_size": hash_size,
                "stage": "md5",
                "md5_hashes": hashes,
                "phash_hashes": phash_precomputed,
                "file_info": file_info,
            })

        def _ckpt_phash(hashes, finfo):
            file_info.update(finfo)
            save_checkpoint(ckpt_path, {
                "directory": directory,
                "mode": mode,
                "threshold": threshold,
                "recursive": recursive,
                "hash_size": hash_size,
                "stage": "phash",
                "md5_hashes": md5_precomputed,
                "phash_hashes": hashes,
                "file_info": file_info,
            })

        # Exact duplicates
        if mode in ("exact", "both"):
            scan_progress["stage"] = "md5"
            scan_progress["message"] = "Computing MD5 hashes..."
            result = find_exact_duplicates(
                image_paths,
                progress_cb=_update_scan_progress,
                cancel_event=scan_cancel,
                precomputed_hashes=md5_precomputed,
                checkpoint_cb=_ckpt_md5,
                batch_size=batch_size,
            )
            all_errors.extend(result["errors"])
            md5_precomputed = result.get("hashes", {})
            file_info.update(result.get("file_info", {}))

            if result["cancelled"]:
                save_checkpoint(ckpt_path, {
                    "directory": directory,
                    "mode": mode,
                    "threshold": threshold,
                    "recursive": recursive,
                    "hash_size": hash_size,
                    "stage": "md5",
                    "md5_hashes": md5_precomputed,
                    "phash_hashes": phash_precomputed,
                    "file_info": file_info,
                })
                scan_progress["status"] = "cancelled"
                scan_progress["message"] = "Scan cancelled by user"
                _log_activity("scan_cancelled", {
                    "directory": directory,
                    "stage": "md5",
                    "progress": str(scan_progress["current"]) + "/"
                                + str(scan_progress["total"]),
                })
                return

            for group in result["groups"]:
                original = pick_original(group, strategy=keep_strategy)
                if original is None:
                    continue
                dupes = [str(p) for p in group if p != original]
                reclaimable = 0
                for p in group:
                    if p != original:
                        try:
                            reclaimable += p.stat().st_size
                        except Exception:
                            pass
                exact_groups_data.append({
                    "keep": str(original),
                    "duplicates": dupes,
                    "files": len(group),
                    "reclaimable_bytes": reclaimable,
                    "type": "exact",
                })

        if exact_groups_data:
            exact_dupe_paths = set()
            for g in exact_groups_data:
                for d in g["duplicates"]:
                    exact_dupe_paths.add(os.path.normpath(d))
            image_paths = [p for p in image_paths
                           if os.path.normpath(str(p)) not in exact_dupe_paths]

        # Auto-recycle exact duplicates if enabled
        auto_recycled = 0
        if auto_recycle and exact_groups_data:
            scan_progress["stage"] = "auto_recycling"
            scan_progress["message"] = ("Auto-recycling "
                + str(len(exact_groups_data)) + " exact duplicate groups...")

            ar_slot = None
            try:
                from engine.recovery import start_new_operation
                ar_slot = start_new_operation("auto_recycle")
            except Exception:
                pass

            recycle_groups = []
            for g in exact_groups_data:
                recycle_groups.append({
                    "keep": g["keep"],
                    "duplicates": g["duplicates"],
                })

            recycle_result = delete_files(
                recycle_groups, keep_strategy,
                cancel_event=scan_cancel,
                archive_slot=ar_slot,
            )
            auto_recycled = recycle_result.get("deleted", 0)

            recycled_paths = set()
            for g in recycle_groups:
                for d in g["duplicates"]:
                    recycled_paths.add(os.path.normpath(d))
            image_paths = [p for p in image_paths
                           if os.path.normpath(str(p)) not in recycled_paths]

            _log_activity("auto_recycled", {
                "groups": len(exact_groups_data),
                "files": auto_recycled,
            })

            exact_groups_data = []

        # Perceptual duplicates
        if mode in ("perceptual", "both"):
            scan_progress["stage"] = "phash_hash"
            scan_progress["message"] = "Computing perceptual hashes..."
            result = find_perceptual_duplicates(
                image_paths,
                threshold=threshold,
                hash_size=hash_size,
                progress_cb=_update_scan_progress,
                cancel_event=scan_cancel,
                precomputed_hashes=phash_precomputed,
                checkpoint_cb=_ckpt_phash,
                batch_size=batch_size,
            )
            all_errors.extend(result["errors"])
            phash_precomputed = result.get("hashes", {})
            file_info.update(result.get("file_info", {}))

            if result["cancelled"]:
                save_checkpoint(ckpt_path, {
                    "directory": directory,
                    "mode": mode,
                    "threshold": threshold,
                    "recursive": recursive,
                    "hash_size": hash_size,
                    "stage": "phash",
                    "md5_hashes": md5_precomputed,
                    "phash_hashes": phash_precomputed,
                    "file_info": file_info,
                })
                scan_progress["status"] = "cancelled"
                scan_progress["message"] = "Scan cancelled by user"
                _log_activity("scan_cancelled", {
                    "directory": directory,
                    "stage": "phash",
                    "progress": str(scan_progress["current"]) + "/"
                                + str(scan_progress["total"]),
                })
                return

            for g in result["groups"]:
                paths = g["paths"]
                distances = g.get("distances", {})
                original = pick_original(paths, strategy=keep_strategy)
                if original is None:
                    continue
                dupes = [str(p) for p in paths if p != original]
                reclaimable = 0
                for p in paths:
                    if p != original:
                        try:
                            reclaimable += Path(p).stat().st_size
                        except Exception:
                            pass
                perceptual_groups_data.append({
                    "keep": str(original),
                    "duplicates": dupes,
                    "files": len(paths),
                    "reclaimable_bytes": reclaimable,
                    "distances": distances,
                    "type": "perceptual",
                })

        if scan_cancel.is_set():
            elapsed = time.time() - start_time
            scan_progress.update({
                "status": "cancelled",
                "stage": "done",
                "elapsed": round(elapsed, 1),
                "message": "Scan cancelled by user.",
            })
            _log_activity("scan_cancelled", {
                "directory": directory, "mode": mode,
            })
            return

        # Save results
        scan_progress["stage"] = "saving"
        scan_progress["message"] = "Saving results..."
        scan_progress["current"] = 0
        scan_progress["total"] = 0
        elapsed = time.time() - start_time
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = "scan_" + timestamp + "_" + mode + ".json"
        os.makedirs(str(SCANS_DIR), exist_ok=True)
        result_path = SCANS_DIR / filename

        group_files = set()
        for g in exact_groups_data:
            group_files.add(g["keep"])
            group_files.update(g["duplicates"])
        for g in perceptual_groups_data:
            group_files.add(g["keep"])
            group_files.update(g["duplicates"])
        report_file_info = {k: v for k, v in file_info.items()
                            if k in group_files}

        report = {
            "metadata": {
                "directory": directory,
                "mode": mode,
                "threshold": threshold,
                "hash_size": hash_size,
                "recursive": recursive,
                "timestamp": datetime.now().isoformat(),
                "total_images": total_images,
                "duration_seconds": round(elapsed, 1),
                "exact_groups": len(exact_groups_data),
                "perceptual_groups": len(perceptual_groups_data),
                "errors": len(all_errors),
            },
            "exact_groups": exact_groups_data,
            "perceptual_groups": perceptual_groups_data,
            "file_info": report_file_info,
        }

        from engine.config import safe_json_write
        safe_json_write(result_path, report)

        if not result_path.exists() or result_path.stat().st_size == 0:
            raise OSError(
                "Could not save scan results. If Windows Defender "
                "Controlled Folder Access is enabled, please whitelist "
                "the Python executable in Windows Security settings."
            )

        delete_checkpoint(ckpt_path)

        total_groups = len(exact_groups_data) + len(perceptual_groups_data)
        total_duplicate_files = (
            sum(len(g["duplicates"]) for g in exact_groups_data) +
            sum(len(g["duplicates"]) for g in perceptual_groups_data)
        )
        total_reclaimable = (
            sum(g["reclaimable_bytes"] for g in exact_groups_data) +
            sum(g["reclaimable_bytes"] for g in perceptual_groups_data)
        )
        mb = total_reclaimable / (1024 * 1024)

        scan_progress.update({
            "status": "complete",
            "stage": "done",
            "elapsed": round(elapsed, 1),
            "errors": len(all_errors),
            "message": ("Scan complete: " + str(total_groups) + " groups, " +
                        str(round(mb, 1)) + " MB reclaimable"),
            "result_file": filename,
            "summary": {
                "total_images": total_images,
                "exact_groups": len(exact_groups_data),
                "perceptual_groups": len(perceptual_groups_data),
                "total_groups": total_groups,
                "total_duplicate_files": total_duplicate_files,
                "reclaimable_mb": round(mb, 1),
                "duration": round(elapsed, 1),
                "errors": len(all_errors),
                "auto_recycled": auto_recycled,
            },
        })

        _log_activity("scan_completed", {
            "directory": directory,
            "mode": mode,
            "result_file": filename,
            "groups": total_groups,
            "reclaimable_mb": round(mb, 1),
            "duration": round(elapsed, 1),
        })

    except Exception as e:
        try:
            save_checkpoint(ckpt_path, {
                "directory": directory,
                "mode": mode,
                "threshold": threshold,
                "recursive": recursive,
                "hash_size": hash_size,
                "stage": scan_progress.get("stage", "unknown"),
                "md5_hashes": md5_precomputed,
                "phash_hashes": phash_precomputed,
                "file_info": file_info,
            })
        except Exception:
            pass

        import traceback
        tb = traceback.format_exc()
        err_msg = str(e)
        if "Errno 2" in err_msg or "No such file" in err_msg:
            err_msg = ("Could not save scan results. Windows Defender "
                       "Controlled Folder Access may be blocking writes. "
                       "Please whitelist the Python executable in "
                       "Windows Security settings.")
        elif "Permission" in err_msg or "Access" in err_msg:
            err_msg = ("Permission denied. Check that PixHerder has "
                       "write access to its data folders.")
        logger.error("Scan failed: %s", e)
        scan_progress.update({
            "status": "error",
            "message": err_msg,
        })
        _log_activity("scan_error", {
            "directory": directory,
            "error": str(e),
            "traceback": tb,
        })


def _run_action(action_type, groups, move_dir=None, keep_strategy="largest",
                report_file=None, scan_dir=None):
    """Background action thread target."""
    action_progress.update({
        "status": "running",
        "current": 0,
        "total": 0,
        "result": None,
    })

    _log_activity("action_started", {
        "type": action_type,
        "groups_count": len(groups),
        "move_destination": move_dir,
    })

    try:
        archive_slot = None
        if action_type == "delete":
            try:
                from engine.recovery import start_new_operation
                archive_slot = start_new_operation("delete_action")
            except Exception:
                pass

        if action_type == "move":
            result = move_files(
                groups, move_dir, keep_strategy,
                progress_cb=_update_action_progress,
                cancel_event=action_cancel,
                scan_dir=scan_dir,
            )
            action_progress["result"] = result
            moved_sources = result.get("moved_sources", [])
            if moved_sources:
                _save_source_dupe_map(moved_sources)
        elif action_type == "delete":
            result = delete_files(
                groups, keep_strategy,
                progress_cb=_update_action_progress,
                cancel_event=action_cancel,
                archive_slot=archive_slot,
            )
            action_progress["result"] = result

        action_progress["status"] = "complete"
        _log_activity("action_completed", {
            "type": action_type,
            "result": action_progress.get("result"),
        })

        if report_file and result and not result.get("errors"):
            try:
                report_path = SCANS_DIR / report_file
                if report_path.exists():
                    report_path.unlink()
                    _log_activity("scan_report_removed", {
                        "file": report_file,
                        "reason": "All actions completed successfully",
                    })
            except Exception:
                pass
    except Exception as e:
        action_progress["status"] = "error"
        action_progress["result"] = {"error": str(e)}
        _log_activity("action_error", {
            "type": action_type,
            "error": str(e),
        })


def _run_oddball(report_data, dupes_folder):
    """Background oddball verification thread target."""
    oddball_progress.update({
        "status": "running",
        "current": 0,
        "total": 0,
        "result": None,
    })

    try:
        result = verify_pairs(
            report_data,
            dupes_folder=dupes_folder,
            progress_cb=_update_oddball_progress,
            cancel_event=oddball_cancel,
        )
        oddballs = filter_oddballs(result["results"])
        oddball_progress["result"] = {
            "oddballs": oddballs,
            "total_checked": result["checked"],
            "total_skipped": result["skipped"],
            "cancelled": result["cancelled"],
        }
        oddball_progress["status"] = "complete"
    except Exception as e:
        oddball_progress["status"] = "error"
        oddball_progress["result"] = {"error": str(e)}


def _run_staging(source_dir, staging_dir, extensions):
    """Background staging thread target."""
    start_time = time.time()

    staging_progress.update({
        "status": "running",
        "current": 0,
        "total": 0,
        "bytes_copied": 0,
        "bytes_total": 0,
        "copied": 0,
        "skipped": 0,
        "failed": 0,
        "message": "Counting files...",
        "staging_dir": staging_dir,
        "source_dir": source_dir,
        "manifest_path": None,
    })

    _log_activity("staging_started", {
        "source": source_dir,
        "destination": staging_dir,
    })

    try:
        ext_set = set(extensions) if extensions else None
        result = start_staging(
            source_dir, staging_dir,
            extensions=ext_set,
            progress_cb=_update_staging_progress,
            cancel_event=staging_cancel,
        )

        elapsed = time.time() - start_time

        if result.get("cancelled"):
            staging_progress["status"] = "cancelled"
            staging_progress["message"] = "Staging cancelled"
            _log_activity("staging_cancelled", {
                "source": source_dir,
                "copied": result.get("copied", 0),
            })
            return

        staging_progress.update({
            "status": "complete",
            "copied": result.get("copied", 0),
            "skipped": result.get("skipped", 0),
            "failed": result.get("failed", 0),
            "manifest_path": result.get("manifest_path"),
            "message": (
                "Staging complete: " + str(result.get("total_staged", 0))
                + " files in " + str(round(elapsed, 1)) + "s"
            ),
        })

        _log_activity("staging_completed", {
            "source": source_dir,
            "destination": staging_dir,
            "copied": result.get("copied", 0),
            "skipped": result.get("skipped", 0),
            "failed": result.get("failed", 0),
            "duration": round(elapsed, 1),
        })

    except Exception as e:
        staging_progress["status"] = "error"
        staging_progress["message"] = "Staging failed: " + str(e)
        _log_activity("staging_error", {
            "source": source_dir,
            "error": str(e),
        })


def _run_restore(staging_dir, source_dir, full_restore, include_keepers):
    """Background restore thread. Copies files back to source with progress."""
    restore_progress.update({
        "status": "running", "current": 0, "total": 0,
        "copied": 0, "skipped": 0, "errors": 0,
        "message": "Counting files...", "phase": "counting",
    })

    settings = load_settings()
    dupes_dir = settings.get("move_destination", DEFAULTS["move_destination"])
    keepers_dir = settings.get("keepers_dir", DEFAULTS["keepers_dir"])

    total = 0
    folders_to_restore = []
    if staging_dir and os.path.isdir(staging_dir):
        folders_to_restore.append((staging_dir, True))
    if full_restore or include_keepers:
        if os.path.isdir(dupes_dir):
            folders_to_restore.append((dupes_dir, True))
    if include_keepers or full_restore:
        if os.path.isdir(keepers_dir):
            folders_to_restore.append((keepers_dir, True))

    for folder_dir, _ in folders_to_restore:
        for root, dirs, files in os.walk(folder_dir):
            total += len(files)

    restore_progress["total"] = total
    restore_progress["phase"] = "restoring"
    restore_progress["message"] = "Restoring files..."

    os.makedirs(source_dir, exist_ok=True)
    copied = 0
    skipped = 0
    errors = 0
    current = 0

    try:
        for folder_dir, preserve_structure in folders_to_restore:
            for root, dirs, files in os.walk(folder_dir):
                for fname in files:
                    current += 1
                    src = os.path.join(root, fname)
                    if preserve_structure:
                        rel = os.path.relpath(src, folder_dir)
                        dest = os.path.join(source_dir, rel)
                    else:
                        dest = os.path.join(source_dir, fname)
                    try:
                        if os.path.exists(dest):
                            skipped += 1
                        else:
                            os.makedirs(os.path.dirname(dest), exist_ok=True)
                            shutil.copy2(src, dest)
                            copied += 1
                    except Exception as e:
                        errors += 1
                        logger.error("Restore error for %s -> %s: %s",
                                    src, dest, e)
                    restore_progress.update({
                        "current": current, "copied": copied,
                        "skipped": skipped, "errors": errors,
                        "message": "Restoring: " + str(current) + " / "
                                   + str(total) + " files",
                    })

        if full_restore:
            restore_progress["phase"] = "cleanup"
            restore_progress["message"] = "Cleaning up workspace..."
            if staging_dir and os.path.isdir(staging_dir):
                cleanup_staging(staging_dir)
            if os.path.isdir(dupes_dir):
                cleanup_staging(dupes_dir)
            if os.path.isdir(keepers_dir):
                cleanup_staging(keepers_dir)

        _log_activity("staging_restore", {
            "copied": copied, "skipped": skipped, "errors": errors,
            "full_restore": full_restore,
        })

        restore_progress.update({
            "status": "complete", "current": total, "total": total,
            "copied": copied, "skipped": skipped, "errors": errors,
            "message": "Restore complete: " + str(copied) + " files copied",
            "phase": "done",
        })

    except Exception as e:
        restore_progress.update({
            "status": "error",
            "message": "Restore failed: " + str(e),
        })


def _run_syncback(staging_dir, source_dir):
    """Background sync-back thread target."""
    syncback_progress.update({
        "status": "running",
        "current": 0,
        "total": 0,
        "deleted": 0,
        "errors": 0,
        "message": "Starting sync-back...",
    })

    _log_activity("syncback_started", {
        "source": source_dir,
        "staging": staging_dir,
    })

    try:
        result = sync_back_deletions(
            staging_dir, source_dir,
            progress_cb=_update_syncback_progress,
            cancel_event=syncback_cancel,
        )

        syncback_progress.update({
            "status": "complete",
            "deleted": result.get("deleted", 0),
            "errors": result.get("errors", 0),
            "message": (
                "Sync complete: " + str(result.get("deleted", 0))
                + " deleted from OneDrive, "
                + str(result.get("skipped", 0)) + " kept"
            ),
            "result": result,
        })

        _log_activity("syncback_completed", {
            "deleted": result.get("deleted", 0),
            "skipped": result.get("skipped", 0),
            "errors": result.get("errors", 0),
        })

    except Exception as e:
        syncback_progress["status"] = "error"
        syncback_progress["message"] = "Sync-back failed: " + str(e)
        _log_activity("syncback_error", {"error": str(e)})

"""
DupeFinder web server and API routes.
Handles HTTP routing, SSE for progress, and serves the SPA.
"""

import http.server
import json
import os
import sys
import threading
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

# Add project root to path so engine imports work
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.config import (
    SCANS_DIR, LOGS_DIR, ACTIVITY_LOG, PROJECT_ROOT as ROOT,
    DEFAULTS, IMAGE_EXTENSIONS, load_settings, save_settings, ensure_dirs,
    default_pictures_path,
)
from engine.scanner import find_images, count_images
from engine.hasher import md5_hash, perceptual_hash
from engine.comparator import (
    find_exact_duplicates, find_perceptual_duplicates, pick_original,
)
from engine.actions import move_files, delete_files, rescue_file
from engine.oddball import verify_pairs, filter_oddballs
from engine.checkpoint import (
    checkpoint_path, save_checkpoint, load_checkpoint, delete_checkpoint,
    find_checkpoint, validate_checkpoint,
)
from engine.staging import (
    is_onedrive_path, get_staging_dir, count_files_for_staging,
    start_staging, load_manifest, sync_back_deletions, cleanup_staging,
    recycle_staging,
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


# ---- Heartbeat / Auto-shutdown ----

_last_heartbeat = time.time()
_heartbeat_lock = threading.Lock()
_shutdown_grace_seconds = 10


def _touch_heartbeat():
    global _last_heartbeat
    with _heartbeat_lock:
        _last_heartbeat = time.time()


def _heartbeat_checker():
    """Background thread: shuts down server if browser stops pinging."""
    while True:
        time.sleep(5)
        with _heartbeat_lock:
            elapsed = time.time() - _last_heartbeat

        if elapsed > _shutdown_grace_seconds:
            # Don't shut down if a scan, action, or staging is running
            if scan_thread and scan_thread.is_alive():
                _touch_heartbeat()  # keep alive during scans
                continue
            if action_thread and action_thread.is_alive():
                _touch_heartbeat()
                continue
            if oddball_thread and oddball_thread.is_alive():
                _touch_heartbeat()
                continue
            if staging_thread and staging_thread.is_alive():
                _touch_heartbeat()
                continue
            if syncback_thread and syncback_thread.is_alive():
                _touch_heartbeat()
                continue

            _log_activity("auto_shutdown", {
                "reason": "No browser connection for "
                          + str(int(elapsed)) + " seconds",
            })
            time.sleep(0.5)
            if _server_instance:
                _server_instance.shutdown()


# ---- Shared state (accessed by handler and background threads) ----

scan_thread = None
scan_cancel = threading.Event()
scan_progress = {
    "status": "idle",
    "stage": "",
    "current": 0,
    "total": 0,
    "elapsed": 0,
    "errors": 0,
    "message": "",
    "result_file": None,
}

action_thread = None
action_cancel = threading.Event()
action_progress = {
    "status": "idle",
    "current": 0,
    "total": 0,
    "result": None,
}

oddball_thread = None
oddball_cancel = threading.Event()
oddball_progress = {
    "status": "idle",
    "current": 0,
    "total": 0,
    "result": None,
}

staging_thread = None
staging_cancel = threading.Event()
staging_progress = {
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

syncback_thread = None
syncback_cancel = threading.Event()
syncback_progress = {
    "status": "idle",
    "current": 0,
    "total": 0,
    "deleted": 0,
    "errors": 0,
    "message": "",
}


def _update_scan_progress(current, total, stage):
    """Callback for scan engine to report progress."""
    scan_progress["current"] = current
    scan_progress["total"] = total
    scan_progress["stage"] = stage


def _update_action_progress(current, total, stage):
    """Callback for action engine to report progress."""
    action_progress["current"] = current
    action_progress["total"] = total


def _update_oddball_progress(current, total, stage):
    """Callback for oddball engine to report progress."""
    oddball_progress["current"] = current
    oddball_progress["total"] = total


def _run_scan(directory, mode, threshold, recursive, hash_size,
              keep_strategy, extensions, resume_data=None):
    """Background scan thread target."""
    global scan_progress
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
        total_images = len(image_paths)

        scan_progress["total"] = total_images
        scan_progress["message"] = "Found " + str(total_images) + " images"

        if total_images < 2:
            scan_progress.update({
                "status": "complete",
                "message": "Not enough images to compare ("
                           + str(total_images) + " found)",
            })
            return

        # Prepare precomputed hashes from checkpoint
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

        # Checkpoint callback for MD5 phase
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

        # Checkpoint callback for pHash phase
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
                # Save checkpoint on cancel
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

        # Save results
        scan_progress["stage"] = "saving"
        scan_progress["message"] = "Saving results..."
        scan_progress["current"] = 0
        scan_progress["total"] = 0
        elapsed = time.time() - start_time
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = "scan_" + timestamp + "_" + mode + ".json"
        result_path = SCANS_DIR / filename

        report = {
            "metadata": {
                "directory": directory,
                "mode": mode,
                "threshold": threshold,
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
        }

        with open(str(result_path), "w") as f:
            json.dump(report, f, indent=2)

        # Scan succeeded -- delete checkpoint
        delete_checkpoint(ckpt_path)

        total_groups = len(exact_groups_data) + len(perceptual_groups_data)
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
                "reclaimable_mb": round(mb, 1),
                "duration": round(elapsed, 1),
                "errors": len(all_errors),
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
        # Save checkpoint on error too
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

        scan_progress.update({
            "status": "error",
            "message": "Scan failed: " + str(e),
        })
        _log_activity("scan_error", {
            "directory": directory,
            "error": str(e),
        })


def _run_action(action_type, groups, move_dir=None, keep_strategy="largest",
                report_file=None):
    """Background action thread target."""
    global action_progress

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
        if action_type == "move":
            result = move_files(
                groups, move_dir, keep_strategy,
                progress_cb=_update_action_progress,
                cancel_event=action_cancel,
            )
            action_progress["result"] = result
        elif action_type == "delete":
            result = delete_files(
                groups, keep_strategy,
                progress_cb=_update_action_progress,
                cancel_event=action_cancel,
            )
            action_progress["result"] = result

        action_progress["status"] = "complete"
        _log_activity("action_completed", {
            "type": action_type,
            "result": action_progress.get("result"),
        })

        # Clean up the scan report if all files were processed (no real errors)
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
    global oddball_progress

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


def _find_staging_subfolder():
    """Find the active staging subfolder reliably.

    Checks in-memory session first, then falls back to the subfolder
    with the most files. Returns the path or empty string.
    """
    # 1. Check in-memory session
    mem_dir = staging_progress.get("staging_dir", "")
    if mem_dir and os.path.isdir(mem_dir):
        return mem_dir

    # 2. Fall back to disk: find subfolder with most files
    settings = load_settings()
    staging_base = settings.get("staging_dir", DEFAULTS["staging_dir"])
    if not os.path.isdir(staging_base):
        return ""

    best_path = ""
    best_count = 0
    for d in os.listdir(staging_base):
        candidate = os.path.join(staging_base, d)
        if not os.path.isdir(candidate):
            continue
        count = sum(1 for _, _, files in os.walk(candidate) for _ in files)
        if count > best_count:
            best_count = count
            best_path = candidate

    return best_path


def _update_staging_progress(current, total, bytes_copied, bytes_total, stage):
    """Callback for staging engine to report progress."""
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


def _run_staging(source_dir, staging_dir, extensions):
    """Background staging thread target."""
    global staging_progress
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


def _update_syncback_progress(current, total, stage):
    """Callback for sync-back progress."""
    syncback_progress["current"] = current
    syncback_progress["total"] = total
    syncback_progress["message"] = (
        "Syncing: " + str(current) + "/" + str(total) + " files"
    )


def _run_syncback(staging_dir, source_dir):
    """Background sync-back thread target."""
    global syncback_progress

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


class DupeFinderHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for the DupeFinder web API."""

    def log_message(self, format, *args):
        """Suppress default access logs."""
        pass

    # ---- Response helpers ----

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message, status=400):
        self.send_json({"error": message}, status)

    def read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        body = self.rfile.read(length)
        return json.loads(body.decode("utf-8"))

    # ---- GET routes ----

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/" or path == "":
            self._serve_index()
        elif path.startswith("/web/") and path.endswith((".css", ".js")):
            self._serve_static(path)
        elif path == "/api/scans":
            self._handle_get_scans()
        elif path == "/api/scan/progress":
            self._handle_scan_progress_sse()
        elif path == "/api/decisions/load":
            report = params.get("report", [""])[0]
            self._handle_decisions_load(report)
        elif path == "/api/scan/check-resume":
            self._handle_check_resume(params)
        elif path == "/api/groups":
            report = params.get("report", [""])[0]
            self._handle_get_groups(report)
        elif path == "/api/image":
            filepath = params.get("path", [""])[0]
            self._serve_image(filepath)
        elif path == "/api/settings":
            self._handle_get_settings()
        elif path == "/api/action/progress":
            self._handle_action_progress_sse()
        elif path == "/api/oddball/progress":
            self._handle_oddball_progress_sse()
        elif path == "/api/heartbeat":
            self._handle_heartbeat()
        elif path == "/api/folders/status":
            self._handle_folders_status()
        elif path == "/api/activity":
            limit = int(params.get("limit", ["50"])[0])
            self._handle_get_activity(limit)
        elif path == "/api/staging/progress":
            self._handle_staging_progress_sse()
        elif path == "/api/staging/status":
            self._handle_staging_status()
        elif path == "/api/browse":
            dirpath = params.get("path", [""])[0]
            page = int(params.get("page", ["1"])[0])
            page_size = int(params.get("page_size", ["50"])[0])
            sort_by = params.get("sort", ["name"])[0]
            self._handle_browse(dirpath, page, page_size, sort_by)
        elif path == "/api/staging/syncback/progress":
            self._handle_syncback_progress_sse()
        elif path == "/api/browse-folders":
            dirpath = params.get("path", [""])[0]
            self._handle_browse_folders(dirpath)
        else:
            self.send_error(404)

    # ---- POST routes ----

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/scan/start":
            self._handle_scan_start()
        elif path == "/api/scan/cancel":
            self._handle_scan_cancel()
        elif path == "/api/action/move":
            self._handle_action_move()
        elif path == "/api/action/delete":
            self._handle_action_delete()
        elif path == "/api/action/rescue":
            self._handle_action_rescue()
        elif path == "/api/settings":
            self._handle_save_settings()
        elif path == "/api/oddball/run":
            self._handle_oddball_run()
        elif path == "/api/decisions/save":
            self._handle_decisions_save()
        elif path == "/api/scans/delete":
            self._handle_delete_scan()
        elif path == "/api/shutdown":
            self._handle_shutdown()
        elif path == "/api/restart":
            self._handle_restart()
        elif path == "/api/activity/clear":
            self._handle_clear_activity()
        elif path == "/api/staging/check":
            self._handle_staging_check()
        elif path == "/api/staging/start":
            self._handle_staging_start()
        elif path == "/api/staging/cancel":
            self._handle_staging_cancel()
        elif path == "/api/staging/syncback":
            self._handle_syncback_start()
        elif path == "/api/staging/cleanup":
            self._handle_staging_cleanup()
        elif path == "/api/staging/reset":
            self._handle_staging_reset()
        elif path == "/api/staging/recycle-bin":
            self._handle_staging_recycle_bin()
        elif path == "/api/browser/delete":
            self._handle_browser_delete()
        elif path == "/api/browser/delete-folder":
            self._handle_browser_delete_folder()
        elif path == "/api/browser/open-explorer":
            self._handle_open_explorer()
        elif path == "/api/browser/open-recycle-bin":
            self._handle_open_recycle_bin()
        elif path == "/api/staging/restore":
            self._handle_staging_restore()
        elif path == "/api/staging/recycle":
            self._handle_staging_recycle()
        elif path == "/api/dupes/purge":
            self._handle_dupes_purge()
        elif path == "/api/dupes/promote":
            self._handle_dupes_promote()
        elif path == "/api/consolidate":
            self._handle_consolidate()
        else:
            self.send_error(404)

    # ---- Handler implementations ----

    def _serve_index(self):
        html_path = Path(__file__).parent / "index.html"
        try:
            with open(str(html_path), "r", encoding="utf-8") as f:
                content = f.read()
            body = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_error_json("Could not load index.html: " + str(e), 500)

    def _serve_static(self, url_path):
        """Serve static CSS/JS files from the web/ directory."""
        # url_path is like /web/style.css -> resolve to web/style.css
        rel = url_path.lstrip("/")
        file_path = Path(__file__).parent.parent / rel
        # Security: must be within the web/ directory
        try:
            file_path = file_path.resolve()
            web_dir = (Path(__file__).parent).resolve()
            if not str(file_path).startswith(str(web_dir)):
                self.send_error(403)
                return
        except Exception:
            self.send_error(403)
            return

        if not file_path.is_file():
            self.send_error(404)
            return

        content_types = {
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
        }
        ext = file_path.suffix.lower()
        ctype = content_types.get(ext, "application/octet-stream")

        try:
            with open(str(file_path), "r", encoding="utf-8") as f:
                content = f.read()
            body = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control",
                             "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_error_json("Could not serve file: " + str(e), 500)

    def _handle_heartbeat(self):
        _touch_heartbeat()
        self.send_json({"status": "ok"})

    def _handle_folders_status(self):
        settings = load_settings()
        image_exts = IMAGE_EXTENSIONS

        def _count_images(dirpath):
            if not dirpath or not os.path.isdir(dirpath):
                return {"exists": False, "path": dirpath or "", "file_count": 0}
            count = 0
            for root, dirs, files in os.walk(dirpath):
                for f in files:
                    if os.path.splitext(f)[1].lower() in image_exts:
                        count += 1
            return {"exists": True, "path": dirpath, "file_count": count}

        # Find staging session subfolder reliably
        staging_path = _find_staging_subfolder()

        dupes_path = settings.get("move_destination", DEFAULTS["move_destination"])
        keepers_path = settings.get("keepers_dir", DEFAULTS["keepers_dir"])

        self.send_json({
            "staging": _count_images(staging_path),
            "dupes": _count_images(dupes_path),
            "keepers": _count_images(keepers_path),
        })

    def _handle_get_activity(self, limit=50):
        entries = _read_activity(limit)
        self.send_json({"entries": entries})

    def _handle_clear_activity(self):
        try:
            with open(str(ACTIVITY_LOG), "w") as f:
                f.truncate(0)
            self.send_json({"status": "cleared"})
        except Exception as e:
            self.send_error_json("Failed to clear log: " + str(e), 500)

    def _handle_check_resume(self, params):
        directory = params.get("directory", [""])[0]
        mode = params.get("mode", ["both"])[0]

        if not directory:
            self.send_json({"has_checkpoint": False})
            return

        ckpt, data = find_checkpoint(directory, mode)
        if data:
            md5_count = len(data.get("md5_hashes", {}))
            phash_count = len(data.get("phash_hashes", {}))
            self.send_json({
                "has_checkpoint": True,
                "checkpoint_info": {
                    "stage": data.get("stage", "unknown"),
                    "md5_hashed": md5_count,
                    "phash_hashed": phash_count,
                    "timestamp": data.get("timestamp", ""),
                    "threshold": data.get("threshold"),
                    "mode": data.get("mode", mode),
                },
            })
        else:
            self.send_json({"has_checkpoint": False})

    def _handle_get_scans(self):
        scans = []

        # Scan results from scans/ directory
        if SCANS_DIR.exists():
            for f in sorted(SCANS_DIR.glob("*.json"), reverse=True):
                try:
                    with open(str(f), "r") as fh:
                        data = json.load(fh)
                    meta = data.get("metadata", {})
                    exact_count = len(data.get("exact_groups", []))
                    perceptual_count = len(data.get("perceptual_groups", []))
                    all_groups = (
                        data.get("exact_groups", []) +
                        data.get("perceptual_groups", [])
                    )
                    reclaimable = sum(
                        g.get("reclaimable_bytes", 0) for g in all_groups
                    )
                    scans.append({
                        "filename": f.name,
                        "source": "scan",
                        "directory": meta.get("directory", ""),
                        "mode": meta.get("mode", ""),
                        "timestamp": meta.get("timestamp", ""),
                        "total_images": meta.get("total_images", 0),
                        "exact_groups": exact_count,
                        "perceptual_groups": perceptual_count,
                        "total_groups": exact_count + perceptual_count,
                        "reclaimable_bytes": reclaimable,
                        "duration": meta.get("duration_seconds", 0),
                    })
                except Exception:
                    continue

        # Legacy reports from project root
        for pattern in ["*_report.json", "dupes_report.json"]:
            for f in ROOT.glob(pattern):
                if f.parent == ROOT and f.name not in [s["filename"] for s in scans]:
                    try:
                        with open(str(f), "r") as fh:
                            data = json.load(fh)
                        if isinstance(data, list):
                            total_groups = len(data)
                            reclaimable = sum(
                                g.get("reclaimable_bytes", 0) for g in data
                            )
                            total_dupes = sum(
                                len(g.get("duplicates", [])) for g in data
                            )
                            scans.append({
                                "filename": f.name,
                                "source": "legacy",
                                "directory": "",
                                "mode": "",
                                "timestamp": "",
                                "total_images": 0,
                                "exact_groups": 0,
                                "perceptual_groups": 0,
                                "total_groups": total_groups,
                                "total_dupes": total_dupes,
                                "reclaimable_bytes": reclaimable,
                                "duration": 0,
                            })
                    except Exception:
                        continue

        self.send_json(scans)

    def _handle_scan_progress_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            while True:
                data = dict(scan_progress)
                data["elapsed"] = round(data.get("elapsed", 0), 1)
                msg = "data: " + json.dumps(data) + "\n\n"
                self.wfile.write(msg.encode("utf-8"))
                self.wfile.flush()

                if data.get("status") in ("complete", "error", "cancelled", "idle"):
                    break

                time.sleep(0.5)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _handle_action_progress_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            while True:
                data = dict(action_progress)
                msg = "data: " + json.dumps(data) + "\n\n"
                self.wfile.write(msg.encode("utf-8"))
                self.wfile.flush()

                if data.get("status") in ("complete", "error", "idle"):
                    break

                time.sleep(0.5)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _handle_oddball_progress_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            while True:
                data = dict(oddball_progress)
                msg = "data: " + json.dumps(data) + "\n\n"
                self.wfile.write(msg.encode("utf-8"))
                self.wfile.flush()

                if data.get("status") in ("complete", "error", "idle"):
                    break

                time.sleep(0.5)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _handle_get_groups(self, report):
        if not report:
            self.send_error_json("Missing report parameter")
            return

        # Try scans/ directory first, then project root
        report_path = SCANS_DIR / report
        if not report_path.exists():
            report_path = ROOT / report
        if not report_path.exists():
            self.send_error_json("Report not found: " + report, 404)
            return

        try:
            with open(str(report_path), "r") as f:
                data = json.load(f)

            # Handle both formats: new (with metadata) and legacy (flat array)
            if isinstance(data, list):
                # Legacy format -- flat array of groups
                self.send_json({"groups": data, "metadata": None})
            elif isinstance(data, dict):
                groups = (
                    data.get("exact_groups", []) +
                    data.get("perceptual_groups", [])
                )
                self.send_json({
                    "groups": groups,
                    "metadata": data.get("metadata"),
                })
            else:
                self.send_error_json("Invalid report format")
        except Exception as e:
            self.send_error_json("Error reading report: " + str(e), 500)

    def _serve_image(self, filepath):
        import shutil as _shutil
        filepath = os.path.normpath(filepath)

        # Validate path is within allowed directories (prevent traversal)
        settings = load_settings()
        allowed_dirs = [
            settings.get("staging_dir", DEFAULTS["staging_dir"]),
            settings.get("move_destination", DEFAULTS["move_destination"]),
            settings.get("keepers_dir", DEFAULTS.get("keepers_dir", "")),
        ]
        src = staging_progress.get("source_dir") or ""
        if src:
            allowed_dirs.append(src)
        allowed_dirs = [os.path.normpath(d) for d in allowed_dirs if d]
        if not any(filepath.startswith(d + os.sep) or filepath == d
                   for d in allowed_dirs):
            self.send_error(403, "Access denied")
            return

        if not os.path.isfile(filepath):
            self.send_error(404, "File not found")
            return

        ext = os.path.splitext(filepath)[1].lower()
        content_types = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".gif": "image/gif",
            ".bmp": "image/bmp", ".webp": "image/webp",
            ".tiff": "image/tiff", ".tif": "image/tiff",
            ".heic": "image/heic", ".heif": "image/heif",
        }
        ct = content_types.get(ext, "application/octet-stream")

        try:
            file_stat = os.stat(filepath)
            etag = '"' + str(file_stat.st_mtime) + "-" + str(file_stat.st_size) + '"'

            # Check if client has cached version
            if_none_match = self.headers.get("If-None-Match")
            if if_none_match == etag:
                self.send_response(304)
                self.end_headers()
                return

            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(file_stat.st_size))
            self.send_header("Cache-Control", "max-age=3600")
            self.send_header("ETag", etag)
            self.end_headers()

            with open(filepath, "rb") as f:
                _shutil.copyfileobj(f, self.wfile)
        except Exception as e:
            self.send_error(500, str(e))

    def _handle_get_settings(self):
        settings = load_settings()
        settings["default_pictures_path"] = default_pictures_path()
        self.send_json(settings)

    def _handle_scan_start(self):
        global scan_thread, scan_cancel

        if scan_thread and scan_thread.is_alive():
            self.send_error_json("A scan is already running", 409)
            return

        try:
            body = self.read_json_body()
        except Exception:
            self.send_error_json("Invalid JSON body")
            return

        directory = body.get("directory", "")
        if not directory or not os.path.isdir(directory):
            self.send_error_json("Invalid directory: " + str(directory))
            return

        settings = load_settings()
        mode = body.get("mode", "both")
        threshold = body.get("threshold", settings.get("threshold", 5))
        recursive = body.get("recursive", settings.get("recursive", True))
        hash_size = settings.get("hash_size", 16)
        keep_strategy = settings.get("keep_strategy", "largest")
        extensions = settings.get("extensions")

        # Handle resume
        resume = body.get("resume", False)
        resume_data = None
        if resume:
            _, resume_data = find_checkpoint(directory, mode)

        # If not resuming, delete any stale checkpoint
        if not resume:
            ckpt = checkpoint_path(directory, mode)
            delete_checkpoint(ckpt)

        scan_cancel = threading.Event()
        scan_thread = threading.Thread(
            target=_run_scan,
            args=(directory, mode, threshold, recursive, hash_size,
                  keep_strategy, extensions, resume_data),
            daemon=True,
        )
        scan_thread.start()

        self.send_json({
            "status": "started",
            "directory": directory,
            "mode": mode,
            "resumed": bool(resume_data),
        })

    def _handle_scan_cancel(self):
        scan_cancel.set()
        self.send_json({"status": "cancelling"})

    def _handle_action_move(self):
        global action_thread, action_cancel

        if action_thread and action_thread.is_alive():
            self.send_error_json("An action is already running", 409)
            return

        try:
            body = self.read_json_body()
        except Exception:
            self.send_error_json("Invalid JSON body")
            return

        groups = body.get("groups", [])
        if not groups:
            self.send_error_json("No groups provided")
            return

        settings = load_settings()
        move_dir = body.get("destination",
                            settings.get("move_destination", DEFAULTS["move_destination"]))
        keep_strategy = settings.get("keep_strategy", "largest")
        report_file = body.get("report")

        action_cancel = threading.Event()
        action_thread = threading.Thread(
            target=_run_action,
            args=("move", groups, move_dir, keep_strategy, report_file),
            daemon=True,
        )
        action_thread.start()

        self.send_json({"status": "started", "action": "move"})

    def _handle_action_delete(self):
        global action_thread, action_cancel

        if action_thread and action_thread.is_alive():
            self.send_error_json("An action is already running", 409)
            return

        try:
            body = self.read_json_body()
        except Exception:
            self.send_error_json("Invalid JSON body")
            return

        groups = body.get("groups", [])
        if not groups:
            self.send_error_json("No groups provided")
            return

        settings = load_settings()
        keep_strategy = settings.get("keep_strategy", "largest")
        report_file = body.get("report")

        action_cancel = threading.Event()
        action_thread = threading.Thread(
            target=_run_action,
            args=("delete", groups, None, keep_strategy, report_file),
            daemon=True,
        )
        action_thread.start()

        self.send_json({"status": "started", "action": "delete"})

    def _handle_action_rescue(self):
        try:
            body = self.read_json_body()
        except Exception:
            self.send_error_json("Invalid JSON body")
            return

        source = body.get("source", "")
        destination = body.get("destination", "")
        if not source or not destination:
            self.send_error_json("Missing source or destination")
            return

        result = rescue_file(source, destination)
        self.send_json(result)

    def _handle_save_settings(self):
        try:
            body = self.read_json_body()
        except Exception:
            self.send_error_json("Invalid JSON body")
            return

        saved = save_settings(body)
        self.send_json(saved)

    def _handle_oddball_run(self):
        global oddball_thread, oddball_cancel

        if oddball_thread and oddball_thread.is_alive():
            self.send_error_json("Oddball check is already running", 409)
            return

        try:
            body = self.read_json_body()
        except Exception:
            self.send_error_json("Invalid JSON body")
            return

        report_name = body.get("report", "")
        dupes_folder = body.get("dupes_folder", "")

        # Load the report data
        report_path = SCANS_DIR / report_name
        if not report_path.exists():
            report_path = ROOT / report_name
        if not report_path.exists():
            self.send_error_json("Report not found: " + report_name, 404)
            return

        try:
            with open(str(report_path), "r") as f:
                data = json.load(f)

            if isinstance(data, list):
                report_data = data
            elif isinstance(data, dict):
                report_data = (
                    data.get("exact_groups", []) +
                    data.get("perceptual_groups", [])
                )
            else:
                self.send_error_json("Invalid report format")
                return
        except Exception as e:
            self.send_error_json("Error reading report: " + str(e), 500)
            return

        oddball_cancel = threading.Event()
        oddball_thread = threading.Thread(
            target=_run_oddball,
            args=(report_data, dupes_folder),
            daemon=True,
        )
        oddball_thread.start()

        self.send_json({"status": "started"})

    def _handle_decisions_save(self):
        """Save review decisions for a scan report."""
        try:
            body = self.read_json_body()
        except Exception:
            self.send_error_json("Invalid JSON body")
            return
        report = body.get("report", "")
        decisions = body.get("decisions", [])
        if not report:
            self.send_error_json("No report specified")
            return
        scans_dir = Path(__file__).parent.parent / "scans"
        os.makedirs(str(scans_dir), exist_ok=True)
        # Sanitize filename
        safe_name = os.path.basename(report).replace(".json", "")
        dec_path = scans_dir / ("decisions_" + safe_name + ".json")
        try:
            with open(str(dec_path), "w", encoding="utf-8") as f:
                json.dump({"report": report, "decisions": decisions}, f)
            self.send_json({"success": True})
        except Exception as e:
            self.send_error_json("Failed to save decisions: " + str(e))

    def _handle_decisions_load(self, report):
        """Load saved review decisions for a scan report."""
        if not report:
            self.send_json({"decisions": []})
            return
        scans_dir = Path(__file__).parent.parent / "scans"
        safe_name = os.path.basename(report).replace(".json", "")
        dec_path = scans_dir / ("decisions_" + safe_name + ".json")
        if dec_path.is_file():
            try:
                with open(str(dec_path), "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.send_json({"decisions": data.get("decisions", [])})
            except Exception:
                self.send_json({"decisions": []})
        else:
            self.send_json({"decisions": []})

    def _handle_delete_scan(self):
        try:
            body = self.read_json_body()
        except Exception:
            self.send_error_json("Invalid JSON body")
            return

        filename = body.get("filename", "")
        if not filename:
            self.send_error_json("Missing filename")
            return

        # Only allow deleting from scans/ directory
        target = SCANS_DIR / filename
        if not target.exists():
            self.send_error_json("Scan not found", 404)
            return

        try:
            os.remove(str(target))
            # Also delete corresponding decisions file if it exists
            safe_name = os.path.basename(filename).replace(".json", "")
            dec_path = SCANS_DIR / ("decisions_" + safe_name + ".json")
            if dec_path.exists():
                try:
                    os.remove(str(dec_path))
                except Exception:
                    pass  # Non-critical: orphaned decision file is harmless
            self.send_json({"status": "deleted", "filename": filename})
        except Exception as e:
            self.send_error_json("Failed to delete: " + str(e), 500)

    def _handle_shutdown(self):
        _log_activity("shutdown", {"source": "user"})
        self.send_json({"status": "shutting_down"})
        # Cancel any running operations
        scan_cancel.set()
        action_cancel.set()
        # Shut down the server in a separate thread so this response completes
        def _shutdown():
            time.sleep(0.5)
            if _server_instance:
                _server_instance.shutdown()
        threading.Thread(target=_shutdown, daemon=True).start()

    def _handle_restart(self):
        _log_activity("restart", {"source": "user"})
        self.send_json({"status": "restarting"})
        scan_cancel.set()
        action_cancel.set()
        def _restart():
            import subprocess
            time.sleep(0.5)
            # Spawn new process before shutting down
            subprocess.Popen(
                [sys.executable] + sys.argv,
                cwd=str(ROOT),
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if _server_instance:
                _server_instance.shutdown()
        threading.Thread(target=_restart, daemon=True).start()

    def _handle_browser_delete(self):
        try:
            body = self.read_json_body()
        except Exception:
            self.send_error_json("Invalid JSON body")
            return

        filepath = body.get("path", "")
        if not filepath or not os.path.isfile(filepath):
            self.send_error_json("File not found", 404)
            return

        # Security: only allow deleting within staging or dupes directories
        real = os.path.realpath(filepath).lower()
        settings = load_settings()
        allowed = []
        staging_base = settings.get("staging_dir", DEFAULTS["staging_dir"])
        dupes_dir = settings.get("move_destination", DEFAULTS["move_destination"])
        keepers_dir = settings.get("keepers_dir", DEFAULTS.get("keepers_dir", ""))
        if os.path.isdir(staging_base):
            allowed.append(os.path.realpath(staging_base).lower())
        if os.path.isdir(dupes_dir):
            allowed.append(os.path.realpath(dupes_dir).lower())
        if keepers_dir and os.path.isdir(keepers_dir):
            allowed.append(os.path.realpath(keepers_dir).lower())
        if not any(real.startswith(a) for a in allowed):
            self.send_error_json("Access denied: path outside allowed directories", 403)
            return

        try:
            from engine.staging import _recycle_file_powershell
            import stat
            if not os.access(filepath, os.W_OK):
                os.chmod(filepath, stat.S_IWRITE | stat.S_IREAD)
            _recycle_file_powershell(filepath)
            _log_activity("browser_delete", {"path": filepath})
            self.send_json({"success": True})
        except Exception as e:
            self.send_json({"success": False, "error": str(e)})

    def _handle_open_recycle_bin(self):
        """Open the Windows Recycle Bin."""
        try:
            import subprocess
            subprocess.Popen(
                ["explorer.exe", "shell:RecycleBinFolder"],
                creationflags=0x00000008  # DETACHED_PROCESS
            )
            self.send_json({"success": True})
        except Exception as e:
            self.send_error_json("Could not open Recycle Bin: " + str(e))

    def _handle_open_explorer(self):
        try:
            body = self.read_json_body()
        except Exception:
            self.send_error_json("Invalid JSON body")
            return

        dirpath = body.get("path", "")
        if not dirpath or not os.path.isdir(dirpath):
            self.send_error_json("Directory not found", 404)
            return

        # Security: only allow opening staging or dupes directories
        real = os.path.realpath(dirpath).lower()
        settings = load_settings()
        allowed = []
        staging_base = settings.get("staging_dir", DEFAULTS["staging_dir"])
        dupes_dir = settings.get("move_destination", DEFAULTS["move_destination"])
        keepers_dir = settings.get("keepers_dir", DEFAULTS.get("keepers_dir", ""))
        if os.path.isdir(staging_base):
            allowed.append(os.path.realpath(staging_base).lower())
        if os.path.isdir(dupes_dir):
            allowed.append(os.path.realpath(dupes_dir).lower())
        if keepers_dir and os.path.isdir(keepers_dir):
            allowed.append(os.path.realpath(keepers_dir).lower())
        if not any(real.startswith(a) for a in allowed):
            self.send_error_json("Access denied", 403)
            return

        try:
            import subprocess
            normpath = os.path.normpath(dirpath)
            # Write a temp Python script that minimizes browser then opens Explorer
            helper_path = str(ROOT / "_open_explorer.py")
            helper_code = (
                "import ctypes, subprocess, time, sys\n"
                "u = ctypes.windll.user32\n"
                "h = u.FindWindowW(None, 'DupeFinder')\n"
                "if h: u.ShowWindow(h, 6)\n"
                "time.sleep(0.3)\n"
                "subprocess.Popen(['explorer.exe', sys.argv[1]])\n"
            )
            with open(helper_path, "w") as f:
                f.write(helper_code)
            proc = subprocess.Popen(
                [sys.executable, helper_path, normpath],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self.send_json({"success": True})
            def _cleanup():
                proc.wait()
                try:
                    os.remove(helper_path)
                except Exception:
                    pass
            threading.Thread(target=_cleanup, daemon=True).start()
        except Exception as e:
            self.send_json({"success": False, "error": str(e)})

    def _handle_browser_delete_folder(self):
        try:
            body = self.read_json_body()
        except Exception:
            self.send_error_json("Invalid JSON body")
            return

        dirpath = body.get("path", "")
        if not dirpath or not os.path.isdir(dirpath):
            self.send_error_json("Directory not found", 404)
            return

        # Security: only allow deleting within staging or dupes directories
        real = os.path.realpath(dirpath).lower()
        settings = load_settings()
        allowed = []
        staging_base = settings.get("staging_dir", DEFAULTS["staging_dir"])
        dupes_dir = settings.get("move_destination", DEFAULTS["move_destination"])
        keepers_dir = settings.get("keepers_dir", DEFAULTS.get("keepers_dir", ""))
        if os.path.isdir(staging_base):
            allowed.append(os.path.realpath(staging_base).lower())
        if os.path.isdir(dupes_dir):
            allowed.append(os.path.realpath(dupes_dir).lower())
        if keepers_dir and os.path.isdir(keepers_dir):
            allowed.append(os.path.realpath(keepers_dir).lower())

        # Must be inside an allowed dir but NOT the allowed dir itself
        inside = any(real.startswith(a + os.sep) or real.startswith(a + "/")
                     for a in allowed)
        if not inside:
            self.send_error_json("Access denied: cannot delete this directory", 403)
            return

        try:
            result = recycle_staging(dirpath)
            _log_activity("browser_delete_folder", {
                "path": dirpath,
                "recycled": result.get("files_recycled", 0),
            })
            self.send_json({"success": True})
        except Exception as e:
            self.send_json({"success": False, "error": str(e)})

    def _handle_staging_restore(self):
        """Copy files from system folders back to OneDrive source directory.

        When full_restore is true, restores from all system folders
        (staging, dupes, keepers) and cleans them up afterward.
        """
        try:
            body = self.read_json_body()
        except Exception:
            self.send_error_json("Invalid JSON body")
            return

        staging_dir = body.get("staging_dir", "")
        source_dir = body.get("source_dir", "")
        full_restore = body.get("full_restore", False)
        include_keepers = body.get("include_keepers", False)

        if not source_dir:
            self.send_error_json("Source directory not specified")
            return

        # Validate paths match the active staging session
        known_staging = staging_progress.get("staging_dir") or ""
        if staging_dir and known_staging:
            if os.path.normpath(staging_dir) != os.path.normpath(known_staging):
                self.send_error_json(
                    "Staging directory mismatch: does not match active session",
                    403)
                return
        known_source = staging_progress.get("source_dir") or ""
        if source_dir and known_source:
            if os.path.normpath(source_dir) != os.path.normpath(known_source):
                self.send_error_json(
                    "Source directory mismatch: does not match active session",
                    403)
                return

        os.makedirs(source_dir, exist_ok=True)

        import shutil as _shutil
        import stat
        copied = 0
        skipped = 0
        errors = 0

        def _restore_folder(folder_dir, preserve_structure):
            """Copy files from a folder back to source_dir."""
            nonlocal copied, skipped, errors
            if not folder_dir or not os.path.isdir(folder_dir):
                return
            for root, dirs, files in os.walk(folder_dir):
                rel_root = os.path.relpath(root, folder_dir)
                for f in files:
                    src = os.path.join(root, f)
                    if preserve_structure and rel_root != ".":
                        dst_dir = os.path.join(source_dir, rel_root)
                        os.makedirs(dst_dir, exist_ok=True)
                        dst = os.path.join(dst_dir, f)
                    else:
                        dst = os.path.join(source_dir, f)
                    try:
                        if os.path.exists(dst):
                            skipped += 1
                            continue
                        _shutil.copy2(src, dst)
                        copied += 1
                    except Exception:
                        errors += 1

        # Restore workspace (preserves subfolder structure)
        if staging_dir and os.path.isdir(staging_dir):
            _restore_folder(staging_dir, True)

        if full_restore or include_keepers:
            settings = load_settings()
            keepers_dir = settings.get(
                "keepers_dir", DEFAULTS.get("keepers_dir", ""))
            if keepers_dir:
                _restore_folder(keepers_dir, False)

        if full_restore:
            # Restore dupes folder (flat files, no structure to preserve)
            settings = load_settings()
            dupes_dir = settings.get(
                "move_destination", DEFAULTS["move_destination"])
            _restore_folder(dupes_dir, False)

            # Clean up all system folders silently
            if staging_dir and os.path.isdir(staging_dir):
                cleanup_staging(staging_dir)
            if dupes_dir and os.path.isdir(dupes_dir):
                cleanup_staging(dupes_dir)
            if keepers_dir and os.path.isdir(keepers_dir):
                cleanup_staging(keepers_dir)

        if full_restore:
            # Clear in-memory staging session so wizard starts fresh
            staging_progress.update({
                "status": "idle",
                "staging_dir": "",
                "source_dir": "",
                "current": 0,
                "total": 0,
                "bytes_copied": 0,
                "bytes_total": 0,
                "stage": "",
                "message": "",
            })

        _log_activity("staging_restore", {
            "staging_dir": staging_dir,
            "source_dir": source_dir,
            "full_restore": full_restore,
            "copied": copied,
            "skipped": skipped,
            "errors": errors,
        })

        self.send_json({
            "success": True,
            "copied": copied,
            "skipped": skipped,
            "errors": errors,
        })

    def _handle_staging_recycle(self):
        """Move dupes folder contents into the staging folder for re-review."""
        try:
            body = self.read_json_body()
        except Exception:
            body = {}
        force = body.get("force", False)

        settings = load_settings()
        staging_base = settings.get("staging_dir", DEFAULTS["staging_dir"])
        dupes_dir = settings.get("move_destination", DEFAULTS["move_destination"])

        if not os.path.isdir(dupes_dir):
            self.send_error_json("Duplicates folder not found", 404)
            return

        # Find or create staging session subfolder
        staging_path = _find_staging_subfolder()

        if not staging_path:
            # Create a new staging subfolder
            import hashlib
            key = os.path.normpath(dupes_dir).lower()
            short_hash = hashlib.md5(key.encode("utf-8")).hexdigest()[:10]
            staging_path = os.path.join(staging_base, short_hash)

        os.makedirs(staging_path, exist_ok=True)

        # Check if staging has image files already
        image_exts = IMAGE_EXTENSIONS
        staging_files = 0
        for root, dirs, files in os.walk(staging_path):
            for f in files:
                if os.path.splitext(f)[1].lower() in image_exts:
                    staging_files += 1
                    break
            if staging_files:
                break

        if staging_files > 0 and not force:
            self.send_error_json(
                "Staging folder is not empty. Sync cleaned files back to "
                "OneDrive first, or clean up the staging folder.", 409)
            return

        # Move all files from dupes into staging
        import stat
        import shutil as _shutil
        moved = 0
        errors = 0
        error_details = []
        for item in os.listdir(dupes_dir):
            src = os.path.join(dupes_dir, item)
            dst = os.path.join(staging_path, item)
            # Collision avoidance — file may already exist in staging
            if os.path.exists(dst):
                stem, ext = os.path.splitext(item)
                counter = 1
                while os.path.exists(dst):
                    dst = os.path.join(
                        staging_path, stem + "_" + str(counter) + ext)
                    counter += 1
            try:
                if not os.access(src, os.W_OK) and os.path.isfile(src):
                    os.chmod(src, stat.S_IWRITE | stat.S_IREAD)
                os.rename(src, dst)
                moved += 1
            except Exception:
                # rename failed (cross-device?), try copy+delete
                try:
                    if os.path.isdir(src):
                        _shutil.copytree(src, dst)
                        _shutil.rmtree(src, onerror=lambda f, p, e: (
                            os.chmod(p, stat.S_IWRITE), f(p)))
                    else:
                        _shutil.copy2(src, dst)
                        os.remove(src)
                    moved += 1
                except Exception as e2:
                    errors += 1
                    error_details.append(item + ": " + str(e2))

        _log_activity("staging_recycle", {
            "from": dupes_dir,
            "to": staging_path,
            "moved": moved,
            "errors": errors,
            "error_details": error_details[:10],
        })

        self.send_json({
            "success": True,
            "files_moved": moved,
            "errors": errors,
            "staging_path": staging_path,
        })

    def _handle_dupes_purge(self):
        """Send all files in the dupes folder to the Recycle Bin."""
        settings = load_settings()
        dupes_dir = settings.get("move_destination", DEFAULTS["move_destination"])

        if not os.path.isdir(dupes_dir):
            self.send_error_json("Duplicates folder not found", 404)
            return

        result = recycle_staging(dupes_dir)
        _log_activity("dupes_purge", {
            "path": dupes_dir,
            "recycled": result.get("files_recycled", 0),
            "errors": result.get("errors", 0),
            "used_fallback": result.get("used_fallback", False),
        })

        self.send_json({
            "success": True,
            "deleted": result.get("files_recycled", 0),
            "errors": result.get("errors", 0),
        })

    def _handle_dupes_promote(self):
        """Move all files from dupes folder to keepers folder."""
        settings = load_settings()
        dupes_dir = settings.get("move_destination", DEFAULTS["move_destination"])
        keepers_dir = settings.get("keepers_dir", DEFAULTS["keepers_dir"])

        if not os.path.isdir(dupes_dir):
            self.send_error_json("Duplicates folder not found", 404)
            return

        os.makedirs(keepers_dir, exist_ok=True)

        import shutil as _shutil
        moved = 0
        errors = 0

        for root, dirs, files in os.walk(dupes_dir):
            for f in files:
                src = os.path.join(root, f)
                dst = os.path.join(keepers_dir, f)
                # Collision avoidance
                if os.path.exists(dst):
                    stem, ext = os.path.splitext(f)
                    counter = 1
                    while os.path.exists(dst):
                        dst = os.path.join(
                            keepers_dir, stem + "_" + str(counter) + ext)
                        counter += 1
                try:
                    _shutil.copy2(src, dst)
                    os.remove(src)
                    moved += 1
                except Exception:
                    errors += 1

        _log_activity("dupes_promote", {
            "dupes_dir": dupes_dir,
            "keepers_dir": keepers_dir,
            "moved": moved,
            "errors": errors,
        })

        self.send_json({
            "success": True,
            "moved": moved,
            "errors": errors,
        })

    def _handle_consolidate(self):
        """Move all files from dupes and keepers back into staging folder."""
        settings = load_settings()
        dupes_dir = settings.get("move_destination", DEFAULTS["move_destination"])
        keepers_dir = settings.get("keepers_dir", DEFAULTS.get("keepers_dir", ""))

        # Find staging subfolder
        staging_dir = _find_staging_subfolder()

        if not staging_dir:
            self.send_error_json("No workspace folder found", 404)
            return

        import shutil as _shutil
        moved = 0
        errors = 0

        def _move_into_staging(source_dir):
            nonlocal moved, errors
            if not source_dir or not os.path.isdir(source_dir):
                return
            for root, dirs, files in os.walk(source_dir):
                for f in files:
                    src = os.path.join(root, f)
                    dst = os.path.join(staging_dir, f)
                    if os.path.exists(dst):
                        stem, ext = os.path.splitext(f)
                        counter = 1
                        while os.path.exists(dst):
                            dst = os.path.join(
                                staging_dir,
                                stem + "_" + str(counter) + ext)
                            counter += 1
                    try:
                        _shutil.copy2(src, dst)
                        os.remove(src)
                        moved += 1
                    except Exception:
                        errors += 1

        _move_into_staging(dupes_dir)
        _move_into_staging(keepers_dir)

        _log_activity("consolidate", {
            "staging_dir": staging_dir,
            "moved": moved,
            "errors": errors,
        })

        self.send_json({
            "success": True,
            "moved": moved,
            "errors": errors,
        })

    # ---- Staging handlers ----

    def _handle_browse_folders(self, dirpath):
        """List subfolders for the folder picker. No file listing."""
        if not dirpath:
            # Default to user home
            dirpath = os.path.expanduser("~")

        dirpath = os.path.normpath(dirpath)
        if not os.path.isdir(dirpath):
            self.send_error_json("Directory not found", 404)
            return

        # Block system directories
        lower = dirpath.lower()
        windir = os.environ.get("WINDIR", "C:\\Windows").lower()
        blocked = [
            windir,
            os.path.join(windir, "system32"),
            os.environ.get("PROGRAMFILES", "C:\\Program Files").lower(),
            os.environ.get("PROGRAMFILES(X86)",
                           "C:\\Program Files (x86)").lower(),
        ]
        if any(lower == b or lower.startswith(b + os.sep)
               for b in blocked):
            self.send_error_json("Access denied", 403)
            return

        folders = []
        try:
            for entry in sorted(os.listdir(dirpath)):
                full = os.path.join(dirpath, entry)
                if os.path.isdir(full) and not entry.startswith("."):
                    folders.append(entry)
        except PermissionError:
            pass
        except Exception:
            pass

        # Get parent directory (for "up" navigation)
        parent = os.path.dirname(dirpath)
        if parent == dirpath:
            parent = ""  # at root

        self.send_json({
            "path": dirpath,
            "parent": parent,
            "folders": folders,
        })

    def _handle_browse(self, dirpath, page, page_size, sort_by):
        if not dirpath or not os.path.isdir(dirpath):
            self.send_error_json("Invalid directory", 400)
            return

        # Security: only allow browsing staging or dupes directories
        real = os.path.realpath(dirpath).lower()
        settings = load_settings()
        allowed = []
        staging_base = settings.get("staging_dir", DEFAULTS["staging_dir"])
        dupes_dir = settings.get("move_destination", DEFAULTS["move_destination"])
        keepers_dir = settings.get("keepers_dir", DEFAULTS.get("keepers_dir", ""))
        if os.path.isdir(staging_base):
            allowed.append(os.path.realpath(staging_base).lower())
        if os.path.isdir(dupes_dir):
            allowed.append(os.path.realpath(dupes_dir).lower())
        if keepers_dir and os.path.isdir(keepers_dir):
            allowed.append(os.path.realpath(keepers_dir).lower())
        if not any(real.startswith(a) for a in allowed):
            self.send_error_json("Access denied: path outside allowed directories", 403)
            return

        image_exts = IMAGE_EXTENSIONS

        entries = []
        try:
            for entry in os.scandir(dirpath):
                try:
                    is_dir = entry.is_dir()
                    ext = os.path.splitext(entry.name)[1].lower()
                    if not is_dir and ext not in image_exts:
                        continue
                    stat = entry.stat()
                    item = {
                        "name": entry.name,
                        "is_dir": is_dir,
                        "path": entry.path,
                        "size": stat.st_size if not is_dir else 0,
                        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "ext": ext,
                    }
                    entries.append(item)
                except Exception:
                    continue
        except Exception as e:
            self.send_error_json("Error reading directory: " + str(e), 500)
            return

        # Sort: folders first, then by chosen field
        dirs = [e for e in entries if e["is_dir"]]
        files = [e for e in entries if not e["is_dir"]]
        if sort_by == "size":
            files.sort(key=lambda x: x["size"], reverse=True)
        elif sort_by == "date":
            files.sort(key=lambda x: x["mtime"], reverse=True)
        else:
            files.sort(key=lambda x: x["name"].lower())
        dirs.sort(key=lambda x: x["name"].lower())
        sorted_entries = dirs + files

        total = len(sorted_entries)
        start = (page - 1) * page_size
        end = start + page_size
        page_entries = sorted_entries[start:end]

        parent = os.path.dirname(dirpath)
        # Only allow parent navigation within allowed dirs
        parent_real = os.path.realpath(parent).lower()
        if not any(parent_real.startswith(a) for a in allowed):
            parent = None

        self.send_json({
            "path": os.path.normpath(dirpath),
            "parent": parent,
            "entries": page_entries,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": end < total,
        })

    def _handle_staging_check(self):
        try:
            body = self.read_json_body()
        except Exception:
            self.send_error_json("Invalid JSON body")
            return

        directory = body.get("directory", "")
        if not directory:
            self.send_json({"is_onedrive": False})
            return

        is_od = is_onedrive_path(directory)
        settings = load_settings()
        staging_dir = get_staging_dir(
            directory, settings.get("staging_dir", DEFAULTS["staging_dir"]))

        result = {"is_onedrive": is_od, "staging_dir": staging_dir}

        if is_od and os.path.isdir(directory):
            try:
                file_count, total_bytes = count_files_for_staging(directory)
                result["file_count"] = file_count
                result["estimated_bytes"] = total_bytes
                result["estimated_gb"] = round(total_bytes / (1024 ** 3), 1)
            except Exception:
                result["file_count"] = 0
                result["estimated_bytes"] = 0

            # Check free space
            import shutil as _shutil
            try:
                _, _, free = _shutil.disk_usage(
                    os.path.splitdrive(staging_dir)[0] or "C:")
                result["free_space_gb"] = round(free / (1024 ** 3), 1)
            except Exception:
                pass

            # Check for existing staging session (only if it has files)
            manifest = load_manifest(directory)
            if manifest:
                mf_staging = manifest.get("staging_dir", "")
                has_files = False
                if mf_staging and os.path.isdir(mf_staging):
                    has_files = any(
                        f for _, _, files in os.walk(mf_staging)
                        for f in files
                    )
                if has_files:
                    result["existing_session"] = {
                        "staging_dir": mf_staging,
                        "file_count": manifest.get("file_count", 0),
                        "created": manifest.get("created", ""),
                    }

        self.send_json(result)

    def _handle_staging_start(self):
        global staging_thread, staging_cancel

        if staging_thread and staging_thread.is_alive():
            self.send_error_json("Staging is already running", 409)
            return

        try:
            body = self.read_json_body()
        except Exception:
            self.send_error_json("Invalid JSON body")
            return

        source_dir = body.get("source_dir", "")
        if not source_dir or not os.path.isdir(source_dir):
            self.send_error_json("Invalid source directory")
            return

        settings = load_settings()
        staging_dir = body.get("staging_dir") or get_staging_dir(
            source_dir, settings.get("staging_dir", DEFAULTS["staging_dir"]))
        extensions = settings.get("extensions")

        # Check available disk space on target drive (best-effort)
        try:
            import shutil as _shutil
            source_size = 0
            ext_set = set(extensions) if extensions else None
            for root, dirs, fnames in os.walk(source_dir):
                for fname in fnames:
                    if ext_set:
                        ext = os.path.splitext(fname)[1].lower()
                        if ext not in ext_set:
                            continue
                    fpath = os.path.join(root, fname)
                    try:
                        source_size += os.path.getsize(fpath)
                    except OSError:
                        pass
            target_drive = os.path.splitdrive(staging_dir)[0]
            if target_drive:
                usage = _shutil.disk_usage(target_drive + os.sep)
                buffer = 100 * 1024 * 1024  # 100 MB buffer
                if usage.free < source_size + buffer:
                    needed_gb = round(
                        (source_size + buffer) / (1024 ** 3), 1)
                    free_gb = round(usage.free / (1024 ** 3), 1)
                    self.send_error_json(
                        "Not enough disk space. Need about "
                        + str(needed_gb) + " GB but only "
                        + str(free_gb) + " GB free on "
                        + target_drive, 400)
                    return
        except Exception:
            pass  # If space check fails, proceed anyway

        staging_cancel = threading.Event()
        staging_thread = threading.Thread(
            target=_run_staging,
            args=(source_dir, staging_dir, extensions),
            daemon=True,
        )
        staging_thread.start()

        self.send_json({
            "status": "started",
            "source_dir": source_dir,
            "staging_dir": staging_dir,
        })

    def _handle_staging_cancel(self):
        staging_cancel.set()
        self.send_json({"status": "cancelling"})

    def _handle_staging_progress_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            while True:
                data = dict(staging_progress)
                msg = "data: " + json.dumps(data) + "\n\n"
                self.wfile.write(msg.encode("utf-8"))
                self.wfile.flush()

                if data.get("status") in ("complete", "error", "cancelled", "idle"):
                    break

                time.sleep(0.5)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _handle_staging_status(self):
        result = dict(staging_progress)

        # If no in-memory session, try to reconstruct from disk
        if not result.get("staging_dir"):
            staging_path = _find_staging_subfolder()
            if staging_path:
                has_files = any(
                    f for _, _, files in os.walk(staging_path)
                    for f in files
                )
                if has_files:
                    result["staging_dir"] = staging_path
                    result["status"] = "complete"

                    # Try to find source_dir from settings or manifest
                    settings = load_settings()
                    source = settings.get("default_pictures_path", "")
                    if not source:
                        source = default_pictures_path()
                    scans_dir = Path(__file__).parent.parent / "scans"
                    if scans_dir.is_dir():
                        for mf in scans_dir.glob(
                                "staging_manifest_*.json"):
                            try:
                                with open(str(mf), "r",
                                          encoding="utf-8") as f:
                                    manifest = json.load(f)
                                if manifest.get(
                                        "staging_dir") == staging_path:
                                    source = manifest.get(
                                        "source_dir", source)
                                    break
                            except Exception:
                                pass
                    result["source_dir"] = source

        self.send_json(result)

    def _handle_syncback_start(self):
        global syncback_thread, syncback_cancel

        if syncback_thread and syncback_thread.is_alive():
            self.send_error_json("Sync-back is already running", 409)
            return

        try:
            body = self.read_json_body()
        except Exception:
            self.send_error_json("Invalid JSON body")
            return

        staging_dir = body.get("staging_dir", "")
        source_dir = body.get("source_dir", "")

        if not staging_dir or not source_dir:
            self.send_error_json("Missing staging_dir or source_dir")
            return

        syncback_cancel = threading.Event()
        syncback_thread = threading.Thread(
            target=_run_syncback,
            args=(staging_dir, source_dir),
            daemon=True,
        )
        syncback_thread.start()

        self.send_json({"status": "started"})

    def _handle_syncback_progress_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            while True:
                data = dict(syncback_progress)
                msg = "data: " + json.dumps(data) + "\n\n"
                self.wfile.write(msg.encode("utf-8"))
                self.wfile.flush()

                if data.get("status") in ("complete", "error", "idle"):
                    break

                time.sleep(0.5)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _handle_staging_cleanup(self):
        try:
            body = self.read_json_body()
        except Exception:
            self.send_error_json("Invalid JSON body")
            return

        staging_dir = body.get("staging_dir", "")
        if not staging_dir:
            self.send_error_json("Missing staging_dir")
            return

        result = cleanup_staging(staging_dir)
        _log_activity("staging_cleanup", {
            "staging_dir": staging_dir,
            "result": result.get("status"),
        })
        self.send_json(result)

    def _handle_staging_reset(self):
        """Reset in-memory staging session state (no file operations)."""
        staging_progress.update({
            "status": "idle",
            "staging_dir": "",
            "source_dir": "",
            "current": 0,
            "total": 0,
            "bytes_copied": 0,
            "bytes_total": 0,
            "stage": "",
            "message": "",
        })
        _log_activity("staging_reset", {"source": "finish_cleanup"})
        self.send_json({"status": "reset"})

    def _handle_staging_recycle_bin(self):
        try:
            body = self.read_json_body()
        except Exception:
            self.send_error_json("Invalid JSON body")
            return

        # Support both explicit staging_dir and folder name ("staging"/"dupes")
        folder = body.get("folder", "")
        staging_dir = body.get("staging_dir", "")

        if folder == "dupes":
            settings = load_settings()
            target_dir = settings.get(
                "move_destination", DEFAULTS["move_destination"]
            )
        elif folder == "staging" or staging_dir:
            target_dir = staging_dir or ""
        else:
            self.send_error_json("Missing folder or staging_dir")
            return

        if not target_dir:
            self.send_error_json("Could not resolve target directory")
            return

        result = recycle_staging(target_dir)
        _log_activity("staging_recycle_bin", {
            "folder": folder or "staging",
            "target_dir": target_dir,
            "files_recycled": result.get("files_recycled", 0),
            "errors": result.get("errors", 0),
        })
        self.send_json(result)


_server_instance = None


def create_server(port=8787, enable_heartbeat=True):
    """Create and return a ThreadingHTTPServer instance."""
    global _server_instance
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", port),
        DupeFinderHandler,
    )
    _server_instance = server

    # Start heartbeat checker (browser mode only)
    if enable_heartbeat:
        _touch_heartbeat()
        checker = threading.Thread(target=_heartbeat_checker, daemon=True)
        checker.start()

    _log_activity("server_started", {"port": port})

    return server

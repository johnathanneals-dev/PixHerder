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
    load_settings, save_settings, ensure_dirs,
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
_shutdown_grace_seconds = 30


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
            # Don't shut down if a scan or action is running
            if scan_thread and scan_thread.is_alive():
                _touch_heartbeat()  # keep alive during scans
                continue
            if action_thread and action_thread.is_alive():
                _touch_heartbeat()
                continue
            if oddball_thread and oddball_thread.is_alive():
                _touch_heartbeat()
                continue

            _log_activity("auto_shutdown", {
                "reason": "No browser connection for "
                          + str(int(elapsed)) + " seconds",
            })
            time.sleep(0.5)
            if _server_instance:
                _server_instance.shutdown()
            os._exit(0)


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

    scan_progress.update({
        "status": "running",
        "stage": "discovering",
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


def _run_action(action_type, groups, move_dir=None, keep_strategy="largest"):
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
        elif path == "/api/scans":
            self._handle_get_scans()
        elif path == "/api/scan/progress":
            self._handle_scan_progress_sse()
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
        elif path == "/api/activity":
            limit = int(params.get("limit", ["50"])[0])
            self._handle_get_activity(limit)
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
        elif path == "/api/scans/delete":
            self._handle_delete_scan()
        elif path == "/api/shutdown":
            self._handle_shutdown()
        elif path == "/api/activity/clear":
            self._handle_clear_activity()
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
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_error_json("Could not load index.html: " + str(e), 500)

    def _handle_heartbeat(self):
        _touch_heartbeat()
        self.send_json({"status": "ok"})

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
        self.send_header("Access-Control-Allow-Origin", "*")
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
        filepath = os.path.normpath(filepath)
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
            stat = os.stat(filepath)
            etag = '"' + str(stat.st_mtime) + "-" + str(stat.st_size) + '"'

            # Check if client has cached version
            if_none_match = self.headers.get("If-None-Match")
            if if_none_match == etag:
                self.send_response(304)
                self.end_headers()
                return

            with open(filepath, "rb") as f:
                data = f.read()

            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "max-age=3600")
            self.send_header("ETag", etag)
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_error(500, str(e))

    def _handle_get_settings(self):
        self.send_json(load_settings())

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
                            settings.get("move_destination", "C:\\Temp\\dupes"))
        keep_strategy = settings.get("keep_strategy", "largest")

        action_cancel = threading.Event()
        action_thread = threading.Thread(
            target=_run_action,
            args=("move", groups, move_dir, keep_strategy),
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

        action_cancel = threading.Event()
        action_thread = threading.Thread(
            target=_run_action,
            args=("delete", groups, None, keep_strategy),
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
            os._exit(0)
        threading.Thread(target=_shutdown, daemon=True).start()


_server_instance = None


def create_server(port=8787):
    """Create and return a ThreadingHTTPServer instance."""
    global _server_instance
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", port),
        DupeFinderHandler,
    )
    _server_instance = server

    # Start heartbeat checker
    _touch_heartbeat()
    checker = threading.Thread(target=_heartbeat_checker, daemon=True)
    checker.start()

    _log_activity("server_started", {"port": port})

    return server

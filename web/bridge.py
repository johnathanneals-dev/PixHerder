"""
PixHerder pywebview API bridge.
Maps all HTTP API endpoints to Python methods callable from JS.
Imports shared state and runner functions from server.py.
"""

import json
import logging
import os
import shutil
import stat
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.config import (
    SCANS_DIR, ACTIVITY_LOG, PROJECT_ROOT as ROOT,
    DEFAULTS, VERSION, load_settings, save_settings, default_pictures_path,
    verify_copy as _verify_copy,
)
from engine.scanner import find_images, count_images
from engine.comparator import pick_original
from engine.actions import rescue_file
from engine.checkpoint import (
    checkpoint_path, find_checkpoint, delete_checkpoint,
)
from engine.staging import (
    is_onedrive_path, is_onedrive_running, get_staging_dir,
    count_files_for_staging, cleanup_staging, recycle_staging,
)
from engine.state_validator import validate_state

# Import shared state and runners from workers module
from web.workers import (
    worker_manager,
    scan_progress, action_progress, oddball_progress,
    staging_progress, syncback_progress, restore_progress,
    scan_cancel, action_cancel, oddball_cancel,
    staging_cancel, syncback_cancel,
    _log_activity, _read_activity, _find_staging_subfolder,
    _run_scan, _run_action, _run_oddball, _run_staging, _run_syncback,
    _run_restore, _reset_all_progress,
    recycle_source_dupes, move_dupes_to_folder,
)

# Thread references (mirrors server.py globals)
_threads = {
    "scan": None,
    "action": None,
    "oddball": None,
    "staging": None,
    "syncback": None,
}

from engine.config import IMAGE_EXTENSIONS
IMAGE_EXTS = IMAGE_EXTENSIONS

_BLOCKED_PREFIXES = None

def _is_safe_source_path(dirpath):
    """Reject system directories and drive roots as scan/staging sources."""
    global _BLOCKED_PREFIXES
    if _BLOCKED_PREFIXES is None:
        windir = os.environ.get("WINDIR", "C:\\Windows")
        _BLOCKED_PREFIXES = [
            os.path.realpath(windir).lower(),
            os.path.realpath(os.path.join(windir, "system32")).lower(),
            os.path.realpath(
                os.environ.get("PROGRAMFILES", "C:\\Program Files")).lower(),
            os.path.realpath(os.environ.get(
                "PROGRAMFILES(X86)", "C:\\Program Files (x86)")).lower(),
        ]
    norm = os.path.realpath(dirpath).lower()
    if len(norm) <= 3:
        return False
    return not any(norm == b or norm.startswith(b + os.sep)
                   for b in _BLOCKED_PREFIXES)


class Api:
    """pywebview API bridge. Each method maps to an HTTP endpoint."""

    def __init__(self):
        self._window = None
        self._stop_events = {}  # Track stop events per progress type

    def set_window(self, window):
        self._window = window

    # ---- Progress push (replaces SSE) ----

    def _push_progress(self, progress_dict, callback_name, terminals,
                       stop_event):
        """Generic progress pusher. Polls dict, calls JS callback."""
        while not stop_event.is_set():
            data = dict(progress_dict)
            if "elapsed" in data:
                data["elapsed"] = round(data.get("elapsed", 0), 1)
            try:
                js = callback_name + "(" + json.dumps(data) + ")"
                self._window.evaluate_js(js)
            except Exception as e:
                logger.error("Progress push failed for %s: %s", callback_name, e)
                break
            if data.get("status") in terminals:
                break
            time.sleep(0.5)

    def _subscribe(self, key, progress_dict, callback_name, terminals):
        """Start a progress pusher, cancelling any previous one for this key."""
        old = self._stop_events.get(key)
        if old:
            old.set()
        stop = threading.Event()
        self._stop_events[key] = stop
        t = threading.Thread(
            target=self._push_progress,
            args=(progress_dict, callback_name, terminals, stop),
            daemon=True)
        t.start()
        return {"subscribed": True}

    def subscribe_scan_progress(self, params=None):
        return self._subscribe("scan", scan_progress, "_onScanProgress",
                               ("complete", "error", "cancelled", "idle"))

    def subscribe_action_progress(self, params=None):
        return self._subscribe("action", action_progress,
                               "_onActionProgress",
                               ("complete", "error", "idle"))

    def subscribe_oddball_progress(self, params=None):
        return self._subscribe("oddball", oddball_progress,
                               "_onOddballProgress",
                               ("complete", "error", "idle"))

    def subscribe_staging_progress(self, params=None):
        return self._subscribe("staging", staging_progress,
                               "_onStagingProgress",
                               ("complete", "error", "cancelled", "idle"))

    def subscribe_syncback_progress(self, params=None):
        return self._subscribe("syncback", syncback_progress,
                               "_onSyncbackProgress",
                               ("complete", "error", "idle"))

    def subscribe_restore_progress(self, params=None):
        return self._subscribe("restore", restore_progress,
                               "_onRestoreProgress",
                               ("complete", "error"))

    # ---- GET equivalents ----

    def get_scans(self, params=None):
        scans = []
        if SCANS_DIR.exists():
            for f in sorted(SCANS_DIR.glob("*.json"), reverse=True):
                if f.name.startswith("decisions_"):
                    continue
                try:
                    with open(str(f), "r") as fh:
                        data = json.load(fh)
                    meta = data.get("metadata", {})
                    exact_count = len(data.get("exact_groups", []))
                    perceptual_count = len(data.get("perceptual_groups", []))
                    all_groups = (
                        data.get("exact_groups", [])
                        + data.get("perceptual_groups", [])
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
        return scans

    def get_settings(self, params=None):
        settings = load_settings()
        settings["default_pictures_path"] = default_pictures_path()
        settings["version"] = VERSION
        return settings

    def get_folders_status(self, params=None):
        settings = load_settings()

        def _count(dirpath):
            if not dirpath or not os.path.isdir(dirpath):
                return {"exists": False, "path": dirpath or "", "file_count": 0}
            count = 0
            for root, dirs, files in os.walk(dirpath):
                for f in files:
                    if os.path.splitext(f)[1].lower() in IMAGE_EXTS:
                        count += 1
            return {"exists": True, "path": dirpath, "file_count": count}

        staging_path = _find_staging_subfolder()
        dupes_path = settings.get("move_destination", DEFAULTS["move_destination"])
        keepers_path = settings.get("keepers_dir", DEFAULTS["keepers_dir"])
        return {
            "staging": _count(staging_path),
            "dupes": _count(dupes_path),
            "keepers": _count(keepers_path),
        }

    def get_activity(self, limit=50):
        if isinstance(limit, dict):
            limit = limit.get("limit", 50)
        entries = _read_activity(int(limit))
        return {"entries": entries}

    def check_resume(self, params=None):
        if params is None:
            params = {}
        directory = params.get("directory", "")
        mode = params.get("mode", "both")
        if not directory:
            return {"has_checkpoint": False}
        ckpt, data = find_checkpoint(directory, mode)
        if data:
            md5_count = len(data.get("md5_hashes", {}))
            phash_count = len(data.get("phash_hashes", {}))
            return {
                "has_checkpoint": True,
                "checkpoint_info": {
                    "stage": data.get("stage", "unknown"),
                    "md5_hashed": md5_count,
                    "phash_hashed": phash_count,
                    "timestamp": data.get("timestamp", ""),
                    "threshold": data.get("threshold"),
                    "mode": data.get("mode", mode),
                },
            }
        return {"has_checkpoint": False}

    def get_groups(self, params=None):
        if params is None:
            params = {}
        report = params.get("report", "")
        if not report:
            return {"error": "Missing report parameter"}
        report_path = SCANS_DIR / report
        if not report_path.exists():
            report_path = ROOT / report
        if not report_path.exists():
            return {"error": "Report not found: " + report}
        try:
            with open(str(report_path), "r") as f:
                data = json.load(f)
            if isinstance(data, list):
                return {"groups": data, "metadata": None}
            elif isinstance(data, dict):
                groups = (
                    data.get("exact_groups", [])
                    + data.get("perceptual_groups", [])
                )
                return {"groups": groups, "metadata": data.get("metadata"),
                        "file_info": data.get("file_info", {})}
            return {"error": "Invalid report format"}
        except Exception as e:
            return {"error": "Error reading report: " + str(e)}

    def decisions_load(self, params=None):
        if params is None:
            params = {}
        report = params.get("report", "")
        if not report:
            return {"decisions": []}
        safe_name = os.path.basename(report).replace(".json", "")
        dec_path = SCANS_DIR / ("decisions_" + safe_name + ".json")
        if dec_path.is_file():
            try:
                with open(str(dec_path), "r") as f:
                    data = json.load(f)
                return {"decisions": data.get("decisions", [])}
            except Exception:
                return {"decisions": []}
        return {"decisions": []}

    def app_state(self, params=None):
        """Single source of truth: derive complete app state from filesystem.
        No in-memory caches -- everything checked fresh."""
        settings = load_settings()
        image_exts = IMAGE_EXTS

        def _count(dirpath):
            if not dirpath or not os.path.isdir(dirpath):
                return {"exists": False, "path": dirpath or "", "count": 0}
            count = 0
            for root, dirs, files in os.walk(dirpath):
                for f in files:
                    if os.path.splitext(f)[1].lower() in image_exts:
                        count += 1
            return {"exists": True, "path": dirpath, "count": count}

        # Folders -- derived from filesystem
        staging_path = _find_staging_subfolder()
        dupes_path = settings.get("move_destination", DEFAULTS["move_destination"])
        keepers_path = settings.get("keepers_dir", DEFAULTS["keepers_dir"])

        staging = _count(staging_path)
        dupes = _count(dupes_path)
        keepers = _count(keepers_path)

        # Session -- derived from manifest files on disk
        source_dir = ""
        if staging_path:
            scans_dir = Path(__file__).parent.parent / "scans"
            if scans_dir.is_dir():
                for mf in scans_dir.glob("staging_manifest_*.json"):
                    try:
                        with open(str(mf), "r", encoding="utf-8") as f:
                            manifest = json.load(f)
                        if manifest.get("staging_dir") == staging_path:
                            source_dir = manifest.get("source_dir", "")
                            break
                    except Exception:
                        pass

        has_session = bool(staging_path and staging["count"] > 0 and source_dir)

        # Scans -- derived from scan result files on disk
        scans = []
        scans_dir_path = Path(__file__).parent.parent / "scans"
        if scans_dir_path.is_dir():
            for f in sorted(scans_dir_path.glob("scan_*.json"), reverse=True):
                try:
                    with open(str(f), "r") as fh:
                        data = json.load(fh)
                    meta = data.get("metadata", {})
                    exact_count = len(data.get("exact_groups", []))
                    perceptual_count = len(data.get("perceptual_groups", []))
                    scans.append({
                        "filename": f.name,
                        "directory": meta.get("directory", ""),
                        "mode": meta.get("mode", ""),
                        "total_groups": exact_count + perceptual_count,
                    })
                except Exception:
                    pass

        # Recovery archive
        try:
            from engine.recovery import get_archive_status
            recovery = get_archive_status()
        except Exception:
            recovery = {"has_files": False}

        return {
            "folders": {
                "staging": staging,
                "dupes": dupes,
                "keepers": keepers,
            },
            "session": {
                "source_dir": source_dir,
                "staging_dir": staging_path or "",
                "active": has_session,
            },
            "scans": scans,
            "has_scans": len(scans) > 0,
            "recovery": recovery,
        }

    def reset_state(self, params=None):
        """Clear all in-memory state. Called after cleanup operations."""
        _reset_all_progress()
        return {"status": "reset"}

    def validate_state(self, params=None):
        """Run state validator to clean up stale artifacts."""
        return validate_state()

    def staging_status(self, params=None):
        data = dict(staging_progress)
        if not data.get("staging_dir") and not data.get("source_dir"):
            # Try to recover from disk
            staging_sub = _find_staging_subfolder()
            if staging_sub:
                # Only recover session if we have a manifest with source_dir
                source = ""
                scans_dir = Path(__file__).parent.parent / "scans"
                if scans_dir.is_dir():
                    for mf in scans_dir.glob("staging_manifest_*.json"):
                        try:
                            with open(str(mf), "r", encoding="utf-8") as f:
                                manifest = json.load(f)
                            if manifest.get("staging_dir") == staging_sub:
                                source = manifest.get("source_dir", "")
                                break
                        except Exception:
                            pass
                if source:
                    data["staging_dir"] = staging_sub
                    data["source_dir"] = source
                    data["status"] = "complete"
                # No manifest = no session. Don't fabricate source_dir.
        return data

    def browse(self, params=None):
        if params is None:
            params = {}
        dirpath = params.get("path", "")
        page = int(params.get("page", 1))
        page_size = int(params.get("page_size", 50))
        sort_by = params.get("sort", "name")

        if not dirpath or not os.path.isdir(dirpath):
            return {"error": "Invalid directory", "files": [], "total": 0}

        # Security: restrict to staging/dupes/keepers dirs
        settings = load_settings()
        allowed = [
            settings.get("staging_dir", DEFAULTS["staging_dir"]),
            settings.get("move_destination", DEFAULTS["move_destination"]),
            settings.get("keepers_dir", DEFAULTS["keepers_dir"]),
        ]
        # Also allow the active staging subfolder (may differ from settings)
        active_staging = _find_staging_subfolder()
        if active_staging:
            allowed.append(os.path.dirname(active_staging))
            allowed.append(active_staging)
        norm_dir = os.path.normpath(dirpath)
        allowed_norms = [os.path.normpath(d) for d in allowed if d]
        if not any(norm_dir == a or norm_dir.startswith(a + os.sep)
                   for a in allowed_norms):
            logger.warning("Browse access denied: %s not in %s", norm_dir, allowed_norms)
            return {"error": "Access denied", "files": [], "total": 0}

        files = []
        for root, dirs, fnames in os.walk(dirpath):
            for fname in fnames:
                ext = os.path.splitext(fname)[1].lower()
                if ext in IMAGE_EXTS:
                    fpath = os.path.join(root, fname)
                    try:
                        st = os.stat(fpath)
                        files.append({
                            "name": fname,
                            "path": fpath,
                            "size": st.st_size,
                            "modified": st.st_mtime,
                        })
                    except OSError:
                        pass

        if sort_by == "size":
            files.sort(key=lambda x: x["size"], reverse=True)
        elif sort_by == "modified":
            files.sort(key=lambda x: x["modified"], reverse=True)
        else:
            files.sort(key=lambda x: x["name"].lower())

        total = len(files)
        start = (page - 1) * page_size
        end = start + page_size
        page_files = files[start:end]
        entries = []
        for f in page_files:
            entries.append({
                "name": f["name"],
                "path": f["path"],
                "size": f["size"],
                "modified": f["modified"],
                "is_dir": False,
            })
        # Also include subdirectories at current level
        if page == 1:
            try:
                for d in sorted(os.listdir(dirpath)):
                    dpath = os.path.join(dirpath, d)
                    if os.path.isdir(dpath) and not d.startswith("."):
                        entries.insert(0, {
                            "name": d,
                            "path": dpath,
                            "is_dir": True,
                        })
            except OSError:
                pass
        return {
            "entries": entries,
            "total": total,
            "path": dirpath,
            "has_more": end < total,
            "page": page,
            "page_size": page_size,
        }

    def browse_folders(self, params=None):
        if params is None:
            params = {}
        dirpath = params.get("path", "")

        # Drive listing: enumerate available Windows drives
        if dirpath == "__drives__":
            import string
            drives = []
            for letter in string.ascii_uppercase:
                drive = letter + ":\\"
                if os.path.isdir(drive):
                    drives.append(drive)
            return {
                "path": "My Computer",
                "parent": "",
                "folders": drives,
                "is_drives": True,
            }

        if not dirpath or not os.path.isdir(dirpath):
            return {"folders": [], "error": "Invalid path"}
        # Block system directories
        lower = os.path.normpath(dirpath).lower()
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
            return {"folders": [], "error": "Access denied"}
        try:
            folders = []
            for entry in sorted(os.listdir(dirpath)):
                full = os.path.join(dirpath, entry)
                if os.path.isdir(full) and not entry.startswith("."):
                    folders.append(entry)
        except PermissionError:
            pass
        except Exception as e:
            return {"folders": [], "error": str(e)}

        parent = os.path.dirname(dirpath)
        if parent == dirpath:
            parent = "__drives__"
        return {"path": dirpath, "parent": parent, "folders": folders}

    # ---- POST equivalents ----

    def scan_start(self, params=None):
        logger.debug("Bridge call: scan_start(%s)", params)
        if params is None:
            params = {}
        if worker_manager.scan_thread and worker_manager.scan_thread.is_alive():
            return {"error": "A scan is already running"}

        directory = params.get("directory", "")
        if not directory or not os.path.isdir(directory):
            return {"error": "Invalid directory: " + str(directory)}
        if not _is_safe_source_path(directory):
            return {"error": "Cannot scan system directories or drive roots"}

        settings = load_settings()
        mode = params.get("mode", "both")
        threshold = params.get("threshold", settings.get("threshold", 5))
        recursive = params.get("recursive", settings.get("recursive", True))
        hash_size = settings.get("hash_size", 16)
        keep_strategy = settings.get("keep_strategy", "largest")
        extensions = settings.get("extensions")

        resume = params.get("resume", False)
        auto_recycle = params.get("auto_recycle", False)
        scan_limit = int(params.get("scan_limit", 0) or 0)
        logger.debug("Scan start: dir=%s, mode=%s, scan_limit=%s", directory, mode, scan_limit)
        resume_data = None
        if resume:
            _, resume_data = find_checkpoint(directory, mode)
        if not resume:
            ckpt = checkpoint_path(directory, mode)
            delete_checkpoint(ckpt)

        def _prime_scan_progress():
            scan_progress.update({
                "status": "running",
                "stage": "starting",
                "current": 0, "total": 0, "elapsed": 0, "errors": 0,
                "message": "Starting scan...",
                "result_file": None,
            })

        if not worker_manager.start_worker(
                "scan_thread", _run_scan,
                (directory, mode, threshold, recursive, hash_size,
                 keep_strategy, extensions, resume_data, auto_recycle,
                 scan_limit),
                cancel_attr="scan_cancel",
                before_start=_prime_scan_progress):
            return {"error": "A scan is already running"}

        return {
            "status": "started",
            "directory": directory,
            "mode": mode,
            "resumed": bool(resume_data),
        }

    def scan_cancel_op(self, params=None):
        worker_manager.scan_cancel.set()
        return {"status": "cancelling"}

    def action_move(self, params=None):
        logger.debug("Bridge call: action_move(%d groups)", len((params or {}).get("groups", [])))
        if params is None:
            params = {}
        if worker_manager.action_thread and worker_manager.action_thread.is_alive():
            return {"error": "An action is already running"}

        groups = params.get("groups", [])
        if not groups:
            return {"error": "No groups provided"}

        settings = load_settings()
        move_dir = params.get("destination",
                              settings.get("move_destination",
                                           DEFAULTS["move_destination"]))
        if not _is_safe_source_path(move_dir):
            return {"error": "Cannot move files to system directories or drive roots"}
        keep_strategy = settings.get("keep_strategy", "largest")
        report_file = params.get("report")
        scan_dir = _find_staging_subfolder() or ""

        if not worker_manager.start_worker(
                "action_thread", _run_action,
                ("move", groups, move_dir, keep_strategy, report_file,
                 scan_dir),
                cancel_attr="action_cancel"):
            return {"error": "An action is already running"}
        return {"status": "started", "action": "move"}

    def action_delete(self, params=None):
        logger.debug("Bridge call: action_delete(%d groups)", len((params or {}).get("groups", [])))
        if params is None:
            params = {}
        if worker_manager.action_thread and worker_manager.action_thread.is_alive():
            return {"error": "An action is already running"}

        groups = params.get("groups", [])
        if not groups:
            return {"error": "No groups provided"}

        settings = load_settings()
        keep_strategy = settings.get("keep_strategy", "largest")
        report_file = params.get("report")

        if not worker_manager.start_worker(
                "action_thread", _run_action,
                ("delete", groups, None, keep_strategy, report_file),
                cancel_attr="action_cancel"):
            return {"error": "An action is already running"}
        return {"status": "started", "action": "delete"}

    def action_rescue(self, params=None):
        if params is None:
            params = {}
        source = params.get("source", "")
        destination = params.get("destination", "")
        if not source or not destination:
            return {"error": "Missing source or destination"}
        return rescue_file(source, destination)

    def save_settings(self, params=None):
        if params is None:
            params = {}
        return save_settings(params)

    def oddball_run(self, params=None):
        if params is None:
            params = {}
        if worker_manager.oddball_thread and worker_manager.oddball_thread.is_alive():
            return {"error": "Oddball check is already running"}

        report = params.get("report", "")
        if not report:
            return {"error": "Missing report filename"}

        report_path = SCANS_DIR / report
        if not report_path.exists():
            report_path = ROOT / report
        if not report_path.exists():
            return {"error": "Report not found"}

        try:
            with open(str(report_path), "r") as f:
                report_data = json.load(f)
        except Exception as e:
            return {"error": "Failed to read report: " + str(e)}

        dupes_folder = params.get("dupes_folder", "")
        if not dupes_folder:
            settings = load_settings()
            dupes_folder = settings.get("move_destination",
                                        DEFAULTS["move_destination"])

        if not worker_manager.start_worker(
                "oddball_thread", _run_oddball, (report_data, dupes_folder),
                cancel_attr="oddball_cancel"):
            return {"error": "Oddball check is already running"}
        return {"status": "started"}

    def decisions_save(self, params=None):
        if params is None:
            params = {}
        report = params.get("report", "")
        decisions = params.get("decisions", [])
        if not report or not decisions:
            return {"error": "Missing report or decisions"}
        scans_dir = Path(__file__).parent.parent / "scans"
        os.makedirs(str(scans_dir), exist_ok=True)
        safe_name = os.path.basename(report).replace(".json", "")
        dec_path = scans_dir / ("decisions_" + safe_name + ".json")
        try:
            from engine.config import safe_json_write
            safe_json_write(dec_path, {"report": report, "decisions": decisions})
            return {"success": True}
        except Exception as e:
            return {"error": "Failed to save decisions: " + str(e)}

    def scans_delete(self, params=None):
        if params is None:
            params = {}
        filename = params.get("filename", "")
        if not filename:
            return {"error": "Missing filename"}
        target = SCANS_DIR / filename
        if not target.exists():
            return {"error": "Scan not found"}
        try:
            os.remove(str(target))
            # Also clean up decisions file
            safe_name = os.path.basename(filename).replace(".json", "")
            dec_path = SCANS_DIR / ("decisions_" + safe_name + ".json")
            if dec_path.exists():
                try:
                    os.remove(str(dec_path))
                except Exception:
                    pass
            return {"status": "deleted", "filename": filename}
        except Exception as e:
            return {"error": "Failed to delete: " + str(e)}

    def clear_activity(self, params=None):
        try:
            with open(str(ACTIVITY_LOG), "w") as f:
                f.truncate(0)
            return {"status": "cleared"}
        except Exception as e:
            return {"error": "Failed to clear log: " + str(e)}

    def onedrive_status(self, params=None):
        """Check if OneDrive is running and if a path is OneDrive-managed."""
        if params is None:
            params = {}
        directory = params.get("directory", "")
        running = is_onedrive_running()
        is_od = is_onedrive_path(directory) if directory else False
        settings = load_settings()
        return {
            "running": running,
            "is_onedrive": is_od,
            "show_prompts": settings.get("show_onedrive_prompts", True),
        }

    def staging_check(self, params=None):
        if params is None:
            params = {}
        directory = params.get("directory", "")
        if not directory:
            directory = default_pictures_path()
        is_od = is_onedrive_path(directory)

        settings = load_settings()
        staging_dir = get_staging_dir(
            directory, settings.get("staging_dir", DEFAULTS["staging_dir"]))

        # Check if staging exists with files
        existing = _find_staging_subfolder()
        existing_count = 0
        if existing:
            for root, dirs, files in os.walk(existing):
                for f in files:
                    if os.path.splitext(f)[1].lower() in IMAGE_EXTS:
                        existing_count += 1

        # Count source files
        source_count = 0
        if os.path.isdir(directory):
            extensions = settings.get("extensions", DEFAULTS["extensions"])
            source_count = count_files_for_staging(directory, extensions)

        # Disk space check
        free_gb = 0
        try:
            target_drive = os.path.splitdrive(staging_dir)[0]
            if target_drive:
                usage = shutil.disk_usage(target_drive + os.sep)
                free_gb = round(usage.free / (1024 ** 3), 1)
        except Exception:
            pass

        return {
            "directory": directory,
            "is_onedrive": is_od,
            "staging_dir": staging_dir,
            "existing_staging": existing or "",
            "existing_count": existing_count,
            "source_count": source_count,
            "free_space_gb": free_gb,
        }

    def staging_start(self, params=None):
        logger.debug("Bridge call: staging_start(%s)", params)
        if params is None:
            params = {}
        if worker_manager.staging_thread and worker_manager.staging_thread.is_alive():
            return {"error": "Staging is already running"}

        source_dir = params.get("source_dir", "")
        if not source_dir or not os.path.isdir(source_dir):
            return {"error": "Invalid source directory"}
        if not _is_safe_source_path(source_dir):
            return {"error": "Cannot stage system directories or drive roots"}

        settings = load_settings()
        staging_dir = params.get("staging_dir") or get_staging_dir(
            source_dir, settings.get("staging_dir", DEFAULTS["staging_dir"]))
        extensions = settings.get("extensions")

        # Disk space check (best-effort)
        try:
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
                usage = shutil.disk_usage(target_drive + os.sep)
                buffer = 100 * 1024 * 1024
                if usage.free < source_size + buffer:
                    needed = round((source_size + buffer) / (1024 ** 3), 1)
                    free = round(usage.free / (1024 ** 3), 1)
                    return {
                        "error": "Not enough disk space. Need about "
                        + str(needed) + " GB but only "
                        + str(free) + " GB free on " + target_drive
                    }
        except Exception:
            pass

        if not worker_manager.start_worker(
                "staging_thread", _run_staging,
                (source_dir, staging_dir, extensions),
                cancel_attr="staging_cancel"):
            return {"error": "Staging is already running"}

        return {
            "status": "started",
            "source_dir": source_dir,
            "staging_dir": staging_dir,
        }

    def staging_cancel_op(self, params=None):
        worker_manager.staging_cancel.set()
        return {"status": "cancelling"}

    def staging_syncback(self, params=None):
        logger.debug("Bridge call: staging_syncback(%s)", params)
        if params is None:
            params = {}
        if worker_manager.syncback_thread and worker_manager.syncback_thread.is_alive():
            return {"error": "Sync-back is already running"}

        staging_dir = params.get("staging_dir", "")
        source_dir = params.get("source_dir", "")
        if not staging_dir or not source_dir:
            return {"error": "Missing staging or source directory"}
        if not _is_safe_source_path(source_dir):
            return {"error": "Cannot write to system directories or drive roots"}

        if not worker_manager.start_worker(
                "syncback_thread", _run_syncback, (staging_dir, source_dir),
                cancel_attr="syncback_cancel"):
            return {"error": "Sync-back is already running"}
        return {"status": "started"}

    def staging_cleanup(self, params=None):
        if params is None:
            params = {}
        staging_dir = params.get("staging_dir", "")
        if not staging_dir:
            return {"error": "Missing staging_dir"}
        result = cleanup_staging(staging_dir)
        # Clean up system recovery backups on session finish
        from engine.config import cleanup_system_recovery
        cleanup_system_recovery()
        _log_activity("staging_cleanup", {
            "staging_dir": staging_dir,
            "result": result.get("status"),
        })
        return result

    def staging_reset(self, params=None):
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
        _log_activity("staging_reset", {"source": "bridge"})
        return {"status": "reset"}

    def staging_recycle_bin(self, params=None):
        if params is None:
            params = {}
        folder = params.get("folder", "")
        settings = load_settings()

        if folder == "staging":
            target = _find_staging_subfolder()
        elif folder == "dupes":
            target = settings.get("move_destination",
                                  DEFAULTS["move_destination"])
        elif folder == "keepers":
            target = settings.get("keepers_dir", DEFAULTS["keepers_dir"])
        else:
            return {"error": "Invalid folder: " + folder}

        if not target or not os.path.isdir(target):
            return {"error": "Folder not found or empty"}

        result = recycle_staging(target)
        _log_activity("recycle_bin", {
            "folder": folder,
            "recycled": result.get("recycled", 0),
        })
        return {"status": "recycled", **result}

    def recycle_source_dupes(self, params=None):
        """Recycle original duplicate files from the source folder."""
        if params is None:
            params = {}
        staging_dir = params.get("staging_dir", "")
        source_dir = params.get("source_dir", "")
        if not staging_dir or not source_dir:
            return {"error": "staging_dir and source_dir required"}
        if not _is_safe_source_path(source_dir):
            return {"error": "Cannot modify system directories or drive roots"}
        result = recycle_source_dupes(staging_dir, source_dir)
        _log_activity("recycle_source_dupes", {
            "recycled": result.get("recycled", 0),
            "source_dir": source_dir,
        })
        return result

    def move_dupes_to_folder(self, params=None):
        """Move duplicates to PixHerder_Duplicates folder in source dir."""
        params = params or {}
        staging_dir = params.get("staging_dir", "")
        source_dir = params.get("source_dir", "")
        if not staging_dir or not source_dir:
            return {"error": "Missing staging_dir or source_dir"}
        if not _is_safe_source_path(source_dir):
            return {"error": "Cannot modify system directories or drive roots"}
        result = move_dupes_to_folder(staging_dir, source_dir)
        _log_activity("move_dupes_to_folder",
                      "Moved %d files to folder" % result.get("total_moved", 0))
        return result

    def staging_restore(self, params=None):
        if params is None:
            params = {}
        staging_dir = params.get("staging_dir", "")
        source_dir = params.get("source_dir", "")
        full_restore = params.get("full_restore", False)
        include_keepers = params.get("include_keepers", False)

        if not source_dir:
            return {"error": "Source directory not specified"}
        if not _is_safe_source_path(source_dir):
            return {"error": "Cannot restore to system directories or drive roots"}

        if worker_manager.restore_thread and worker_manager.restore_thread.is_alive():
            return {"error": "Restore already running"}

        if not worker_manager.start_worker(
                "restore_thread", _run_restore,
                (staging_dir, source_dir, full_restore, include_keepers)):
            return {"error": "Restore already running"}
        return {"status": "started"}

    def staging_recycle(self, params=None):
        """Rescue & Review: move dupes back into staging."""
        if params is None:
            params = {}
        settings = load_settings()
        dupes_dir = settings.get("move_destination",
                                 DEFAULTS["move_destination"])
        staging_path = _find_staging_subfolder()
        force = params.get("force", False)

        if not os.path.isdir(dupes_dir):
            return {"error": "Recovery folder not found"}
        if not staging_path:
            return {"error": "Staging folder not found"}

        moved = 0
        errors_count = 0
        for root, dirs, files in os.walk(dupes_dir):
            for fname in files:
                src = os.path.join(root, fname)
                dest = os.path.join(staging_path, fname)
                # Collision avoidance
                if os.path.exists(dest):
                    base, ext = os.path.splitext(fname)
                    counter = 1
                    while os.path.exists(dest):
                        dest = os.path.join(
                            staging_path,
                            base + "_" + str(counter) + ext)
                        counter += 1
                try:
                    shutil.copy2(src, dest)
                    if not _verify_copy(src, dest):
                        errors_count += 1
                        continue
                    try:
                        os.chmod(src, stat.S_IWRITE | stat.S_IREAD)
                        os.remove(src)
                    except Exception:
                        pass
                    moved += 1
                except Exception:
                    errors_count += 1

        _log_activity("staging_recycle", {"moved": moved, "errors": errors_count})
        return {"status": "complete", "moved": moved, "errors": errors_count}

    def dupes_purge(self, params=None):
        settings = load_settings()
        dupes_dir = settings.get("move_destination",
                                 DEFAULTS["move_destination"])
        if not os.path.isdir(dupes_dir):
            return {"error": "Recovery folder not found"}
        result = recycle_staging(dupes_dir)
        _log_activity("dupes_purge", result)
        return {"status": "purged", **result}

    def dupes_promote(self, params=None):
        settings = load_settings()
        dupes_dir = settings.get("move_destination",
                                 DEFAULTS["move_destination"])
        keepers_dir = settings.get("keepers_dir", DEFAULTS["keepers_dir"])
        if not os.path.isdir(dupes_dir):
            return {"error": "Recovery folder not found"}
        os.makedirs(keepers_dir, exist_ok=True)
        moved = 0
        errors_count = 0
        for root, dirs, files in os.walk(dupes_dir):
            for fname in files:
                src = os.path.join(root, fname)
                dest = os.path.join(keepers_dir, fname)
                if os.path.exists(dest):
                    base, ext = os.path.splitext(fname)
                    counter = 1
                    while os.path.exists(dest):
                        dest = os.path.join(
                            keepers_dir,
                            base + "_" + str(counter) + ext)
                        counter += 1
                try:
                    shutil.move(str(src), str(dest))
                    moved += 1
                except Exception:
                    errors_count += 1
        _log_activity("dupes_promote", {"moved": moved})
        return {"success": True, "moved": moved, "errors": errors_count}

    def consolidate(self, params=None):
        settings = load_settings()
        dupes_dir = settings.get("move_destination",
                                 DEFAULTS["move_destination"])
        keepers_dir = settings.get("keepers_dir", DEFAULTS["keepers_dir"])
        staging_path = _find_staging_subfolder()
        if not staging_path:
            # Create a new staging subfolder when none exists
            # (e.g., after Send Files Home + state validator cleanup)
            import hashlib
            staging_base = settings.get("staging_dir",
                                        DEFAULTS["staging_dir"])
            key = "consolidate_" + str(int(time.time()))
            short_hash = hashlib.md5(
                key.encode("utf-8")).hexdigest()[:10]
            staging_path = os.path.join(staging_base, short_hash)
            try:
                os.makedirs(staging_path, exist_ok=True)
            except OSError as e:
                return {"error": "Could not create staging folder: "
                        + str(e)}

        moved = 0
        errors_count = 0

        def _move_back(source_dir):
            nonlocal moved, errors_count
            if not source_dir or not os.path.isdir(source_dir):
                return
            for root, dirs, files in os.walk(source_dir):
                for fname in files:
                    src = os.path.join(root, fname)
                    dest = os.path.join(staging_path, fname)
                    if os.path.exists(dest):
                        base, ext = os.path.splitext(fname)
                        counter = 1
                        while os.path.exists(dest):
                            dest = os.path.join(
                                staging_path,
                                base + "_" + str(counter) + ext)
                            counter += 1
                    try:
                        shutil.move(str(src), str(dest))
                        moved += 1
                    except Exception:
                        errors_count += 1

        _move_back(dupes_dir)
        _move_back(keepers_dir)
        _log_activity("consolidate", {"moved": moved})
        return {"success": True, "moved": moved, "errors": errors_count}

    def browser_delete(self, params=None):
        if params is None:
            params = {}
        filepath = params.get("path", "")
        if not filepath or not os.path.isfile(filepath):
            return {"error": "File not found"}

        # Security: restrict to allowed dirs
        settings = load_settings()
        allowed = [
            _find_staging_subfolder() or "",
            settings.get("move_destination", DEFAULTS["move_destination"]),
            settings.get("keepers_dir", DEFAULTS["keepers_dir"]),
        ]
        # realpath, not normpath: junctions/symlinks must resolve before the
        # prefix check or a link inside an allowed dir can escape it (Adj-2)
        real = os.path.realpath(filepath)
        if not any(real == os.path.realpath(a)
                   or real.startswith(os.path.realpath(a) + os.sep)
                   for a in allowed if a):
            return {"error": "Access denied"}

        try:
            from engine.staging import _recycle_file_powershell
            os.chmod(filepath, stat.S_IWRITE | stat.S_IREAD)
            _recycle_file_powershell(filepath)
            _log_activity("browser_delete", {"path": filepath})
            return {"status": "deleted"}
        except Exception as e:
            return {"error": str(e)}

    def move_to_keepers(self, params=None):
        if params is None:
            params = {}
        filepath = params.get("path", "")
        if not filepath or not os.path.isfile(filepath):
            return {"success": False, "error": "File not found"}

        settings = load_settings()
        keepers_dir = settings.get("keepers_dir", DEFAULTS["keepers_dir"])
        os.makedirs(keepers_dir, exist_ok=True)
        filename = os.path.basename(filepath)
        dest = os.path.join(keepers_dir, filename)

        # Collision avoidance
        if os.path.exists(dest):
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(dest):
                dest = os.path.join(keepers_dir, base + "_" + str(counter) + ext)
                counter += 1

        try:
            shutil.copy2(filepath, dest)
            if os.path.exists(dest) and os.path.getsize(dest) == os.path.getsize(filepath):
                os.remove(filepath)
                _log_activity("move_to_keepers", {
                    "source": filepath, "destination": dest,
                })
                return {"success": True, "destination": dest}
            else:
                return {"success": False, "error": "Copy verification failed"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def browser_delete_folder(self, params=None):
        if params is None:
            params = {}
        folderpath = params.get("path", "")
        if not folderpath or not os.path.isdir(folderpath):
            return {"error": "Folder not found"}

        settings = load_settings()
        allowed = [
            _find_staging_subfolder() or "",
            settings.get("move_destination", DEFAULTS["move_destination"]),
            settings.get("keepers_dir", DEFAULTS["keepers_dir"]),
        ]
        # realpath, not normpath: junctions/symlinks must resolve before the
        # prefix check or a link inside an allowed dir can escape it (Adj-2)
        real = os.path.realpath(folderpath)
        if not any(real == os.path.realpath(a)
                   or real.startswith(os.path.realpath(a) + os.sep)
                   for a in allowed if a):
            return {"error": "Access denied"}

        result = recycle_staging(folderpath)
        _log_activity("browser_delete_folder", {
            "path": folderpath, **result
        })
        return {"status": "deleted", **result}

    def open_explorer(self, params=None):
        if params is None:
            params = {}
        path = params.get("path", "")
        if path and os.path.exists(path):
            import subprocess
            subprocess.Popen(["explorer", os.path.normpath(path)])
            return {"status": "opened"}
        return {"error": "Path not found"}

    def open_recycle_bin(self, params=None):
        import subprocess
        subprocess.Popen(["explorer", "shell:RecycleBinFolder"])
        return {"status": "opened"}

    # ---- Recovery Archive ----

    def recovery_status(self, params=None):
        from engine.recovery import get_archive_status
        return get_archive_status()

    def recovery_list(self, params=None):
        from engine.recovery import list_archived_files
        return {"files": list_archived_files()}

    def recovery_restore(self, params=None):
        if params is None:
            params = {}
        from engine.recovery import restore_file
        archived_path = params.get("archived_path", "")
        # Restore to staging (Staging) by default
        settings = load_settings()
        dest_dir = params.get("destination", "")
        if not dest_dir:
            dest_dir = _find_staging_subfolder() or ""
        if not dest_dir:
            return {"success": False, "error": "No destination folder available"}
        result = restore_file(archived_path, dest_dir)
        if result.get("success"):
            _log_activity("recovery_restore", {
                "archived_path": archived_path,
                "destination": result.get("destination", ""),
            })
        return result

    def recovery_clear(self, params=None):
        from engine.recovery import clear_archive
        result = clear_archive()
        _log_activity("recovery_cleared", {})
        return result

    # ---- Logging ----

    def logs_status(self, params=None):
        from engine.logging_config import is_logging_enabled
        return {"enabled": is_logging_enabled()}

    def logs_enable(self, params=None):
        from engine.logging_config import enable_logging
        enable_logging()
        return {"enabled": True}

    def logs_disable(self, params=None):
        from engine.logging_config import disable_logging
        disable_logging()
        return {"enabled": False}

    def logs_read(self, params=None):
        if params is None:
            params = {}
        log_type = params.get("type", "debug")
        lines = int(params.get("lines", 200))
        from engine.config import LOGS_DIR
        log_file = LOGS_DIR / (log_type + ".log")
        if not log_file.is_file():
            return {"content": "", "lines": 0}
        try:
            with open(str(log_file), "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            tail = all_lines[-lines:] if len(all_lines) > lines else all_lines
            return {"content": "".join(tail), "lines": len(tail)}
        except Exception as e:
            return {"content": "Error reading log: " + str(e), "lines": 0}

    def logs_clear(self, params=None):
        from engine.config import LOGS_DIR
        for name in ("debug.log", "error.log"):
            p = LOGS_DIR / name
            if p.is_file():
                try:
                    with open(str(p), "w") as f:
                        f.write("")
                except Exception:
                    pass
        return {"success": True}

    def app_shutdown(self, params=None):
        """Close the pywebview window."""
        if self._window:
            self._window.destroy()
        return {"status": "closing"}

"""
PixHerder web server — thin dispatcher.
Routes requests to domain-specific handler modules.
"""

import http.server
import json
import logging
import os
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.config import (
    SCANS_DIR, ACTIVITY_LOG, DEFAULTS, IMAGE_EXTENSIONS,
    load_settings, default_pictures_path,
)
from engine.staging import is_onedrive_path

from web.workers import (
    worker_manager, _log_activity, _read_activity, _find_staging_subfolder,
    _reset_all_progress,
    scan_progress, action_progress, oddball_progress,
    staging_progress, syncback_progress, restore_progress,
    scan_cancel, action_cancel, oddball_cancel,
    staging_cancel, syncback_cancel,
    _run_scan, _run_action, _run_oddball,
    _run_staging, _run_restore, _run_syncback,
    recycle_source_dupes, move_dupes_to_folder,
)
from web.image_server import _is_allowed_path, serve_image
from web import routes_scan, routes_actions, routes_staging, routes_browser


class PixHerderHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for the PixHerder web API."""

    _ALLOWED_HOSTS = {"127.0.0.1", "localhost"}

    def log_message(self, format, *args):
        pass

    def _check_origin(self):
        """Reject requests from external origins (CSRF/DNS-rebinding)."""
        host = (self.headers.get("Host") or "").split(":")[0]
        if host and host not in self._ALLOWED_HOSTS:
            self.send_error_json("Forbidden", 403)
            return False
        origin = self.headers.get("Origin")
        if origin:
            from urllib.parse import urlparse
            o = urlparse(origin)
            if o.hostname and o.hostname not in self._ALLOWED_HOSTS:
                self.send_error_json("Forbidden", 403)
                return False
        return True

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

        if path.startswith("/api/") and not self._check_origin():
            return

        if path == "/" or path == "":
            self._serve_index()
        elif path.startswith("/web/") and path.endswith((".css", ".js")):
            self._serve_static(path)
        elif path == "/api/scans":
            routes_scan.handle_get_scans(self, worker_manager)
        elif path == "/api/decisions/load":
            report = params.get("report", [""])[0]
            routes_actions.handle_decisions_load(self, worker_manager, report)
        elif path == "/api/scan/check-resume":
            routes_scan.handle_check_resume(self, worker_manager, params)
        elif path == "/api/groups":
            report = params.get("report", [""])[0]
            routes_scan.handle_get_groups(self, worker_manager, report)
        elif path == "/api/image":
            filepath = params.get("path", [""])[0]
            serve_image(self, filepath)
        elif path == "/api/settings":
            routes_scan.handle_get_settings(self, worker_manager)
        elif path == "/api/folders/status":
            self._handle_folders_status()
        elif path == "/api/activity":
            limit = int(params.get("limit", ["50"])[0])
            self._handle_get_activity(limit)
        elif path == "/api/staging/status":
            routes_staging.handle_staging_status(self, worker_manager)
        elif path == "/api/browse":
            dirpath = params.get("path", [""])[0]
            page = int(params.get("page", ["1"])[0])
            page_size = int(params.get("page_size", ["50"])[0])
            sort_by = params.get("sort", ["name"])[0]
            routes_browser.handle_browse(
                self, worker_manager, dirpath, page, page_size, sort_by)
        elif path == "/api/browse-folders":
            dirpath = params.get("path", [""])[0]
            routes_browser.handle_browse_folders(
                self, worker_manager, dirpath)
        elif path == "/api/app/state":
            self._handle_app_state()
        else:
            self.send_error(404)

    # ---- POST routes ----

    def do_POST(self):
        if not self._check_origin():
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/scan/start":
            routes_scan.handle_scan_start(self, worker_manager)
        elif path == "/api/scan/cancel":
            routes_scan.handle_scan_cancel(self, worker_manager)
        elif path == "/api/action/move":
            routes_actions.handle_action_move(self, worker_manager)
        elif path == "/api/action/delete":
            routes_actions.handle_action_delete(self, worker_manager)
        elif path == "/api/action/rescue":
            routes_actions.handle_action_rescue(self, worker_manager)
        elif path == "/api/settings":
            routes_scan.handle_save_settings(self, worker_manager)
        elif path == "/api/oddball/run":
            routes_actions.handle_oddball_run(self, worker_manager)
        elif path == "/api/decisions/save":
            routes_actions.handle_decisions_save(self, worker_manager)
        elif path == "/api/scans/delete":
            routes_scan.handle_delete_scan(self, worker_manager)
        elif path == "/api/activity/clear":
            self._handle_clear_activity()
        elif path == "/api/app/reset":
            _reset_all_progress()
            self.send_json({"status": "reset"})
        elif path == "/api/onedrive/status":
            routes_staging.handle_onedrive_status(self, worker_manager)
        elif path == "/api/staging/check":
            routes_staging.handle_staging_check(self, worker_manager)
        elif path == "/api/staging/start":
            routes_staging.handle_staging_start(self, worker_manager)
        elif path == "/api/staging/cancel":
            routes_staging.handle_staging_cancel(self, worker_manager)
        elif path == "/api/staging/syncback":
            routes_staging.handle_syncback_start(self, worker_manager)
        elif path == "/api/staging/cleanup":
            routes_staging.handle_staging_cleanup(self, worker_manager)
        elif path == "/api/staging/reset":
            routes_staging.handle_staging_reset(self, worker_manager)
        elif path == "/api/staging/recycle-bin":
            routes_staging.handle_staging_recycle_bin(self, worker_manager)
        elif path == "/api/browser/delete":
            routes_browser.handle_browser_delete(self, worker_manager)
        elif path == "/api/browser/delete-folder":
            routes_browser.handle_browser_delete_folder(self, worker_manager)
        elif path == "/api/browser/open-explorer":
            routes_browser.handle_open_explorer(self, worker_manager)
        elif path == "/api/browser/open-recycle-bin":
            routes_browser.handle_open_recycle_bin(self, worker_manager)
        elif path == "/api/staging/restore":
            routes_staging.handle_staging_restore(self, worker_manager)
        elif path == "/api/staging/recycle":
            routes_staging.handle_staging_recycle(self, worker_manager)
        elif path == "/api/dupes/purge":
            routes_staging.handle_dupes_purge(self, worker_manager)
        elif path == "/api/browser/move-to-keepers":
            routes_browser.handle_move_to_keepers(self, worker_manager)
        elif path == "/api/dupes/promote":
            routes_staging.handle_dupes_promote(self, worker_manager)
        elif path == "/api/consolidate":
            routes_staging.handle_consolidate(self, worker_manager)
        else:
            self.send_error(404)

    # ---- Static file serving ----

    def _serve_index(self):
        html_path = Path(__file__).parent / "index.html"
        try:
            with open(str(html_path), "r", encoding="utf-8") as f:
                content = f.read()
            body = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control",
                             "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_error_json("Could not load index.html: " + str(e), 500)

    def _serve_static(self, url_path):
        rel = url_path.lstrip("/")
        file_path = Path(__file__).parent.parent / rel
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

    # ---- Dashboard routes (kept inline — read-only aggregators) ----

    def _handle_app_state(self):
        settings = load_settings()
        image_exts = IMAGE_EXTENSIONS

        def _count(dirpath):
            if not dirpath or not os.path.isdir(dirpath):
                return {"exists": False, "path": dirpath or "", "count": 0}
            count = 0
            for root, dirs, files in os.walk(dirpath):
                for f in files:
                    if os.path.splitext(f)[1].lower() in image_exts:
                        count += 1
            return {"exists": True, "path": dirpath, "count": count}

        staging_path = _find_staging_subfolder()
        dupes_path = settings.get("move_destination",
                                  DEFAULTS["move_destination"])
        keepers_path = settings.get("keepers_dir", DEFAULTS["keepers_dir"])

        staging = _count(staging_path)
        dupes = _count(dupes_path)
        keepers = _count(keepers_path)

        source_dir = ""
        if staging_path and SCANS_DIR.is_dir():
            for mf in SCANS_DIR.glob("staging_manifest_*.json"):
                try:
                    with open(str(mf), "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                    if manifest.get("staging_dir") == staging_path:
                        source_dir = manifest.get("source_dir", "")
                        break
                except Exception:
                    pass

        has_session = bool(
            staging_path and staging["count"] > 0 and source_dir)

        scans = []
        if SCANS_DIR.is_dir():
            for f in sorted(SCANS_DIR.glob("scan_*.json"), reverse=True):
                try:
                    with open(str(f), "r") as fh:
                        data = json.load(fh)
                    meta = data.get("metadata", {})
                    exact_count = len(data.get("exact_groups", []))
                    perceptual_count = len(
                        data.get("perceptual_groups", []))
                    scans.append({
                        "filename": f.name,
                        "directory": meta.get("directory", ""),
                        "mode": meta.get("mode", ""),
                        "total_groups": exact_count + perceptual_count,
                    })
                except Exception:
                    pass

        try:
            from engine.recovery import get_archive_status
            recovery = get_archive_status()
        except Exception:
            recovery = {"has_files": False}

        self.send_json({
            "folders": {
                "staging": staging, "dupes": dupes, "keepers": keepers,
            },
            "session": {
                "source_dir": source_dir,
                "staging_dir": staging_path or "",
                "active": has_session,
            },
            "scans": scans,
            "has_scans": len(scans) > 0,
            "recovery": recovery,
        })

    def _handle_folders_status(self):
        settings = load_settings()
        image_exts = IMAGE_EXTENSIONS

        def _count_images(dirpath):
            if not dirpath or not os.path.isdir(dirpath):
                return {"exists": False, "path": dirpath or "",
                        "file_count": 0}
            count = 0
            for root, dirs, files in os.walk(dirpath):
                for f in files:
                    if os.path.splitext(f)[1].lower() in image_exts:
                        count += 1
            return {"exists": True, "path": dirpath, "file_count": count}

        staging_path = _find_staging_subfolder()
        dupes_path = settings.get("move_destination",
                                  DEFAULTS["move_destination"])
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


_server_instance = None


def create_server(port=8787):
    """Create and return a ThreadingHTTPServer instance."""
    global _server_instance
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", port),
        PixHerderHandler,
    )
    _server_instance = server
    logger.info("Server started on port %d", port)

    _log_activity("server_started", {"port": port})

    return server

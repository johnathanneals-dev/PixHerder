"""
PixHerder browser route handlers.
File browser, folder picker, file delete/move, Explorer integration.
"""

import logging
import os
import shutil
import string
import subprocess
import sys
import threading
from datetime import datetime

from engine.config import (
    PROJECT_ROOT as ROOT, DEFAULTS, IMAGE_EXTENSIONS,
    load_settings, verify_copy,
)
from engine.staging import recycle_staging
from web.image_server import _is_allowed_path
from web.workers import _log_activity, _find_staging_subfolder

logger = logging.getLogger(__name__)


def handle_browse_folders(handler, workers, dirpath):
    if dirpath == "__drives__":
        drives = []
        for letter in string.ascii_uppercase:
            drive = letter + ":\\"
            if os.path.isdir(drive):
                drives.append(drive)
        handler.send_json({
            "path": "My Computer",
            "parent": "",
            "folders": drives,
            "is_drives": True,
        })
        return

    if not dirpath:
        dirpath = os.path.expanduser("~")

    dirpath = os.path.normpath(dirpath)
    if not os.path.isdir(dirpath):
        handler.send_error_json("Directory not found", 404)
        return

    lower = dirpath.lower()
    windir = os.environ.get("WINDIR", "C:\\Windows").lower()
    blocked = [
        windir,
        os.path.join(windir, "system32"),
        os.environ.get("PROGRAMFILES", "C:\\Program Files").lower(),
        os.environ.get("PROGRAMFILES(X86)",
                       "C:\\Program Files (x86)").lower(),
    ]
    if any(lower == b or lower.startswith(b + os.sep) for b in blocked):
        handler.send_error_json("Access denied", 403)
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

    parent = os.path.dirname(dirpath)
    if parent == dirpath:
        parent = "__drives__"

    handler.send_json({
        "path": dirpath,
        "parent": parent,
        "folders": folders,
    })


def handle_browse(handler, workers, dirpath, page, page_size, sort_by):
    if not dirpath or not os.path.isdir(dirpath):
        handler.send_error_json("Invalid directory", 400)
        return

    if not _is_allowed_path(dirpath):
        logger.warning("Browse access denied: %s", dirpath)
        handler.send_error_json("Access denied: path outside allowed directories", 403)
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
        handler.send_error_json("Error reading directory: " + str(e), 500)
        return

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
    if not _is_allowed_path(parent):
        parent = None

    handler.send_json({
        "path": os.path.normpath(dirpath),
        "parent": parent,
        "entries": page_entries,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_more": end < total,
    })


def handle_browser_delete(handler, workers):
    try:
        body = handler.read_json_body()
    except Exception:
        handler.send_error_json("Invalid JSON body")
        return

    filepath = body.get("path", "")
    if not filepath or not os.path.isfile(filepath):
        handler.send_error_json("File not found", 404)
        return

    if not _is_allowed_path(filepath, include_active_staging=False):
        logger.warning("Browser delete access denied: %s", filepath)
        handler.send_error_json("Access denied: path outside allowed directories", 403)
        return

    try:
        from engine.staging import _recycle_file_powershell
        import stat
        if not os.access(filepath, os.W_OK):
            os.chmod(filepath, stat.S_IWRITE | stat.S_IREAD)
        _recycle_file_powershell(filepath)
        _log_activity("browser_delete", {"path": filepath})
        handler.send_json({"success": True})
    except Exception as e:
        handler.send_json({"success": False, "error": str(e)})


def handle_open_recycle_bin(handler, workers):
    try:
        subprocess.Popen(
            ["explorer.exe", "shell:RecycleBinFolder"],
            creationflags=0x00000008,
        )
        handler.send_json({"success": True})
    except Exception as e:
        handler.send_error_json("Could not open Recycle Bin: " + str(e))


def handle_open_explorer(handler, workers):
    try:
        body = handler.read_json_body()
    except Exception:
        handler.send_error_json("Invalid JSON body")
        return

    dirpath = body.get("path", "")
    if not dirpath or not os.path.isdir(dirpath):
        handler.send_error_json("Directory not found", 404)
        return

    if not _is_allowed_path(dirpath, include_active_staging=False):
        handler.send_error_json("Access denied", 403)
        return

    try:
        normpath = os.path.normpath(dirpath)
        helper_path = str(ROOT / "_open_explorer.py")
        helper_code = (
            "import ctypes, subprocess, time, sys\n"
            "u = ctypes.windll.user32\n"
            "h = u.FindWindowW(None, 'PixHerder')\n"
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
        handler.send_json({"success": True})

        def _cleanup():
            proc.wait()
            try:
                os.remove(helper_path)
            except Exception:
                pass
        threading.Thread(target=_cleanup, daemon=True).start()
    except Exception as e:
        handler.send_json({"success": False, "error": str(e)})


def handle_move_to_keepers(handler, workers):
    try:
        body = handler.read_json_body()
    except Exception:
        handler.send_error_json("Invalid JSON body")
        return

    filepath = body.get("path", "")
    if not filepath or not os.path.isfile(filepath):
        handler.send_json({"success": False, "error": "File not found"})
        return

    settings = load_settings()
    keepers_dir = settings.get("keepers_dir", "")
    if not keepers_dir:
        import tempfile
        keepers_dir = os.path.join(tempfile.gettempdir(), "PixHerder_Keepers")

    os.makedirs(keepers_dir, exist_ok=True)
    filename = os.path.basename(filepath)
    dest = os.path.join(keepers_dir, filename)

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
                "source": filepath,
                "destination": dest,
            })
            handler.send_json({"success": True, "destination": dest})
        else:
            handler.send_json({"success": False, "error": "Copy verification failed"})
    except Exception as e:
        handler.send_json({"success": False, "error": str(e)})


def handle_browser_delete_folder(handler, workers):
    try:
        body = handler.read_json_body()
    except Exception:
        handler.send_error_json("Invalid JSON body")
        return

    dirpath = body.get("path", "")
    if not dirpath or not os.path.isdir(dirpath):
        handler.send_error_json("Directory not found", 404)
        return

    if not _is_allowed_path(dirpath, include_active_staging=False):
        handler.send_error_json("Access denied: cannot delete this directory", 403)
        return

    try:
        result = recycle_staging(dirpath)
        _log_activity("browser_delete_folder", {
            "path": dirpath,
            "recycled": result.get("files_recycled", 0),
        })
        handler.send_json({"success": True})
    except Exception as e:
        handler.send_json({"success": False, "error": str(e)})

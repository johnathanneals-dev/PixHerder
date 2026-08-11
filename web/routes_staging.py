"""
PixHerder staging route handlers.
OneDrive staging, restore, recycle, sync-back, purge, promote, consolidation.
"""

import hashlib
import json
import logging
import os
import shutil
import stat
from pathlib import Path

from engine.config import (
    DEFAULTS, IMAGE_EXTENSIONS, load_settings, default_pictures_path,
    verify_copy,
)
from engine.staging import (
    is_onedrive_path, get_staging_dir, count_files_for_staging,
    load_manifest, cleanup_staging, recycle_staging,
)
from web.image_server import _is_allowed_path, _is_recyclable_dir
from web.workers import (
    worker_manager, _log_activity, _find_staging_subfolder,
    _run_staging, _run_restore, _run_syncback,
    staging_progress, staging_cancel, syncback_progress,
)

logger = logging.getLogger(__name__)


def handle_onedrive_status(handler, workers):
    try:
        body = handler.read_json_body()
        directory = body.get("directory", "") if body else ""
        from engine.staging import is_onedrive_running
        running = is_onedrive_running()
        is_od = is_onedrive_path(directory) if directory else False
        settings = load_settings()
        handler.send_json({
            "running": running,
            "is_onedrive": is_od,
            "show_prompts": settings.get("show_onedrive_prompts", True),
        })
    except Exception as e:
        handler.send_json({"error": str(e)}, 500)


def handle_staging_check(handler, workers):
    try:
        body = handler.read_json_body()
    except Exception:
        handler.send_error_json("Invalid JSON body")
        return

    directory = body.get("directory", "")
    if not directory:
        handler.send_json({"is_onedrive": False})
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

        try:
            _, _, free = shutil.disk_usage(
                os.path.splitdrive(staging_dir)[0] or "C:")
            result["free_space_gb"] = round(free / (1024 ** 3), 1)
        except Exception:
            pass

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

    handler.send_json(result)


def handle_staging_start(handler, workers):
    if workers.staging_thread and workers.staging_thread.is_alive():
        handler.send_error_json("Staging is already running", 409)
        return

    try:
        body = handler.read_json_body()
    except Exception:
        handler.send_error_json("Invalid JSON body")
        return

    source_dir = body.get("source_dir", "")
    if not source_dir or not os.path.isdir(source_dir):
        handler.send_error_json("Invalid source directory")
        return

    settings = load_settings()
    staging_dir = body.get("staging_dir") or get_staging_dir(
        source_dir, settings.get("staging_dir", DEFAULTS["staging_dir"]))
    extensions = settings.get("extensions")

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
                needed_gb = round((source_size + buffer) / (1024 ** 3), 1)
                free_gb = round(usage.free / (1024 ** 3), 1)
                handler.send_error_json(
                    "Not enough disk space. Need about "
                    + str(needed_gb) + " GB but only "
                    + str(free_gb) + " GB free on "
                    + target_drive, 400)
                return
    except Exception:
        pass

    if not workers.start_worker(
            "staging_thread", _run_staging,
            (source_dir, staging_dir, extensions),
            cancel_attr="staging_cancel"):
        handler.send_error_json("Staging is already running", 409)
        return

    handler.send_json({
        "status": "started",
        "source_dir": source_dir,
        "staging_dir": staging_dir,
    })


def handle_staging_cancel(handler, workers):
    workers.staging_cancel.set()
    handler.send_json({"status": "cancelling"})


def handle_staging_status(handler, workers):
    result = dict(staging_progress)

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

                settings = load_settings()
                source = settings.get("default_pictures_path", "")
                if not source:
                    source = default_pictures_path()
                scans_dir = Path(__file__).parent.parent / "scans"
                if scans_dir.is_dir():
                    for mf in scans_dir.glob("staging_manifest_*.json"):
                        try:
                            with open(str(mf), "r", encoding="utf-8") as f:
                                manifest = json.load(f)
                            if manifest.get("staging_dir") == staging_path:
                                source = manifest.get("source_dir", source)
                                break
                        except Exception:
                            pass
                result["source_dir"] = source

    handler.send_json(result)


def handle_syncback_start(handler, workers):
    if workers.syncback_thread and workers.syncback_thread.is_alive():
        handler.send_error_json("Sync-back is already running", 409)
        return

    try:
        body = handler.read_json_body()
    except Exception:
        handler.send_error_json("Invalid JSON body")
        return

    staging_dir = body.get("staging_dir", "")
    source_dir = body.get("source_dir", "")

    if not staging_dir or not source_dir:
        handler.send_error_json("Missing staging_dir or source_dir")
        return

    if not workers.start_worker(
            "syncback_thread", _run_syncback, (staging_dir, source_dir),
            cancel_attr="syncback_cancel"):
        handler.send_error_json("Sync-back is already running", 409)
        return

    handler.send_json({"status": "started"})


def handle_staging_cleanup(handler, workers):
    try:
        body = handler.read_json_body()
    except Exception:
        handler.send_error_json("Invalid JSON body")
        return

    staging_dir = body.get("staging_dir", "")
    if not staging_dir:
        handler.send_error_json("Missing staging_dir")
        return

    result = cleanup_staging(staging_dir)
    from engine.config import cleanup_system_recovery
    cleanup_system_recovery()
    _log_activity("staging_cleanup", {
        "staging_dir": staging_dir,
        "result": result.get("status"),
    })
    handler.send_json(result)


def handle_staging_reset(handler, workers):
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
    handler.send_json({"status": "reset"})


def handle_staging_recycle_bin(handler, workers):
    try:
        body = handler.read_json_body()
    except Exception:
        handler.send_error_json("Invalid JSON body")
        return

    folder = body.get("folder", "")
    staging_dir = body.get("staging_dir", "")

    if folder == "dupes":
        settings = load_settings()
        target_dir = settings.get(
            "move_destination", DEFAULTS["move_destination"])
    elif folder == "staging" or staging_dir:
        target_dir = staging_dir or ""
    else:
        handler.send_error_json("Missing folder or staging_dir")
        return

    if not target_dir:
        handler.send_error_json("Could not resolve target directory")
        return

    # target_dir may have come straight from the request body. Recycling is
    # recursive and destructive, so it must be confined to the workspace.
    if not _is_recyclable_dir(target_dir):
        logger.warning(
            "Recycle refused for path outside workspace: %s", target_dir)
        handler.send_error_json(
            "Refusing to recycle a folder outside the PixHerder workspace",
            403)
        return

    result = recycle_staging(target_dir)
    _log_activity("staging_recycle_bin", {
        "folder": folder or "staging",
        "target_dir": target_dir,
        "files_recycled": result.get("files_recycled", 0),
        "errors": result.get("errors", 0),
    })
    handler.send_json(result)


def handle_staging_restore(handler, workers):
    try:
        body = handler.read_json_body()
    except Exception:
        handler.send_error_json("Invalid JSON body")
        return

    staging_dir = body.get("staging_dir", "")
    source_dir = body.get("source_dir", "")
    full_restore = body.get("full_restore", False)
    include_keepers = body.get("include_keepers", False)

    if not source_dir:
        handler.send_error_json("Source directory not specified")
        return

    known_staging = staging_progress.get("staging_dir") or ""
    if staging_dir and known_staging:
        if os.path.normpath(staging_dir) != os.path.normpath(known_staging):
            handler.send_error_json(
                "Staging directory mismatch: does not match active session",
                403)
            return
    known_source = staging_progress.get("source_dir") or ""
    if source_dir and known_source:
        if os.path.normpath(source_dir) != os.path.normpath(known_source):
            handler.send_error_json(
                "Source directory mismatch: does not match active session",
                403)
            return

    os.makedirs(source_dir, exist_ok=True)

    copied = 0
    skipped = 0
    errors = 0

    def _restore_folder(folder_dir, preserve_structure):
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
                    shutil.copy2(src, dst)
                    copied += 1
                except Exception:
                    errors += 1

    if staging_dir and os.path.isdir(staging_dir):
        _restore_folder(staging_dir, True)

    if full_restore or include_keepers:
        settings = load_settings()
        keepers_dir = settings.get(
            "keepers_dir", DEFAULTS.get("keepers_dir", ""))
        if keepers_dir:
            _restore_folder(keepers_dir, False)

    if full_restore:
        settings = load_settings()
        dupes_dir = settings.get(
            "move_destination", DEFAULTS["move_destination"])
        _restore_folder(dupes_dir, False)

        if staging_dir and os.path.isdir(staging_dir):
            cleanup_staging(staging_dir)
        if dupes_dir and os.path.isdir(dupes_dir):
            cleanup_staging(dupes_dir)
        if keepers_dir and os.path.isdir(keepers_dir):
            cleanup_staging(keepers_dir)

    if full_restore:
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

    handler.send_json({
        "success": True,
        "copied": copied,
        "skipped": skipped,
        "errors": errors,
    })


def handle_staging_recycle(handler, workers):
    try:
        body = handler.read_json_body()
    except Exception:
        body = {}
    force = body.get("force", False)

    settings = load_settings()
    staging_base = settings.get("staging_dir", DEFAULTS["staging_dir"])
    dupes_dir = settings.get("move_destination", DEFAULTS["move_destination"])

    if not os.path.isdir(dupes_dir):
        handler.send_error_json("Duplicates folder not found", 404)
        return

    staging_path = _find_staging_subfolder()

    if not staging_path:
        key = os.path.normpath(dupes_dir).lower()
        short_hash = hashlib.md5(key.encode("utf-8")).hexdigest()[:10]
        staging_path = os.path.join(staging_base, short_hash)

    os.makedirs(staging_path, exist_ok=True)

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
        handler.send_error_json(
            "Staging folder is not empty. Sync cleaned files back to "
            "OneDrive first, or clean up the staging folder.", 409)
        return

    moved = 0
    errors = 0
    error_details = []
    for item in os.listdir(dupes_dir):
        src = os.path.join(dupes_dir, item)
        dst = os.path.join(staging_path, item)
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
            try:
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                    shutil.rmtree(src, onerror=lambda f, p, e: (
                        os.chmod(p, stat.S_IWRITE), f(p)))
                else:
                    shutil.copy2(src, dst)
                    if not verify_copy(src, dst):
                        errors += 1
                        error_details.append(item + ": copy verification failed")
                        continue
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

    handler.send_json({
        "success": True,
        "files_moved": moved,
        "errors": errors,
        "staging_path": staging_path,
    })


def handle_dupes_purge(handler, workers):
    settings = load_settings()
    dupes_dir = settings.get("move_destination", DEFAULTS["move_destination"])

    if not os.path.isdir(dupes_dir):
        handler.send_error_json("Duplicates folder not found", 404)
        return

    result = recycle_staging(dupes_dir)
    _log_activity("dupes_purge", {
        "path": dupes_dir,
        "recycled": result.get("files_recycled", 0),
        "errors": result.get("errors", 0),
        "used_fallback": result.get("used_fallback", False),
    })

    handler.send_json({
        "success": True,
        "deleted": result.get("files_recycled", 0),
        "errors": result.get("errors", 0),
    })


def handle_dupes_promote(handler, workers):
    settings = load_settings()
    dupes_dir = settings.get("move_destination", DEFAULTS["move_destination"])
    keepers_dir = settings.get("keepers_dir", DEFAULTS["keepers_dir"])

    if not os.path.isdir(dupes_dir):
        handler.send_error_json("Duplicates folder not found", 404)
        return

    os.makedirs(keepers_dir, exist_ok=True)

    moved = 0
    errors = 0

    for root, dirs, files in os.walk(dupes_dir):
        for f in files:
            src = os.path.join(root, f)
            dst = os.path.join(keepers_dir, f)
            if os.path.exists(dst):
                stem, ext = os.path.splitext(f)
                counter = 1
                while os.path.exists(dst):
                    dst = os.path.join(
                        keepers_dir, stem + "_" + str(counter) + ext)
                    counter += 1
            try:
                shutil.copy2(src, dst)
                if not verify_copy(src, dst):
                    errors += 1
                    continue
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

    handler.send_json({
        "success": True,
        "moved": moved,
        "errors": errors,
    })


def handle_consolidate(handler, workers):
    settings = load_settings()
    dupes_dir = settings.get("move_destination", DEFAULTS["move_destination"])
    keepers_dir = settings.get("keepers_dir", DEFAULTS.get("keepers_dir", ""))

    staging_dir = _find_staging_subfolder()

    if not staging_dir:
        handler.send_error_json("No workspace folder found", 404)
        return

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
                    shutil.copy2(src, dst)
                    if not verify_copy(src, dst):
                        errors += 1
                        continue
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

    handler.send_json({
        "success": True,
        "moved": moved,
        "errors": errors,
    })

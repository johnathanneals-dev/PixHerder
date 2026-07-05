"""
PixHerder scan route handlers.
Scan lifecycle, results listing, settings, and checkpoint resume.
"""

import json
import os
import threading
from pathlib import Path

from engine.config import (
    SCANS_DIR, PROJECT_ROOT as ROOT, DEFAULTS, IMAGE_EXTENSIONS,
    load_settings, save_settings, default_pictures_path,
)
from engine.checkpoint import (
    checkpoint_path, find_checkpoint, delete_checkpoint,
)
from web.workers import (
    worker_manager, _run_scan,
    scan_progress, scan_cancel,
)


def handle_check_resume(handler, workers, params):
    directory = params.get("directory", [""])[0]
    mode = params.get("mode", ["both"])[0]

    if not directory:
        handler.send_json({"has_checkpoint": False})
        return

    ckpt, data = find_checkpoint(directory, mode)
    if data:
        md5_count = len(data.get("md5_hashes", {}))
        phash_count = len(data.get("phash_hashes", {}))
        handler.send_json({
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
        handler.send_json({"has_checkpoint": False})


def handle_get_scans(handler, workers):
    scans = []

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
                total_dupes = sum(
                    len(g.get("duplicates", [])) for g in all_groups
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
                    "total_dupes": total_dupes,
                    "reclaimable_bytes": reclaimable,
                    "duration": meta.get("duration_seconds", 0),
                })
            except Exception:
                continue

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

    handler.send_json(scans)


def handle_get_groups(handler, workers, report):
    if not report:
        handler.send_error_json("Missing report parameter")
        return

    report_path = SCANS_DIR / report
    if not report_path.exists():
        report_path = ROOT / report
    if not report_path.exists():
        handler.send_error_json("Report not found: " + report, 404)
        return

    try:
        with open(str(report_path), "r") as f:
            data = json.load(f)

        if isinstance(data, list):
            handler.send_json({"groups": data, "metadata": None})
        elif isinstance(data, dict):
            groups = (
                data.get("exact_groups", []) +
                data.get("perceptual_groups", [])
            )
            handler.send_json({
                "groups": groups,
                "metadata": data.get("metadata"),
                "file_info": data.get("file_info", {}),
            })
        else:
            handler.send_error_json("Invalid report format")
    except Exception as e:
        handler.send_error_json("Error reading report: " + str(e), 500)


def handle_scan_start(handler, workers):
    if workers.scan_thread and workers.scan_thread.is_alive():
        handler.send_error_json("A scan is already running", 409)
        return

    try:
        body = handler.read_json_body()
    except Exception:
        handler.send_error_json("Invalid JSON body")
        return

    directory = body.get("directory", "")
    if not directory or not os.path.isdir(directory):
        handler.send_error_json("Invalid directory: " + str(directory))
        return

    settings = load_settings()
    mode = body.get("mode", "both")
    threshold = body.get("threshold", settings.get("threshold", 5))
    recursive = body.get("recursive", settings.get("recursive", True))
    hash_size = settings.get("hash_size", 16)
    keep_strategy = settings.get("keep_strategy", "largest")
    extensions = settings.get("extensions")

    resume = body.get("resume", False)
    auto_recycle = body.get("auto_recycle", False)
    scan_limit = body.get("scan_limit", 0)
    resume_data = None
    if resume:
        _, resume_data = find_checkpoint(directory, mode)

    if not resume:
        ckpt = checkpoint_path(directory, mode)
        delete_checkpoint(ckpt)

    workers.scan_cancel = threading.Event()
    workers.scan_thread = threading.Thread(
        target=_run_scan,
        args=(directory, mode, threshold, recursive, hash_size,
              keep_strategy, extensions, resume_data, auto_recycle,
              scan_limit),
        daemon=True,
    )
    workers.scan_thread.start()

    handler.send_json({
        "status": "started",
        "directory": directory,
        "mode": mode,
        "resumed": bool(resume_data),
    })


def handle_scan_cancel(handler, workers):
    workers.scan_cancel.set()
    handler.send_json({"status": "cancelling"})


def handle_delete_scan(handler, workers):
    try:
        body = handler.read_json_body()
    except Exception:
        handler.send_error_json("Invalid JSON body")
        return

    filename = body.get("filename", "")
    if not filename:
        handler.send_error_json("Missing filename")
        return

    target = SCANS_DIR / filename
    if not target.exists():
        handler.send_error_json("Scan not found", 404)
        return

    try:
        os.remove(str(target))
        safe_name = os.path.basename(filename).replace(".json", "")
        dec_path = SCANS_DIR / ("decisions_" + safe_name + ".json")
        if dec_path.exists():
            try:
                os.remove(str(dec_path))
            except Exception:
                pass
        handler.send_json({"status": "deleted", "filename": filename})
    except Exception as e:
        handler.send_error_json("Failed to delete: " + str(e), 500)


def handle_get_settings(handler, workers):
    settings = load_settings()
    settings["default_pictures_path"] = default_pictures_path()
    handler.send_json(settings)


def handle_save_settings(handler, workers):
    try:
        body = handler.read_json_body()
    except Exception:
        handler.send_error_json("Invalid JSON body")
        return

    saved = save_settings(body)
    handler.send_json(saved)

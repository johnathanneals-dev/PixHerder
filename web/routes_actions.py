"""
PixHerder action route handlers.
Move, delete, rescue, oddball verification, and review decisions.
"""

import json
import os
import threading
from pathlib import Path

from engine.config import SCANS_DIR, PROJECT_ROOT as ROOT, DEFAULTS, load_settings
from engine.actions import rescue_file
from web.workers import worker_manager, _run_action, _run_oddball


def handle_action_move(handler, workers):
    if workers.action_thread and workers.action_thread.is_alive():
        handler.send_error_json("An action is already running", 409)
        return

    try:
        body = handler.read_json_body()
    except Exception:
        handler.send_error_json("Invalid JSON body")
        return

    groups = body.get("groups", [])
    if not groups:
        handler.send_error_json("No groups provided")
        return

    settings = load_settings()
    move_dir = body.get("destination",
                        settings.get("move_destination", DEFAULTS["move_destination"]))
    keep_strategy = settings.get("keep_strategy", "largest")
    report_file = body.get("report")
    scan_dir = body.get("scan_dir", "")

    workers.action_cancel = threading.Event()
    workers.action_thread = threading.Thread(
        target=_run_action,
        args=("move", groups, move_dir, keep_strategy, report_file,
              scan_dir),
        daemon=True,
    )
    workers.action_thread.start()

    handler.send_json({"status": "started", "action": "move"})


def handle_action_delete(handler, workers):
    if workers.action_thread and workers.action_thread.is_alive():
        handler.send_error_json("An action is already running", 409)
        return

    try:
        body = handler.read_json_body()
    except Exception:
        handler.send_error_json("Invalid JSON body")
        return

    groups = body.get("groups", [])
    if not groups:
        handler.send_error_json("No groups provided")
        return

    settings = load_settings()
    keep_strategy = settings.get("keep_strategy", "largest")
    report_file = body.get("report")

    workers.action_cancel = threading.Event()
    workers.action_thread = threading.Thread(
        target=_run_action,
        args=("delete", groups, None, keep_strategy, report_file),
        daemon=True,
    )
    workers.action_thread.start()

    handler.send_json({"status": "started", "action": "delete"})


def handle_action_rescue(handler, workers):
    try:
        body = handler.read_json_body()
    except Exception:
        handler.send_error_json("Invalid JSON body")
        return

    source = body.get("source", "")
    destination = body.get("destination", "")
    if not source or not destination:
        handler.send_error_json("Missing source or destination")
        return

    result = rescue_file(source, destination)
    handler.send_json(result)


def handle_oddball_run(handler, workers):
    if workers.oddball_thread and workers.oddball_thread.is_alive():
        handler.send_error_json("Oddball check is already running", 409)
        return

    try:
        body = handler.read_json_body()
    except Exception:
        handler.send_error_json("Invalid JSON body")
        return

    report_name = body.get("report", "")
    dupes_folder = body.get("dupes_folder", "")

    report_path = SCANS_DIR / report_name
    if not report_path.exists():
        report_path = ROOT / report_name
    if not report_path.exists():
        handler.send_error_json("Report not found: " + report_name, 404)
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
            handler.send_error_json("Invalid report format")
            return
    except Exception as e:
        handler.send_error_json("Error reading report: " + str(e), 500)
        return

    workers.oddball_cancel = threading.Event()
    workers.oddball_thread = threading.Thread(
        target=_run_oddball,
        args=(report_data, dupes_folder),
        daemon=True,
    )
    workers.oddball_thread.start()

    handler.send_json({"status": "started"})


def handle_decisions_save(handler, workers):
    try:
        body = handler.read_json_body()
    except Exception:
        handler.send_error_json("Invalid JSON body")
        return
    report = body.get("report", "")
    decisions = body.get("decisions", [])
    if not report:
        handler.send_error_json("No report specified")
        return
    scans_dir = Path(__file__).parent.parent / "scans"
    os.makedirs(str(scans_dir), exist_ok=True)
    safe_name = os.path.basename(report).replace(".json", "")
    dec_path = scans_dir / ("decisions_" + safe_name + ".json")
    try:
        from engine.config import safe_json_write
        safe_json_write(dec_path, {"report": report, "decisions": decisions})
        handler.send_json({"success": True})
    except Exception as e:
        handler.send_error_json("Failed to save decisions: " + str(e))


def handle_decisions_load(handler, workers, report):
    if not report:
        handler.send_json({"decisions": []})
        return
    scans_dir = Path(__file__).parent.parent / "scans"
    safe_name = os.path.basename(report).replace(".json", "")
    dec_path = scans_dir / ("decisions_" + safe_name + ".json")
    if dec_path.is_file():
        try:
            with open(str(dec_path), "r", encoding="utf-8") as f:
                data = json.load(f)
            handler.send_json({"decisions": data.get("decisions", [])})
        except Exception:
            handler.send_json({"decisions": []})
    else:
        handler.send_json({"decisions": []})

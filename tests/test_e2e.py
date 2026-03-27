"""
PixHerder End-to-End Test Agent
Runs the full workflow cycle against a real image folder.
Reports issues found at each step.

Usage: python tests/test_e2e.py [source_folder]
Default source: C:\\Projects\\Pictures
"""
import sys
import os
import time
import json
import glob as globmod
from datetime import datetime
from pathlib import Path

# Project root setup
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Test log directory
TEST_LOG_DIR = PROJECT_ROOT / "logs" / "test_runs"

from engine.config import (
    ensure_dirs, load_settings, DEFAULTS,
    SCANS_DIR, IMAGE_EXTENSIONS,
)

# Test log capture
_log_lines = []


def log_line(line):
    """Print a line and capture it for the log file."""
    print(line)
    _log_lines.append(line)


def save_test_log(success):
    """Save captured output to a timestamped log file. Keep last 10 runs."""
    TEST_LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    status = "PASS" if success else "FAIL"
    filename = "e2e_%s_%s.log" % (timestamp, status)
    log_path = TEST_LOG_DIR / filename
    with open(str(log_path), "w", encoding="utf-8") as f:
        f.write("\n".join(_log_lines))
    print("  Test log saved: %s" % log_path)
    prune_test_logs()


def prune_test_logs(keep=10):
    """Delete oldest test logs, keeping only the most recent runs."""
    pattern = str(TEST_LOG_DIR / "e2e_*.log")
    logs = sorted(globmod.glob(pattern))
    while len(logs) > keep:
        os.remove(logs.pop(0))


# Test reporting
_issues = []
_step = ""


def issue(msg):
    """Record a test issue."""
    _issues.append({"step": _step, "message": msg})
    log_line("  !! ISSUE: " + msg)


def check(condition, msg):
    """Assert a condition, record issue if false."""
    if not condition:
        issue(msg)
    return condition


def count_images(directory):
    """Count image files in a directory tree (case-insensitive)."""
    count = 0
    if not os.path.isdir(directory):
        return 0
    for root, dirs, files in os.walk(directory):
        for f in files:
            if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS:
                count += 1
    return count


def poll_progress(progress_dict, name, max_wait=600):
    """Poll a server progress dict until terminal state."""
    start = time.time()
    last_msg = ""
    while time.time() - start < max_wait:
        data = dict(progress_dict)
        status = data.get("status", "idle")
        msg = "%s: %s %d/%d" % (name, status, data.get("current", 0), data.get("total", 0))
        if msg != last_msg:
            log_line("  " + msg)
            last_msg = msg
        if status in ("complete", "error", "cancelled"):
            return data
        time.sleep(0.5)
    issue(name + " timed out after %ds" % max_wait)
    return dict(progress_dict)


def snapshot_source(source_dir):
    """Take a file count snapshot of the source directory."""
    return count_images(source_dir)


# ---- Test Steps ----

def test_migrate(api, source_dir):
    """Step 1: Migrate files from source to staging."""
    global _step
    _step = "migrate"
    log_line("\n=== STEP 1: MIGRATE ===")

    from web.server import staging_progress

    # Count source images before
    source_count = snapshot_source(source_dir)
    log_line("  Source images: %d" % source_count)
    check(source_count > 0, "Source folder has no images: " + source_dir)

    # Reset state
    api.reset_state()

    # Start migration
    result = api.staging_start({"source_dir": source_dir})
    check("error" not in result, "staging_start failed: " + str(result.get("error", "")))

    # Poll until complete
    data = poll_progress(staging_progress, "Migration", max_wait=300)
    check(data.get("status") == "complete", "Migration did not complete: " + data.get("status", ""))

    staging_dir = data.get("staging_dir") or staging_progress.get("staging_dir", "")
    copied = data.get("copied", 0)
    log_line("  Staging dir: %s" % staging_dir)
    log_line("  Files copied: %d" % copied)

    # Verify staging has images
    staged_images = count_images(staging_dir)
    log_line("  Staged images: %d" % staged_images)
    check(staged_images > 0, "No images in staging after migration")
    check(staged_images == source_count,
          "Staged image count (%d) != source count (%d)" % (staged_images, source_count))

    # Verify source untouched
    source_after = snapshot_source(source_dir)
    check(source_after == source_count,
          "Source changed during migration: was %d, now %d" % (source_count, source_after))

    return {"staging_dir": staging_dir, "source_count": source_count, "staged_images": staged_images}


def test_scan(api, staging_dir, staged_images):
    """Step 2: Scan staging for duplicates."""
    global _step
    _step = "scan"
    log_line("\n=== STEP 2: SCAN ===")

    from web.server import scan_progress

    result = api.scan_start({
        "directory": staging_dir,
        "mode": "both",
        "threshold": 5,
        "recursive": True,
        "auto_recycle": False,
        "scan_limit": 0,
    })
    check("error" not in result, "scan_start failed: " + str(result.get("error", "")))

    data = poll_progress(scan_progress, "Scan", max_wait=600)
    check(data.get("status") == "complete", "Scan did not complete: " + data.get("status", ""))

    result_file = data.get("result_file", "")
    summary = data.get("summary", {})
    total_groups = summary.get("total_groups", 0)
    total_dupes = summary.get("total_duplicate_files", 0)
    scanned = summary.get("total_images", 0)

    log_line("  Scanned: %d images" % scanned)
    log_line("  Groups: %d" % total_groups)
    log_line("  Duplicate files: %d" % total_dupes)
    log_line("  Reclaimable: %.1f MB" % summary.get("reclaimable_mb", 0))

    check(scanned == staged_images,
          "Scanned count (%d) != staged images (%d)" % (scanned, staged_images))
    check(len(result_file) > 0, "No scan result file produced")

    return {"result_file": result_file, "total_groups": total_groups, "total_dupes": total_dupes}


def test_execute(api, result_file, staging_dir):
    """Step 3: Load groups, mark all as dupes, execute move."""
    global _step
    _step = "execute"
    log_line("\n=== STEP 3: REVIEW + EXECUTE ===")

    from web.server import action_progress

    # Load groups
    group_data = api.get_groups({"report": result_file})
    groups = group_data.get("groups", [])
    log_line("  Loaded %d groups from %s" % (len(groups), result_file))

    if not groups:
        log_line("  No groups to execute")
        return {"moved": 0}

    # Count expected moves
    expected_moves = sum(len(g.get("duplicates", [])) for g in groups)
    log_line("  Expected moves: %d" % expected_moves)

    # Execute move
    settings = load_settings()
    dupes_dir = settings.get("move_destination", DEFAULTS["move_destination"])

    result = api.action_move({
        "groups": groups,
        "destination": dupes_dir,
        "report": result_file,
    })
    check("error" not in result, "action_move failed: " + str(result.get("error", "")))

    data = poll_progress(action_progress, "Execute", max_wait=300)
    check(data.get("status") == "complete", "Execute did not complete: " + data.get("status", ""))

    move_result = data.get("result", {})
    moved = move_result.get("moved", 0)
    errors = move_result.get("errors", [])
    log_line("  Moved: %d" % moved)
    log_line("  Errors: %d" % len(errors))

    check(moved == expected_moves,
          "Moved count (%d) != expected (%d)" % (moved, expected_moves))
    check(len(errors) == 0, "Move errors: " + str(errors[:3]))

    # Verify source_dupes.json was created
    source_dupes_path = SCANS_DIR / "source_dupes.json"
    check(source_dupes_path.exists(), "source_dupes.json not created after move")

    if source_dupes_path.exists():
        with open(str(source_dupes_path), "r") as f:
            sd = json.load(f)
        paths = sd.get("staging_paths", [])
        log_line("  Source dupe paths saved: %d" % len(paths))
        check(len(paths) == moved,
              "Source dupe paths (%d) != moved count (%d)" % (len(paths), moved))

    # Verify dupes folder has files
    dupes_images = count_images(dupes_dir)
    log_line("  Images in dupes folder: %d" % dupes_images)
    check(dupes_images >= moved,
          "Dupes folder count (%d) < moved (%d)" % (dupes_images, moved))

    return {"moved": moved, "dupes_dir": dupes_dir}


def test_finalize(api, staging_dir, source_dir, source_count, moved):
    """Step 4: Finalize -- restore, recycle source dupes, recycle workspace dupes, cleanup."""
    global _step
    _step = "finalize"
    log_line("\n=== STEP 4: FINALIZE ===")

    from web.server import restore_progress

    # Count staging before restore
    staging_before = count_images(staging_dir)
    log_line("  Staging files before restore: %d" % staging_before)
    log_line("  Expected source dupes to recycle: %d" % moved)

    # Phase 1: Restore kept files to source
    result = api.staging_restore({
        "staging_dir": staging_dir,
        "source_dir": source_dir,
        "include_keepers": True,
    })
    check("error" not in result, "staging_restore failed: " + str(result.get("error", "")))

    # Poll restore progress
    data = poll_progress(restore_progress, "Restore", max_wait=600)
    check(data.get("status") == "complete",
          "Restore did not complete: " + data.get("status", ""))

    restored = data.get("copied", 0)
    skipped = data.get("skipped", 0)
    log_line("  Restored: %d copied, %d skipped" % (restored, skipped))

    # Phase 2: Recycle source duplicates
    log_line("  Recycling source duplicates...")
    recycle_result = api.recycle_source_dupes({
        "staging_dir": staging_dir,
        "source_dir": source_dir,
    })
    source_recycled = recycle_result.get("recycled", 0)
    recycle_errors = recycle_result.get("errors", [])
    log_line("  Source dupes recycled: %d" % source_recycled)
    if recycle_errors:
        log_line("  Recycle errors: %s" % str(recycle_errors[:3]))

    check(source_recycled == moved,
          "Source recycled (%d) != moved (%d)" % (source_recycled, moved))

    # Phase 3: Verify source count reduced
    source_after = snapshot_source(source_dir)
    expected_after = source_count - moved
    log_line("  Source images after finalize: %d (was %d)" % (source_after, source_count))
    check(source_after == expected_after,
          "Source count (%d) != expected (%d = %d - %d)" %
          (source_after, expected_after, source_count, moved))

    # Phase 4: Recycle workspace dupes
    settings = load_settings()
    dupes_dir = settings.get("move_destination", DEFAULTS["move_destination"])
    if os.path.isdir(dupes_dir) and count_images(dupes_dir) > 0:
        log_line("  Recycling workspace dupes...")
        r = api.staging_recycle_bin({"folder": "dupes"})
        log_line("  Workspace dupes recycled: %s" % r.get("recycled", 0))

    # Phase 5: Cleanup workspace
    if os.path.isdir(staging_dir):
        api.staging_cleanup({"staging_dir": staging_dir})
    api.staging_reset()
    api.reset_state()
    log_line("  Workspace cleaned up")

    return {"source_after": source_after, "source_recycled": source_recycled}


def test_finalize_to_folder(api, staging_dir, source_dir, source_count, moved):
    """Step 4 (alt): Finalize -- move dupes to folder instead of recycling."""
    global _step
    _step = "finalize_folder"
    log_line("\n=== STEP 4 (ALT): FINALIZE TO FOLDER ===")

    from web.server import restore_progress

    # Count staging before restore
    staging_before = count_images(staging_dir)
    log_line("  Staging files before restore: %d" % staging_before)

    # Phase 1: Restore kept files to source (same as normal finalize)
    result = api.staging_restore({
        "staging_dir": staging_dir,
        "source_dir": source_dir,
        "include_keepers": True,
    })
    check("error" not in result, "staging_restore failed: " + str(result.get("error", "")))

    data = poll_progress(restore_progress, "Restore", max_wait=600)
    check(data.get("status") == "complete",
          "Restore did not complete: " + data.get("status", ""))

    restored = data.get("copied", 0)
    log_line("  Restored: %d files" % restored)

    # Phase 2: Move dupes to folder
    log_line("  Moving duplicates to folder...")
    folder_result = api.move_dupes_to_folder({
        "staging_dir": staging_dir,
        "source_dir": source_dir,
    })
    folder_path = folder_result.get("folder", "")
    total_moved = folder_result.get("total_moved", 0)
    log_line("  Folder: %s" % folder_path)
    log_line("  Total moved to folder: %d" % total_moved)

    check(len(folder_path) > 0, "No folder path returned")
    check(os.path.isdir(folder_path), "Dupe folder not created: " + folder_path)

    # Verify README exists
    readme_path = os.path.join(folder_path, "README.txt")
    check(os.path.isfile(readme_path), "README.txt not created")

    # Verify subfolders have files
    found_dir = os.path.join(folder_path, "Found_Duplicates")
    source_of_dir = os.path.join(folder_path, "Source_of_Duplicates")
    found_count = count_images(found_dir)
    source_of_count = count_images(source_of_dir)
    log_line("  Found_Duplicates: %d files" % found_count)
    log_line("  Source_of_Duplicates: %d files" % source_of_count)

    check(found_count > 0, "Found_Duplicates is empty")
    check(source_of_count > 0, "Source_of_Duplicates is empty")

    # Verify source folder is clean (dupes removed)
    source_after = count_images(source_dir)
    expected_after = source_count - moved
    log_line("  Source images after: %d (was %d)" % (source_after, source_count))
    check(source_after == expected_after,
          "Source count (%d) != expected (%d)" % (source_after, expected_after))

    # Phase 3: Cleanup workspace
    if os.path.isdir(staging_dir):
        api.staging_cleanup({"staging_dir": staging_dir})
    api.staging_reset()
    api.reset_state()
    log_line("  Workspace cleaned up")

    # Clean up the test dupe folder
    import shutil
    if os.path.isdir(folder_path):
        shutil.rmtree(folder_path, ignore_errors=True)
        log_line("  Test dupe folder cleaned up")

    return {"source_after": source_after, "total_moved": total_moved}


# ---- Main Runner ----

def run_test(source_dir, use_folder=False):
    """Run the full E2E test cycle."""
    log_line("=" * 60)
    log_line("PixHerder E2E Test Agent")
    log_line("Source: %s" % source_dir)
    log_line("=" * 60)

    from web.bridge import Api
    ensure_dirs()
    api = Api()

    # Validate state before starting
    api.validate_state()

    # Run the cycle
    migrate_result = test_migrate(api, source_dir)
    if not migrate_result.get("staging_dir"):
        log_line("\nMigration failed, cannot continue.")
        save_test_log(False)
        return False

    scan_result = test_scan(
        api,
        migrate_result["staging_dir"],
        migrate_result["staged_images"],
    )

    if not scan_result.get("result_file"):
        log_line("\nScan failed, cannot continue.")
        save_test_log(False)
        return False

    execute_result = test_execute(
        api,
        scan_result["result_file"],
        migrate_result["staging_dir"],
    )

    if use_folder:
        finalize_result = test_finalize_to_folder(
            api,
            migrate_result["staging_dir"],
            source_dir,
            migrate_result["source_count"],
            execute_result["moved"],
        )
    else:
        finalize_result = test_finalize(
            api,
            migrate_result["staging_dir"],
            source_dir,
            migrate_result["source_count"],
            execute_result["moved"],
        )

    # Report
    log_line("\n" + "=" * 60)
    log_line("TEST REPORT")
    log_line("=" * 60)
    log_line("Source: %s" % source_dir)
    log_line("Original images: %d" % migrate_result["source_count"])
    log_line("Groups found: %d" % scan_result["total_groups"])
    log_line("Duplicate files: %d" % scan_result["total_dupes"])
    log_line("Duplicates moved: %d" % execute_result["moved"])
    if use_folder:
        log_line("Duplicates moved to folder: %d" % finalize_result.get("total_moved", 0))
    else:
        log_line("Source dupes recycled: %d" % finalize_result.get("source_recycled", 0))
    log_line("Source images after: %d (-%d)" % (
        finalize_result["source_after"],
        migrate_result["source_count"] - finalize_result["source_after"]))
    log_line("")

    if _issues:
        log_line("ISSUES FOUND: %d" % len(_issues))
        for i, iss in enumerate(_issues):
            log_line("  %d. [%s] %s" % (i + 1, iss["step"], iss["message"]))
    else:
        log_line("ALL CHECKS PASSED")

    log_line("=" * 60)
    success = len(_issues) == 0
    save_test_log(success)
    return success


if __name__ == "__main__":
    use_folder = "--folder" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--folder"]
    source = args[0] if args else r"C:\Projects\Pictures"
    if not os.path.isdir(source):
        print("Source folder not found: " + source)
        sys.exit(1)
    success = run_test(source, use_folder=use_folder)
    sys.exit(0 if success else 1)

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
from pathlib import Path

# Project root setup
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine.config import (
    ensure_dirs, load_settings, DEFAULTS,
    SCANS_DIR, IMAGE_EXTENSIONS,
)

# Test reporting
_issues = []
_step = ""


def issue(msg):
    """Record a test issue."""
    _issues.append({"step": _step, "message": msg})
    print("  !! ISSUE: " + msg)


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
            print("  " + msg)
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
    print("\n=== STEP 1: MIGRATE ===")

    from web.server import staging_progress

    # Count source images before
    source_count = snapshot_source(source_dir)
    print("  Source images: %d" % source_count)
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
    print("  Staging dir: %s" % staging_dir)
    print("  Files copied: %d" % copied)

    # Verify staging has images
    staged_images = count_images(staging_dir)
    print("  Staged images: %d" % staged_images)
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
    print("\n=== STEP 2: SCAN ===")

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

    print("  Scanned: %d images" % scanned)
    print("  Groups: %d" % total_groups)
    print("  Duplicate files: %d" % total_dupes)
    print("  Reclaimable: %.1f MB" % summary.get("reclaimable_mb", 0))

    check(scanned == staged_images,
          "Scanned count (%d) != staged images (%d)" % (scanned, staged_images))
    check(len(result_file) > 0, "No scan result file produced")

    return {"result_file": result_file, "total_groups": total_groups, "total_dupes": total_dupes}


def test_execute(api, result_file, staging_dir):
    """Step 3: Load groups, mark all as dupes, execute move."""
    global _step
    _step = "execute"
    print("\n=== STEP 3: REVIEW + EXECUTE ===")

    from web.server import action_progress

    # Load groups
    group_data = api.get_groups({"report": result_file})
    groups = group_data.get("groups", [])
    print("  Loaded %d groups from %s" % (len(groups), result_file))

    if not groups:
        print("  No groups to execute")
        return {"moved": 0}

    # Count expected moves
    expected_moves = sum(len(g.get("duplicates", [])) for g in groups)
    print("  Expected moves: %d" % expected_moves)

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
    print("  Moved: %d" % moved)
    print("  Errors: %d" % len(errors))

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
        print("  Source dupe paths saved: %d" % len(paths))
        check(len(paths) == moved,
              "Source dupe paths (%d) != moved count (%d)" % (len(paths), moved))

    # Verify dupes folder has files
    dupes_images = count_images(dupes_dir)
    print("  Images in dupes folder: %d" % dupes_images)
    check(dupes_images >= moved,
          "Dupes folder count (%d) < moved (%d)" % (dupes_images, moved))

    return {"moved": moved, "dupes_dir": dupes_dir}


def test_finalize(api, staging_dir, source_dir, source_count, moved):
    """Step 4: Finalize -- restore, recycle source dupes, recycle workspace dupes, cleanup."""
    global _step
    _step = "finalize"
    print("\n=== STEP 4: FINALIZE ===")

    from web.server import restore_progress

    # Count staging before restore
    staging_before = count_images(staging_dir)
    print("  Staging files before restore: %d" % staging_before)
    print("  Expected source dupes to recycle: %d" % moved)

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
    print("  Restored: %d copied, %d skipped" % (restored, skipped))

    # Phase 2: Recycle source duplicates
    print("  Recycling source duplicates...")
    recycle_result = api.recycle_source_dupes({
        "staging_dir": staging_dir,
        "source_dir": source_dir,
    })
    source_recycled = recycle_result.get("recycled", 0)
    recycle_errors = recycle_result.get("errors", [])
    print("  Source dupes recycled: %d" % source_recycled)
    if recycle_errors:
        print("  Recycle errors: %s" % str(recycle_errors[:3]))

    check(source_recycled == moved,
          "Source recycled (%d) != moved (%d)" % (source_recycled, moved))

    # Phase 3: Verify source count reduced
    source_after = snapshot_source(source_dir)
    expected_after = source_count - moved
    print("  Source images after finalize: %d (was %d)" % (source_after, source_count))
    check(source_after == expected_after,
          "Source count (%d) != expected (%d = %d - %d)" %
          (source_after, expected_after, source_count, moved))

    # Phase 4: Recycle workspace dupes
    settings = load_settings()
    dupes_dir = settings.get("move_destination", DEFAULTS["move_destination"])
    if os.path.isdir(dupes_dir) and count_images(dupes_dir) > 0:
        print("  Recycling workspace dupes...")
        r = api.staging_recycle_bin({"folder": "dupes"})
        print("  Workspace dupes recycled: %s" % r.get("recycled", 0))

    # Phase 5: Cleanup workspace
    if os.path.isdir(staging_dir):
        api.staging_cleanup({"staging_dir": staging_dir})
    api.staging_reset()
    api.reset_state()
    print("  Workspace cleaned up")

    return {"source_after": source_after, "source_recycled": source_recycled}


# ---- Main Runner ----

def run_test(source_dir):
    """Run the full E2E test cycle."""
    print("=" * 60)
    print("PixHerder E2E Test Agent")
    print("Source: %s" % source_dir)
    print("=" * 60)

    from web.bridge import Api
    ensure_dirs()
    api = Api()

    # Validate state before starting
    api.validate_state()

    # Run the cycle
    migrate_result = test_migrate(api, source_dir)
    if not migrate_result.get("staging_dir"):
        print("\nMigration failed, cannot continue.")
        return False

    scan_result = test_scan(
        api,
        migrate_result["staging_dir"],
        migrate_result["staged_images"],
    )

    if not scan_result.get("result_file"):
        print("\nScan failed, cannot continue.")
        return False

    execute_result = test_execute(
        api,
        scan_result["result_file"],
        migrate_result["staging_dir"],
    )

    finalize_result = test_finalize(
        api,
        migrate_result["staging_dir"],
        source_dir,
        migrate_result["source_count"],
        execute_result["moved"],
    )

    # Report
    print("\n" + "=" * 60)
    print("TEST REPORT")
    print("=" * 60)
    print("Source: %s" % source_dir)
    print("Original images: %d" % migrate_result["source_count"])
    print("Groups found: %d" % scan_result["total_groups"])
    print("Duplicate files: %d" % scan_result["total_dupes"])
    print("Duplicates moved: %d" % execute_result["moved"])
    print("Source dupes recycled: %d" % finalize_result["source_recycled"])
    print("Source images after: %d (-%d)" % (
        finalize_result["source_after"],
        migrate_result["source_count"] - finalize_result["source_after"]))
    print()

    if _issues:
        print("ISSUES FOUND: %d" % len(_issues))
        for i, iss in enumerate(_issues):
            print("  %d. [%s] %s" % (i + 1, iss["step"], iss["message"]))
    else:
        print("ALL CHECKS PASSED")

    print("=" * 60)
    return len(_issues) == 0


if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else r"C:\Projects\Pictures"
    if not os.path.isdir(source):
        print("Source folder not found: " + source)
        sys.exit(1)
    success = run_test(source)
    sys.exit(0 if success else 1)

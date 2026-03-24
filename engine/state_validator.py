"""
PixHerder State Validator.
Enforces consistency rules across all persistent artifacts (manifests,
scan results, decision files, recovery archive, checkpoints, settings).

Runs at startup and after cleanup operations. Removes stale artifacts
that would confuse the app into thinking old sessions are still active.
"""

import json
import logging
import os
import shutil
from pathlib import Path

from engine.config import (
    SCANS_DIR, CHECKPOINTS_DIR, IMAGE_EXTENSIONS,
    load_settings, DEFAULTS,
)

logger = logging.getLogger(__name__)


def validate_state():
    """Run all validation rules. Returns a summary dict of actions taken.

    Safe to call at any time -- only removes artifacts that violate rules.
    Never touches user image files.
    """
    results = {
        "manifests_removed": 0,
        "orphan_staging_removed": 0,
        "stale_scans_removed": 0,
        "stale_decisions_removed": 0,
        "stale_checkpoints_removed": 0,
        "recovery_slots_cleared": 0,
        "errors": [],
    }

    try:
        results["manifests_removed"] = _validate_manifests()
    except Exception as e:
        results["errors"].append("manifest validation: " + str(e))

    try:
        results["orphan_staging_removed"] = _validate_staging_folders()
    except Exception as e:
        results["errors"].append("staging validation: " + str(e))

    try:
        results["stale_scans_removed"] = _validate_scan_results()
    except Exception as e:
        results["errors"].append("scan validation: " + str(e))

    try:
        results["stale_decisions_removed"] = _validate_decision_files()
    except Exception as e:
        results["errors"].append("decision validation: " + str(e))

    try:
        results["stale_checkpoints_removed"] = _validate_checkpoints()
    except Exception as e:
        results["errors"].append("checkpoint validation: " + str(e))

    try:
        results["recovery_slots_cleared"] = _validate_recovery_archive()
    except Exception as e:
        results["errors"].append("recovery validation: " + str(e))

    total = sum(v for k, v in results.items() if k != "errors")
    if total > 0:
        logger.info("State validator cleaned up %d artifacts: %s", total,
                     {k: v for k, v in results.items() if v and k != "errors"})
    else:
        logger.debug("State validator: all clean")

    return results


def _count_images(dirpath):
    """Count image files in a directory tree."""
    count = 0
    if not dirpath or not os.path.isdir(dirpath):
        return 0
    for root, dirs, files in os.walk(dirpath):
        for f in files:
            if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS:
                count += 1
    return count


# -- Rule 1: Manifests must reference existing staging dirs with files --

def _validate_manifests():
    """Remove manifests whose staging_dir doesn't exist or has no images."""
    removed = 0
    if not SCANS_DIR.is_dir():
        return 0

    for mf in list(SCANS_DIR.glob("staging_manifest_*.json")):
        try:
            with open(str(mf), "r", encoding="utf-8") as f:
                manifest = json.load(f)

            staging_dir = manifest.get("staging_dir", "")
            file_count = manifest.get("file_count", 0)

            # Rule 1a: staging_dir must exist
            if not staging_dir or not os.path.isdir(staging_dir):
                logger.info("Removing manifest (staging_dir gone): %s -> %s",
                           mf.name, staging_dir)
                mf.unlink()
                removed += 1
                continue

            # Rule 1b: staging_dir must contain image files
            actual_count = _count_images(staging_dir)
            if actual_count == 0:
                logger.info("Removing manifest (0 images in staging): %s -> %s",
                           mf.name, staging_dir)
                mf.unlink()
                removed += 1
                continue

            # Rule 1c: manifest recorded 0 files (failed migration)
            if file_count == 0:
                logger.info("Removing manifest (file_count=0): %s", mf.name)
                mf.unlink()
                removed += 1
                continue

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Removing corrupt manifest %s: %s", mf.name, e)
            mf.unlink()
            removed += 1

    return removed


# -- Rule 2: Staging subfolders must have a matching manifest --

def _validate_staging_folders():
    """Remove empty staging subfolders that have no manifest."""
    removed = 0
    settings = load_settings()

    # Collect all staging base dirs to check
    staging_bases = set()
    staging_bases.add(settings.get("staging_dir", DEFAULTS["staging_dir"]))
    # Also check common alternative locations
    alt_bases = [
        os.path.join("C:\\Temp", "PixHerder_Staging"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "PixHerder", "Staging"),
    ]
    for ab in alt_bases:
        if ab and os.path.isdir(ab):
            staging_bases.add(ab)

    # Load all manifest staging_dirs for cross-reference
    manifest_dirs = set()
    if SCANS_DIR.is_dir():
        for mf in SCANS_DIR.glob("staging_manifest_*.json"):
            try:
                with open(str(mf), "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                sd = manifest.get("staging_dir", "")
                if sd:
                    manifest_dirs.add(os.path.normpath(sd).lower())
            except Exception:
                pass

    for base in staging_bases:
        if not os.path.isdir(base):
            continue
        for d in os.listdir(base):
            candidate = os.path.join(base, d)
            if not os.path.isdir(candidate):
                continue

            norm = os.path.normpath(candidate).lower()
            has_manifest = norm in manifest_dirs
            has_images = _count_images(candidate) > 0

            # Empty staging subfolder with no manifest = orphan
            if not has_images and not has_manifest:
                logger.info("Removing orphan staging folder (empty, no manifest): %s",
                           candidate)
                try:
                    shutil.rmtree(candidate, ignore_errors=True)
                    removed += 1
                except Exception:
                    pass

    return removed


# -- Rule 3: Scan results should reference directories that exist --
# Note: we do NOT auto-delete scans for missing dirs, because the user
# may want to review old scan data. We only clean up decision files.

def _validate_scan_results():
    """Flag scan results whose directory no longer exists.
    Returns count of flagged (not deleted) scans for logging only."""
    flagged = 0
    if not SCANS_DIR.is_dir():
        return 0

    for sf in SCANS_DIR.glob("scan_*.json"):
        try:
            with open(str(sf), "r", encoding="utf-8") as f:
                data = json.load(f)
            directory = data.get("metadata", {}).get("directory", "")
            if directory and not os.path.isdir(directory):
                logger.debug("Scan references missing directory: %s -> %s",
                            sf.name, directory)
                flagged += 1
        except Exception:
            pass

    return 0  # Informational only, don't delete


# -- Rule 4: Decision files must have a matching scan result --

def _validate_decision_files():
    """Remove decision files whose scan result no longer exists."""
    removed = 0
    if not SCANS_DIR.is_dir():
        return 0

    # Collect existing scan filenames
    scan_names = set()
    for sf in SCANS_DIR.glob("scan_*.json"):
        scan_names.add(sf.name)

    for df in list(SCANS_DIR.glob("decisions_*.json")):
        # decisions_scan_20260321_xxx.json -> scan_20260321_xxx.json
        scan_name = df.name.replace("decisions_", "", 1)
        if scan_name not in scan_names:
            logger.info("Removing orphan decision file (scan gone): %s", df.name)
            df.unlink()
            removed += 1

    return removed


# -- Rule 5: Checkpoints should reference directories that exist --

def _validate_checkpoints():
    """Remove checkpoint files whose directory no longer exists."""
    removed = 0
    if not CHECKPOINTS_DIR.is_dir():
        return 0

    for cf in list(CHECKPOINTS_DIR.glob("*.json")):
        try:
            with open(str(cf), "r", encoding="utf-8") as f:
                data = json.load(f)
            directory = data.get("directory", "")
            if directory and not os.path.isdir(directory):
                logger.info("Removing stale checkpoint (dir gone): %s -> %s",
                           cf.name, directory)
                cf.unlink()
                removed += 1
        except (json.JSONDecodeError, KeyError):
            logger.warning("Removing corrupt checkpoint: %s", cf.name)
            cf.unlink()
            removed += 1

    return removed


# -- Rule 6: Recovery archive slots must have actual files --

def _validate_recovery_archive():
    """Clear recovery archive slots that have no files."""
    cleared = 0
    try:
        import tempfile
        base = os.path.join(tempfile.gettempdir(), "PixHerder_Recovery")
        if not os.path.isdir(base):
            return 0

        for slot_num in (1, 2):
            slot_dir = os.path.join(base, "slot_" + str(slot_num))
            if not os.path.isdir(slot_dir):
                continue

            files_dir = os.path.join(slot_dir, "files")
            has_files = False
            if os.path.isdir(files_dir):
                for _ in os.scandir(files_dir):
                    has_files = True
                    break

            if not has_files:
                logger.info("Clearing empty recovery slot %d", slot_num)
                shutil.rmtree(slot_dir, ignore_errors=True)
                cleared += 1

    except Exception:
        pass

    return cleared

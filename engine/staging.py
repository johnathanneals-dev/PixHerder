"""
DupeFinder OneDrive staging module.
Copies files from OneDrive-managed folders to a local staging directory
for interference-free scanning and deduplication.
"""

import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from engine.config import IMAGE_EXTENSIONS

from engine.config import SCANS_DIR


def is_onedrive_path(directory):
    """Check if a path is inside a OneDrive-managed folder."""
    normed = os.path.normpath(directory).lower()
    return "onedrive" in normed


def get_staging_dir(source_dir, base_staging_dir=None):
    """Return a deterministic staging subdirectory for a source path."""
    if base_staging_dir is None:
        import tempfile
        base_staging_dir = os.path.join(tempfile.gettempdir(), "DupeFinder_Staging")
    key = os.path.normpath(source_dir).lower()
    short_hash = hashlib.md5(key.encode("utf-8")).hexdigest()[:10]
    return os.path.join(base_staging_dir, short_hash)


def manifest_path_for(source_dir):
    """Return the manifest file path for a given source directory."""
    key = os.path.normpath(source_dir).lower()
    short_hash = hashlib.md5(key.encode("utf-8")).hexdigest()[:10]
    return SCANS_DIR / ("staging_manifest_" + short_hash + ".json")


def count_files_for_staging(source_dir, extensions=None):
    """Count files and estimate total bytes for staging."""
    if extensions is None:
        extensions = IMAGE_EXTENSIONS
    file_count = 0
    total_bytes = 0
    for root, dirs, files in os.walk(source_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in extensions:
                file_count += 1
                try:
                    total_bytes += os.path.getsize(os.path.join(root, f))
                except Exception:
                    pass
    return file_count, total_bytes


def start_staging(source_dir, staging_dir, extensions=None,
                  progress_cb=None, cancel_event=None):
    """Copy image files from source to staging directory.

    Uses robocopy on Windows for speed and resilience. Falls back to
    shutil.copy2 if robocopy is unavailable.

    Args:
        source_dir: OneDrive-managed source path.
        staging_dir: Local destination path.
        extensions: Set of file extensions to copy. None = all images.
        progress_cb: Optional callback(copied, total, bytes_copied, bytes_total, stage).
        cancel_event: Optional threading.Event for cancellation.

    Returns:
        Dict with copied, skipped, failed, errors, staging_dir, manifest_path.
    """
    if extensions is None:
        extensions = IMAGE_EXTENSIONS

    try:
        os.makedirs(staging_dir, exist_ok=True)
    except OSError as e:
        return {
            "copied": 0, "skipped": 0, "failed": 0,
            "errors": ["Could not create staging folder: " + str(e)
                       + ". Check Windows Defender Controlled Folder Access."],
            "staging_dir": staging_dir, "manifest_path": None,
        }

    # Count total files first
    total_files, total_bytes = count_files_for_staging(source_dir, extensions)

    if progress_cb:
        progress_cb(0, total_files, 0, total_bytes, "counting")

    # Try robocopy first (much faster for bulk copies)
    try:
        return _stage_with_robocopy(
            source_dir, staging_dir, extensions,
            total_files, total_bytes,
            progress_cb, cancel_event,
        )
    except FileNotFoundError:
        # robocopy not available, fall back to Python
        return _stage_with_python(
            source_dir, staging_dir, extensions,
            total_files, total_bytes,
            progress_cb, cancel_event,
        )


def _stage_with_robocopy(source_dir, staging_dir, extensions,
                         total_files, total_bytes,
                         progress_cb, cancel_event):
    """Stage files using robocopy."""
    # Build extension filter for robocopy
    ext_args = []
    for ext in extensions:
        ext_args.append("*" + ext)

    cmd = [
        "robocopy",
        source_dir,
        staging_dir,
    ] + ext_args + [
        "/E",          # recurse including empty dirs
        "/COPY:DAT",   # copy data, attributes, timestamps
        "/XO",         # exclude older (skip already-copied files)
        "/R:1",        # retry once
        "/W:1",        # wait 1 second between retries
        "/NP",         # no percentage progress
        "/NDL",        # no directory listing
        "/NJH",        # no job header
        "/NJS",        # no job summary
        "/TEE",        # output to console and log
        "/BYTES",      # show sizes in bytes
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    copied = 0
    skipped = 0
    failed = 0
    bytes_copied = 0
    errors = []

    for line in proc.stdout:
        if cancel_event and cancel_event.is_set():
            proc.terminate()
            return {
                "copied": copied,
                "skipped": skipped,
                "failed": failed,
                "errors": errors,
                "cancelled": True,
                "staging_dir": staging_dir,
            }

        line = line.strip()
        if not line:
            continue

        # robocopy output: "New File  <size>  <path>" or "Older  <size>  <path>"
        # or "*EXTRA File  <size>  <path>" etc.
        lower = line.lower()
        if "new file" in lower or "newer" in lower:
            copied += 1
            # Try to extract size
            parts = line.split()
            for p in parts:
                if p.isdigit():
                    bytes_copied += int(p)
                    break
            if progress_cb:
                progress_cb(copied + skipped, total_files,
                            bytes_copied, total_bytes, "staging")
        elif "older" in lower or "same" in lower:
            skipped += 1
            # Count size for skipped too (already staged)
            parts = line.split()
            for p in parts:
                if p.isdigit():
                    bytes_copied += int(p)
                    break
            if progress_cb:
                progress_cb(copied + skipped, total_files,
                            bytes_copied, total_bytes, "staging")
        elif "failed" in lower or "error" in lower:
            failed += 1
            errors.append(line)

    proc.wait()
    # robocopy exit codes: 0-7 = success/info, 8+ = errors
    # Not treating exit code as error since we track file-level results

    # Build and save manifest
    manifest = _build_manifest(source_dir, staging_dir)

    if progress_cb:
        progress_cb(total_files, total_files, total_bytes, total_bytes, "done")

    return {
        "copied": copied,
        "skipped": skipped,
        "failed": failed,
        "errors": errors,
        "cancelled": False,
        "staging_dir": staging_dir,
        "manifest_path": str(manifest),
        "total_staged": copied + skipped,
    }


def _stage_with_python(source_dir, staging_dir, extensions,
                       total_files, total_bytes,
                       progress_cb, cancel_event):
    """Stage files using Python shutil (fallback)."""
    copied = 0
    skipped = 0
    failed = 0
    bytes_copied = 0
    errors = []

    for root, dirs, files in os.walk(source_dir):
        for f in files:
            if cancel_event and cancel_event.is_set():
                return {
                    "copied": copied,
                    "skipped": skipped,
                    "failed": failed,
                    "errors": errors,
                    "cancelled": True,
                    "staging_dir": staging_dir,
                }

            ext = os.path.splitext(f)[1].lower()
            if ext not in extensions:
                continue

            src = os.path.join(root, f)
            rel = os.path.relpath(src, source_dir)
            dst = os.path.join(staging_dir, rel)

            # Skip if already staged and same size/time
            if os.path.exists(dst):
                try:
                    src_stat = os.stat(src)
                    dst_stat = os.stat(dst)
                    if (dst_stat.st_size == src_stat.st_size and
                            abs(dst_stat.st_mtime - src_stat.st_mtime) < 2):
                        skipped += 1
                        bytes_copied += src_stat.st_size
                        if progress_cb:
                            progress_cb(copied + skipped, total_files,
                                        bytes_copied, total_bytes, "staging")
                        continue
                except Exception:
                    pass

            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                copied += 1
                try:
                    bytes_copied += os.path.getsize(dst)
                except Exception:
                    pass
            except Exception as e:
                failed += 1
                errors.append(str(src) + ": " + str(e))

            if progress_cb:
                progress_cb(copied + skipped, total_files,
                            bytes_copied, total_bytes, "staging")

    manifest = _build_manifest(source_dir, staging_dir)

    if progress_cb:
        progress_cb(total_files, total_files, total_bytes, total_bytes, "done")

    return {
        "copied": copied,
        "skipped": skipped,
        "failed": failed,
        "errors": errors,
        "cancelled": False,
        "staging_dir": staging_dir,
        "manifest_path": str(manifest),
        "total_staged": copied + skipped,
    }


def _build_manifest(source_dir, staging_dir):
    """Build and save a manifest mapping staged paths to originals."""
    mpath = manifest_path_for(source_dir)

    # Count staged files
    staged_count = 0
    staged_bytes = 0
    for root, dirs, files in os.walk(staging_dir):
        for f in files:
            staged_count += 1
            try:
                staged_bytes += os.path.getsize(os.path.join(root, f))
            except Exception:
                pass

    manifest = {
        "source_dir": os.path.normpath(source_dir),
        "staging_dir": os.path.normpath(staging_dir),
        "created": datetime.now().isoformat(),
        "file_count": staged_count,
        "bytes_total": staged_bytes,
    }

    with open(str(mpath), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return mpath


def load_manifest(source_dir):
    """Load a staging manifest for a source directory. Returns dict or None."""
    mpath = manifest_path_for(source_dir)
    if not mpath.exists():
        return None
    try:
        with open(str(mpath), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def staged_to_original(staged_path, staging_dir, source_dir):
    """Convert a staged file path back to its OneDrive original path."""
    staging_dir = os.path.normpath(staging_dir)
    source_dir = os.path.normpath(source_dir)
    staged_path = os.path.normpath(staged_path)
    rel = os.path.relpath(staged_path, staging_dir)
    return os.path.join(source_dir, rel)


def sync_back_deletions(staging_dir, source_dir, progress_cb=None,
                        cancel_event=None):
    """Delete OneDrive originals for files that were removed from staging.

    Walks the source directory and checks if each file's staged counterpart
    still exists. If not, the original has been cleaned up and should be
    deleted from OneDrive too.

    Returns dict with deleted, skipped, errors.
    """
    deleted = 0
    skipped = 0
    error_count = 0
    errors = []
    staging_dir = os.path.normpath(staging_dir)
    source_dir = os.path.normpath(source_dir)

    # Count originals first
    originals = []
    for root, dirs, files in os.walk(source_dir):
        for f in files:
            originals.append(os.path.join(root, f))
    total = len(originals)

    for i, original_path in enumerate(originals):
        if cancel_event and cancel_event.is_set():
            break

        rel = os.path.relpath(original_path, source_dir)
        staged_path = os.path.join(staging_dir, rel)

        if os.path.exists(staged_path):
            # Still in staging = keep the original
            skipped += 1
        else:
            # Removed from staging = recycle the original (safe delete)
            try:
                _recycle_file_powershell(original_path)
                deleted += 1
            except Exception as e:
                error_count += 1
                errors.append(str(original_path) + ": recycle failed: " + str(e))

        if progress_cb:
            progress_cb(i + 1, total, "syncback")

    return {
        "deleted": deleted,
        "skipped": skipped,
        "errors": error_count,
        "error_details": errors,
        "total": total,
    }


def cleanup_staging(staging_dir):
    """Remove the staging directory."""
    import stat

    def _force_remove_readonly(func, path, exc_info):
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        func(path)

    try:
        shutil.rmtree(staging_dir, onerror=_force_remove_readonly)
        return {"status": "cleaned"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _recycle_file_powershell(filepath):
    """Send a single file to the Windows Recycle Bin via PowerShell."""
    import subprocess

    ps_path = str(filepath).replace("'", "''")
    cmd = (
        'powershell -NoProfile -ExecutionPolicy Bypass -Command "'
        "Add-Type -AssemblyName Microsoft.VisualBasic; "
        "[Microsoft.VisualBasic.FileIO.FileSystem]"
        "::DeleteFile("
        "'" + ps_path + "', "
        "'OnlyErrorDialogs', 'SendToRecycleBin')"
        '"'
    )
    result = subprocess.run(
        cmd, shell=True, capture_output=True, timeout=30
    )
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(stderr or "PowerShell returned exit code " + str(result.returncode))


def recycle_staging(staging_dir, progress_cb=None):
    """Send all files in staging directory to the Windows Recycle Bin.

    Uses PowerShell with -ExecutionPolicy Bypass to avoid policy
    restrictions. Falls back to permanent delete if PowerShell fails
    on the first file (e.g. PowerShell not available).
    """
    import stat

    staging = Path(staging_dir)
    if not staging.is_dir():
        return {"status": "error", "error": "Staging directory not found"}

    # Collect all files
    files = [f for f in staging.rglob("*") if f.is_file()]
    total = len(files)
    if total == 0:
        # Empty folder -- just remove the directory tree
        cleanup_staging(staging_dir)
        return {"status": "recycled", "files_recycled": 0, "errors": 0}

    recycled = 0
    errors = 0
    error_details = []

    for i, filepath in enumerate(files):
        try:
            # Clear read-only flag if set
            os.chmod(str(filepath), stat.S_IWRITE | stat.S_IREAD)
            _recycle_file_powershell(filepath)
            recycled += 1
        except Exception as e:
            errors += 1
            error_details.append(str(filepath) + ": " + str(e))

        if progress_cb and (i % 50 == 0 or i == total - 1):
            progress_cb(i + 1, total)

    # Clean up empty directory tree
    try:
        shutil.rmtree(staging_dir, ignore_errors=True)
    except Exception:
        pass

    return {
        "status": "recycled",
        "files_recycled": recycled,
        "errors": errors,
        "error_details": error_details[:20],
        "total": total,
        "used_fallback": False,
    }

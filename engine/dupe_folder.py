"""Move duplicates into a user-visible folder in the source directory.

Creates PixHerder_Duplicates/ with two subfolders and a README.
Used as an alternative to Recycle Bin during finalize.
"""
import os
import shutil
import stat
import logging

from engine.config import verify_copy
from engine.actions import log_action

logger = logging.getLogger(__name__)

README_TEXT = """\
PixHerder Duplicates -- What's In This Folder

PixHerder found duplicate files in your photos and moved them here
so your folder only has unique files. Nothing has been deleted.

What's inside:

- Found_Duplicates -- The duplicate files PixHerder identified
  during scanning.

- Source_of_Duplicates -- The files from your folder that had
  matching copies. Moved here to keep your folder clean.

What you can do now:

1. Browse and inspect -- Open either subfolder in File Explorer to
   review the files at your own pace. Right-click any file to
   preview it.

2. Delete files one by one -- Right-click a file and choose
   "Delete." It goes to the Recycle Bin, and you can restore it
   if you change your mind.

3. Delete the entire folder -- If you're satisfied that everything
   here is unnecessary, right-click the "PixHerder_Duplicates"
   folder and choose "Delete." The whole folder goes to the
   Recycle Bin.

About the Recycle Bin:

The Windows Recycle Bin has a size limit (usually a percentage of
your drive). If you send a large number of files there, older items
may be removed automatically to make room. If this folder is very
large, consider deleting in smaller batches.

Need to undo?

If you change your mind, you can copy files from this folder back
to your photos folder. PixHerder did not modify or rename any
files -- they are exactly as they were.
"""

FOLDER_NAME = "PixHerder_Duplicates"
FOUND_SUBFOLDER = "Found_Duplicates"
SOURCE_SUBFOLDER = "Source_of_Duplicates"


def create_dupe_folder(source_dir):
    """Create the PixHerder_Duplicates folder structure with README.

    Args:
        source_dir: Path to the user's source directory.

    Returns:
        Dict with base_dir, found_dir, source_of_dir paths.
    """
    base_dir = os.path.join(source_dir, FOLDER_NAME)
    found_dir = os.path.join(base_dir, FOUND_SUBFOLDER)
    source_of_dir = os.path.join(base_dir, SOURCE_SUBFOLDER)

    os.makedirs(found_dir, exist_ok=True)
    os.makedirs(source_of_dir, exist_ok=True)

    readme_path = os.path.join(base_dir, "README.txt")
    if not os.path.exists(readme_path):
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(README_TEXT)
        logger.info("Created README.txt in %s", base_dir)

    logger.info("Dupe folder ready: %s", base_dir)
    return {
        "base_dir": base_dir,
        "found_dir": found_dir,
        "source_of_dir": source_of_dir,
    }


def _safe_move(src, dest_dir, relative_to=None):
    """Copy+verify+delete a single file into dest_dir.

    Preserves subfolder structure relative to relative_to if provided.
    Uses collision avoidance on the destination filename.

    Args:
        src: Source file path string.
        dest_dir: Destination directory path string.
        relative_to: If provided, preserve relative path structure.

    Returns:
        Destination path string on success, None on failure.
    """
    if not os.path.isfile(src):
        return None

    # Build destination path preserving structure
    if relative_to:
        rel = os.path.relpath(src, relative_to)
        dest = os.path.join(dest_dir, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
    else:
        dest = os.path.join(dest_dir, os.path.basename(src))

    # Collision avoidance
    if os.path.exists(dest):
        base, ext = os.path.splitext(dest)
        counter = 1
        while os.path.exists(dest):
            dest = base + "_" + str(counter) + ext
            counter += 1

    try:
        shutil.copy2(src, dest)
        if not verify_copy(src, dest):
            logger.error("Copy verification failed: %s -> %s", src, dest)
            return None
        # Clear read-only flag if set
        if not os.access(src, os.W_OK):
            os.chmod(src, stat.S_IWRITE | stat.S_IREAD)
        os.remove(src)
        return dest
    except Exception as e:
        logger.error("Failed to move %s -> %s: %s", src, dest, e)
        return None


def move_workspace_dupes(dupes_dir, found_dir):
    """Move workspace duplicate files into Found_Duplicates subfolder.

    Args:
        dupes_dir: Path to the workspace dupes folder (move_destination).
        found_dir: Path to PixHerder_Duplicates/Found_Duplicates/.

    Returns:
        Dict with moved count and errors list.
    """
    moved = 0
    errors = []

    if not os.path.isdir(dupes_dir):
        return {"moved": 0, "errors": []}

    for root, dirs, files in os.walk(dupes_dir):
        for fname in files:
            src = os.path.join(root, fname)
            dest = _safe_move(src, found_dir, relative_to=dupes_dir)
            if dest:
                moved += 1
                log_action("move_to_dupe_folder", {
                    "source": src,
                    "destination": dest,
                    "subfolder": "Found_Duplicates",
                    "success": True,
                })
            else:
                errors.append(src)
                log_action("move_to_dupe_folder", {
                    "source": src,
                    "subfolder": "Found_Duplicates",
                    "success": False,
                })

    return {"moved": moved, "errors": errors}


def move_source_dupes(staging_dir, source_dir, source_of_dir):
    """Move source duplicates into Source_of_Duplicates subfolder.

    Reads source_dupes.json to map staging paths back to source paths,
    then moves the source files into the subfolder.

    Args:
        staging_dir: Path to the staging directory.
        source_dir: Path to the user's source directory.
        source_of_dir: Path to PixHerder_Duplicates/Source_of_Duplicates/.

    Returns:
        Dict with moved count and errors list.
    """
    import json
    from engine.config import SCANS_DIR

    map_path = os.path.join(str(SCANS_DIR), "source_dupes.json")
    if not os.path.isfile(map_path):
        logger.info("No source_dupes.json found, nothing to move")
        return {"moved": 0, "errors": []}

    try:
        with open(map_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error("Failed to read source dupe map: %s", e)
        return {"moved": 0, "errors": [str(e)]}

    staging_paths = data.get("staging_paths", [])
    if not staging_paths:
        return {"moved": 0, "errors": []}

    moved = 0
    errors = []

    for sp in staging_paths:
        try:
            rel = os.path.relpath(sp, staging_dir)
            source_path = os.path.join(source_dir, rel)
            if not os.path.isfile(source_path):
                logger.debug("Source file not found (already gone?): %s",
                            source_path)
                continue
            dest = _safe_move(source_path, source_of_dir,
                            relative_to=source_dir)
            if dest:
                moved += 1
                log_action("move_to_dupe_folder", {
                    "source": source_path,
                    "destination": dest,
                    "subfolder": "Source_of_Duplicates",
                    "success": True,
                })
            else:
                errors.append(source_path)
        except Exception as e:
            logger.warning("Failed to map staging path %s: %s", sp, e)
            errors.append(sp)

    # Clean up the map file
    try:
        os.unlink(map_path)
    except Exception:
        pass

    return {"moved": moved, "errors": errors}

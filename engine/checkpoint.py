"""
DupeFinder scan checkpoint management.
Saves and restores scan state so interrupted scans can be resumed.
"""

import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from engine.config import CHECKPOINTS_DIR

logger = logging.getLogger(__name__)


def _stable_id(directory, mode):
    """Create a deterministic ID from scan parameters."""
    key = os.path.normpath(directory).lower() + "|" + mode
    return hashlib.md5(key.encode("utf-8")).hexdigest()[:12]


def checkpoint_path(directory, mode):
    """Return the checkpoint file path for a given directory and mode."""
    return CHECKPOINTS_DIR / ("checkpoint_" + _stable_id(directory, mode) + ".json")


def save_checkpoint(ckpt_path, data):
    """Atomically save checkpoint data to disk.

    Uses write-to-temp + os.replace pattern for crash safety: if the
    process dies mid-write, the previous checkpoint remains intact.
    """
    logger.debug("Saving checkpoint to %s", ckpt_path)
    data["timestamp"] = datetime.now().isoformat()
    tmp_path = str(ckpt_path) + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp_path, str(ckpt_path))
    except Exception:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


def load_checkpoint(ckpt_path):
    """Load checkpoint data. Returns dict or None if missing/corrupt."""
    try:
        logger.debug("Loading checkpoint from %s", ckpt_path)
        with open(str(ckpt_path), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


def delete_checkpoint(ckpt_path):
    """Remove a checkpoint file."""
    try:
        os.remove(str(ckpt_path))
    except Exception:
        pass


def find_checkpoint(directory, mode):
    """Check if a resumable checkpoint exists. Returns (path, data) or (None, None)."""
    ckpt = checkpoint_path(directory, mode)
    if ckpt.exists():
        data = load_checkpoint(ckpt)
        if data:
            return ckpt, data
    return None, None


def validate_checkpoint(data, current_files):
    """Validate checkpoint hashes against current file state.

    Removes entries for files that no longer exist or have changed
    (different mtime or size). Returns the cleaned data.
    """
    file_info = data.get("file_info", {})
    md5_hashes = data.get("md5_hashes", {})
    phash_hashes = data.get("phash_hashes", {})

    current_set = set(str(p) for p in current_files)
    stale = []

    for filepath in list(md5_hashes.keys()) + list(phash_hashes.keys()):
        if filepath in stale:
            continue
        if filepath not in current_set:
            stale.append(filepath)
            continue
        saved_info = file_info.get(filepath)
        if saved_info:
            try:
                st = os.stat(filepath)
                if (st.st_mtime != saved_info.get("mtime") or
                        st.st_size != saved_info.get("size")):
                    stale.append(filepath)
            except Exception:
                stale.append(filepath)

    for filepath in stale:
        md5_hashes.pop(filepath, None)
        phash_hashes.pop(filepath, None)
        file_info.pop(filepath, None)

    data["md5_hashes"] = md5_hashes
    data["phash_hashes"] = phash_hashes
    data["file_info"] = file_info
    data["stale_removed"] = len(stale)
    return data

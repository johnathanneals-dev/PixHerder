"""
PixHerder image serving and path validation.
Security-critical: validates all file paths against allowed directories.
"""

import logging
import os
import shutil

from engine.config import DEFAULTS, load_settings
from web.workers import _find_staging_subfolder, staging_progress

logger = logging.getLogger(__name__)


def _is_allowed_path(filepath, include_active_staging=True):
    """Check if filepath is within allowed directories (staging, dupes, keepers).

    Uses os.path.realpath for consistent comparison across all callers.
    Returns True if the path is inside an allowed directory.
    """
    settings = load_settings()
    allowed = [
        settings.get("staging_dir", DEFAULTS["staging_dir"]),
        settings.get("move_destination", DEFAULTS["move_destination"]),
        settings.get("keepers_dir", DEFAULTS.get("keepers_dir", "")),
    ]
    src = staging_progress.get("source_dir") or ""
    if src:
        allowed.append(src)
    if include_active_staging:
        active = _find_staging_subfolder()
        if active:
            allowed.append(active)
            allowed.append(os.path.dirname(active))
    resolved = []
    for d in allowed:
        if d and os.path.isdir(d):
            resolved.append(os.path.realpath(d).lower())
    real = os.path.realpath(filepath).lower()
    return any(real.startswith(a + os.sep) or real.startswith(a + "/")
               or real == a for a in resolved)


def serve_image(handler, filepath):
    """Serve an image file with path validation, ETag caching, and content-type detection."""
    filepath = os.path.normpath(filepath)

    if not _is_allowed_path(filepath):
        logger.warning("Image access denied: %s", filepath)
        handler.send_error(403, "Access denied")
        return

    if not os.path.isfile(filepath):
        handler.send_error(404, "File not found")
        return

    ext = os.path.splitext(filepath)[1].lower()
    content_types = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
        ".bmp": "image/bmp", ".webp": "image/webp",
        ".tiff": "image/tiff", ".tif": "image/tiff",
        ".heic": "image/heic", ".heif": "image/heif",
    }
    ct = content_types.get(ext, "application/octet-stream")

    try:
        file_stat = os.stat(filepath)
        etag = '"' + str(file_stat.st_mtime) + "-" + str(file_stat.st_size) + '"'

        if_none_match = handler.headers.get("If-None-Match")
        if if_none_match == etag:
            handler.send_response(304)
            handler.end_headers()
            return

        handler.send_response(200)
        handler.send_header("Content-Type", ct)
        handler.send_header("Content-Length", str(file_stat.st_size))
        handler.send_header("Cache-Control", "max-age=3600")
        handler.send_header("ETag", etag)
        handler.end_headers()

        with open(filepath, "rb") as f:
            shutil.copyfileobj(f, handler.wfile)
    except Exception as e:
        handler.send_error(500, str(e))

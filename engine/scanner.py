"""
DupeFinder image scanner.
Discovers image files in directories with extension filtering.
"""

import logging
from pathlib import Path
from engine.config import IMAGE_EXTENSIONS

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS


def find_images(directory, recursive=True, extensions=None):
    """Walk a directory and yield all image file paths.

    Args:
        directory: Path to scan.
        recursive: Whether to scan subdirectories.
        extensions: Set of extensions to match, or None for defaults.

    Yields:
        Path objects for each matching image file.
    """
    exts = extensions or SUPPORTED_EXTENSIONS
    # Normalize extensions to lowercase with leading dot
    exts = {e.lower() if e.startswith(".") else "." + e.lower() for e in exts}
    directory = Path(directory)
    logger.debug("Discovering images in %s (recursive=%s)", directory, recursive)
    pattern = "**/*" if recursive else "*"
    try:
        for filepath in directory.glob(pattern):
            try:
                if filepath.is_file() and filepath.suffix.lower() in exts:
                    yield filepath
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass


def count_images(directory, recursive=True, extensions=None):
    """Fast count of image files without loading them.

    Returns:
        Integer count of matching image files.
    """
    count = 0
    for _ in find_images(directory, recursive, extensions):
        count += 1
    logger.debug("Found %d images", count)
    return count

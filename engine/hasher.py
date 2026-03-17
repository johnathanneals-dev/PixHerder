"""
DupeFinder hashing utilities.
Provides MD5 (exact match) and perceptual (visual similarity) hashing.
"""

import hashlib
from PIL import Image
import imagehash


DEFAULT_HASH_SIZE = 16


def md5_hash(filepath):
    """Compute MD5 hex digest of a file.

    Returns:
        Tuple of (hash_string_or_None, error_string_or_None).
    """
    try:
        h = hashlib.md5()
        with open(str(filepath), "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return (h.hexdigest(), None)
    except Exception as e:
        return (None, str(e))


def perceptual_hash(filepath, hash_size=DEFAULT_HASH_SIZE):
    """Compute perceptual hash (pHash) of an image.

    Returns:
        Tuple of (imagehash_object_or_None, error_string_or_None).
    """
    try:
        img = Image.open(str(filepath))
        return (imagehash.phash(img, hash_size=hash_size), None)
    except Exception as e:
        return (None, str(e))

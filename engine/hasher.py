"""
PixHerder hashing utilities.
Provides MD5 (exact match) and perceptual (visual similarity) hashing.
"""

import hashlib
import logging
from PIL import Image
import imagehash

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

logger = logging.getLogger(__name__)

Image.MAX_IMAGE_PIXELS = 200_000_000

DEFAULT_HASH_SIZE = 16


def md5_hash(filepath):
    """Compute MD5 hex digest of a file.

    Returns:
        Tuple of (hash_string_or_None, error_string_or_None).
    """
    try:
        logger.debug("Computing MD5 for %s", filepath)
        h = hashlib.md5()
        with open(str(filepath), "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return (h.hexdigest(), None)
    except Exception as e:
        logger.error("Hash error for %s: %s", filepath, e)
        return (None, str(e))


def perceptual_hash(filepath, hash_size=DEFAULT_HASH_SIZE):
    """Compute perceptual hash (pHash) of an image.

    Returns:
        Tuple of (imagehash_object_or_None, error_string_or_None).
    """
    try:
        logger.debug("Computing pHash for %s", filepath)
        with Image.open(str(filepath)) as img:
            return (imagehash.phash(img, hash_size=hash_size), None)
    except Exception as e:
        logger.error("Hash error for %s: %s", filepath, e)
        return (None, str(e))


def perceptual_hash_with_dims(filepath, hash_size=DEFAULT_HASH_SIZE):
    """Compute perceptual hash and extract image dimensions.

    Opens the image once for both operations. Image.size reads
    only the header -- no pixel decode, effectively free.

    Returns:
        Tuple of (imagehash_object_or_None, (width, height)_or_None,
                  error_string_or_None).
    """
    try:
        logger.debug("Computing pHash+dims for %s", filepath)
        with Image.open(str(filepath)) as img:
            dims = img.size
            return (imagehash.phash(img, hash_size=hash_size), dims, None)
    except Exception as e:
        logger.error("Hash error for %s: %s", filepath, e)
        return (None, None, str(e))

"""
Unit tests for engine/hasher.py.

Covers Mimir s-39 finding T-1: the engine layer carried zero unit coverage.
`hasher` is the bottom of the dependency chain — comparator, and through it
actions, are only as trustworthy as the digests this module returns.

Contract under test: every public function returns a tuple whose last element
is an error string, and returns `None` (never raises) in the error slot for
unreadable or non-image input. Callers in `comparator` branch on exactly that,
so a raise here would abort a whole scan instead of recording one bad file.

CI-safe — creates only temp files; no network, no subprocess, no recycling.
"""

import hashlib
import os
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PIL import Image

from engine.hasher import (
    DEFAULT_HASH_SIZE,
    md5_hash,
    perceptual_hash,
    perceptual_hash_with_dims,
)


def _write_image(path, color=(255, 0, 0), size=(64, 64)):
    """Write a solid-color PNG. Deterministic, so hashes are reproducible."""
    Image.new("RGB", size, color).save(path)
    return path


def _gradient_image(path, size=(64, 64), invert=False):
    """Write a horizontal gradient — visually distinct from a solid fill."""
    img = Image.new("RGB", size)
    px = img.load()
    for x in range(size[0]):
        v = int(255 * x / max(1, size[0] - 1))
        if invert:
            v = 255 - v
        for y in range(size[1]):
            px[x, y] = (v, v, v)
    img.save(path)
    return path


class TestMd5Hash(unittest.TestCase):
    """md5_hash: exact-match digest used for the exact-duplicate pass."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def test_returns_digest_and_no_error_for_readable_file(self):
        p = os.path.join(self.tmp, "a.bin")
        with open(p, "wb") as f:
            f.write(b"pixherder")
        digest, err = md5_hash(p)
        self.assertIsNone(err)
        self.assertEqual(digest, hashlib.md5(b"pixherder").hexdigest())

    def test_matches_hashlib_across_the_8192_byte_chunk_boundary(self):
        # The implementation reads in 8192-byte chunks. Payloads either side
        # of that boundary would expose an off-by-one in the read loop.
        for size in (0, 1, 8191, 8192, 8193, 70000):
            with self.subTest(size=size):
                payload = bytes((i * 7 + size) % 256 for i in range(size))
                p = os.path.join(self.tmp, "chunk_%d.bin" % size)
                with open(p, "wb") as f:
                    f.write(payload)
                digest, err = md5_hash(p)
                self.assertIsNone(err)
                self.assertEqual(digest, hashlib.md5(payload).hexdigest())

    def test_identical_content_hashes_identically_regardless_of_name(self):
        a = os.path.join(self.tmp, "one.bin")
        b = os.path.join(self.tmp, "two_different_name.bin")
        for p in (a, b):
            with open(p, "wb") as f:
                f.write(b"same bytes")
        self.assertEqual(md5_hash(a)[0], md5_hash(b)[0])

    def test_single_bit_difference_changes_the_digest(self):
        a = os.path.join(self.tmp, "a.bin")
        b = os.path.join(self.tmp, "b.bin")
        with open(a, "wb") as f:
            f.write(b"\x00")
        with open(b, "wb") as f:
            f.write(b"\x01")
        self.assertNotEqual(md5_hash(a)[0], md5_hash(b)[0])

    def test_missing_file_returns_none_and_an_error_string(self):
        digest, err = md5_hash(os.path.join(self.tmp, "nope.bin"))
        self.assertIsNone(digest)
        self.assertIsInstance(err, str)
        self.assertTrue(err)

    def test_directory_argument_returns_error_rather_than_raising(self):
        digest, err = md5_hash(self.tmp)
        self.assertIsNone(digest)
        self.assertIsInstance(err, str)

    def test_accepts_path_object_not_just_str(self):
        from pathlib import Path
        p = os.path.join(self.tmp, "p.bin")
        with open(p, "wb") as f:
            f.write(b"path object")
        digest, err = md5_hash(Path(p))
        self.assertIsNone(err)
        self.assertEqual(digest, hashlib.md5(b"path object").hexdigest())


class TestPerceptualHash(unittest.TestCase):
    """perceptual_hash: visual-similarity digest for the pHash pass."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def test_returns_hash_and_no_error_for_a_real_image(self):
        p = _gradient_image(os.path.join(self.tmp, "g.png"))
        h, err = perceptual_hash(p)
        self.assertIsNone(err)
        self.assertIsNotNone(h)

    def test_identical_images_have_zero_hamming_distance(self):
        a = _gradient_image(os.path.join(self.tmp, "a.png"))
        b = _gradient_image(os.path.join(self.tmp, "b.png"))
        ha, _ = perceptual_hash(a)
        hb, _ = perceptual_hash(b)
        self.assertEqual(int(ha - hb), 0)

    def test_visually_opposite_images_have_nonzero_distance(self):
        # Guards the comparator's threshold logic: if every image hashed the
        # same, find_perceptual_duplicates would group the entire library.
        a = _gradient_image(os.path.join(self.tmp, "a.png"))
        b = _gradient_image(os.path.join(self.tmp, "b.png"), invert=True)
        ha, _ = perceptual_hash(a)
        hb, _ = perceptual_hash(b)
        self.assertGreater(int(ha - hb), 0)

    def test_hash_size_controls_hash_width(self):
        p = _gradient_image(os.path.join(self.tmp, "g.png"))
        small, _ = perceptual_hash(p, hash_size=8)
        large, _ = perceptual_hash(p, hash_size=DEFAULT_HASH_SIZE)
        self.assertLess(len(str(small)), len(str(large)))

    def test_non_image_file_returns_none_and_an_error_string(self):
        p = os.path.join(self.tmp, "not_an_image.png")
        with open(p, "wb") as f:
            f.write(b"this is plainly not a PNG")
        h, err = perceptual_hash(p)
        self.assertIsNone(h)
        self.assertIsInstance(err, str)
        self.assertTrue(err)

    def test_missing_file_returns_none_and_an_error_string(self):
        h, err = perceptual_hash(os.path.join(self.tmp, "ghost.png"))
        self.assertIsNone(h)
        self.assertIsInstance(err, str)


class TestPerceptualHashWithDims(unittest.TestCase):
    """perceptual_hash_with_dims: one open() for both hash and dimensions."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def test_reports_actual_image_dimensions(self):
        p = _write_image(os.path.join(self.tmp, "wide.png"), size=(80, 30))
        h, dims, err = perceptual_hash_with_dims(p)
        self.assertIsNone(err)
        self.assertIsNotNone(h)
        self.assertEqual(dims, (80, 30))

    def test_hash_agrees_with_the_single_purpose_function(self):
        # comparator uses these two interchangeably depending on cache state;
        # if they disagreed, a cache hit would silently regroup images.
        p = _gradient_image(os.path.join(self.tmp, "g.png"))
        plain, _ = perceptual_hash(p)
        combined, _dims, _err = perceptual_hash_with_dims(p)
        self.assertEqual(str(plain), str(combined))

    def test_error_case_returns_three_slots_with_none_hash_and_none_dims(self):
        p = os.path.join(self.tmp, "broken.png")
        with open(p, "wb") as f:
            f.write(b"nope")
        h, dims, err = perceptual_hash_with_dims(p)
        self.assertIsNone(h)
        self.assertIsNone(dims)
        self.assertIsInstance(err, str)

    def test_missing_file_returns_none_hash_and_none_dims(self):
        h, dims, err = perceptual_hash_with_dims(
            os.path.join(self.tmp, "ghost.png"))
        self.assertIsNone(h)
        self.assertIsNone(dims)
        self.assertIsInstance(err, str)


if __name__ == "__main__":
    unittest.main()

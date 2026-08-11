"""
Unit tests for engine/comparator.py.

Covers Mimir s-39 finding T-1. This module decides which of the user's photos
are duplicates; everything destructive downstream (`actions.move_files`,
`actions.delete_files`) acts on the groups it returns. A false grouping here
is a data-loss bug with extra steps, so the grouping rules are pinned hard.

Both clustering paths are exercised. `find_perceptual_duplicates` switches to
LSH bit-banding above 500 images and brute-force O(n^2) below it, and the two
paths are independent implementations of the same contract. They are driven
here through `precomputed_hashes`, which short-circuits all image I/O — that
lets the 500-image threshold be crossed deterministically and in milliseconds.

CI-safe — temp files only; no recycling, no subprocess, no network.
"""

import os
import sys
import tempfile
import threading
import unittest

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.comparator import (
    find_exact_duplicates,
    find_perceptual_duplicates,
    pick_original,
)

HASH_BITS = 256          # hash_size=16 -> 16x16 bits
HEX_LEN = HASH_BITS // 4  # 64 hex chars


def _hex_from_int(value):
    """Render an int as a fixed-width hex hash string imagehash can parse."""
    return format(value & ((1 << HASH_BITS) - 1), "0%dx" % HEX_LEN)


def _flip_low_bits(base, count):
    """Return base with `count` low-order bits flipped -> hamming distance == count."""
    mask = (1 << count) - 1
    return base ^ mask


def _distant_hashes(count, seed=20260811):
    """Deterministic pseudo-random hashes, mutually far apart.

    Filler hashes must not be near each other or near the fixture hashes,
    or Union-Find chains them into one library-sized cluster and the
    assertions stop meaning anything. Random 256-bit values sit ~128 bits
    apart, so accidental sub-threshold pairs do not occur.
    """
    import random
    rng = random.Random(seed)
    return [rng.getrandbits(HASH_BITS) for _ in range(count)]


class TestFindExactDuplicates(unittest.TestCase):
    """MD5 grouping — the exact-match pass."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def _write(self, name, content):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f:
            f.write(content)
        return p

    def test_identical_files_are_grouped_together(self):
        a = self._write("a.jpg", b"same")
        b = self._write("b.jpg", b"same")
        result = find_exact_duplicates([a, b])
        self.assertEqual(len(result["groups"]), 1)
        self.assertCountEqual([str(p) for p in result["groups"][0]], [a, b])

    def test_unique_files_produce_no_groups(self):
        a = self._write("a.jpg", b"one")
        b = self._write("b.jpg", b"two")
        self.assertEqual(find_exact_duplicates([a, b])["groups"], [])

    def test_singleton_is_not_reported_as_a_group(self):
        # A group of one is not a duplicate. If this regressed, every photo in
        # the library would show up as its own "duplicate group".
        a = self._write("only.jpg", b"lonely")
        self.assertEqual(find_exact_duplicates([a])["groups"], [])

    def test_three_way_duplicate_forms_one_group_of_three(self):
        paths = [self._write("%d.jpg" % i, b"triplet") for i in range(3)]
        groups = find_exact_duplicates(paths)["groups"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]), 3)

    def test_two_separate_duplicate_pairs_form_two_groups(self):
        self._write("a1.jpg", b"alpha")
        self._write("a2.jpg", b"alpha")
        self._write("b1.jpg", b"beta")
        self._write("b2.jpg", b"beta")
        paths = [os.path.join(self.tmp, n)
                 for n in ("a1.jpg", "a2.jpg", "b1.jpg", "b2.jpg")]
        groups = find_exact_duplicates(paths)["groups"]
        self.assertEqual(len(groups), 2)
        self.assertTrue(all(len(g) == 2 for g in groups))

    def test_unreadable_file_is_recorded_as_an_error_not_raised(self):
        good = self._write("good.jpg", b"ok")
        missing = os.path.join(self.tmp, "gone.jpg")
        result = find_exact_duplicates([good, missing])
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["path"], missing)

    def test_one_bad_file_does_not_abort_the_remaining_scan(self):
        missing = os.path.join(self.tmp, "gone.jpg")
        a = self._write("a.jpg", b"dup")
        b = self._write("b.jpg", b"dup")
        result = find_exact_duplicates([missing, a, b])
        self.assertEqual(len(result["groups"]), 1)
        self.assertEqual(len(result["errors"]), 1)

    def test_returns_computed_hashes_for_reuse(self):
        a = self._write("a.jpg", b"cacheable")
        result = find_exact_duplicates([a])
        self.assertIn(a, result["hashes"])

    def test_precomputed_hash_is_trusted_and_the_file_is_not_reread(self):
        # The cache path must not touch disk — that is the whole point of it.
        ghost = os.path.join(self.tmp, "never_existed.jpg")
        real = self._write("real.jpg", b"whatever")
        result = find_exact_duplicates(
            [ghost, real], precomputed_hashes={ghost: "deadbeef", real: "deadbeef"})
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(result["groups"]), 1)
        self.assertEqual(len(result["groups"][0]), 2)

    def test_file_info_captures_size_for_hashed_files(self):
        a = self._write("a.jpg", b"0123456789")
        info = find_exact_duplicates([a])["file_info"]
        self.assertEqual(info[a]["size"], 10)
        self.assertIn("mtime", info[a])

    def test_progress_callback_reports_one_tick_per_file(self):
        paths = [self._write("%d.jpg" % i, bytes([i])) for i in range(4)]
        seen = []
        find_exact_duplicates(paths, progress_cb=lambda c, t, s: seen.append((c, t, s)))
        self.assertEqual([c for c, _, _ in seen], [1, 2, 3, 4])
        self.assertTrue(all(t == 4 for _, t, _ in seen))
        self.assertTrue(all(s == "md5" for _, _, s in seen))

    def test_cancel_event_stops_the_scan_and_flags_cancelled(self):
        paths = [self._write("%d.jpg" % i, bytes([i])) for i in range(5)]
        ev = threading.Event()
        ev.set()
        result = find_exact_duplicates(paths, cancel_event=ev)
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["groups"], [])

    def test_cancel_midway_stops_early_and_keeps_partial_hashes(self):
        paths = [self._write("%d.jpg" % i, bytes([i])) for i in range(6)]
        ev = threading.Event()

        def cb(current, total, stage):
            if current == 2:
                ev.set()

        result = find_exact_duplicates(paths, cancel_event=ev, progress_cb=cb)
        self.assertTrue(result["cancelled"])
        self.assertEqual(len(result["hashes"]), 2)

    def test_checkpoint_callback_fires_on_the_batch_boundary(self):
        paths = [self._write("%d.jpg" % i, bytes([i])) for i in range(5)]
        calls = []
        find_exact_duplicates(
            paths, checkpoint_cb=lambda h, fi: calls.append(len(h)), batch_size=2)
        self.assertEqual(calls, [2, 4])

    def test_empty_input_is_handled(self):
        result = find_exact_duplicates([])
        self.assertEqual(result["groups"], [])
        self.assertFalse(result["cancelled"])


class TestFindPerceptualDuplicatesBruteForce(unittest.TestCase):
    """Similarity grouping below the 500-image LSH threshold."""

    def _run(self, hash_ints, threshold=5, **kw):
        paths = ["img_%03d.jpg" % i for i in range(len(hash_ints))]
        pre = {p: _hex_from_int(v) for p, v in zip(paths, hash_ints)}
        return find_perceptual_duplicates(
            paths, threshold=threshold, precomputed_hashes=pre, **kw)

    def test_identical_hashes_are_grouped(self):
        result = self._run([0, 0])
        self.assertEqual(len(result["groups"]), 1)
        self.assertEqual(len(result["groups"][0]["paths"]), 2)

    def test_distance_within_threshold_is_grouped(self):
        result = self._run([0, _flip_low_bits(0, 3)], threshold=5)
        self.assertEqual(len(result["groups"]), 1)

    def test_distance_exactly_at_threshold_is_grouped(self):
        # Boundary is `distance <= threshold`. Pinning it stops a future
        # refactor from silently turning it into `<`.
        result = self._run([0, _flip_low_bits(0, 5)], threshold=5)
        self.assertEqual(len(result["groups"]), 1)

    def test_distance_one_past_threshold_is_not_grouped(self):
        result = self._run([0, _flip_low_bits(0, 6)], threshold=5)
        self.assertEqual(result["groups"], [])

    def test_threshold_zero_groups_only_exact_hash_matches(self):
        result = self._run([0, 0, _flip_low_bits(0, 1)], threshold=0)
        self.assertEqual(len(result["groups"]), 1)
        self.assertEqual(len(result["groups"][0]["paths"]), 2)

    def test_reported_distances_are_measured_from_the_first_member(self):
        result = self._run([0, _flip_low_bits(0, 2)], threshold=5)
        distances = result["groups"][0]["distances"]
        self.assertEqual(list(distances.values()), [2])

    def test_unrelated_images_are_not_grouped(self):
        far = (1 << 200) | (1 << 100) | 0xFFFF
        self.assertEqual(self._run([0, far], threshold=5)["groups"], [])

    def test_two_distinct_clusters_are_reported_separately(self):
        # base_b needs real hamming weight — a single set bit is distance 1
        # from zero and would collapse both pairs into one cluster.
        base_b = ((1 << 64) - 1) << 128
        result = self._run(
            [0, _flip_low_bits(0, 1), base_b, base_b ^ 0b11], threshold=5)
        self.assertEqual(len(result["groups"]), 2)
        self.assertTrue(all(len(g["paths"]) == 2 for g in result["groups"]))

    def test_singleton_is_not_reported_as_a_group(self):
        self.assertEqual(self._run([0])["groups"], [])

    def test_empty_input_is_handled(self):
        result = self._run([])
        self.assertEqual(result["groups"], [])
        self.assertFalse(result["cancelled"])

    def test_corrupt_cached_hash_does_not_abort_the_scan(self):
        # A corrupt cache entry must degrade to a recompute attempt, not kill
        # the run. The file does not exist, so it becomes a recorded error.
        result = find_perceptual_duplicates(
            ["broken.jpg"], precomputed_hashes={"broken.jpg": "not-hex-at-all"})
        self.assertEqual(result["groups"], [])
        self.assertEqual(len(result["errors"]), 1)

    def test_cancel_during_hashing_returns_immediately_as_cancelled(self):
        ev = threading.Event()
        ev.set()
        result = self._run([0, 0, 0], cancel_event=ev)
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["groups"], [])

    def test_progress_callback_reports_the_hashing_stage(self):
        seen = []
        self._run([0, 0, 0], progress_cb=lambda c, t, s: seen.append(s))
        self.assertIn("phash_hash", seen)

    def test_checkpoint_callback_fires_on_the_batch_boundary(self):
        calls = []
        self._run([0, 0, 0, 0], checkpoint_cb=lambda h, fi: calls.append(1),
                  batch_size=2)
        self.assertEqual(len(calls), 2)


class TestFindPerceptualDuplicatesLSH(unittest.TestCase):
    """Similarity grouping above the 500-image threshold (bit-banded + union-find)."""

    LSH_MIN = 501  # implementation switches at n > 500

    def _padded(self, extra_hashes, threshold=5):
        """Pad with mutually-distant hashes so n crosses the LSH threshold."""
        hash_ints = list(extra_hashes) + _distant_hashes(self.LSH_MIN)
        paths = ["img_%04d.jpg" % i for i in range(len(hash_ints))]
        pre = {p: _hex_from_int(v) for p, v in zip(paths, hash_ints)}
        return find_perceptual_duplicates(
            paths, threshold=threshold, precomputed_hashes=pre), paths

    def test_lsh_path_groups_identical_hashes(self):
        result, paths = self._padded([0, 0])
        matched = [g for g in result["groups"]
                   if set(str(p) for p in g["paths"]) >= {paths[0], paths[1]}]
        self.assertEqual(len(matched), 1)

    def test_lsh_path_groups_near_duplicates_sharing_a_band(self):
        # Bands are 16 hex chars each. Differences confined to the low bits
        # leave the leading bands identical, so the pair is a candidate.
        result, paths = self._padded([0, _flip_low_bits(0, 3)], threshold=5)
        matched = [g for g in result["groups"]
                   if set(str(p) for p in g["paths"]) >= {paths[0], paths[1]}]
        self.assertEqual(len(matched), 1)

    def test_lsh_path_respects_the_threshold(self):
        result, paths = self._padded([0, _flip_low_bits(0, 9)], threshold=5)
        matched = [g for g in result["groups"]
                   if set(str(p) for p in g["paths"]) >= {paths[0], paths[1]}]
        self.assertEqual(matched, [])

    def test_lsh_clustering_is_transitive_via_union_find(self):
        # a~b and b~c but a and c are 6 apart (> threshold). Union-Find must
        # still put all three in one cluster; that is what makes the result
        # order-independent.
        a = 0
        b = _flip_low_bits(0, 3)
        c = b ^ 0b111000
        result, paths = self._padded([a, b, c], threshold=5)
        matched = [g for g in result["groups"]
                   if set(str(p) for p in g["paths"]) >= set(paths[:3])]
        self.assertEqual(len(matched), 1)
        self.assertEqual(len(matched[0]["paths"]), 3)

    def test_lsh_path_actually_engaged_for_this_input_size(self):
        # Guard the guard: if the 500 threshold moved, the tests above would
        # quietly be re-testing brute force instead.
        result, paths = self._padded([0, 0])
        self.assertGreater(len(paths), 500)

    def test_lsh_recall_limit_differences_spread_across_every_band(self):
        # Characterizing current behavior, not endorsing it: two images within
        # the distance threshold are MISSED when their differing bits fall in
        # all four bands, because no band matches exactly and the pair is
        # never nominated as a candidate. Brute force below 500 images would
        # catch this pair. If bucketing is ever reworked, this test should be
        # updated deliberately rather than discovered by a user.
        spread = (1 << 0) | (1 << 64) | (1 << 128) | (1 << 192)
        result, paths = self._padded([0, spread], threshold=5)
        matched = [g for g in result["groups"]
                   if set(str(p) for p in g["paths"]) >= {paths[0], paths[1]}]
        self.assertEqual(matched, [])

        # Same pair, same threshold, below the LSH cutoff -> found.
        small_paths = ["s0.jpg", "s1.jpg"]
        small = find_perceptual_duplicates(
            small_paths, threshold=5,
            precomputed_hashes={"s0.jpg": _hex_from_int(0),
                                "s1.jpg": _hex_from_int(spread)})
        self.assertEqual(len(small["groups"]), 1)


class TestPickOriginal(unittest.TestCase):
    """Which file survives — the single most consequential choice in the app."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def _write(self, name, size=10, mtime=None):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f:
            f.write(b"x" * size)
        if mtime is not None:
            os.utime(p, (mtime, mtime))
        return p

    def test_largest_strategy_keeps_the_biggest_file(self):
        small = self._write("small.jpg", size=10)
        big = self._write("big.jpg", size=500)
        self.assertEqual(str(pick_original([small, big], "largest")), big)

    def test_oldest_strategy_keeps_the_earliest_mtime(self):
        old = self._write("old.jpg", mtime=1_000_000)
        new = self._write("new.jpg", mtime=2_000_000)
        self.assertEqual(str(pick_original([old, new], "oldest")), old)

    def test_newest_strategy_keeps_the_latest_mtime(self):
        old = self._write("old.jpg", mtime=1_000_000)
        new = self._write("new.jpg", mtime=2_000_000)
        self.assertEqual(str(pick_original([old, new], "newest")), new)

    def test_shortest_name_strategy_keeps_the_shortest_filename(self):
        short = self._write("a.jpg")
        long = self._write("a_much_longer_name.jpg")
        self.assertEqual(str(pick_original([short, long], "shortest_name")), short)

    def test_unknown_strategy_falls_back_to_largest(self):
        small = self._write("small.jpg", size=10)
        big = self._write("big.jpg", size=500)
        self.assertEqual(str(pick_original([small, big], "no_such_strategy")), big)

    def test_default_strategy_is_largest(self):
        small = self._write("small.jpg", size=10)
        big = self._write("big.jpg", size=500)
        self.assertEqual(str(pick_original([small, big])), big)

    def test_missing_files_are_skipped_not_fatal(self):
        real = self._write("real.jpg", size=42)
        ghost = os.path.join(self.tmp, "ghost.jpg")
        self.assertEqual(str(pick_original([ghost, real])), real)

    def test_returns_none_when_no_candidate_is_readable(self):
        # actions.move_files/delete_files skip the whole group on None. If this
        # returned an arbitrary path instead, they would act on a phantom.
        ghosts = [os.path.join(self.tmp, n) for n in ("a.jpg", "b.jpg")]
        self.assertIsNone(pick_original(ghosts))

    def test_returns_none_for_an_empty_group(self):
        self.assertIsNone(pick_original([]))

    def test_accepts_string_paths_as_well_as_path_objects(self):
        from pathlib import Path
        small = self._write("small.jpg", size=10)
        big = self._write("big.jpg", size=500)
        self.assertEqual(str(pick_original([Path(small), Path(big)])), big)


if __name__ == "__main__":
    unittest.main()

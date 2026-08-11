"""
Unit tests for engine/actions.py.

Covers Mimir s-39 finding T-1. This is the module that actually touches the
user's files. The properties pinned here are the ones whose failure loses
photos: a source is deleted only after its copy is verified, a failure in one
file never takes the batch down with it, and a path listed in two groups is
acted on exactly once.

CI-safe by construction:
  * `engine.staging._recycle_file_powershell` is patched in every test that
    can reach it — no test may send a real file to the Recycle Bin.
  * `engine.actions.LOGS_DIR` is redirected to a temp dir, so the repo's
    logs/ folder is never written to.
Both are asserted, not just assumed — see TestCiSafety at the bottom.
"""

import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.actions import delete_files, log_action, move_files, rescue_file

_RECYCLE = "engine.staging._recycle_file_powershell"


class _ActionTestCase(unittest.TestCase):
    """Temp workspace + log redirection shared by the action suites."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

        self.src_dir = os.path.join(self.tmp, "source")
        self.dest_dir = os.path.join(self.tmp, "dupes")
        os.makedirs(self.src_dir)

        # Keep action logging out of the repo.
        self.log_dir = Path(self.tmp) / "logs"
        self.log_dir.mkdir()
        p = patch("engine.actions.LOGS_DIR", self.log_dir)
        p.start()
        self.addCleanup(p.stop)

    def write(self, name, content=b"payload", parent=None):
        p = os.path.join(parent or self.src_dir, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(content)
        return p


class TestMoveFiles(_ActionTestCase):
    """move_files: copy to the dupes folder, then remove the original."""

    def test_moves_duplicate_and_leaves_the_keeper_in_place(self):
        keep = self.write("keep.jpg", b"aaaa")
        dupe = self.write("dupe.jpg", b"aaaa")
        result = move_files([{"keep": keep, "duplicates": [dupe]}], self.dest_dir)

        self.assertEqual(result["moved"], 1)
        self.assertEqual(result["errors"], [])
        self.assertTrue(os.path.exists(keep))
        self.assertFalse(os.path.exists(dupe))
        self.assertTrue(os.path.exists(os.path.join(self.dest_dir, "dupe.jpg")))

    def test_moved_file_keeps_its_contents(self):
        keep = self.write("keep.jpg", b"exact bytes")
        dupe = self.write("dupe.jpg", b"exact bytes")
        move_files([{"keep": keep, "duplicates": [dupe]}], self.dest_dir)
        with open(os.path.join(self.dest_dir, "dupe.jpg"), "rb") as f:
            self.assertEqual(f.read(), b"exact bytes")

    def test_list_style_group_picks_the_keeper_by_strategy(self):
        small = self.write("small.jpg", b"x")
        big = self.write("big.jpg", b"x" * 100)
        result = move_files([[small, big]], self.dest_dir, keep_strategy="largest")

        self.assertEqual(result["moved"], 1)
        self.assertTrue(os.path.exists(big), "largest must be kept")
        self.assertFalse(os.path.exists(small))

    def test_creates_the_destination_directory(self):
        keep = self.write("keep.jpg")
        dupe = self.write("dupe.jpg")
        self.assertFalse(os.path.isdir(self.dest_dir))
        move_files([{"keep": keep, "duplicates": [dupe]}], self.dest_dir)
        self.assertTrue(os.path.isdir(self.dest_dir))

    def test_name_collision_gets_a_numeric_suffix_and_does_not_overwrite(self):
        os.makedirs(self.dest_dir)
        existing = os.path.join(self.dest_dir, "dupe.jpg")
        with open(existing, "wb") as f:
            f.write(b"PRE-EXISTING")

        keep = self.write("keep.jpg", b"new content")
        dupe = self.write("dupe.jpg", b"new content")
        move_files([{"keep": keep, "duplicates": [dupe]}], self.dest_dir)

        with open(existing, "rb") as f:
            self.assertEqual(f.read(), b"PRE-EXISTING")
        with open(os.path.join(self.dest_dir, "dupe_1.jpg"), "rb") as f:
            self.assertEqual(f.read(), b"new content")

    def test_repeated_collisions_keep_incrementing(self):
        os.makedirs(self.dest_dir)
        for name in ("dupe.jpg", "dupe_1.jpg"):
            with open(os.path.join(self.dest_dir, name), "wb") as f:
                f.write(b"taken")
        keep = self.write("keep.jpg")
        dupe = self.write("dupe.jpg")
        move_files([{"keep": keep, "duplicates": [dupe]}], self.dest_dir)
        self.assertTrue(os.path.exists(os.path.join(self.dest_dir, "dupe_2.jpg")))

    def test_scan_dir_preserves_subfolder_structure(self):
        keep = self.write("keep.jpg")
        nested = self.write(os.path.join("2019", "trip", "dupe.jpg"))
        move_files([{"keep": keep, "duplicates": [nested]}],
                   self.dest_dir, scan_dir=self.src_dir)
        self.assertTrue(os.path.exists(
            os.path.join(self.dest_dir, "2019", "trip", "dupe.jpg")))

    def test_path_outside_scan_dir_falls_back_to_a_flat_destination(self):
        outside = os.path.join(self.tmp, "elsewhere")
        os.makedirs(outside)
        keep = self.write("keep.jpg")
        dupe = self.write("stray.jpg", parent=outside)
        move_files([{"keep": keep, "duplicates": [dupe]}],
                   self.dest_dir, scan_dir=self.src_dir)
        self.assertTrue(os.path.exists(os.path.join(self.dest_dir, "stray.jpg")))

    def test_missing_source_is_skipped_not_an_error(self):
        keep = self.write("keep.jpg")
        ghost = os.path.join(self.src_dir, "ghost.jpg")
        result = move_files([{"keep": keep, "duplicates": [ghost]}], self.dest_dir)
        self.assertEqual(result["moved"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["errors"], [])

    def test_failed_copy_verification_preserves_the_source_file(self):
        # The core data-safety invariant: the original is removed only after
        # the copy is confirmed. If verify_copy is ever wired up wrong, this
        # is the test that stops a delete-without-a-copy shipping.
        keep = self.write("keep.jpg")
        dupe = self.write("dupe.jpg")
        with patch("engine.actions.verify_copy", return_value=False):
            result = move_files([{"keep": keep, "duplicates": [dupe]}], self.dest_dir)

        self.assertTrue(os.path.exists(dupe), "source must survive a bad copy")
        self.assertEqual(result["moved"], 0)
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("verification", result["errors"][0]["error"])

    def test_one_failure_does_not_stop_the_rest_of_the_batch(self):
        keep = self.write("keep.jpg")
        bad = self.write("bad.jpg")
        good = self.write("good.jpg")
        real_copy = __import__("shutil").copy2

        def flaky(src, dst, *a, **kw):
            if src.endswith("bad.jpg"):
                raise OSError("device not ready")
            return real_copy(src, dst, *a, **kw)

        with patch("engine.actions.shutil.copy2", side_effect=flaky):
            result = move_files(
                [{"keep": keep, "duplicates": [bad, good]}], self.dest_dir)

        self.assertEqual(result["moved"], 1)
        self.assertEqual(len(result["errors"]), 1)
        self.assertTrue(os.path.exists(bad))
        self.assertFalse(os.path.exists(good))

    def test_same_path_in_two_groups_is_moved_only_once(self):
        keep_a = self.write("keep_a.jpg")
        keep_b = self.write("keep_b.jpg")
        shared = self.write("shared.jpg")
        result = move_files([
            {"keep": keep_a, "duplicates": [shared]},
            {"keep": keep_b, "duplicates": [shared]},
        ], self.dest_dir)
        self.assertEqual(result["moved"], 1)
        self.assertEqual(result["skipped"], 0)

    def test_moved_sources_lists_what_actually_moved(self):
        keep = self.write("keep.jpg")
        dupe = self.write("dupe.jpg")
        result = move_files([{"keep": keep, "duplicates": [dupe]}], self.dest_dir)
        self.assertEqual(result["moved_sources"], [dupe])

    def test_progress_total_counts_unique_duplicates(self):
        keep = self.write("keep.jpg")
        d1 = self.write("d1.jpg")
        d2 = self.write("d2.jpg")
        totals = []
        move_files([{"keep": keep, "duplicates": [d1, d2]}], self.dest_dir,
                   progress_cb=lambda c, t, s: totals.append(t))
        self.assertTrue(all(t == 2 for t in totals))

    def test_cancel_event_stops_the_batch_and_flags_cancelled(self):
        keep = self.write("keep.jpg")
        dupe = self.write("dupe.jpg")
        ev = threading.Event()
        ev.set()
        result = move_files([{"keep": keep, "duplicates": [dupe]}],
                            self.dest_dir, cancel_event=ev)
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["moved"], 0)
        self.assertTrue(os.path.exists(dupe))

    def test_unresolvable_list_group_is_skipped(self):
        ghosts = [os.path.join(self.src_dir, n) for n in ("a.jpg", "b.jpg")]
        result = move_files([ghosts], self.dest_dir)
        self.assertEqual(result["moved"], 0)
        self.assertEqual(result["errors"], [])

    def test_empty_group_list_is_a_no_op(self):
        result = move_files([], self.dest_dir)
        self.assertEqual(result["moved"], 0)
        self.assertFalse(result["cancelled"])


class TestDeleteFiles(_ActionTestCase):
    """delete_files: route duplicates to the Recycle Bin. Always mocked."""

    def test_recycles_each_duplicate_once(self):
        keep = self.write("keep.jpg")
        d1 = self.write("d1.jpg")
        d2 = self.write("d2.jpg")
        with patch(_RECYCLE) as recycle:
            result = delete_files([{"keep": keep, "duplicates": [d1, d2]}])

        self.assertEqual(result["deleted"], 2)
        self.assertEqual(result["errors"], [])
        self.assertCountEqual(
            [str(c.args[0]) for c in recycle.call_args_list], [d1, d2])

    def test_keeper_is_never_recycled(self):
        keep = self.write("keep.jpg")
        dupe = self.write("dupe.jpg")
        with patch(_RECYCLE) as recycle:
            delete_files([{"keep": keep, "duplicates": [dupe]}])
        recycled = [str(c.args[0]) for c in recycle.call_args_list]
        self.assertNotIn(keep, recycled)

    def test_list_style_group_recycles_all_but_the_keeper(self):
        small = self.write("small.jpg", b"x")
        big = self.write("big.jpg", b"x" * 100)
        with patch(_RECYCLE) as recycle:
            delete_files([[small, big]], keep_strategy="largest")
        self.assertEqual([str(c.args[0]) for c in recycle.call_args_list], [small])

    def test_archive_slot_is_forwarded_for_recovery(self):
        keep = self.write("keep.jpg")
        dupe = self.write("dupe.jpg")
        with patch(_RECYCLE) as recycle:
            delete_files([{"keep": keep, "duplicates": [dupe]}], archive_slot=3)
        self.assertEqual(recycle.call_args.kwargs.get("archive_slot"), 3)

    def test_missing_file_is_skipped_and_never_reaches_the_recycler(self):
        keep = self.write("keep.jpg")
        ghost = os.path.join(self.src_dir, "ghost.jpg")
        with patch(_RECYCLE) as recycle:
            result = delete_files([{"keep": keep, "duplicates": [ghost]}])
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["deleted"], 0)
        recycle.assert_not_called()

    def test_recycle_failure_is_recorded_and_the_batch_continues(self):
        keep = self.write("keep.jpg")
        bad = self.write("bad.jpg")
        good = self.write("good.jpg")

        def flaky(path, **kw):
            if str(path).endswith("bad.jpg"):
                raise RuntimeError("PowerShell unavailable")

        with patch(_RECYCLE, side_effect=flaky):
            result = delete_files([{"keep": keep, "duplicates": [bad, good]}])

        self.assertEqual(result["deleted"], 1)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["path"], bad)

    def test_same_path_in_two_groups_is_recycled_only_once(self):
        keep_a = self.write("keep_a.jpg")
        keep_b = self.write("keep_b.jpg")
        shared = self.write("shared.jpg")
        with patch(_RECYCLE) as recycle:
            result = delete_files([
                {"keep": keep_a, "duplicates": [shared]},
                {"keep": keep_b, "duplicates": [shared]},
            ])
        self.assertEqual(result["deleted"], 1)
        self.assertEqual(recycle.call_count, 1)

    def test_cancel_event_prevents_any_recycling(self):
        keep = self.write("keep.jpg")
        dupe = self.write("dupe.jpg")
        ev = threading.Event()
        ev.set()
        with patch(_RECYCLE) as recycle:
            result = delete_files([{"keep": keep, "duplicates": [dupe]}],
                                  cancel_event=ev)
        self.assertTrue(result["cancelled"])
        recycle.assert_not_called()

    def test_progress_callback_reports_the_delete_stage(self):
        keep = self.write("keep.jpg")
        dupe = self.write("dupe.jpg")
        seen = []
        with patch(_RECYCLE):
            delete_files([{"keep": keep, "duplicates": [dupe]}],
                         progress_cb=lambda c, t, s: seen.append((c, t, s)))
        self.assertEqual(seen, [(1, 1, "delete")])

    def test_empty_group_list_is_a_no_op(self):
        with patch(_RECYCLE) as recycle:
            result = delete_files([])
        self.assertEqual(result["deleted"], 0)
        recycle.assert_not_called()


class TestRescueFile(_ActionTestCase):
    """rescue_file: pull a file back out of the dupes folder."""

    def test_restores_the_file_and_removes_it_from_the_dupes_folder(self):
        source = self.write("in_dupes.jpg", b"rescue me", parent=self.tmp)
        dest = os.path.join(self.src_dir, "restored.jpg")

        result = rescue_file(source, dest)

        self.assertTrue(result["success"])
        self.assertIsNone(result["error"])
        self.assertFalse(os.path.exists(source))
        with open(dest, "rb") as f:
            self.assertEqual(f.read(), b"rescue me")

    def test_creates_missing_parent_directories(self):
        source = self.write("in_dupes.jpg", parent=self.tmp)
        dest = os.path.join(self.src_dir, "2019", "trip", "restored.jpg")
        self.assertTrue(rescue_file(source, dest)["success"])
        self.assertTrue(os.path.exists(dest))

    def test_missing_source_reports_failure_without_raising(self):
        result = rescue_file(os.path.join(self.tmp, "ghost.jpg"),
                             os.path.join(self.src_dir, "x.jpg"))
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Source file not found")

    def test_failed_verification_preserves_the_source(self):
        source = self.write("in_dupes.jpg", parent=self.tmp)
        dest = os.path.join(self.src_dir, "restored.jpg")
        with patch("engine.actions.verify_copy", return_value=False):
            result = rescue_file(source, dest)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Copy verification failed")
        self.assertTrue(os.path.exists(source), "source must survive")

    def test_unwritable_destination_reports_failure_without_raising(self):
        source = self.write("in_dupes.jpg", parent=self.tmp)
        with patch("engine.actions.shutil.copy2", side_effect=OSError("denied")):
            result = rescue_file(source, os.path.join(self.src_dir, "x.jpg"))
        self.assertFalse(result["success"])
        self.assertIn("denied", result["error"])
        self.assertTrue(os.path.exists(source))


class TestLogAction(_ActionTestCase):
    """log_action: best-effort audit trail that must never break an action."""

    def test_writes_a_json_line_with_action_and_timestamp(self):
        log_action("move", {"source": "a.jpg", "success": True})
        written = list(self.log_dir.glob("actions_*.log"))
        self.assertEqual(len(written), 1)

        entry = json.loads(written[0].read_text().strip())
        self.assertEqual(entry["action"], "move")
        self.assertEqual(entry["source"], "a.jpg")
        self.assertTrue(entry["success"])
        self.assertIn("timestamp", entry)

    def test_appends_rather_than_overwrites(self):
        log_action("move", {"n": 1})
        log_action("delete", {"n": 2})
        written = list(self.log_dir.glob("actions_*.log"))[0]
        lines = [ln for ln in written.read_text().splitlines() if ln.strip()]
        self.assertEqual(len(lines), 2)

    def test_logging_failure_is_swallowed(self):
        # The action must still succeed when the log cannot be written.
        with patch("engine.actions.open", side_effect=OSError("read-only fs")):
            log_action("move", {"source": "a.jpg"})  # must not raise

    def test_a_failed_move_still_produces_a_log_entry(self):
        keep = self.write("keep.jpg")
        dupe = self.write("dupe.jpg")
        with patch("engine.actions.shutil.copy2", side_effect=OSError("boom")):
            move_files([{"keep": keep, "duplicates": [dupe]}], self.dest_dir)

        written = list(self.log_dir.glob("actions_*.log"))[0]
        entry = json.loads(written.read_text().strip())
        self.assertFalse(entry["success"])
        self.assertIn("boom", entry["error"])


class TestCiSafety(_ActionTestCase):
    """The safety rails this file depends on are real, not assumed."""

    def test_log_dir_patch_actually_redirects_away_from_the_repo(self):
        log_action("move", {"probe": True})
        self.assertTrue(list(self.log_dir.glob("actions_*.log")),
                        "LOGS_DIR patch is not taking effect")

    def test_patching_the_recycler_intercepts_the_real_call_site(self):
        # delete_files imports _recycle_file_powershell inside the function
        # body, so the patch target must be engine.staging, not engine.actions.
        # If this ever stops intercepting, the suite would recycle real files.
        keep = self.write("keep.jpg")
        dupe = self.write("dupe.jpg")
        with patch(_RECYCLE) as recycle:
            delete_files([{"keep": keep, "duplicates": [dupe]}])
        self.assertEqual(recycle.call_count, 1)
        self.assertTrue(os.path.exists(dupe),
                        "mocked recycle must leave the file on disk")


if __name__ == "__main__":
    unittest.main()

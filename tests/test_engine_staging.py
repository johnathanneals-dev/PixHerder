"""
Unit tests for engine/staging.py.

Covers Mimir s-39 finding T-1. Staging is the OneDrive safety layer: files are
copied out to a local working directory so scanning never fights the sync
client, and `sync_back_deletions` later mirrors the user's cleanup decisions
back onto the originals. That last function deletes files in the user's real
photo library, so its skip/delete rule is pinned precisely.

CI-safe by construction:
  * `_recycle_file_powershell` is patched in every test that can reach it.
    Nothing here may recycle a real file. Asserted in TestCiSafety.
  * `SCANS_DIR` and `SYSTEM_RECOVERY_DIR` are redirected to temp dirs, so
    manifests never land in the repo.
  * robocopy is never invoked — the Python fallback path is driven directly.
"""

import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.staging import (
    _build_manifest,
    _stage_with_python,
    cleanup_staging,
    count_files_for_staging,
    get_staging_dir,
    is_onedrive_path,
    is_onedrive_running,
    load_manifest,
    manifest_path_for,
    recycle_staging,
    start_staging,
    staged_to_original,
    sync_back_deletions,
)

_RECYCLE = "engine.staging._recycle_file_powershell"


class _StagingTestCase(unittest.TestCase):
    """Temp workspace with scans/ and recovery redirected out of the repo."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

        self.source = os.path.join(self.tmp, "source")
        self.staging = os.path.join(self.tmp, "staging")
        os.makedirs(self.source)

        self.scans = Path(self.tmp) / "scans"
        self.scans.mkdir()
        for target, value in (
            ("engine.staging.SCANS_DIR", self.scans),
            ("engine.config.SYSTEM_RECOVERY_DIR", Path(self.tmp) / "_recovery"),
        ):
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)

    def write(self, relpath, content=b"img", parent=None):
        p = os.path.join(parent or self.source, relpath)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(content)
        return p


class TestIsOnedrivePath(unittest.TestCase):
    """Detects whether a folder is sync-managed."""

    def test_path_containing_onedrive_is_detected(self):
        self.assertTrue(is_onedrive_path(r"C:\Users\me\OneDrive\Pictures"))

    def test_detection_is_case_insensitive(self):
        self.assertTrue(is_onedrive_path(r"C:\Users\me\onedrive\Pictures"))

    def test_plain_local_path_is_not_onedrive(self):
        with patch.dict(os.environ, {"OneDrive": "", "OneDriveConsumer": "",
                                     "OneDriveCommercial": ""}, clear=False):
            self.assertFalse(is_onedrive_path(r"C:\Photos\2019"))

    def test_path_under_the_onedrive_env_var_is_detected(self):
        with patch.dict(os.environ, {"OneDrive": r"D:\Synced"}, clear=False):
            self.assertTrue(is_onedrive_path(r"D:\Synced\Pictures\trip"))

    def test_sibling_prefix_collision_is_correctly_rejected(self):
        # Fixed: Adj-5 added os.sep boundary check to the env-var branch,
        # matching the pattern in _is_recyclable_dir (S-1, bb9fbf9).
        # D:\SyncedBackup is a sibling of D:\Synced, not a child.
        with patch.dict(os.environ, {"OneDrive": r"D:\Synced",
                                     "OneDriveConsumer": "",
                                     "OneDriveCommercial": ""}, clear=False):
            self.assertFalse(is_onedrive_path(r"D:\SyncedBackup\Pictures"))

    def test_unrelated_root_is_correctly_rejected(self):
        # The guard does work when there is no shared prefix — this is what
        # makes the case above a boundary bug rather than a dead branch.
        with patch.dict(os.environ, {"OneDrive": r"D:\Synced",
                                     "OneDriveConsumer": "",
                                     "OneDriveCommercial": ""}, clear=False):
            self.assertFalse(is_onedrive_path(r"E:\Elsewhere\Pictures"))


class TestIsOnedriveRunning(unittest.TestCase):
    """Process check — subprocess is always mocked."""

    def test_reports_running_when_tasklist_lists_the_process(self):
        with patch("engine.staging.subprocess.run",
                   return_value=MagicMock(stdout="OneDrive.exe  1234 Console")):
            self.assertTrue(is_onedrive_running())

    def test_reports_not_running_when_absent_from_tasklist(self):
        with patch("engine.staging.subprocess.run",
                   return_value=MagicMock(stdout="INFO: no tasks are running")):
            self.assertFalse(is_onedrive_running())

    def test_subprocess_failure_degrades_to_false(self):
        with patch("engine.staging.subprocess.run", side_effect=OSError("nope")):
            self.assertFalse(is_onedrive_running())


class TestStagingPathDerivation(_StagingTestCase):
    """Staging dir and manifest path are derived, not stored — so they must be stable."""

    def test_same_source_yields_the_same_staging_dir(self):
        base = os.path.join(self.tmp, "base")
        self.assertEqual(get_staging_dir(self.source, base),
                         get_staging_dir(self.source, base))

    def test_different_sources_yield_different_staging_dirs(self):
        base = os.path.join(self.tmp, "base")
        self.assertNotEqual(get_staging_dir(r"C:\a", base),
                            get_staging_dir(r"C:\b", base))

    def test_derivation_is_case_insensitive(self):
        base = os.path.join(self.tmp, "base")
        self.assertEqual(get_staging_dir(r"C:\Photos\Trip", base),
                         get_staging_dir(r"c:\photos\trip", base))

    def test_trailing_separator_does_not_change_the_result(self):
        base = os.path.join(self.tmp, "base")
        self.assertEqual(get_staging_dir(r"C:\Photos\Trip", base),
                         get_staging_dir("C:\\Photos\\Trip\\", base))

    def test_staging_dir_is_nested_under_the_given_base(self):
        base = os.path.join(self.tmp, "base")
        self.assertTrue(get_staging_dir(self.source, base).startswith(base))

    def test_manifest_path_is_stable_and_lives_under_scans(self):
        first = manifest_path_for(self.source)
        self.assertEqual(first, manifest_path_for(self.source))
        self.assertEqual(first.parent, self.scans)

    def test_manifest_path_differs_per_source(self):
        self.assertNotEqual(manifest_path_for(r"C:\a"), manifest_path_for(r"C:\b"))


class TestCountFilesForStaging(_StagingTestCase):
    """Pre-flight count that drives the progress bar."""

    def test_counts_images_and_sums_their_bytes(self):
        self.write("a.jpg", b"12345")
        self.write("b.png", b"123")
        count, total = count_files_for_staging(self.source)
        self.assertEqual(count, 2)
        self.assertEqual(total, 8)

    def test_non_image_files_are_ignored(self):
        self.write("a.jpg", b"12345")
        self.write("notes.txt", b"ignore me")
        self.write("video.mp4", b"ignore me too")
        self.assertEqual(count_files_for_staging(self.source)[0], 1)

    def test_extension_matching_is_case_insensitive(self):
        self.write("SHOUTY.JPG", b"12345")
        self.assertEqual(count_files_for_staging(self.source)[0], 1)

    def test_subdirectories_are_included(self):
        self.write(os.path.join("2019", "trip", "a.jpg"))
        self.write(os.path.join("2020", "b.jpg"))
        self.assertEqual(count_files_for_staging(self.source)[0], 2)

    def test_custom_extension_set_is_respected(self):
        self.write("a.jpg")
        self.write("b.png")
        self.assertEqual(
            count_files_for_staging(self.source, extensions={".png"})[0], 1)

    def test_empty_directory_counts_zero(self):
        self.assertEqual(count_files_for_staging(self.source), (0, 0))


class TestStageWithPython(_StagingTestCase):
    """The shutil fallback used when robocopy is unavailable."""

    def _stage(self, **kw):
        total_files, total_bytes = count_files_for_staging(self.source)
        return _stage_with_python(
            self.source, self.staging,
            kw.pop("extensions", None) or {".jpg", ".png"},
            total_files, total_bytes,
            kw.pop("progress_cb", None), kw.pop("cancel_event", None))

    def test_copies_images_into_staging(self):
        self.write("a.jpg", b"content")
        result = self._stage()
        self.assertEqual(result["copied"], 1)
        self.assertFalse(result["cancelled"])
        with open(os.path.join(self.staging, "a.jpg"), "rb") as f:
            self.assertEqual(f.read(), b"content")

    def test_originals_are_left_in_place(self):
        # Staging is a copy, never a move — the whole safety model depends on it.
        src = self.write("a.jpg", b"content")
        self._stage()
        self.assertTrue(os.path.exists(src))

    def test_subfolder_structure_is_preserved(self):
        self.write(os.path.join("2019", "trip", "a.jpg"))
        self._stage()
        self.assertTrue(os.path.exists(
            os.path.join(self.staging, "2019", "trip", "a.jpg")))

    def test_non_matching_extensions_are_not_copied(self):
        self.write("a.jpg")
        self.write("notes.txt")
        self._stage()
        self.assertFalse(os.path.exists(os.path.join(self.staging, "notes.txt")))

    def test_restaging_skips_files_already_present_and_unchanged(self):
        self.write("a.jpg", b"content")
        self.assertEqual(self._stage()["copied"], 1)
        second = self._stage()
        self.assertEqual(second["copied"], 0)
        self.assertEqual(second["skipped"], 1)

    def test_changed_source_is_recopied(self):
        p = self.write("a.jpg", b"original")
        self._stage()
        with open(p, "wb") as f:
            f.write(b"a much longer replacement body")
        os.utime(p, (100_000, 100_000))
        self.assertEqual(self._stage()["copied"], 1)

    def test_copy_failure_is_counted_and_does_not_abort(self):
        self.write("bad.jpg")
        self.write("good.jpg")
        real_copy = __import__("shutil").copy2

        def flaky(src, dst, *a, **kw):
            if src.endswith("bad.jpg"):
                raise OSError("locked by another process")
            return real_copy(src, dst, *a, **kw)

        with patch("engine.staging.shutil.copy2", side_effect=flaky):
            result = self._stage()

        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["copied"], 1)
        self.assertEqual(len(result["errors"]), 1)

    def test_cancel_event_stops_staging_and_flags_cancelled(self):
        self.write("a.jpg")
        ev = threading.Event()
        ev.set()
        result = self._stage(cancel_event=ev)
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["copied"], 0)

    def test_progress_callback_reports_the_staging_stage(self):
        self.write("a.jpg")
        seen = []
        self._stage(progress_cb=lambda c, t, b, bt, s: seen.append(s))
        self.assertIn("staging", seen)
        self.assertEqual(seen[-1], "done")

    def test_reports_the_manifest_path_after_staging(self):
        self.write("a.jpg")
        result = self._stage()
        self.assertIsNotNone(result["manifest_path"])
        self.assertTrue(os.path.exists(result["manifest_path"]))


class TestStartStaging(_StagingTestCase):
    """Orchestration: robocopy first, Python fallback, unwritable destination."""

    def test_falls_back_to_python_when_robocopy_is_missing(self):
        self.write("a.jpg", b"content")
        with patch("engine.staging._stage_with_robocopy",
                   side_effect=FileNotFoundError("robocopy")):
            result = start_staging(self.source, self.staging)
        self.assertEqual(result["copied"], 1)
        self.assertTrue(os.path.exists(os.path.join(self.staging, "a.jpg")))

    def test_uses_robocopy_when_available(self):
        self.write("a.jpg")
        sentinel = {"copied": 99, "errors": []}
        with patch("engine.staging._stage_with_robocopy",
                   return_value=sentinel) as robo:
            result = start_staging(self.source, self.staging)
        robo.assert_called_once()
        self.assertEqual(result, sentinel)

    def test_unwritable_staging_dir_returns_a_actionable_error(self):
        # Controlled Folder Access is a real and common failure here, so the
        # message must name it rather than surfacing a bare OSError.
        with patch("engine.staging.os.makedirs",
                   side_effect=OSError("access denied")):
            result = start_staging(self.source, self.staging)
        self.assertEqual(result["copied"], 0)
        self.assertIsNone(result["manifest_path"])
        self.assertIn("Controlled Folder Access", result["errors"][0])


class TestManifest(_StagingTestCase):
    """Manifests link a staging dir back to its source."""

    def test_manifest_records_source_staging_and_counts(self):
        os.makedirs(self.staging)
        with open(os.path.join(self.staging, "a.jpg"), "wb") as f:
            f.write(b"12345")

        mpath = _build_manifest(self.source, self.staging)
        self.assertIsNotNone(mpath)

        data = json.loads(Path(mpath).read_text(encoding="utf-8"))
        self.assertEqual(data["source_dir"], os.path.normpath(self.source))
        self.assertEqual(data["staging_dir"], os.path.normpath(self.staging))
        self.assertEqual(data["file_count"], 1)
        self.assertEqual(data["bytes_total"], 5)
        self.assertIn("created", data)

    def test_no_manifest_is_written_for_an_empty_staging_dir(self):
        # A zero-file manifest would advertise a session that never happened
        # and strand the UI on a stale artifact.
        os.makedirs(self.staging)
        self.assertIsNone(_build_manifest(self.source, self.staging))
        self.assertFalse(manifest_path_for(self.source).exists())

    def test_load_manifest_round_trips_what_build_wrote(self):
        os.makedirs(self.staging)
        with open(os.path.join(self.staging, "a.jpg"), "wb") as f:
            f.write(b"x")
        _build_manifest(self.source, self.staging)

        loaded = load_manifest(self.source)
        self.assertEqual(loaded["staging_dir"], os.path.normpath(self.staging))

    def test_load_manifest_returns_none_when_absent(self):
        self.assertIsNone(load_manifest(self.source))

    def test_load_manifest_returns_none_when_corrupt(self):
        manifest_path_for(self.source).write_text("{not json", encoding="utf-8")
        self.assertIsNone(load_manifest(self.source))


class TestStagedToOriginal(unittest.TestCase):
    """Mapping a staged path back to the user's real file."""

    def test_maps_a_staged_path_onto_the_source_tree(self):
        self.assertEqual(
            os.path.normpath(staged_to_original(
                r"C:\stage\abc\2019\a.jpg", r"C:\stage\abc", r"D:\Photos")),
            os.path.normpath(r"D:\Photos\2019\a.jpg"))

    def test_file_at_the_staging_root_maps_to_the_source_root(self):
        self.assertEqual(
            os.path.normpath(staged_to_original(
                r"C:\stage\abc\a.jpg", r"C:\stage\abc", r"D:\Photos")),
            os.path.normpath(r"D:\Photos\a.jpg"))

    def test_trailing_separators_are_tolerated(self):
        self.assertEqual(
            os.path.normpath(staged_to_original(
                "C:\\stage\\abc\\a.jpg", "C:\\stage\\abc\\", "D:\\Photos\\")),
            os.path.normpath(r"D:\Photos\a.jpg"))


class TestSyncBackDeletions(_StagingTestCase):
    """Mirrors staging-side deletions onto the user's originals. Always mocked."""

    def _prepare(self, names):
        os.makedirs(self.staging, exist_ok=True)
        for n in names:
            self.write(n)
            dst = os.path.join(self.staging, n)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(b"img")

    def test_original_is_kept_when_its_staged_copy_still_exists(self):
        self._prepare(["a.jpg"])
        with patch(_RECYCLE) as recycle:
            result = sync_back_deletions(self.staging, self.source)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["deleted"], 0)
        recycle.assert_not_called()

    def test_original_is_recycled_when_its_staged_copy_was_removed(self):
        self._prepare(["a.jpg"])
        os.remove(os.path.join(self.staging, "a.jpg"))
        with patch(_RECYCLE) as recycle:
            result = sync_back_deletions(self.staging, self.source)
        self.assertEqual(result["deleted"], 1)
        self.assertEqual(recycle.call_count, 1)
        self.assertTrue(str(recycle.call_args.args[0]).endswith("a.jpg"))

    def test_only_the_removed_file_is_recycled(self):
        self._prepare(["keep.jpg", "gone.jpg"])
        os.remove(os.path.join(self.staging, "gone.jpg"))
        with patch(_RECYCLE) as recycle:
            result = sync_back_deletions(self.staging, self.source)
        self.assertEqual(result["deleted"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertTrue(str(recycle.call_args.args[0]).endswith("gone.jpg"))

    def test_nested_paths_are_matched_by_relative_path(self):
        self._prepare([os.path.join("2019", "trip", "a.jpg")])
        os.remove(os.path.join(self.staging, "2019", "trip", "a.jpg"))
        with patch(_RECYCLE) as recycle:
            result = sync_back_deletions(self.staging, self.source)
        self.assertEqual(result["deleted"], 1)

    def test_recycle_failure_is_counted_and_the_walk_continues(self):
        self._prepare(["a.jpg", "b.jpg"])
        os.remove(os.path.join(self.staging, "a.jpg"))
        os.remove(os.path.join(self.staging, "b.jpg"))

        def flaky(path, *a, **kw):
            if str(path).endswith("a.jpg"):
                raise RuntimeError("recycle bin unavailable")

        with patch(_RECYCLE, side_effect=flaky):
            result = sync_back_deletions(self.staging, self.source)

        self.assertEqual(result["deleted"], 1)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(len(result["error_details"]), 1)

    def test_cancel_event_stops_before_any_recycling(self):
        self._prepare(["a.jpg"])
        os.remove(os.path.join(self.staging, "a.jpg"))
        ev = threading.Event()
        ev.set()
        with patch(_RECYCLE) as recycle:
            sync_back_deletions(self.staging, self.source, cancel_event=ev)
        recycle.assert_not_called()

    def test_reports_the_total_number_of_originals_examined(self):
        self._prepare(["a.jpg", "b.jpg"])
        with patch(_RECYCLE):
            self.assertEqual(
                sync_back_deletions(self.staging, self.source)["total"], 2)


class TestCleanupStaging(_StagingTestCase):
    """Removing the staging tree."""

    def test_removes_the_directory_tree(self):
        os.makedirs(os.path.join(self.staging, "nested"))
        with open(os.path.join(self.staging, "nested", "a.jpg"), "wb") as f:
            f.write(b"x")
        self.assertEqual(cleanup_staging(self.staging)["status"], "cleaned")
        self.assertFalse(os.path.exists(self.staging))

    def test_read_only_files_do_not_block_cleanup(self):
        import stat as stat_mod
        os.makedirs(self.staging)
        p = os.path.join(self.staging, "locked.jpg")
        with open(p, "wb") as f:
            f.write(b"x")
        os.chmod(p, stat_mod.S_IREAD)
        try:
            self.assertEqual(cleanup_staging(self.staging)["status"], "cleaned")
            self.assertFalse(os.path.exists(self.staging))
        finally:
            if os.path.exists(p):
                os.chmod(p, stat_mod.S_IWRITE | stat_mod.S_IREAD)

    def test_failure_is_reported_rather_than_raised(self):
        os.makedirs(self.staging)
        with patch("engine.staging.shutil.rmtree", side_effect=OSError("in use")):
            result = cleanup_staging(self.staging)
        self.assertEqual(result["status"], "error")
        self.assertIn("in use", result["error"])


class TestRecycleStaging(_StagingTestCase):
    """Emptying a staging workspace to the Recycle Bin. Always mocked."""

    def test_recycles_every_file_and_removes_the_tree(self):
        os.makedirs(os.path.join(self.staging, "nested"))
        for rel in ("a.jpg", os.path.join("nested", "b.jpg")):
            with open(os.path.join(self.staging, rel), "wb") as f:
                f.write(b"x")

        with patch(_RECYCLE) as recycle:
            result = recycle_staging(self.staging)

        self.assertEqual(result["status"], "recycled")
        self.assertEqual(result["files_recycled"], 2)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(recycle.call_count, 2)
        self.assertFalse(os.path.exists(self.staging))

    def test_missing_directory_reports_an_error(self):
        with patch(_RECYCLE) as recycle:
            result = recycle_staging(os.path.join(self.tmp, "nope"))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "Staging directory not found")
        recycle.assert_not_called()

    def test_empty_directory_is_removed_without_recycling_anything(self):
        os.makedirs(self.staging)
        with patch(_RECYCLE) as recycle:
            result = recycle_staging(self.staging)
        self.assertEqual(result["files_recycled"], 0)
        recycle.assert_not_called()
        self.assertFalse(os.path.exists(self.staging))

    def test_per_file_failure_is_counted_and_the_rest_continue(self):
        os.makedirs(self.staging)
        for rel in ("a.jpg", "b.jpg"):
            with open(os.path.join(self.staging, rel), "wb") as f:
                f.write(b"x")

        def flaky(path, *a, **kw):
            if str(path).endswith("a.jpg"):
                raise RuntimeError("denied")

        with patch(_RECYCLE, side_effect=flaky):
            result = recycle_staging(self.staging)

        self.assertEqual(result["files_recycled"], 1)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(len(result["error_details"]), 1)

    def test_progress_callback_is_invoked(self):
        os.makedirs(self.staging)
        with open(os.path.join(self.staging, "a.jpg"), "wb") as f:
            f.write(b"x")
        seen = []
        with patch(_RECYCLE):
            recycle_staging(self.staging, progress_cb=lambda c, t: seen.append((c, t)))
        self.assertEqual(seen, [(1, 1)])


class TestCiSafety(_StagingTestCase):
    """The safety rails this file depends on are real, not assumed."""

    def test_patching_the_recycler_leaves_files_on_disk(self):
        os.makedirs(self.staging)
        p = os.path.join(self.staging, "a.jpg")
        with open(p, "wb") as f:
            f.write(b"x")
        with patch(_RECYCLE) as recycle:
            recycle_staging(self.staging)
        self.assertEqual(recycle.call_count, 1)

    def test_manifests_are_written_to_the_temp_scans_dir_not_the_repo(self):
        self.assertEqual(manifest_path_for(self.source).parent, self.scans)
        repo_scans = Path(PROJECT_ROOT) / "scans"
        self.assertNotEqual(manifest_path_for(self.source).parent, repo_scans)


if __name__ == "__main__":
    unittest.main()

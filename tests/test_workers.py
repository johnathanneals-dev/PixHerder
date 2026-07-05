"""Unit tests for web.workers.WorkerManager."""

import os
import sys
import threading
import unittest
from unittest.mock import patch, MagicMock

# Ensure project root is on sys.path so `web.workers` resolves.
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from web.workers import WorkerManager, worker_manager
import web.workers as workers_mod


class TestWorkerManagerInit(unittest.TestCase):
    """WorkerManager initializes with all threads None and progress dicts idle."""

    def setUp(self):
        self.wm = WorkerManager()

    # -- threads --

    def test_all_threads_none(self):
        thread_names = [
            "scan_thread", "action_thread", "oddball_thread",
            "staging_thread", "syncback_thread", "restore_thread",
        ]
        for name in thread_names:
            self.assertIsNone(
                getattr(self.wm, name),
                f"{name} should be None on init",
            )

    # -- cancel events --

    def test_cancel_events_are_threading_events(self):
        event_names = [
            "scan_cancel", "action_cancel", "oddball_cancel",
            "staging_cancel", "syncback_cancel",
        ]
        for name in event_names:
            evt = getattr(self.wm, name)
            self.assertIsInstance(evt, threading.Event, f"{name} not an Event")

    def test_cancel_events_not_set_on_init(self):
        event_names = [
            "scan_cancel", "action_cancel", "oddball_cancel",
            "staging_cancel", "syncback_cancel",
        ]
        for name in event_names:
            self.assertFalse(
                getattr(self.wm, name).is_set(),
                f"{name} should not be set on init",
            )

    # -- progress dicts --

    def test_all_progress_dicts_idle(self):
        progress_names = [
            "scan_progress", "action_progress", "oddball_progress",
            "staging_progress", "syncback_progress", "restore_progress",
        ]
        for name in progress_names:
            d = getattr(self.wm, name)
            self.assertIsInstance(d, dict, f"{name} not a dict")
            self.assertEqual(
                d["status"], "idle",
                f"{name}['status'] should be 'idle' on init",
            )

    def test_scan_progress_initial_keys(self):
        expected = {
            "status": "idle", "stage": "", "current": 0, "total": 0,
            "elapsed": 0, "errors": 0, "message": "", "result_file": None,
        }
        self.assertEqual(self.wm.scan_progress, expected)

    def test_action_progress_initial_keys(self):
        expected = {
            "status": "idle", "current": 0, "total": 0, "result": None,
        }
        self.assertEqual(self.wm.action_progress, expected)

    def test_oddball_progress_initial_keys(self):
        expected = {
            "status": "idle", "current": 0, "total": 0, "result": None,
        }
        self.assertEqual(self.wm.oddball_progress, expected)

    def test_staging_progress_initial_keys(self):
        expected = {
            "status": "idle", "current": 0, "total": 0,
            "bytes_copied": 0, "bytes_total": 0,
            "copied": 0, "skipped": 0, "failed": 0,
            "message": "", "staging_dir": None,
            "source_dir": None, "manifest_path": None,
        }
        self.assertEqual(self.wm.staging_progress, expected)

    def test_syncback_progress_initial_keys(self):
        expected = {
            "status": "idle", "current": 0, "total": 0,
            "deleted": 0, "errors": 0, "message": "",
        }
        self.assertEqual(self.wm.syncback_progress, expected)

    def test_restore_progress_initial_keys(self):
        expected = {
            "status": "idle", "current": 0, "total": 0,
            "copied": 0, "skipped": 0, "errors": 0,
            "message": "", "phase": "",
        }
        self.assertEqual(self.wm.restore_progress, expected)

    def test_no_restore_cancel_event(self):
        """restore has no cancel event -- only 5 cancel events exist."""
        self.assertFalse(hasattr(self.wm, "restore_cancel"))


class TestResetAllProgress(unittest.TestCase):
    """reset_all_progress() restores all dicts to idle after mutation."""

    def setUp(self):
        self.wm = WorkerManager()

    def _dirty_all(self):
        """Mutate every progress dict so reset has something to undo."""
        self.wm.scan_progress.update({
            "status": "running", "stage": "md5", "current": 42,
            "total": 100, "elapsed": 12.5, "errors": 3,
            "message": "hashing...", "result_file": "scan_123.json",
        })
        self.wm.action_progress.update({
            "status": "complete", "current": 10, "total": 10,
            "result": {"moved": 5},
        })
        self.wm.oddball_progress.update({
            "status": "error", "current": 7, "total": 20,
            "result": {"error": "boom"},
        })
        self.wm.staging_progress.update({
            "status": "running", "current": 50, "total": 200,
            "bytes_copied": 1024, "bytes_total": 4096,
            "copied": 50, "skipped": 2, "failed": 1,
            "message": "copying", "staging_dir": "C:\\tmp\\stage",
            "source_dir": "D:\\photos", "manifest_path": "m.json",
        })
        self.wm.syncback_progress.update({
            "status": "complete", "current": 30, "total": 30,
            "deleted": 25, "errors": 1, "message": "done",
        })
        self.wm.restore_progress.update({
            "status": "running", "current": 15, "total": 100,
            "copied": 10, "skipped": 3, "errors": 2,
            "message": "restoring", "phase": "cleanup",
        })

    @patch("web.workers.SCANS_DIR", new_callable=lambda: MagicMock())
    def test_reset_restores_scan_progress(self, mock_scans_dir):
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_scans_dir.__truediv__ = MagicMock(return_value=mock_path)

        self._dirty_all()
        self.wm.reset_all_progress()

        self.assertEqual(self.wm.scan_progress["status"], "idle")
        self.assertEqual(self.wm.scan_progress["current"], 0)
        self.assertEqual(self.wm.scan_progress["total"], 0)
        self.assertEqual(self.wm.scan_progress["elapsed"], 0)
        self.assertEqual(self.wm.scan_progress["errors"], 0)
        self.assertEqual(self.wm.scan_progress["stage"], "")
        self.assertEqual(self.wm.scan_progress["message"], "")
        self.assertIsNone(self.wm.scan_progress["result_file"])

    @patch("web.workers.SCANS_DIR", new_callable=lambda: MagicMock())
    def test_reset_restores_action_progress(self, mock_scans_dir):
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_scans_dir.__truediv__ = MagicMock(return_value=mock_path)

        self._dirty_all()
        self.wm.reset_all_progress()

        self.assertEqual(self.wm.action_progress["status"], "idle")
        self.assertEqual(self.wm.action_progress["current"], 0)
        self.assertEqual(self.wm.action_progress["total"], 0)
        self.assertIsNone(self.wm.action_progress["result"])

    @patch("web.workers.SCANS_DIR", new_callable=lambda: MagicMock())
    def test_reset_restores_oddball_progress(self, mock_scans_dir):
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_scans_dir.__truediv__ = MagicMock(return_value=mock_path)

        self._dirty_all()
        self.wm.reset_all_progress()

        self.assertEqual(self.wm.oddball_progress["status"], "idle")
        self.assertEqual(self.wm.oddball_progress["current"], 0)
        self.assertIsNone(self.wm.oddball_progress["result"])

    @patch("web.workers.SCANS_DIR", new_callable=lambda: MagicMock())
    def test_reset_restores_staging_progress(self, mock_scans_dir):
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_scans_dir.__truediv__ = MagicMock(return_value=mock_path)

        self._dirty_all()
        self.wm.reset_all_progress()

        p = self.wm.staging_progress
        self.assertEqual(p["status"], "idle")
        self.assertEqual(p["current"], 0)
        self.assertEqual(p["bytes_copied"], 0)
        self.assertEqual(p["bytes_total"], 0)
        self.assertEqual(p["copied"], 0)
        self.assertEqual(p["skipped"], 0)
        self.assertEqual(p["failed"], 0)
        self.assertIsNone(p["staging_dir"])
        self.assertIsNone(p["source_dir"])
        self.assertIsNone(p["manifest_path"])

    @patch("web.workers.SCANS_DIR", new_callable=lambda: MagicMock())
    def test_reset_restores_syncback_progress(self, mock_scans_dir):
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_scans_dir.__truediv__ = MagicMock(return_value=mock_path)

        self._dirty_all()
        self.wm.reset_all_progress()

        p = self.wm.syncback_progress
        self.assertEqual(p["status"], "idle")
        self.assertEqual(p["deleted"], 0)
        self.assertEqual(p["errors"], 0)
        self.assertEqual(p["message"], "")

    @patch("web.workers.SCANS_DIR", new_callable=lambda: MagicMock())
    def test_reset_restores_restore_progress(self, mock_scans_dir):
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_scans_dir.__truediv__ = MagicMock(return_value=mock_path)

        self._dirty_all()
        self.wm.reset_all_progress()

        p = self.wm.restore_progress
        self.assertEqual(p["status"], "idle")
        self.assertEqual(p["copied"], 0)
        self.assertEqual(p["skipped"], 0)
        self.assertEqual(p["errors"], 0)
        self.assertEqual(p["phase"], "")

    @patch("web.workers.SCANS_DIR", new_callable=lambda: MagicMock())
    def test_reset_deletes_source_dupes_json_when_present(self, mock_scans_dir):
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_scans_dir.__truediv__ = MagicMock(return_value=mock_path)

        self.wm.reset_all_progress()
        mock_path.unlink.assert_called_once()

    @patch("web.workers.SCANS_DIR", new_callable=lambda: MagicMock())
    def test_reset_skips_unlink_when_no_source_dupes_json(self, mock_scans_dir):
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_scans_dir.__truediv__ = MagicMock(return_value=mock_path)

        self.wm.reset_all_progress()
        mock_path.unlink.assert_not_called()

    @patch("web.workers.SCANS_DIR", new_callable=lambda: MagicMock())
    def test_reset_preserves_dict_identity(self, mock_scans_dir):
        """reset_all_progress uses .update(), so the dict object must not change."""
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_scans_dir.__truediv__ = MagicMock(return_value=mock_path)

        originals = {
            name: getattr(self.wm, name)
            for name in [
                "scan_progress", "action_progress", "oddball_progress",
                "staging_progress", "syncback_progress", "restore_progress",
            ]
        }
        self._dirty_all()
        self.wm.reset_all_progress()

        for name, orig_dict in originals.items():
            self.assertIs(
                getattr(self.wm, name), orig_dict,
                f"{name} dict object replaced instead of updated in-place",
            )


class TestModuleLevelAliases(unittest.TestCase):
    """Module-level aliases point to the same objects as the singleton instance."""

    def test_progress_aliases_are_same_object(self):
        aliases = {
            "scan_progress": workers_mod.scan_progress,
            "action_progress": workers_mod.action_progress,
            "oddball_progress": workers_mod.oddball_progress,
            "staging_progress": workers_mod.staging_progress,
            "syncback_progress": workers_mod.syncback_progress,
            "restore_progress": workers_mod.restore_progress,
        }
        for name, alias in aliases.items():
            self.assertIs(
                alias, getattr(worker_manager, name),
                f"module-level {name} is not the same object as worker_manager.{name}",
            )

    def test_cancel_aliases_are_same_object(self):
        aliases = {
            "scan_cancel": workers_mod.scan_cancel,
            "action_cancel": workers_mod.action_cancel,
            "oddball_cancel": workers_mod.oddball_cancel,
            "staging_cancel": workers_mod.staging_cancel,
            "syncback_cancel": workers_mod.syncback_cancel,
        }
        for name, alias in aliases.items():
            self.assertIs(
                alias, getattr(worker_manager, name),
                f"module-level {name} is not the same object as worker_manager.{name}",
            )

    def test_mutation_via_alias_visible_on_instance(self):
        """Mutating the module-level alias dict is visible via the instance attr."""
        workers_mod.scan_progress["status"] = "test_sentinel"
        self.assertEqual(worker_manager.scan_progress["status"], "test_sentinel")
        # Clean up
        worker_manager.scan_progress["status"] = "idle"

    def test_mutation_via_instance_visible_on_alias(self):
        """Mutating via instance attr is visible via the module-level alias."""
        worker_manager.action_progress["status"] = "test_sentinel"
        self.assertEqual(workers_mod.action_progress["status"], "test_sentinel")
        # Clean up
        worker_manager.action_progress["status"] = "idle"

    def test_reset_alias_points_to_bound_method(self):
        alias = workers_mod._reset_all_progress
        method = worker_manager.reset_all_progress
        # Bound methods are recreated on each attribute access, so compare
        # the underlying function and the instance they are bound to.
        self.assertIs(alias.__func__, method.__func__)
        self.assertIs(alias.__self__, method.__self__)


class TestCancelEvents(unittest.TestCase):
    """Cancel events set/clear correctly."""

    def setUp(self):
        self.wm = WorkerManager()

    def test_set_and_is_set(self):
        for name in ["scan_cancel", "action_cancel", "oddball_cancel",
                      "staging_cancel", "syncback_cancel"]:
            evt = getattr(self.wm, name)
            self.assertFalse(evt.is_set())
            evt.set()
            self.assertTrue(evt.is_set(), f"{name}.set() did not stick")

    def test_clear(self):
        for name in ["scan_cancel", "action_cancel", "oddball_cancel",
                      "staging_cancel", "syncback_cancel"]:
            evt = getattr(self.wm, name)
            evt.set()
            evt.clear()
            self.assertFalse(evt.is_set(), f"{name}.clear() did not reset")

    def test_events_are_independent(self):
        """Setting one cancel event must not affect the others."""
        events = {
            name: getattr(self.wm, name)
            for name in ["scan_cancel", "action_cancel", "oddball_cancel",
                          "staging_cancel", "syncback_cancel"]
        }
        for set_name, set_evt in events.items():
            set_evt.set()
            for other_name, other_evt in events.items():
                if other_name != set_name:
                    self.assertFalse(
                        other_evt.is_set(),
                        f"Setting {set_name} polluted {other_name}",
                    )
            set_evt.clear()

    def test_wait_returns_immediately_when_set(self):
        self.wm.scan_cancel.set()
        result = self.wm.scan_cancel.wait(timeout=0)
        self.assertTrue(result)

    def test_wait_times_out_when_not_set(self):
        result = self.wm.scan_cancel.wait(timeout=0)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()

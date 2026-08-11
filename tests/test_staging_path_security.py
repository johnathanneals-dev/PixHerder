"""
Security tests for destructive staging operations.

Covers Mimir s-39 finding S-1: `handle_staging_recycle_bin` accepted a
client-supplied `staging_dir` from the JSON request body and handed it
straight to `recycle_staging()` — a recursive, destructive operation — with
no path validation.

The guard is `_is_recyclable_dir`, which is deliberately STRICTER than
`_is_allowed_path`: it must not admit the user's source directory. Reading
originals is fine; recycling them is the data-loss case the product exists
to prevent.

CI-safe — `recycle_staging` is always mocked; no file is ever recycled.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_IMG = "web.image_server"
_ROUTES = "web.routes_staging"


class TestIsRecyclableDir(unittest.TestCase):
    """The workspace allowlist gating destructive directory operations."""

    def _settings(self, staging="", dupes="", keepers=""):
        return {
            "staging_dir": staging,
            "move_destination": dupes,
            "keepers_dir": keepers,
        }

    def _guard(self, target, settings, source_dir=""):
        with (
            patch(f"{_IMG}.load_settings", return_value=settings),
            patch(f"{_IMG}.staging_progress", {"source_dir": source_dir}),
        ):
            from web.image_server import _is_recyclable_dir
            return _is_recyclable_dir(target)

    # ---- allowed: the three workspace roots ----

    def test_staging_base_is_recyclable(self):
        with tempfile.TemporaryDirectory() as staging:
            self.assertTrue(
                self._guard(staging, self._settings(staging=staging)))

    def test_subfolder_of_staging_base_is_recyclable(self):
        with tempfile.TemporaryDirectory() as staging:
            sub = os.path.join(staging, "a1b2c3d4e5")
            os.makedirs(sub)
            self.assertTrue(
                self._guard(sub, self._settings(staging=staging)))

    def test_dupes_dir_is_recyclable(self):
        with tempfile.TemporaryDirectory() as dupes:
            self.assertTrue(
                self._guard(dupes, self._settings(dupes=dupes)))

    def test_keepers_dir_is_recyclable(self):
        with tempfile.TemporaryDirectory() as keepers:
            self.assertTrue(
                self._guard(keepers, self._settings(keepers=keepers)))

    # ---- rejected: the data-loss cases ----

    def test_active_source_dir_is_NOT_recyclable(self):
        """The user's original photo folder must never be a recycle target.

        This is the case that makes _is_allowed_path unsuitable here: it
        admits source_dir so images can be served from it.
        """
        with tempfile.TemporaryDirectory() as staging:
            with tempfile.TemporaryDirectory() as source:
                self.assertFalse(
                    self._guard(source, self._settings(staging=staging),
                                source_dir=source))

    def test_unrelated_directory_is_NOT_recyclable(self):
        with tempfile.TemporaryDirectory() as staging:
            with tempfile.TemporaryDirectory() as outside:
                self.assertFalse(
                    self._guard(outside, self._settings(staging=staging)))

    def test_traversal_escape_from_staging_is_NOT_recyclable(self):
        """`<staging>/../<sibling>` must resolve before comparison."""
        with tempfile.TemporaryDirectory() as parent:
            staging = os.path.join(parent, "staging")
            sibling = os.path.join(parent, "important_photos")
            os.makedirs(staging)
            os.makedirs(sibling)
            escape = os.path.join(staging, "..", "important_photos")
            self.assertFalse(
                self._guard(escape, self._settings(staging=staging)))

    def test_sibling_prefix_collision_is_NOT_recyclable(self):
        """`<staging>_backup` must not match a `<staging>` prefix test."""
        with tempfile.TemporaryDirectory() as parent:
            staging = os.path.join(parent, "workspace")
            trap = os.path.join(parent, "workspace_backup")
            os.makedirs(staging)
            os.makedirs(trap)
            self.assertFalse(
                self._guard(trap, self._settings(staging=staging)))

    def test_empty_target_is_NOT_recyclable(self):
        with tempfile.TemporaryDirectory() as staging:
            self.assertFalse(
                self._guard("", self._settings(staging=staging)))

    def test_unconfigured_workspace_admits_nothing(self):
        """Empty settings must fail closed, not open."""
        with tempfile.TemporaryDirectory() as anywhere:
            self.assertFalse(self._guard(anywhere, self._settings()))


class TestRecycleBinRouteRejectsUnvalidatedPaths(unittest.TestCase):
    """handle_staging_recycle_bin must gate the client-supplied staging_dir."""

    def _handler(self, body):
        h = MagicMock()
        h.read_json_body = MagicMock(return_value=body)
        h.send_json = MagicMock()
        h.send_error_json = MagicMock()
        return h

    def test_arbitrary_staging_dir_is_refused_and_nothing_recycled(self):
        with tempfile.TemporaryDirectory() as attacker_target:
            handler = self._handler({"staging_dir": attacker_target})
            with (
                patch(f"{_ROUTES}._is_recyclable_dir", return_value=False),
                patch(f"{_ROUTES}.recycle_staging") as recycle,
                patch(f"{_ROUTES}._log_activity"),
            ):
                from web.routes_staging import handle_staging_recycle_bin
                handle_staging_recycle_bin(handler, MagicMock())

            recycle.assert_not_called()
            handler.send_json.assert_not_called()
            handler.send_error_json.assert_called_once()
            self.assertEqual(handler.send_error_json.call_args[0][1], 403)

    def test_validated_staging_dir_is_recycled(self):
        with tempfile.TemporaryDirectory() as staging:
            handler = self._handler({"staging_dir": staging})
            with (
                patch(f"{_ROUTES}._is_recyclable_dir", return_value=True),
                patch(f"{_ROUTES}.recycle_staging",
                      return_value={"files_recycled": 3, "errors": 0}) as recycle,
                patch(f"{_ROUTES}._log_activity"),
            ):
                from web.routes_staging import handle_staging_recycle_bin
                handle_staging_recycle_bin(handler, MagicMock())

            recycle.assert_called_once_with(staging)
            handler.send_error_json.assert_not_called()

    def test_server_resolved_dupes_folder_is_still_validated(self):
        """`folder: dupes` resolves server-side but still passes the guard."""
        handler = self._handler({"folder": "dupes"})
        with (
            patch(f"{_ROUTES}.load_settings",
                  return_value={"move_destination": "C:\\Windows"}),
            patch(f"{_ROUTES}._is_recyclable_dir", return_value=False),
            patch(f"{_ROUTES}.recycle_staging") as recycle,
            patch(f"{_ROUTES}._log_activity"),
        ):
            from web.routes_staging import handle_staging_recycle_bin
            handle_staging_recycle_bin(handler, MagicMock())

        recycle.assert_not_called()
        handler.send_error_json.assert_called_once()


if __name__ == "__main__":
    unittest.main()

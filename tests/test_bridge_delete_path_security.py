"""
Security tests for the pywebview bridge's destructive delete endpoints.

Covers Sabretooth s-75 finding Adj-2: `bridge.browser_delete_folder` (and its
file-variant sister `bridge.browser_delete`) validated client-supplied paths
with `os.path.normpath`, which collapses `..` lexically but does NOT resolve
junctions/symlinks. A junction inside an allowed workspace dir pointing
OUTSIDE it passes the normpath prefix check, so the allowlist can be escaped.
`os.path.realpath` is the correct primitive, matching `_is_allowed_path` and
`_is_recyclable_dir` in web.image_server.

CI-safe — recycle primitives are always mocked; no file is ever recycled.
Junction tests are Windows-only (the platform PixHerder targets).
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_BRIDGE = "web.bridge"
_STAGING = "engine.staging"


def _make_junction(target, junction):
    """Create an NTFS junction at `junction` pointing to `target`.

    Junctions need no elevation, unlike symlinks. Raises unittest.SkipTest
    where the primitive is unavailable.
    """
    if sys.platform != "win32":
        raise unittest.SkipTest("NTFS junctions are Windows-only")
    try:
        import _winapi
        _winapi.CreateJunction(target, junction)
    except (ImportError, AttributeError, OSError) as e:
        raise unittest.SkipTest(f"cannot create junction: {e}")


class _BridgeDeleteTestCase(unittest.TestCase):
    def _settings(self, dupes="", keepers=""):
        return {"move_destination": dupes, "keepers_dir": keepers}


class TestBrowserDeleteFolder(_BridgeDeleteTestCase):
    """browser_delete_folder must resolve junctions before the allowlist check."""

    def _call(self, target, settings):
        with (
            patch(f"{_BRIDGE}.load_settings", return_value=settings),
            patch(f"{_BRIDGE}._find_staging_subfolder", return_value=None),
            patch(f"{_BRIDGE}.recycle_staging",
                  return_value={"files_recycled": 0, "errors": 0}) as recycle,
            patch(f"{_BRIDGE}._log_activity"),
        ):
            from web.bridge import Api
            result = Api().browser_delete_folder({"path": target})
        return result, recycle

    def test_junction_escaping_dupes_is_refused(self):
        """A junction inside dupes pointing outside it must be denied.

        normpath leaves `<dupes>\\jx` intact, so the prefix check passes;
        realpath resolves it to the victim dir, which is outside the allowlist.
        """
        with tempfile.TemporaryDirectory() as dupes:
            with tempfile.TemporaryDirectory() as victim:
                junction = os.path.join(dupes, "jx")
                _make_junction(victim, junction)

                result, recycle = self._call(
                    junction, self._settings(dupes=dupes))

                self.assertEqual(result, {"error": "Access denied"})
                recycle.assert_not_called()

    def test_real_subfolder_of_dupes_is_deleted(self):
        """The legitimate case must keep working after the fix."""
        with tempfile.TemporaryDirectory() as dupes:
            sub = os.path.join(dupes, "batch_01")
            os.makedirs(sub)

            result, recycle = self._call(sub, self._settings(dupes=dupes))

            self.assertEqual(result.get("status"), "deleted")
            recycle.assert_called_once_with(sub)


class TestBrowserDelete(_BridgeDeleteTestCase):
    """browser_delete (file variant) shares the same allowlist and the same class."""

    def _call(self, target, settings):
        with (
            patch(f"{_BRIDGE}.load_settings", return_value=settings),
            patch(f"{_BRIDGE}._find_staging_subfolder", return_value=None),
            patch(f"{_STAGING}._recycle_file_powershell") as recycle,
            patch(f"{_BRIDGE}._log_activity"),
        ):
            from web.bridge import Api
            result = Api().browser_delete({"path": target})
        return result, recycle

    def test_file_reached_through_junction_is_refused(self):
        """`<dupes>\\jx\\photo.jpg` resolving outside dupes must be denied."""
        with tempfile.TemporaryDirectory() as dupes:
            with tempfile.TemporaryDirectory() as victim:
                victim_file = os.path.join(victim, "photo.jpg")
                with open(victim_file, "w") as f:
                    f.write("originals")
                junction = os.path.join(dupes, "jx")
                _make_junction(victim, junction)

                result, recycle = self._call(
                    os.path.join(junction, "photo.jpg"),
                    self._settings(dupes=dupes))

                self.assertEqual(result, {"error": "Access denied"})
                recycle.assert_not_called()
                self.assertTrue(os.path.isfile(victim_file))

    def test_real_file_inside_dupes_is_deleted(self):
        """The legitimate case must keep working after the fix."""
        with tempfile.TemporaryDirectory() as dupes:
            filepath = os.path.join(dupes, "dupe.jpg")
            with open(filepath, "w") as f:
                f.write("dupe")

            result, recycle = self._call(
                filepath, self._settings(dupes=dupes))

            self.assertEqual(result, {"status": "deleted"})
            recycle.assert_called_once_with(filepath)


if __name__ == "__main__":
    unittest.main()

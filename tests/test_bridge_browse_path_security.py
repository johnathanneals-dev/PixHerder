"""Security tests for the bridge's read-side (enumeration) path gates.

Covers Sabretooth s-76 findings OBS-A and OBS-B -- the read-side twins of
Adj-2. Same primitive gap: normpath collapses `..` lexically but does not
resolve junctions, so a junction escapes both an allowlist (enumerate an
unlisted directory) and a blocklist (enumerate a blocked system directory).
os.path.realpath is the fix, matching the destructive-side Adj-2 change.

- OBS-A: `Api.browse` allowlist (bridge.py) -- junction inside an allowed
  workspace dir pointing outside it must not be enumerable.
- OBS-B: `Api.browse_folders` (bridge.py) + `handle_browse_folders`
  (routes_browser.py) system-dir blocklists -- a junction pointing INTO a
  blocked dir must be denied, not silently followed.

CI-safe -- no enumeration of real system directories occurs (the guard
denies before any listdir). Junction tests are Windows-only.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_BRIDGE = "web.bridge"


def _make_junction(target, junction):
    if sys.platform != "win32":
        raise unittest.SkipTest("NTFS junctions are Windows-only")
    try:
        import _winapi
        _winapi.CreateJunction(target, junction)
    except (ImportError, AttributeError, OSError) as e:
        raise unittest.SkipTest(f"cannot create junction: {e}")


class TestBrowseAllowlist(unittest.TestCase):
    """OBS-A: Api.browse must resolve junctions before its allowlist check."""

    def _browse(self, target, dupes):
        with (
            patch(f"{_BRIDGE}.load_settings",
                  return_value={"staging_dir": "", "move_destination": dupes,
                                "keepers_dir": ""}),
            patch(f"{_BRIDGE}._find_staging_subfolder", return_value=None),
        ):
            from web.bridge import Api
            return Api().browse({"path": target})

    def test_junction_escaping_dupes_is_denied(self):
        with tempfile.TemporaryDirectory() as dupes:
            with tempfile.TemporaryDirectory() as outside:
                with open(os.path.join(outside, "secret.jpg"), "w") as f:
                    f.write("x")
                junction = os.path.join(dupes, "jx")
                _make_junction(outside, junction)

                result = self._browse(junction, dupes)

                self.assertEqual(result.get("error"), "Access denied")

    def test_real_subfolder_of_dupes_is_allowed(self):
        with tempfile.TemporaryDirectory() as dupes:
            sub = os.path.join(dupes, "batch")
            os.makedirs(sub)
            result = self._browse(sub, dupes)
            self.assertNotIn("error", result)


class TestBrowseFoldersBlocklist(unittest.TestCase):
    """OBS-B: Api.browse_folders must resolve junctions before the blocklist."""

    def test_junction_into_windows_is_denied(self):
        windir = os.environ.get("WINDIR", r"C:\Windows")
        if not os.path.isdir(windir):
            self.skipTest("no Windows directory to point at")
        with tempfile.TemporaryDirectory() as parent:
            junction = os.path.join(parent, "peek")
            _make_junction(windir, junction)

            from web.bridge import Api
            result = Api().browse_folders({"path": junction})

            self.assertEqual(result.get("error"), "Access denied")

    def test_ordinary_directory_still_lists(self):
        with tempfile.TemporaryDirectory() as ordinary:
            os.makedirs(os.path.join(ordinary, "child"))
            from web.bridge import Api
            result = Api().browse_folders({"path": ordinary})
            self.assertNotIn("error", result)
            self.assertIn("child", result.get("folders", []))


class TestHandleBrowseFoldersBlocklist(unittest.TestCase):
    """OBS-B: routes_browser.handle_browse_folders shares the blocklist class."""

    def _handler(self):
        h = MagicMock()
        h.send_json = MagicMock()
        h.send_error_json = MagicMock()
        return h

    def test_junction_into_windows_is_denied(self):
        windir = os.environ.get("WINDIR", r"C:\Windows")
        if not os.path.isdir(windir):
            self.skipTest("no Windows directory to point at")
        with tempfile.TemporaryDirectory() as parent:
            junction = os.path.join(parent, "peek")
            _make_junction(windir, junction)

            from web.routes_browser import handle_browse_folders
            handler = self._handler()
            handle_browse_folders(handler, MagicMock(), junction)

            handler.send_json.assert_not_called()
            handler.send_error_json.assert_called_once()
            self.assertEqual(handler.send_error_json.call_args[0][1], 403)

    def test_ordinary_directory_still_lists(self):
        with tempfile.TemporaryDirectory() as ordinary:
            os.makedirs(os.path.join(ordinary, "child"))
            from web.routes_browser import handle_browse_folders
            handler = self._handler()
            handle_browse_folders(handler, MagicMock(), ordinary)

            handler.send_error_json.assert_not_called()
            handler.send_json.assert_called_once()
            payload = handler.send_json.call_args[0][0]
            self.assertIn("child", payload.get("folders", []))


if __name__ == "__main__":
    unittest.main()

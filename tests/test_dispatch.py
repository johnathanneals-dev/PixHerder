"""
Dispatch-table wiring tests for PixHerderHandler.

Verifies that:
1. Every handler function referenced by the dispatch table is callable.
2. do_GET and do_POST route to the correct handler for each API path.

CI-safe — no real HTTP connections; all socket/request machinery is mocked.
"""

import io
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Helper: build a fake PixHerderHandler without a real socket
# ---------------------------------------------------------------------------

def _make_handler(method, path):
    """
    Construct a PixHerderHandler wired to a fake request line.

    The handler's __init__ normally calls handle() which calls do_GET/POST,
    so we bypass __init__ entirely and set up just enough state for the
    dispatch methods to work.
    """
    # Import here so patches applied by individual tests are in effect
    from web.server import PixHerderHandler

    handler = PixHerderHandler.__new__(PixHerderHandler)
    handler.path = path
    handler.command = method
    handler.headers = {"Content-Length": "0"}
    handler.rfile = io.BytesIO(b"")
    handler.wfile = io.BytesIO()
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.client_address = ("127.0.0.1", 9999)
    handler.server = MagicMock()
    handler.request = MagicMock()

    # Stub response helpers so handlers don't crash on socket writes
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.send_error = MagicMock()
    handler.send_json = MagicMock()
    handler.send_error_json = MagicMock()
    handler.read_json_body = MagicMock(return_value={})

    return handler


# ===================================================================
# 1. Callable checks — every handler in every route module exists
# ===================================================================

class TestHandlersAreCallable(unittest.TestCase):
    """Each handler function referenced by the dispatch table must be callable."""

    def test_routes_scan_handlers(self):
        from web import routes_scan
        handlers = [
            "handle_get_scans",
            "handle_check_resume",
            "handle_get_groups",
            "handle_get_settings",
            "handle_scan_start",
            "handle_scan_cancel",
            "handle_save_settings",
            "handle_delete_scan",
        ]
        for name in handlers:
            with self.subTest(handler=name):
                fn = getattr(routes_scan, name, None)
                self.assertIsNotNone(fn, f"routes_scan.{name} does not exist")
                self.assertTrue(callable(fn), f"routes_scan.{name} is not callable")

    def test_routes_actions_handlers(self):
        from web import routes_actions
        handlers = [
            "handle_action_move",
            "handle_action_delete",
            "handle_action_rescue",
            "handle_oddball_run",
            "handle_decisions_save",
            "handle_decisions_load",
        ]
        for name in handlers:
            with self.subTest(handler=name):
                fn = getattr(routes_actions, name, None)
                self.assertIsNotNone(fn, f"routes_actions.{name} does not exist")
                self.assertTrue(callable(fn), f"routes_actions.{name} is not callable")

    def test_routes_staging_handlers(self):
        from web import routes_staging
        handlers = [
            "handle_staging_status",
            "handle_staging_start",
            "handle_staging_cancel",
            "handle_syncback_start",
            "handle_staging_cleanup",
            "handle_staging_reset",
            "handle_staging_recycle_bin",
            "handle_staging_restore",
            "handle_staging_recycle",
            "handle_dupes_purge",
            "handle_dupes_promote",
            "handle_consolidate",
            "handle_onedrive_status",
            "handle_staging_check",
        ]
        for name in handlers:
            with self.subTest(handler=name):
                fn = getattr(routes_staging, name, None)
                self.assertIsNotNone(fn, f"routes_staging.{name} does not exist")
                self.assertTrue(callable(fn), f"routes_staging.{name} is not callable")

    def test_routes_browser_handlers(self):
        from web import routes_browser
        handlers = [
            "handle_browse",
            "handle_browse_folders",
            "handle_browser_delete",
            "handle_browser_delete_folder",
            "handle_open_explorer",
            "handle_open_recycle_bin",
            "handle_move_to_keepers",
        ]
        for name in handlers:
            with self.subTest(handler=name):
                fn = getattr(routes_browser, name, None)
                self.assertIsNotNone(fn, f"routes_browser.{name} does not exist")
                self.assertTrue(callable(fn), f"routes_browser.{name} is not callable")

    def test_image_server_serve_image(self):
        from web import image_server
        fn = getattr(image_server, "serve_image", None)
        self.assertIsNotNone(fn, "image_server.serve_image does not exist")
        self.assertTrue(callable(fn), "image_server.serve_image is not callable")


# ===================================================================
# 2. Dispatch wiring — do_GET routes to the right handler
# ===================================================================

class TestGetDispatch(unittest.TestCase):
    """do_GET dispatches each path to the correct route-module function."""

    @patch("web.routes_scan.handle_get_scans")
    def test_get_scans(self, mock_fn):
        handler = _make_handler("GET", "/api/scans")
        handler.do_GET()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_scan.handle_check_resume")
    def test_get_check_resume(self, mock_fn):
        handler = _make_handler("GET", "/api/scan/check-resume?report=foo")
        handler.do_GET()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_scan.handle_get_groups")
    def test_get_groups(self, mock_fn):
        handler = _make_handler("GET", "/api/groups?report=test.json")
        handler.do_GET()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.server.serve_image")
    def test_get_image(self, mock_fn):
        handler = _make_handler("GET", "/api/image?path=C%3A%2Ftest.jpg")
        handler.do_GET()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_scan.handle_get_settings")
    def test_get_settings(self, mock_fn):
        handler = _make_handler("GET", "/api/settings")
        handler.do_GET()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_staging.handle_staging_status")
    def test_get_staging_status(self, mock_fn):
        handler = _make_handler("GET", "/api/staging/status")
        handler.do_GET()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_browser.handle_browse")
    def test_get_browse(self, mock_fn):
        handler = _make_handler("GET", "/api/browse?path=C%3A%2F&page=2&page_size=25&sort=size")
        handler.do_GET()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_browser.handle_browse_folders")
    def test_get_browse_folders(self, mock_fn):
        handler = _make_handler("GET", "/api/browse-folders?path=C%3A%2F")
        handler.do_GET()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_actions.handle_decisions_load")
    def test_get_decisions_load(self, mock_fn):
        handler = _make_handler("GET", "/api/decisions/load?report=scan_1.json")
        handler.do_GET()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    def test_get_unknown_returns_404(self):
        handler = _make_handler("GET", "/api/nonexistent")
        handler.do_GET()
        handler.send_error.assert_called_once_with(404)


# ===================================================================
# 3. Dispatch wiring — do_POST routes to the right handler
# ===================================================================

class TestPostDispatch(unittest.TestCase):
    """do_POST dispatches each path to the correct route-module function."""

    # --- routes_scan ---

    @patch("web.routes_scan.handle_scan_start")
    def test_post_scan_start(self, mock_fn):
        handler = _make_handler("POST", "/api/scan/start")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_scan.handle_scan_cancel")
    def test_post_scan_cancel(self, mock_fn):
        handler = _make_handler("POST", "/api/scan/cancel")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_scan.handle_save_settings")
    def test_post_settings(self, mock_fn):
        handler = _make_handler("POST", "/api/settings")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_scan.handle_delete_scan")
    def test_post_delete_scan(self, mock_fn):
        handler = _make_handler("POST", "/api/scans/delete")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    # --- routes_actions ---

    @patch("web.routes_actions.handle_action_move")
    def test_post_action_move(self, mock_fn):
        handler = _make_handler("POST", "/api/action/move")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_actions.handle_action_delete")
    def test_post_action_delete(self, mock_fn):
        handler = _make_handler("POST", "/api/action/delete")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_actions.handle_action_rescue")
    def test_post_action_rescue(self, mock_fn):
        handler = _make_handler("POST", "/api/action/rescue")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_actions.handle_oddball_run")
    def test_post_oddball_run(self, mock_fn):
        handler = _make_handler("POST", "/api/oddball/run")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_actions.handle_decisions_save")
    def test_post_decisions_save(self, mock_fn):
        handler = _make_handler("POST", "/api/decisions/save")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    # --- routes_staging ---

    @patch("web.routes_staging.handle_staging_start")
    def test_post_staging_start(self, mock_fn):
        handler = _make_handler("POST", "/api/staging/start")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_staging.handle_staging_cancel")
    def test_post_staging_cancel(self, mock_fn):
        handler = _make_handler("POST", "/api/staging/cancel")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_staging.handle_syncback_start")
    def test_post_syncback(self, mock_fn):
        handler = _make_handler("POST", "/api/staging/syncback")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_staging.handle_staging_cleanup")
    def test_post_staging_cleanup(self, mock_fn):
        handler = _make_handler("POST", "/api/staging/cleanup")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_staging.handle_staging_reset")
    def test_post_staging_reset(self, mock_fn):
        handler = _make_handler("POST", "/api/staging/reset")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_staging.handle_staging_recycle_bin")
    def test_post_staging_recycle_bin(self, mock_fn):
        handler = _make_handler("POST", "/api/staging/recycle-bin")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_staging.handle_staging_restore")
    def test_post_staging_restore(self, mock_fn):
        handler = _make_handler("POST", "/api/staging/restore")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_staging.handle_staging_recycle")
    def test_post_staging_recycle(self, mock_fn):
        handler = _make_handler("POST", "/api/staging/recycle")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_staging.handle_dupes_purge")
    def test_post_dupes_purge(self, mock_fn):
        handler = _make_handler("POST", "/api/dupes/purge")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_staging.handle_dupes_promote")
    def test_post_dupes_promote(self, mock_fn):
        handler = _make_handler("POST", "/api/dupes/promote")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_staging.handle_consolidate")
    def test_post_consolidate(self, mock_fn):
        handler = _make_handler("POST", "/api/consolidate")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_staging.handle_onedrive_status")
    def test_post_onedrive_status(self, mock_fn):
        handler = _make_handler("POST", "/api/onedrive/status")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_staging.handle_staging_check")
    def test_post_staging_check(self, mock_fn):
        handler = _make_handler("POST", "/api/staging/check")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    # --- routes_browser ---

    @patch("web.routes_browser.handle_browser_delete")
    def test_post_browser_delete(self, mock_fn):
        handler = _make_handler("POST", "/api/browser/delete")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_browser.handle_browser_delete_folder")
    def test_post_browser_delete_folder(self, mock_fn):
        handler = _make_handler("POST", "/api/browser/delete-folder")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_browser.handle_open_explorer")
    def test_post_open_explorer(self, mock_fn):
        handler = _make_handler("POST", "/api/browser/open-explorer")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_browser.handle_open_recycle_bin")
    def test_post_open_recycle_bin(self, mock_fn):
        handler = _make_handler("POST", "/api/browser/open-recycle-bin")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    @patch("web.routes_browser.handle_move_to_keepers")
    def test_post_move_to_keepers(self, mock_fn):
        handler = _make_handler("POST", "/api/browser/move-to-keepers")
        handler.do_POST()
        mock_fn.assert_called_once()
        self.assertIs(mock_fn.call_args[0][0], handler)

    def test_post_unknown_returns_404(self):
        handler = _make_handler("POST", "/api/nonexistent")
        handler.do_POST()
        handler.send_error.assert_called_once_with(404)


if __name__ == "__main__":
    unittest.main()

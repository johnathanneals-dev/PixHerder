"""Tests for web.image_server — path validation and image serving."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch, mock_open


# Patch targets (module under test imports these at top level)
_MOD = "web.image_server"


class TestIsAllowedPath(unittest.TestCase):
    """Tests for _is_allowed_path."""

    def _make_settings(self, staging, dupes, keepers):
        return {
            "staging_dir": staging,
            "move_destination": dupes,
            "keepers_dir": keepers,
        }

    # ---- positive cases ----

    def test_path_inside_staging_dir(self):
        with tempfile.TemporaryDirectory() as staging:
            settings = self._make_settings(staging, "", "")
            img = os.path.join(staging, "photo.jpg")
            with (
                patch(f"{_MOD}.load_settings", return_value=settings),
                patch(f"{_MOD}._find_staging_subfolder", return_value=""),
                patch(f"{_MOD}.staging_progress", {"source_dir": ""}),
            ):
                from web.image_server import _is_allowed_path
                self.assertTrue(_is_allowed_path(img))

    def test_path_inside_move_destination(self):
        with tempfile.TemporaryDirectory() as dupes:
            settings = self._make_settings("", dupes, "")
            img = os.path.join(dupes, "subdir", "dup.png")
            with (
                patch(f"{_MOD}.load_settings", return_value=settings),
                patch(f"{_MOD}._find_staging_subfolder", return_value=""),
                patch(f"{_MOD}.staging_progress", {"source_dir": ""}),
                patch("os.path.isdir", return_value=True),
            ):
                from web.image_server import _is_allowed_path
                self.assertTrue(_is_allowed_path(img))

    def test_path_inside_keepers_dir(self):
        with tempfile.TemporaryDirectory() as keepers:
            settings = self._make_settings("", "", keepers)
            img = os.path.join(keepers, "keep.jpg")
            with (
                patch(f"{_MOD}.load_settings", return_value=settings),
                patch(f"{_MOD}._find_staging_subfolder", return_value=""),
                patch(f"{_MOD}.staging_progress", {"source_dir": ""}),
            ):
                from web.image_server import _is_allowed_path
                self.assertTrue(_is_allowed_path(img))

    def test_path_equal_to_allowed_dir(self):
        """A path that equals the directory itself should be allowed."""
        with tempfile.TemporaryDirectory() as staging:
            settings = self._make_settings(staging, "", "")
            with (
                patch(f"{_MOD}.load_settings", return_value=settings),
                patch(f"{_MOD}._find_staging_subfolder", return_value=""),
                patch(f"{_MOD}.staging_progress", {"source_dir": ""}),
            ):
                from web.image_server import _is_allowed_path
                self.assertTrue(_is_allowed_path(staging))

    def test_path_inside_source_dir(self):
        """staging_progress['source_dir'] should also be allowed."""
        with tempfile.TemporaryDirectory() as src_dir:
            settings = self._make_settings("", "", "")
            img = os.path.join(src_dir, "orig.jpg")
            with (
                patch(f"{_MOD}.load_settings", return_value=settings),
                patch(f"{_MOD}._find_staging_subfolder", return_value=""),
                patch(f"{_MOD}.staging_progress", {"source_dir": src_dir}),
            ):
                from web.image_server import _is_allowed_path
                self.assertTrue(_is_allowed_path(img))

    def test_active_staging_subfolder_allowed(self):
        """When include_active_staging=True, the active subfolder is allowed."""
        with tempfile.TemporaryDirectory() as staging:
            sub = os.path.join(staging, "batch_001")
            os.makedirs(sub)
            settings = self._make_settings("", "", "")
            img = os.path.join(sub, "photo.jpg")
            with (
                patch(f"{_MOD}.load_settings", return_value=settings),
                patch(f"{_MOD}._find_staging_subfolder", return_value=sub),
                patch(f"{_MOD}.staging_progress", {"source_dir": ""}),
            ):
                from web.image_server import _is_allowed_path
                self.assertTrue(_is_allowed_path(img))

    def test_active_staging_parent_allowed(self):
        """The parent of the active subfolder should also be allowed."""
        with tempfile.TemporaryDirectory() as staging:
            sub = os.path.join(staging, "batch_001")
            os.makedirs(sub)
            settings = self._make_settings("", "", "")
            # File in the parent (staging) dir, not in the subfolder itself
            img = os.path.join(staging, "other.jpg")
            with (
                patch(f"{_MOD}.load_settings", return_value=settings),
                patch(f"{_MOD}._find_staging_subfolder", return_value=sub),
                patch(f"{_MOD}.staging_progress", {"source_dir": ""}),
            ):
                from web.image_server import _is_allowed_path
                self.assertTrue(_is_allowed_path(img))

    # ---- negative cases ----

    def test_path_outside_all_allowed_dirs(self):
        with tempfile.TemporaryDirectory() as staging, \
             tempfile.TemporaryDirectory() as outside:
            settings = self._make_settings(staging, "", "")
            img = os.path.join(outside, "evil.jpg")
            with (
                patch(f"{_MOD}.load_settings", return_value=settings),
                patch(f"{_MOD}._find_staging_subfolder", return_value=""),
                patch(f"{_MOD}.staging_progress", {"source_dir": ""}),
            ):
                from web.image_server import _is_allowed_path
                self.assertFalse(_is_allowed_path(img))

    def test_traversal_with_dotdot(self):
        """.. sequences that escape the allowed dir must be rejected."""
        with tempfile.TemporaryDirectory() as staging:
            # Build a path that starts inside staging but resolves outside
            traversal = os.path.join(staging, "..", "etc", "passwd")
            settings = self._make_settings(staging, "", "")
            with (
                patch(f"{_MOD}.load_settings", return_value=settings),
                patch(f"{_MOD}._find_staging_subfolder", return_value=""),
                patch(f"{_MOD}.staging_progress", {"source_dir": ""}),
            ):
                from web.image_server import _is_allowed_path
                self.assertFalse(_is_allowed_path(traversal))

    def test_traversal_multiple_dotdots(self):
        """Multiple .. sequences must still be rejected."""
        with tempfile.TemporaryDirectory() as staging:
            traversal = os.path.join(staging, "a", "..", "..", "secret.jpg")
            settings = self._make_settings(staging, "", "")
            with (
                patch(f"{_MOD}.load_settings", return_value=settings),
                patch(f"{_MOD}._find_staging_subfolder", return_value=""),
                patch(f"{_MOD}.staging_progress", {"source_dir": ""}),
            ):
                from web.image_server import _is_allowed_path
                self.assertFalse(_is_allowed_path(traversal))

    def test_similar_prefix_not_allowed(self):
        """A dir whose name starts with the allowed dir name must not match.

        e.g. allowed = /tmp/stage  -> /tmp/stage_evil/photo.jpg must fail.
        """
        with tempfile.TemporaryDirectory() as base:
            allowed = os.path.join(base, "stage")
            evil = os.path.join(base, "stage_evil")
            os.makedirs(allowed)
            os.makedirs(evil)
            settings = self._make_settings(allowed, "", "")
            img = os.path.join(evil, "photo.jpg")
            with (
                patch(f"{_MOD}.load_settings", return_value=settings),
                patch(f"{_MOD}._find_staging_subfolder", return_value=""),
                patch(f"{_MOD}.staging_progress", {"source_dir": ""}),
            ):
                from web.image_server import _is_allowed_path
                self.assertFalse(_is_allowed_path(img))

    def test_empty_dirs_reject_everything(self):
        """When all allowed dirs are empty strings, nothing should be allowed."""
        settings = self._make_settings("", "", "")
        with (
            patch(f"{_MOD}.load_settings", return_value=settings),
            patch(f"{_MOD}._find_staging_subfolder", return_value=""),
            patch(f"{_MOD}.staging_progress", {"source_dir": ""}),
        ):
            from web.image_server import _is_allowed_path
            self.assertFalse(_is_allowed_path("/some/random/path.jpg"))

    def test_include_active_staging_false_skips_subfolder(self):
        """When include_active_staging=False, active subfolder is NOT checked."""
        with tempfile.TemporaryDirectory() as staging:
            sub = os.path.join(staging, "batch_001")
            os.makedirs(sub)
            settings = self._make_settings("", "", "")
            img = os.path.join(sub, "photo.jpg")
            with (
                patch(f"{_MOD}.load_settings", return_value=settings),
                # _find_staging_subfolder should not even be called, but mock
                # it anyway for safety
                patch(f"{_MOD}._find_staging_subfolder", return_value=sub),
                patch(f"{_MOD}.staging_progress", {"source_dir": ""}),
            ):
                from web.image_server import _is_allowed_path
                self.assertFalse(
                    _is_allowed_path(img, include_active_staging=False)
                )


class TestServeImage(unittest.TestCase):
    """Tests for serve_image — content-type detection, ETag, error paths."""

    def _make_handler(self, if_none_match=None):
        handler = MagicMock()
        handler.headers = {"If-None-Match": if_none_match}
        handler.wfile = MagicMock()
        return handler

    # ---- content-type detection ----

    _EXTENSION_MAP = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
        ".heic": "image/heic",
        ".heif": "image/heif",
    }

    def test_content_type_for_known_extensions(self):
        for ext, expected_ct in self._EXTENSION_MAP.items():
            with self.subTest(ext=ext):
                handler = self._make_handler()
                filepath = os.path.join("C:", os.sep, "imgs", f"photo{ext}")
                fake_stat = MagicMock(st_mtime=1000.0, st_size=5000)
                with (
                    patch(f"{_MOD}._is_allowed_path", return_value=True),
                    patch("os.path.isfile", return_value=True),
                    patch("os.stat", return_value=fake_stat),
                    patch("builtins.open", mock_open(read_data=b"\x00")),
                    patch("shutil.copyfileobj"),
                ):
                    from web.image_server import serve_image
                    serve_image(handler, filepath)

                # Find the Content-Type header in the send_header calls
                ct_calls = [
                    c for c in handler.send_header.call_args_list
                    if c[0][0] == "Content-Type"
                ]
                self.assertEqual(len(ct_calls), 1)
                self.assertEqual(ct_calls[0][0][1], expected_ct)

    def test_unknown_extension_uses_octet_stream(self):
        handler = self._make_handler()
        filepath = os.path.join("C:", os.sep, "imgs", "data.xyz")
        fake_stat = MagicMock(st_mtime=1000.0, st_size=100)
        with (
            patch(f"{_MOD}._is_allowed_path", return_value=True),
            patch("os.path.isfile", return_value=True),
            patch("os.stat", return_value=fake_stat),
            patch("builtins.open", mock_open(read_data=b"\x00")),
            patch("shutil.copyfileobj"),
        ):
            from web.image_server import serve_image
            serve_image(handler, filepath)

        ct_calls = [
            c for c in handler.send_header.call_args_list
            if c[0][0] == "Content-Type"
        ]
        self.assertEqual(ct_calls[0][0][1], "application/octet-stream")

    # ---- ETag / 304 ----

    def test_etag_match_returns_304(self):
        fake_stat = MagicMock(st_mtime=1234.5, st_size=9999)
        etag = f'"{fake_stat.st_mtime}-{fake_stat.st_size}"'
        handler = self._make_handler(if_none_match=etag)
        filepath = os.path.join("C:", os.sep, "imgs", "photo.jpg")
        with (
            patch(f"{_MOD}._is_allowed_path", return_value=True),
            patch("os.path.isfile", return_value=True),
            patch("os.stat", return_value=fake_stat),
        ):
            from web.image_server import serve_image
            serve_image(handler, filepath)

        handler.send_response.assert_called_once_with(304)
        handler.end_headers.assert_called_once()
        # Body should NOT be sent
        handler.send_header.assert_not_called()

    def test_etag_mismatch_returns_200(self):
        fake_stat = MagicMock(st_mtime=1234.5, st_size=9999)
        handler = self._make_handler(if_none_match='"stale-etag"')
        filepath = os.path.join("C:", os.sep, "imgs", "photo.jpg")
        with (
            patch(f"{_MOD}._is_allowed_path", return_value=True),
            patch("os.path.isfile", return_value=True),
            patch("os.stat", return_value=fake_stat),
            patch("builtins.open", mock_open(read_data=b"\x00")),
            patch("shutil.copyfileobj"),
        ):
            from web.image_server import serve_image
            serve_image(handler, filepath)

        handler.send_response.assert_called_once_with(200)

    # ---- access denied / not found ----

    def test_disallowed_path_returns_403(self):
        handler = self._make_handler()
        filepath = os.path.join("C:", os.sep, "secret", "photo.jpg")
        with patch(f"{_MOD}._is_allowed_path", return_value=False):
            from web.image_server import serve_image
            serve_image(handler, filepath)

        handler.send_error.assert_called_once_with(403, "Access denied")

    def test_missing_file_returns_404(self):
        handler = self._make_handler()
        filepath = os.path.join("C:", os.sep, "imgs", "gone.jpg")
        with (
            patch(f"{_MOD}._is_allowed_path", return_value=True),
            patch("os.path.isfile", return_value=False),
        ):
            from web.image_server import serve_image
            serve_image(handler, filepath)

        handler.send_error.assert_called_once_with(404, "File not found")

    # ---- server error ----

    def test_read_failure_returns_500(self):
        handler = self._make_handler()
        filepath = os.path.join("C:", os.sep, "imgs", "corrupt.jpg")
        fake_stat = MagicMock(st_mtime=1.0, st_size=10)
        with (
            patch(f"{_MOD}._is_allowed_path", return_value=True),
            patch("os.path.isfile", return_value=True),
            patch("os.stat", return_value=fake_stat),
            patch("builtins.open", side_effect=PermissionError("denied")),
        ):
            from web.image_server import serve_image
            serve_image(handler, filepath)

        handler.send_error.assert_called_once()
        self.assertEqual(handler.send_error.call_args[0][0], 500)

    # ---- headers ----

    def test_response_headers_include_cache_control_and_etag(self):
        handler = self._make_handler()
        filepath = os.path.join("C:", os.sep, "imgs", "photo.png")
        fake_stat = MagicMock(st_mtime=42.0, st_size=1024)
        with (
            patch(f"{_MOD}._is_allowed_path", return_value=True),
            patch("os.path.isfile", return_value=True),
            patch("os.stat", return_value=fake_stat),
            patch("builtins.open", mock_open(read_data=b"\x89PNG")),
            patch("shutil.copyfileobj"),
        ):
            from web.image_server import serve_image
            serve_image(handler, filepath)

        header_names = [c[0][0] for c in handler.send_header.call_args_list]
        self.assertIn("Cache-Control", header_names)
        self.assertIn("ETag", header_names)
        self.assertIn("Content-Length", header_names)
        self.assertIn("Content-Type", header_names)

        # Verify ETag value format
        etag_calls = [
            c for c in handler.send_header.call_args_list
            if c[0][0] == "ETag"
        ]
        etag_val = etag_calls[0][0][1]
        self.assertEqual(etag_val, '"42.0-1024"')


if __name__ == "__main__":
    unittest.main()

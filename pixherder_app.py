#!/usr/bin/env python3
"""
PixHerder - Native desktop application for finding and cleaning duplicate images.

Usage:
    python pixherder_app.py
    python pixherder_app.py --port 8787

Opens a native window for scanning folders, reviewing duplicates side-by-side,
and cleaning them up.
"""

import argparse
import sys
import threading
from pathlib import Path

# Ensure project root is on the path
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.config import load_settings, ensure_dirs, SCANS_DIR


def _check_write_access():
    """Test if the app can write to its data directories.

    Controlled Folder Access (CFA) in Windows Defender silently blocks
    writes with misleading FileNotFoundError. Detect this early and
    warn the user to whitelist pythonw.exe.
    """
    import os
    test_file = os.path.join(str(SCANS_DIR), "_write_test.tmp")
    try:
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
    except (OSError, PermissionError):
        # CFA or permissions blocking writes
        python_exe = sys.executable
        try:
            import webview
            webview.create_window(
                "PixHerder - Setup Required",
                html=(
                    '<html><body style="background:#1a1a22;color:#e8e8ed;'
                    'font-family:sans-serif;padding:40px;text-align:center;">'
                    '<h2 style="color:#f87171;">Write Access Blocked</h2>'
                    '<p style="color:#7a7a8a;max-width:500px;margin:16px auto;">'
                    'Windows Defender Controlled Folder Access is preventing '
                    'PixHerder from saving files.</p>'
                    '<p style="color:#e8e8ed;max-width:500px;margin:16px auto;">'
                    'To fix this:</p>'
                    '<ol style="text-align:left;max-width:420px;margin:0 auto;'
                    'color:#7a7a8a;line-height:2;">'
                    '<li>Open <b style="color:#e8e8ed;">Windows Security</b></li>'
                    '<li>Go to <b style="color:#e8e8ed;">Virus &amp; threat '
                    'protection</b></li>'
                    '<li>Click <b style="color:#e8e8ed;">Ransomware protection'
                    '</b></li>'
                    '<li>Click <b style="color:#e8e8ed;">Allow an app through '
                    'Controlled Folder Access</b></li>'
                    '<li>Add: <code style="background:#0a0a0c;padding:2px 8px;'
                    'border-radius:4px;color:#6ee7b7;">'
                    + python_exe.replace("\\", "\\\\")
                    + '</code></li></ol>'
                    '<p style="color:#7a7a8a;margin-top:24px;">Then restart '
                    'PixHerder.</p></body></html>'
                ),
                width=600, height=480,
            )
            webview.start()
        except Exception:
            pass
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="PixHerder - Find and clean duplicate images",
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="Port to run on (default: from settings or 8787)",
    )
    parser.add_argument(
        "--support-mode", action="store_true",
        help="Enable DevTools (F12) for troubleshooting",
    )
    args = parser.parse_args()

    # Setup
    ensure_dirs()

    from engine.logging_config import setup_logging
    setup_logging()

    settings = load_settings()
    port = args.port or settings.get("port", 8787)

    # Check for Controlled Folder Access blocking writes
    _check_write_access()

    # Single-instance check: if port is already in use, exit silently
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        sock.close()
    except OSError:
        # Port in use — another instance is already running
        sys.exit(0)

    _run_native_mode(port, support_mode=args.support_mode)


def _run_native_mode(port, support_mode=False):
    """Run with pywebview native window."""
    try:
        import webview
    except ImportError:
        print("[ERROR] pywebview not installed. Run: pip install pywebview")
        sys.exit(1)

    from web.server import create_server
    from web.bridge import Api

    # Start the HTTP server in background (for images + static files)
    try:
        server = create_server(port)
    except OSError as e:
        print("[ERROR] Could not start server on port " + str(port) + ": " + str(e))
        sys.exit(1)

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    url = "http://127.0.0.1:" + str(port)

    print("")
    print("  PixHerder")
    print("  " + "-" * 40)
    print("  Mode:    Native window")
    print("  Server:  " + url + " (internal)")
    print("")

    # Create API bridge
    api = Api()

    # Create native window with API bridge
    _settings = load_settings()
    open_fullscreen = _settings.get("open_fullscreen", True)
    window = webview.create_window(
        "PixHerder",
        url=url,
        js_api=api,
        width=1200,
        height=800,
        min_size=(900, 600),
        maximized=open_fullscreen,
    )

    # Wire up the bridge
    api.set_window(window)

    def on_closing():
        """Clean up on window close."""
        try:
            from web.server import (
                scan_cancel, staging_cancel, syncback_cancel,
                action_cancel, oddball_cancel,
            )
            scan_cancel.set()
            staging_cancel.set()
            syncback_cancel.set()
            action_cancel.set()
            oddball_cancel.set()
        except Exception:
            pass
        server.shutdown()

    window.events.closing += on_closing

    debug = support_mode or _settings.get("debug_mode", False)
    icon_path = str(PROJECT_ROOT / "web" / "pixherder.ico")
    webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False
    webview.start(debug=debug, icon=icon_path)

    # Ensure clean exit after window closes
    server.shutdown()
    import sys
    sys.exit(0)


if __name__ == "__main__":
    main()

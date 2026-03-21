#!/usr/bin/env python3
"""
DupeFinder - Native desktop application for finding and cleaning duplicate images.

Usage:
    python dupefinder_app.py
    python dupefinder_app.py --port 8787

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

from engine.config import load_settings, ensure_dirs


def main():
    parser = argparse.ArgumentParser(
        description="DupeFinder - Find and clean duplicate images",
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="Port to run on (default: from settings or 8787)",
    )
    args = parser.parse_args()

    # Setup
    ensure_dirs()
    settings = load_settings()
    port = args.port or settings.get("port", 8787)

    _run_native_mode(port)


def _run_native_mode(port):
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
    print("  DupeFinder")
    print("  " + "-" * 40)
    print("  Mode:    Native window")
    print("  Server:  " + url + " (internal)")
    print("")

    # Create API bridge
    api = Api()

    # Create native window with API bridge
    window = webview.create_window(
        "DupeFinder",
        url=url,
        js_api=api,
        width=1200,
        height=800,
        min_size=(900, 600),
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

    # Start the window (blocks until closed)
    webview.start(debug=False)

    # Ensure clean exit after window closes
    server.shutdown()
    import sys
    sys.exit(0)


if __name__ == "__main__":
    main()

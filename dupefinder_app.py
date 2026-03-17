#!/usr/bin/env python3
"""
DupeFinder - Unified web application for finding and cleaning duplicate images.

Usage:
    python dupefinder_app.py
    python dupefinder_app.py --port 8787

Opens a browser-based UI for scanning folders, reviewing duplicates side-by-side,
and cleaning them up -- all without touching the command line again.
"""

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

# Ensure project root is on the path
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.config import load_settings, ensure_dirs
from web.server import create_server


def main():
    parser = argparse.ArgumentParser(
        description="DupeFinder - Find and clean duplicate images via browser UI",
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

    # Create server
    try:
        server = create_server(port)
    except OSError as e:
        print("[ERROR] Could not start server on port " + str(port) + ": " + str(e))
        print("  Try a different port: python dupefinder_app.py --port 8788")
        sys.exit(1)

    url = "http://127.0.0.1:" + str(port)

    print("")
    print("  DupeFinder")
    print("  " + "-" * 40)
    print("  Server:  " + url)
    print("  Port:    " + str(port))
    print("  Press Ctrl+C to stop")
    print("")

    # Open browser, but skip if a restored tab already connected
    def _maybe_open_browser():
        import time
        # Wait for any restored browser tabs to connect via heartbeat
        time.sleep(4)
        from web.server import _last_heartbeat, _heartbeat_lock
        with _heartbeat_lock:
            # Server sets _last_heartbeat at startup. If a browser tab
            # sent a heartbeat since then, the timestamp will be newer.
            age = time.time() - _last_heartbeat
        if age < 3:
            # A tab already connected -- don't open another
            return
        webbrowser.open(url)
    threading.Timer(0.1, _maybe_open_browser).start()

    # Serve forever
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()

"""Open the NeuroElectroMap viewer in a native desktop window.

The viewer is a self-contained HTML/JSX app under viewer/. We serve it over
loopback HTTP from an in-process thread (browsers refuse to load JSX scripts
or fetch JSON over file://) and then point a pywebview-managed native window
at it. No browser is required at runtime.

Run with:
    make desktop                          # via the Makefile
    .venv/bin/python scripts/launch_desktop.py

Pre-requisite:
    .venv/bin/pip install -r requirements-desktop.txt
"""

from __future__ import annotations

import http.server
import socket
import socketserver
import sys
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VIEWER_PATH = "viewer/index.html"


class _Handler(http.server.SimpleHTTPRequestHandler):
    """Static handler that serves the project root and disables HTTP caching."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def end_headers(self) -> None:
        # Editing a JSX file during a dev session should be picked up on reload.
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def log_message(self, *_args, **_kwargs) -> None:
        # Keep the desktop launcher quiet — no per-request access log.
        return


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _pick_free_port() -> int:
    """Ask the OS for an unused loopback TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server() -> tuple[_Server, int]:
    port = _pick_free_port()
    server = _Server(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def main() -> int:
    # pywebview is heavy (PyObjC on macOS, pythonnet on Windows) so we import
    # it lazily and print a helpful message if it's missing.
    try:
        import webview  # type: ignore
    except ImportError:
        print(
            "pywebview is not installed.\n"
            "Run:  .venv/bin/pip install -r requirements-desktop.txt\n"
            "Or:   make install-desktop",
            file=sys.stderr,
        )
        return 1

    # Friendly check: nothing to render without the viewer assets / data.
    viewer_html = PROJECT_ROOT / VIEWER_PATH
    if not viewer_html.exists():
        print(f"Viewer source missing at {viewer_html} — aborting.", file=sys.stderr)
        return 1
    data_js = PROJECT_ROOT / "outputs" / "viewer" / "data.js"
    if not data_js.exists():
        print(
            "[WARNING] outputs/viewer/data.js not found.\n"
            "The viewer will load but show its empty-state error screen.\n"
            "Run the pipeline with --export-viewer to populate it:\n"
            "    python main.py --mri ... --ct ... --subject-dir ... --export-viewer",
        )

    server, port = _start_server()
    url = f"http://127.0.0.1:{port}/{VIEWER_PATH}"
    print(f"Local viewer server on http://127.0.0.1:{port}/  (press the window's close button to exit)")

    webview.create_window(
        "NeuroElectroMap",
        url,
        width=1400, height=900, min_size=(1000, 700),
        background_color="#0d1117",   # matches dark theme so there's no flash
    )

    # On macOS pywebview uses WKWebView (system Safari engine). On Windows it
    # uses Edge WebView2. Linux uses WebKitGTK. All three honour our local
    # HTTP server identically.
    try:
        webview.start()
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

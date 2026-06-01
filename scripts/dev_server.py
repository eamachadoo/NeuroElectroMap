"""Local dev server that disables HTTP caching.

Used by the Claude Preview during viewer development so that edits to
viewer/*.jsx and viewer/*.js are picked up on the next reload without
having to bump cache-busting query strings or restart the server.
"""
import http.server
import socketserver
import sys


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    with socketserver.TCPServer(("127.0.0.1", port), NoCacheHandler) as srv:
        print(f"Dev server (no-cache) on http://127.0.0.1:{port}/")
        srv.serve_forever()

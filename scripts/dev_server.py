"""Local dev server with two affordances for viewer development:

1. **No-cache headers** so the browser never serves a stale copy.
2. **`?v=<mtime>` rewriting** for `viewer/index.html`: every `?v=N` query
   string on a `.js` / `.jsx` script tag is replaced with the file's actual
   mtime, on the fly. The HTML on disk stays untouched (still says `?v=N`),
   but the browser sees a fresh URL the moment a source file changes — no
   manual bumping, no rebuild step.

Used by:
  • `make viewer`              (browser mode)
  • `make desktop`             (pywebview launcher)
  • `python scripts/dev_server.py <port>`
"""

from __future__ import annotations

import http.server
import re
import socketserver
import sys
from pathlib import Path

# Matches `name.js?v=N` or `name.jsx?v=N` (any digits/identifiers after v=).
# The substitution callback replaces the query value with the file's mtime.
_VERSION_RE = re.compile(rb'(src=["\'](?P<name>[^"\']+\.(?:jsx|js))\?v=)[^"\']*')


def _rewrite_index_html(body: bytes, base_dir: Path) -> bytes:
    """Replace `?v=N` for every local script src with the file's mtime."""
    def sub(match: re.Match) -> bytes:
        prefix = match.group(1)
        name   = match.group("name").decode()
        target = base_dir / name
        try:
            mtime = int(target.stat().st_mtime)
        except OSError:
            # File doesn't exist — leave the original placeholder alone.
            return match.group(0)
        return prefix + str(mtime).encode()
    return _VERSION_RE.sub(sub, body)


class _Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802 — http.server's name
        # Only rewrite the viewer's index.html. Everything else is served
        # byte-for-byte by the parent implementation.
        if self.path.rstrip("/").endswith("viewer/index.html") \
           or self.path.rstrip("/").endswith("viewer"):
            html_path = Path(self.translate_path("/viewer/index.html"))
            if html_path.is_file():
                try:
                    body = _rewrite_index_html(html_path.read_bytes(), html_path.parent)
                except Exception:
                    return super().do_GET()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        return super().do_GET()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    with socketserver.TCPServer(("127.0.0.1", port), _Handler) as srv:
        print(f"Dev server (no-cache + mtime cache-bust) on http://127.0.0.1:{port}/")
        srv.serve_forever()

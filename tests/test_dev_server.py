"""Tests for scripts/dev_server.py — the rewriter that swaps `?v=N` script
query strings for each source file's mtime, so a JSX edit is picked up on
the next reload without any manual cache-busting bumps.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from scripts.dev_server import _rewrite_index_html


def _html(jsxes: list[tuple[str, str]]) -> bytes:
    """Build a tiny index.html-like snippet with placeholder versions."""
    tags = "\n".join(
        f'<script type="text/babel" src="{name}?v={ver}"></script>'
        for name, ver in jsxes
    )
    return tags.encode()


def test_rewrites_jsx_version_to_mtime(tmp_path):
    (tmp_path / "app.jsx").write_text("// app")
    target_mtime = 1_700_000_000  # fixed, easy to assert against
    import os
    os.utime(tmp_path / "app.jsx", (target_mtime, target_mtime))

    body = _html([("app.jsx", "4")])
    out = _rewrite_index_html(body, tmp_path)

    assert b'src="app.jsx?v=1700000000"' in out
    assert b'?v=4' not in out


def test_rewrites_each_file_to_its_own_mtime(tmp_path):
    (tmp_path / "a.jsx").write_text("a")
    (tmp_path / "b.jsx").write_text("b")
    import os
    os.utime(tmp_path / "a.jsx", (1_000_000_111, 1_000_000_111))
    os.utime(tmp_path / "b.jsx", (1_000_000_222, 1_000_000_222))

    body = _html([("a.jsx", "1"), ("b.jsx", "1")])
    out = _rewrite_index_html(body, tmp_path).decode()

    assert "a.jsx?v=1000000111" in out
    assert "b.jsx?v=1000000222" in out


def test_leaves_unknown_files_untouched(tmp_path):
    body = b'<script src="missing.jsx?v=4"></script>'
    out = _rewrite_index_html(body, tmp_path)
    assert out == body, "should leave the placeholder when the source doesn't exist"


def test_handles_js_extensions_too(tmp_path):
    (tmp_path / "regions.js").write_text("// regions")
    import os
    os.utime(tmp_path / "regions.js", (1_700_000_000, 1_700_000_000))

    body = b'<script src="regions.js?v=4"></script>'
    out = _rewrite_index_html(body, tmp_path)
    assert b'regions.js?v=1700000000' in out


def test_does_not_touch_external_or_unmarked_scripts(tmp_path):
    """External CDN scripts (no v= param) must not be rewritten."""
    body = (
        b'<script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>'
        b'<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'
    )
    out = _rewrite_index_html(body, tmp_path)
    assert out == body, "external URLs without ?v= must be left alone"


def test_does_not_touch_non_script_v_params(tmp_path):
    """`v=N` outside a script src should not be rewritten."""
    body = b'<meta name="version" content="v=4">'
    out = _rewrite_index_html(body, tmp_path)
    assert out == body


def test_root_redirects_to_viewer():
    """The dev server should bounce `/` to `/viewer/` so users don't have to
    navigate the source tree from the directory listing."""
    import http.client
    import socketserver
    import threading
    import time

    from scripts.dev_server import _Handler

    class _Srv(socketserver.TCPServer):
        allow_reuse_address = True

    srv = _Srv(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.05)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("GET", "/")
        resp = conn.getresponse()
        assert resp.status == 302
        assert resp.headers.get("Location") == "/viewer/"
    finally:
        srv.shutdown()
        srv.server_close()

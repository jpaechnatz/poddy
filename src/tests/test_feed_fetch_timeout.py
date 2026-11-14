"""Feed fetches give up on a silent server instead of hanging forever."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app import feeds

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>
<item><title>E1</title><guid isPermaLink="false">tag:example.com,2026:g1</guid>
<enclosure url="https://example.com/e1.mp3" type="audio/mpeg" length="1"/></item>
</channel></rss>"""


@pytest.fixture
def silent_server() -> Iterator[str]:
    """Accepts connections and never answers."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(5)
    accepted: list[socket.socket] = []
    stop = threading.Event()

    def accept() -> None:
        sock.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = sock.accept()
                accepted.append(conn)
            except OSError:
                continue

    thread = threading.Thread(target=accept, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{sock.getsockname()[1]}/feed.xml"
    stop.set()
    thread.join(timeout=2)
    for conn in accepted:
        conn.close()
    sock.close()


@pytest.fixture
def rss_server() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml")
            self.end_headers()
            self.wfile.write(RSS)

        def log_message(self, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/feed.xml"
    server.shutdown()
    server.server_close()


def test_silent_server_times_out(
    silent_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(feeds, "FEED_FETCH_TIMEOUT_SECONDS", 0.5)
    started = time.monotonic()
    result = feeds.fetch_feed(silent_server)
    assert time.monotonic() - started < 5
    assert result.bozo
    assert not result.entries
    assert isinstance(result.bozo_exception, OSError)
    with pytest.raises(RuntimeError, match="could not be read"):
        feeds._raise_for_failed_fetch(result)


def test_normal_feed_still_parses(rss_server: str) -> None:
    result = feeds.fetch_feed(rss_server)
    assert result.status == 200
    assert [e.id for e in result.entries] == ["tag:example.com,2026:g1"]

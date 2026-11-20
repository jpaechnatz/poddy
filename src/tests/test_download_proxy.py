"""DOWNLOAD_PROXY routes chosen episode downloads through another connection."""

from __future__ import annotations

import logging
import socket
import threading
from collections.abc import Iterator
from typing import Any
from unittest import mock

import pytest
import requests

from app.models import Post
from podcast_processor.podcast_downloader import (
    PodcastDownloader,
    _redact_proxy,
    download_proxies,
    proxy_failure_reason,
)

PATREON = "https://www.patreon.com/api/rss/u/x/e/1.mp3?sig=abc"
PROXY = "http://100.64.0.7:8888"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOWNLOAD_PROXY", raising=False)
    monkeypatch.delenv("DOWNLOAD_PROXY_HOSTS", raising=False)
    monkeypatch.delenv("DOWNLOAD_PROXY_FALLBACK", raising=False)


def test_no_proxy_by_default() -> None:
    assert download_proxies(PATREON) is None


def test_proxy_for_every_download_without_host_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOWNLOAD_PROXY", PROXY)
    assert download_proxies("https://cdn.example.com/a.mp3") == {
        "http": PROXY,
        "https": PROXY,
    }


def test_host_list_limits_the_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOWNLOAD_PROXY", PROXY)
    monkeypatch.setenv("DOWNLOAD_PROXY_HOSTS", " patreon.com , .supercast.com ")
    assert download_proxies(PATREON) is not None
    assert download_proxies("https://patreon.com/x.mp3") is not None
    assert download_proxies("https://feeds.supercast.com/x.mp3") is not None
    assert download_proxies("https://audio.podigee-cdn.net/x.mp3") is None
    # A look-alike domain is not a subdomain.
    assert download_proxies("https://evilpatreon.com/x.mp3") is None


def test_socks_or_garbage_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOWNLOAD_PROXY", "socks5h://127.0.0.1:40000")
    with pytest.raises(ValueError, match="http:// or https://"):
        download_proxies(PATREON)


def test_credentials_are_not_logged() -> None:
    assert _redact_proxy("http://joh:geheim@100.64.0.7:8888") == (
        "http://***@100.64.0.7:8888"
    )
    assert _redact_proxy(PROXY) == PROXY


def _response() -> Any:
    response = mock.MagicMock()
    response.status_code = 200
    response.iter_content.return_value = [b"audio"]
    response.__enter__.return_value = response
    response.__exit__.return_value = None
    return response


@mock.patch("podcast_processor.podcast_downloader.requests.get")
def test_download_uses_the_proxy_only_for_listed_hosts(
    mock_get: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Any, app: Any
) -> None:
    monkeypatch.setenv("DOWNLOAD_PROXY", PROXY)
    monkeypatch.setenv("DOWNLOAD_PROXY_HOSTS", "patreon.com")
    mock_get.return_value = _response()
    downloader = PodcastDownloader(download_dir=str(tmp_path))

    with app.app_context():
        downloader.download_episode(
            Post(id=1, download_url=PATREON), dest_path=str(tmp_path / "a.mp3")
        )
    assert mock_get.call_args.kwargs["proxies"] == {"http": PROXY, "https": PROXY}

    with app.app_context():
        downloader.download_episode(
            Post(id=2, download_url="https://cdn.example.com/b.mp3"),
            dest_path=str(tmp_path / "b.mp3"),
        )
    assert "proxies" not in mock_get.call_args.kwargs


def _status(code: int) -> Any:
    response = _response()
    response.status_code = code
    return response


def _download(app: Any, tmp_path: Any) -> tuple[PodcastDownloader, str | None]:
    downloader = PodcastDownloader(download_dir=str(tmp_path))
    with app.app_context():
        result = downloader.download_episode(
            Post(id=1, download_url=PATREON), dest_path=str(tmp_path / "a.mp3")
        )
    return downloader, result


@pytest.mark.parametrize(
    "proxy_error",
    [
        requests.exceptions.ProxyError("Cannot connect to proxy"),
        requests.exceptions.ConnectTimeout("timed out"),
    ],
)
@mock.patch("podcast_processor.podcast_downloader.requests.get")
def test_unreachable_proxy_falls_back_to_direct_download(
    mock_get: Any,
    proxy_error: Exception,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    app: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("DOWNLOAD_PROXY", PROXY)
    mock_get.side_effect = [proxy_error, _response()]

    with caplog.at_level(logging.WARNING):
        downloader, result = _download(app, tmp_path)

    assert result == str(tmp_path / "a.mp3")
    assert (tmp_path / "a.mp3").read_bytes() == b"audio"
    assert downloader.last_error is None
    first, second = mock_get.call_args_list
    assert first.kwargs["proxies"] == {"http": PROXY, "https": PROXY}
    assert "proxies" not in second.kwargs
    assert "downloading directly" in caplog.text


@mock.patch("podcast_processor.podcast_downloader.requests.get")
def test_fallback_can_be_switched_off(
    mock_get: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Any, app: Any
) -> None:
    monkeypatch.setenv("DOWNLOAD_PROXY", PROXY)
    monkeypatch.setenv("DOWNLOAD_PROXY_FALLBACK", "none")
    mock_get.side_effect = requests.exceptions.ProxyError("down")

    downloader, result = _download(app, tmp_path)

    assert result is None
    assert mock_get.call_count == 1
    assert downloader.last_error == f"DOWNLOAD_PROXY {PROXY} failed: ProxyError"


@mock.patch("podcast_processor.podcast_downloader.requests.get")
def test_failed_direct_download_reports_both_reasons(
    mock_get: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Any, app: Any
) -> None:
    monkeypatch.setenv("DOWNLOAD_PROXY", PROXY)
    mock_get.side_effect = [requests.exceptions.ProxyError("down"), _status(403)]

    downloader, result = _download(app, tmp_path)

    assert result is None
    assert downloader.last_error == (
        f"DOWNLOAD_PROXY {PROXY} failed: ProxyError; direct download: HTTP 403"
    )
    assert not (tmp_path / "a.mp3").exists()


@mock.patch("podcast_processor.podcast_downloader.requests.get")
def test_http_error_through_the_proxy_is_not_retried_directly(
    mock_get: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Any, app: Any
) -> None:
    monkeypatch.setenv("DOWNLOAD_PROXY", PROXY)
    mock_get.return_value = _status(404)

    downloader, result = _download(app, tmp_path)

    assert result is None
    assert mock_get.call_count == 1
    assert downloader.last_error == "HTTP 404"


# Exception texts as requests 2.33 / urllib3 2.x raise them; each names the
# full episode URL, which must never reach the log.
_URL = "HTTPSConnectionPool(host='example.com', port=443): Max retries exceeded with url: /e.mp3?token=SECRET"


@pytest.mark.parametrize(
    ("exc", "reason"),
    [
        (
            requests.exceptions.ProxyError(
                f"{_URL} (Caused by ProxyError('Unable to connect to proxy', "
                "ConnectTimeoutError(<HTTPSConnection(host='10.147.28.97', port=8888)>, "
                "'Connection to 10.147.28.97 timed out. (connect timeout=60)')))"
            ),
            "connection timed out",
        ),
        (
            requests.exceptions.ProxyError(
                f"{_URL} (Caused by ProxyError('Unable to connect to proxy', "
                "NewConnectionError(\"HTTPSConnection(host='10.147.28.97', port=8888): "
                'Failed to establish a new connection: [Errno 111] Connection refused")))'
            ),
            "connection refused",
        ),
        (
            requests.exceptions.ProxyError(
                f"{_URL} (Caused by ProxyError('Unable to connect to proxy', "
                "OSError('Tunnel connection failed: 403 Access denied')))"
            ),
            "proxy answered HTTP 403",
        ),
        (
            requests.exceptions.ProxyError(
                f"{_URL} (Caused by ProxyError('Unable to connect to proxy', "
                "NameResolutionError(\"HTTPSConnection(host='pi.invalid', port=8888): "
                "Failed to resolve 'pi.invalid' ([Errno -2] Name or service not known)\")))"
            ),
            "proxy host name not resolvable",
        ),
        (
            requests.exceptions.ProxyError(
                f"{_URL} (Caused by ProxyError('Unable to connect to proxy', "
                "NewConnectionError(\"HTTPSConnection(host='10.147.28.97', port=8888): "
                'Failed to establish a new connection: [Errno 113] No route to host")))'
            ),
            "no route to the proxy host",
        ),
        (requests.exceptions.ConnectTimeout("timed out"), "connection timed out"),
        (requests.exceptions.ProxyError("Cannot connect to proxy"), "ProxyError"),
    ],
)
def test_proxy_failure_reason_names_the_cause_without_the_url(
    exc: requests.RequestException, reason: str
) -> None:
    assert proxy_failure_reason(exc) == reason


@pytest.fixture
def denying_proxy() -> Iterator[str]:
    """A local proxy that answers every CONNECT like tinyproxy's Allow list."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(5)

    def serve() -> None:
        while True:
            try:
                client, _ = server.accept()
            except OSError:
                return
            with client:
                client.recv(4096)
                client.sendall(b"HTTP/1.0 403 Access denied\r\n\r\n")

    threading.Thread(target=serve, daemon=True).start()
    yield f"http://127.0.0.1:{server.getsockname()[1]}"
    server.close()


def test_denied_proxy_is_reported_with_its_http_status(
    denying_proxy: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Any, app: Any
) -> None:
    # Real requests/urllib3 against a real socket, so a changed error text in
    # a library update shows up here instead of as a bare "ProxyError".
    monkeypatch.setenv("DOWNLOAD_PROXY", denying_proxy)
    monkeypatch.setenv("DOWNLOAD_PROXY_FALLBACK", "none")

    downloader, result = _download(app, tmp_path)

    assert result is None
    assert downloader.last_error == (
        f"DOWNLOAD_PROXY {denying_proxy} failed: proxy answered HTTP 403"
    )
    assert "sig=abc" not in (downloader.last_error or "")

"""DOWNLOAD_PROXY routes chosen episode downloads through another connection."""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest

from app.models import Post
from podcast_processor.podcast_downloader import (
    PodcastDownloader,
    _redact_proxy,
    download_proxies,
)

PATREON = "https://www.patreon.com/api/rss/u/x/e/1.mp3?sig=abc"
PROXY = "http://100.64.0.7:8888"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOWNLOAD_PROXY", raising=False)
    monkeypatch.delenv("DOWNLOAD_PROXY_HOSTS", raising=False)


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

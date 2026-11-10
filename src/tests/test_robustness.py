"""Cleanup and error reporting around downloads, transcription and feeds."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest
import requests

from app.feeds import _raise_for_failed_fetch, _url_for_log
from app.models import Post, ProcessingJob
from podcast_processor import transcribe
from podcast_processor.podcast_downloader import PodcastDownloader
from podcast_processor.podcast_processor import PodcastProcessor, ProcessorException
from podcast_processor.transcribe import OpenAIWhisperTranscriber
from shared.config import RemoteWhisperConfig

SIGNED = "https://www.patreon.com/api/rss/u/SECRET/e/1.mp3?sig=TOKEN"


# --- transcription chunks -------------------------------------------------


def _transcriber() -> OpenAIWhisperTranscriber:
    return OpenAIWhisperTranscriber(
        logging.getLogger("test"),
        RemoteWhisperConfig(api_key="k", base_url="https://x/v1", model="m"),
    )


def _fake_split(audio: Path, parts: Path, _size: int) -> list[tuple[Path, int]]:
    parts.mkdir(parents=True, exist_ok=True)
    chunk = parts / "0.mp3"
    chunk.write_bytes(b"audio")
    return [(chunk, 0)]


def test_chunk_dir_is_removed_when_a_chunk_fails(tmp_path: Path) -> None:
    audio = tmp_path / "ep.mp3"
    audio.write_bytes(b"x")
    t = _transcriber()
    with (
        mock.patch.object(transcribe, "split_audio", side_effect=_fake_split),
        mock.patch.object(
            t, "get_segments_for_chunk", side_effect=RuntimeError("boom")
        ),
        pytest.raises(RuntimeError),
    ):
        t.transcribe(str(audio), "de")
    assert not (tmp_path / "ep.mp3_parts").exists()


def test_chunk_dir_is_removed_when_splitting_fails(tmp_path: Path) -> None:
    audio = tmp_path / "ep.mp3"
    audio.write_bytes(b"x")

    def half_split(_a: Path, parts: Path, _s: int) -> list[tuple[Path, int]]:
        parts.mkdir(parents=True)
        (parts / "0.mp3").write_bytes(b"partial")
        raise RuntimeError("ffmpeg died")

    with (
        mock.patch.object(transcribe, "split_audio", side_effect=half_split),
        pytest.raises(RuntimeError),
    ):
        _transcriber().transcribe(str(audio), "de")
    assert not (tmp_path / "ep.mp3_parts").exists()


# --- downloads ----------------------------------------------------------------


def _streaming(chunks: Any) -> Any:
    response = mock.MagicMock()
    response.status_code = 200
    response.iter_content.side_effect = chunks
    response.__enter__.return_value = response
    response.__exit__.return_value = None
    return response


@pytest.fixture
def downloader(tmp_path: Path) -> PodcastDownloader:
    return PodcastDownloader(download_dir=str(tmp_path))


@mock.patch("podcast_processor.podcast_downloader.requests.get")
def test_broken_download_leaves_no_file(
    mock_get: Any, downloader: PodcastDownloader, tmp_path: Path, app: Any
) -> None:
    def cut_off(chunk_size: int) -> Any:
        yield b"first half"
        raise requests.exceptions.ChunkedEncodingError("connection reset")

    mock_get.return_value = _streaming(cut_off)
    dest = tmp_path / "ep.mp3"
    with app.app_context():
        assert (
            downloader.download_episode(Post(id=1, download_url=SIGNED), str(dest))
            is None
        )
    assert not dest.exists()
    assert not Path(str(dest) + ".part").exists()
    assert downloader.last_error == "network error (ChunkedEncodingError)"


@mock.patch("podcast_processor.podcast_downloader.requests.get")
def test_proxy_down_gives_short_reason_without_url(
    mock_get: Any,
    downloader: PodcastDownloader,
    tmp_path: Path,
    app: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("DOWNLOAD_PROXY", "http://joh:pw@100.96.132.65:8888")
    monkeypatch.delenv("DOWNLOAD_PROXY_HOSTS", raising=False)
    mock_get.side_effect = requests.exceptions.ProxyError(
        f"HTTPSConnectionPool: Max retries exceeded with url: {SIGNED}"
    )
    with app.app_context(), caplog.at_level(logging.INFO):
        result = downloader.download_episode(
            Post(id=1, download_url=SIGNED), str(tmp_path / "ep.mp3")
        )
    assert result is None
    assert downloader.last_error == (
        "DOWNLOAD_PROXY http://***@100.96.132.65:8888 not reachable"
    )
    assert "SECRET" not in caplog.text and "TOKEN" not in caplog.text


@mock.patch("podcast_processor.podcast_downloader.requests.get")
def test_http_error_is_reported(
    mock_get: Any, downloader: PodcastDownloader, tmp_path: Path, app: Any
) -> None:
    response = _streaming([])
    response.status_code = 403
    mock_get.return_value = response
    with app.app_context():
        downloader.download_episode(
            Post(id=1, download_url=SIGNED), str(tmp_path / "a.mp3")
        )
    assert downloader.last_error == "HTTP 403"


def test_job_status_names_the_download_reason(tmp_path: Path, app: Any) -> None:
    processor = object.__new__(PodcastProcessor)
    processor.logger = logging.getLogger("test")
    processor.status_manager = mock.MagicMock()
    processor.downloader = mock.MagicMock()
    processor.downloader.download_episode.return_value = None
    processor.downloader.last_error = "HTTP 403"
    with (
        app.app_context(),
        mock.patch(
            "podcast_processor.podcast_processor.get_job_unprocessed_path",
            return_value=tmp_path / "missing.mp3",
        ),
        pytest.raises(ProcessorException, match=r"^Download failed: HTTP 403$"),
    ):
        processor._handle_download_step(
            Post(id=1, download_url=SIGNED), ProcessingJob(), "g", "t", "j"
        )


# --- feeds --------------------------------------------------------------------


def test_feed_url_in_log_has_no_query_token() -> None:
    url = "https://www.patreon.com/rss/show?auth=TOKEN&show=1"
    assert _url_for_log(url) == "https://www.patreon.com/rss/show"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"status": 403, "entries": []}, "Feed returned HTTP 403"),
        ({"status": 404, "entries": [{"id": 1}]}, "Feed returned HTTP 404"),
        (
            {
                "status": 200,
                "entries": [],
                "bozo": True,
                "bozo_exception": ValueError(),
            },
            r"Feed could not be read \(ValueError\)",
        ),
    ],
)
def test_failed_feed_fetch_raises(data: dict[str, Any], message: str) -> None:
    feed_data = SimpleNamespace(entries=data["entries"], get=data.get)
    with pytest.raises(RuntimeError, match=message):
        _raise_for_failed_fetch(feed_data)  # type: ignore[arg-type]


def test_good_or_empty_feed_passes() -> None:
    for data in (
        {"status": 200, "entries": [{"id": 1}]},
        {"status": 200, "entries": [], "bozo": False},  # empty but valid
        {"status": 301, "entries": [{"id": 1}], "bozo": True},  # redirect, minor issue
    ):
        _raise_for_failed_fetch(SimpleNamespace(entries=data["entries"], get=data.get))  # type: ignore[arg-type]


def test_feed_response_declares_utf8(app: Any) -> None:
    from app.routes.feed_routes import _feed_xml_response

    with app.test_request_context():
        assert (
            _feed_xml_response("<rss/>").headers["Content-Type"]
            == "application/rss+xml; charset=utf-8"
        )

"""Silence trimming and loudness normalization of processed episodes."""

import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

import ffmpeg
import pytest

from app.extensions import db
from app.models import Feed, Post, ProcessingJob
from app.routes.feed_routes import feed_bp
from podcast_processor.audio import get_audio_duration_ms
from podcast_processor.audio_polish import (
    PolishOptions,
    polish_audio,
    silence_cut_windows,
)
from podcast_processor.chapter_reader import Chapter, read_chapters
from podcast_processor.chapter_writer import write_chapters
from podcast_processor.podcast_processor import PodcastProcessor, _shift_chapter_data


def _tone_silence_tone(tmp_path: Path, volume_db: float = -10.0) -> Path:
    """5s tone, 6s digital silence, 5s tone, with one chapter per tone."""
    path = tmp_path / "episode.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=5",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono:d=6",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=660:duration=5",
            "-filter_complex",
            f"[0][1][2]concat=n=3:v=0:a=1,volume={volume_db}dB",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(path),
        ],
        check=True,
    )
    write_chapters(
        str(path),
        [
            Chapter("a", "Erster Ton", 0, 5_000),
            Chapter("b", "Zweiter Ton", 11_000, 16_000),
        ],
    )
    return path


def _integrated_loudness(path: Path) -> float:
    _, stderr = (
        ffmpeg.input(str(path))
        .filter("ebur128")
        .output("-", format="null")
        .run(capture_stdout=True, capture_stderr=True)
    )
    values = re.findall(r"I:\s+(-?[0-9.]+) LUFS", stderr.decode())
    return float(values[-1])


def test_silence_cut_windows_keep_part_of_each_pause() -> None:
    assert silence_cut_windows([(5.0, 11.0), (20.0, 20.4)], keep_seconds=0.6) == [
        (5.3, 10.7)
    ]


def test_trim_silence_shortens_pause_and_moves_chapters(tmp_path: Path) -> None:
    path = _tone_silence_tone(tmp_path)

    windows = polish_audio(str(path), PolishOptions(trim_silence=True))

    assert len(windows) == 1
    start, end = windows[0]
    assert start == pytest.approx(5.3, abs=0.2)
    assert end == pytest.approx(10.7, abs=0.2)
    duration_ms = get_audio_duration_ms(str(path))
    assert duration_ms is not None
    assert duration_ms / 1000 == pytest.approx(16.0 - (end - start), abs=0.3)
    chapters = read_chapters(str(path))
    assert [c.title for c in chapters] == ["Erster Ton", "Zweiter Ton"]
    assert chapters[1].start_time_ms / 1000 == pytest.approx(
        11.0 - (end - start), abs=0.05
    )


def test_normalize_loudness_reaches_podcast_target(tmp_path: Path) -> None:
    path = _tone_silence_tone(tmp_path, volume_db=-30.0)
    assert _integrated_loudness(path) < -30

    windows = polish_audio(str(path), PolishOptions(normalize_loudness=True))

    assert windows == []
    assert _integrated_loudness(path) == pytest.approx(-16.0, abs=1.5)
    # Nothing was cut, so the duration and chapters stay as they were.
    duration_ms = get_audio_duration_ms(str(path))
    assert duration_ms is not None
    assert duration_ms / 1000 == pytest.approx(16.0, abs=0.2)
    assert read_chapters(str(path))[1].start_time_ms == 11_000


def test_polish_failure_keeps_file_and_returns_nothing(tmp_path: Path) -> None:
    broken = tmp_path / "broken.mp3"
    broken.write_bytes(b"not audio")

    options = PolishOptions(trim_silence=True, normalize_loudness=True)
    assert polish_audio(str(broken), options) == []
    assert broken.read_bytes() == b"not audio"
    assert polish_audio(str(broken), PolishOptions()) == []


def test_shift_chapter_data_moves_output_chapters() -> None:
    data = json.dumps(
        {
            "chapter_source": "embedded",
            "chapters_for_output": [
                {"title": "A", "start_time": 0.0, "end_time": 5.0},
                {"title": "B", "start_time": 11.0, "end_time": 16.0},
            ],
        }
    )

    shifted = json.loads(_shift_chapter_data(data, [(5.3, 10.7)]))

    assert shifted["chapter_source"] == "embedded"
    assert shifted["chapters_for_output"][1] == {
        "title": "B",
        "start_time": 5.6,
        "end_time": 10.6,
    }
    assert _shift_chapter_data("not json", [(1.0, 2.0)]) == "not json"


def test_finalize_polishes_when_feed_enables_it() -> None:
    processor = object.__new__(PodcastProcessor)
    processor.logger = mock.MagicMock()
    processor.status_manager = mock.MagicMock()
    processor._remove_unprocessed_audio = mock.MagicMock()
    post = Post(id=1, guid="g")
    chapter_data = json.dumps(
        {"chapters_for_output": [{"title": "B", "start_time": 11.0, "end_time": 16.0}]}
    )

    with (
        mock.patch(
            "podcast_processor.podcast_processor.polish_audio",
            return_value=[(5.0, 10.0)],
        ) as polish_mock,
        mock.patch(
            "podcast_processor.podcast_processor.get_audio_duration_ms",
            return_value=None,
        ),
        mock.patch("podcast_processor.podcast_processor.writer_client") as writer,
    ):
        writer.update.return_value = SimpleNamespace(success=True)
        processor._finalize_processing(
            post,
            ProcessingJob(),
            "/out.mp3",
            chapter_data=chapter_data,
            polish_options=PolishOptions(trim_silence=True),
        )

    polish_mock.assert_called_once_with(
        "/out.mp3", PolishOptions(trim_silence=True, normalize_loudness=False)
    )
    stored = json.loads(writer.update.call_args.args[2]["chapter_data"])
    assert stored["chapters_for_output"][0]["start_time"] == 6.0


def test_finalize_skips_polish_by_default() -> None:
    processor = object.__new__(PodcastProcessor)
    processor.logger = mock.MagicMock()
    processor.status_manager = mock.MagicMock()
    processor._remove_unprocessed_audio = mock.MagicMock()

    with (
        mock.patch("podcast_processor.podcast_processor.polish_audio") as polish_mock,
        mock.patch(
            "podcast_processor.podcast_processor.get_audio_duration_ms",
            return_value=None,
        ),
        mock.patch("podcast_processor.podcast_processor.writer_client") as writer,
    ):
        writer.update.return_value = SimpleNamespace(success=True)
        processor._finalize_processing(Post(id=1, guid="g"), ProcessingJob(), "/o.mp3")

    polish_mock.assert_not_called()


def test_settings_accept_polish_flags(app: Any) -> None:
    app.testing = True
    app.register_blueprint(feed_bp)
    with app.app_context():
        feed = Feed(title="RK", rss_url="https://example.com/polish.xml")
        db.session.add(feed)
        db.session.commit()
        feed_id = feed.id
    client = app.test_client()

    def _update(model: str, model_id: int, updates: dict[str, Any], wait: bool = True):
        Feed.query.filter_by(id=model_id).update(updates)
        db.session.commit()
        return SimpleNamespace(success=True)

    with mock.patch("app.routes.feed_routes.writer_client") as writer:
        writer.update.side_effect = _update
        ok = client.patch(
            f"/api/feeds/{feed_id}/settings",
            json={"trim_silence": True, "normalize_loudness": False},
        )
        bad = client.patch(
            f"/api/feeds/{feed_id}/settings", json={"trim_silence": "yes"}
        )

    assert ok.status_code == 200
    assert ok.get_json()["trim_silence"] is True
    assert ok.get_json()["normalize_loudness"] is False
    assert bad.status_code == 400


def test_windows_are_reported_even_if_chapter_rewrite_fails(tmp_path: Path) -> None:
    path = _tone_silence_tone(tmp_path)

    with mock.patch(
        "podcast_processor.audio_polish.write_adjusted_chapters",
        side_effect=RuntimeError("mutagen failed"),
    ):
        windows = polish_audio(str(path), PolishOptions(trim_silence=True))

    # The audio was already trimmed, so callers must still shift their data.
    assert len(windows) == 1


def test_polish_options_are_read_before_processing_not_in_finalize() -> None:
    """finalize must not lazy-load post.feed (the post is expired by then)."""
    feed = Feed(
        title="RK",
        rss_url="u",
        ad_detection_strategy="llm",
        trim_silence=True,
        normalize_loudness=None,
    )
    processor = object.__new__(PodcastProcessor)
    steps = mock.MagicMock()
    processor._perform_processing_steps = steps
    processor.status_manager = mock.MagicMock()
    processor.logger = mock.MagicMock()
    processor._check_existing_processed_audio = mock.MagicMock(return_value=False)
    processor._simulate_developer_processing = mock.MagicMock(return_value=None)
    processor._handle_download_step = mock.MagicMock()
    processor._raise_if_cancelled = mock.MagicMock()
    processor._acquire_processing_lock = mock.MagicMock(return_value="/nope/out.mp3")
    processor.config = mock.MagicMock(enable_llm_chapter_fallback_tagging=False)
    processor.db_session = mock.MagicMock()
    post = Post(id=1, guid="g", title="t", whitelisted=True, feed=feed)
    processor.db_session.get.return_value = ProcessingJob(id="j", current_step=0)

    processor.process(post, "j")

    assert steps.call_args.kwargs["polish_options"] == PolishOptions(
        trim_silence=True, normalize_loudness=False
    )

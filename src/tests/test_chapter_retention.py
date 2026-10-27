"""Chapter markers must follow the audio after segments are cut out."""

import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

from app.models import Post, ProcessingJob
from podcast_processor.audio import clip_segments_with_fade
from podcast_processor.chapter_reader import Chapter, read_chapters
from podcast_processor.chapter_writer import write_adjusted_chapters, write_chapters
from podcast_processor.podcast_processor import PodcastProcessor
from shared.test_utils import create_standard_test_config

TEST_MP3 = Path(__file__).parent / "data" / "count_0_99.mp3"


def _mp3_with_chapters(tmp_path: Path) -> Path:
    source = tmp_path / "source.mp3"
    shutil.copyfile(TEST_MP3, source)
    write_chapters(
        str(source),
        [
            Chapter("c0", "Intro", 0, 10_000),
            Chapter("c1", "Werbung", 10_000, 20_000),
            Chapter("c2", "Thema", 20_000, 40_000),
        ],
    )
    return source


def test_ffmpeg_cut_keeps_stale_chapter_times(tmp_path: Path) -> None:
    # Documents why the processor must rewrite chapters after every cut.
    source = _mp3_with_chapters(tmp_path)
    out = tmp_path / "out.mp3"

    clip_segments_with_fade([(10_000, 20_000)], 0, str(source), str(out))

    stale = read_chapters(str(out))
    assert [c.title for c in stale] == ["Intro", "Werbung", "Thema"]
    assert stale[2].start_time_ms >= 19_000


def test_adjusted_chapters_follow_cut_audio(tmp_path: Path) -> None:
    source = _mp3_with_chapters(tmp_path)
    out = tmp_path / "out.mp3"
    clip_segments_with_fade([(10_000, 20_000)], 0, str(source), str(out))

    write_adjusted_chapters(str(out), read_chapters(str(source)), [(10.0, 20.0)])

    chapters = read_chapters(str(out))
    assert [c.title for c in chapters] == ["Intro", "Thema"]
    assert [(c.start_time_ms, c.end_time_ms) for c in chapters] == [
        (0, 10_000),
        (10_000, 30_000),
    ]


def _llm_processor(fallback_enabled: bool) -> PodcastProcessor:
    config = create_standard_test_config()
    config.enable_llm_chapter_fallback_tagging = fallback_enabled
    processor = object.__new__(PodcastProcessor)
    processor.config = config
    processor.logger = MagicMock()
    processor.transcription_manager = MagicMock()
    processor.transcription_manager.transcribe.return_value = [
        SimpleNamespace(sequence_num=0, start_time=0.0, end_time=5.0, text="hi")
    ]
    processor.audio_processor = MagicMock()
    processor.audio_processor.process_audio.return_value = [(10_000, 20_000)]
    processor.status_manager = MagicMock()
    processor._classify_ad_segments = MagicMock()
    processor._finalize_processing = MagicMock()
    return processor


def _post() -> Post:
    return Post(
        id=1,
        feed_id=1,
        guid="g",
        title="Episode",
        download_url="https://example.com/e.mp3",
        unprocessed_audio_path="/tmp/input.mp3",
    )


def test_llm_path_rewrites_embedded_chapters_without_fallback_tagging() -> None:
    processor = _llm_processor(fallback_enabled=False)
    finalize_mock = cast(MagicMock, processor._finalize_processing)
    embedded = [Chapter("c0", "Intro", 0, 10_000), Chapter("c1", "B", 10_000, 50_000)]
    job = ProcessingJob(id="job", post_guid="g", status="running")

    with (
        patch(
            "podcast_processor.podcast_processor.read_chapters",
            return_value=embedded,
        ) as read_mock,
        patch(
            "podcast_processor.podcast_processor.write_adjusted_chapters"
        ) as write_mock,
    ):
        processor._perform_llm_based_processing(_post(), job, "/tmp/out.mp3")

    read_mock.assert_called_once_with("/tmp/input.mp3")
    write_mock.assert_called_once_with(
        audio_path="/tmp/out.mp3",
        chapters_to_keep=embedded,
        removed_segments=[(10.0, 20.0)],
    )
    # Without fallback tagging no Podly chapter list is added to the feed.
    assert finalize_mock.call_args.kwargs["chapter_data"] is None


def test_llm_path_without_embedded_chapters_writes_nothing() -> None:
    processor = _llm_processor(fallback_enabled=False)
    job = ProcessingJob(id="job", post_guid="g", status="running")

    with (
        patch("podcast_processor.podcast_processor.read_chapters", return_value=[]),
        patch(
            "podcast_processor.podcast_processor.write_adjusted_chapters"
        ) as write_mock,
    ):
        processor._perform_llm_based_processing(_post(), job, "/tmp/out.mp3")

    write_mock.assert_not_called()

"""Chapter strategy falls back to LLM detection for episodes without chapters."""

import logging
from typing import cast
from unittest.mock import MagicMock, patch

from app.models import Post, ProcessingJob
from podcast_processor.chapter_ad_detector import ChapterDetectionError
from podcast_processor.podcast_processor import PodcastProcessor


def _processor() -> PodcastProcessor:
    processor = object.__new__(PodcastProcessor)
    processor.logger = logging.getLogger("test")
    processor.status_manager = MagicMock()
    processor._perform_llm_based_processing = MagicMock()
    processor._finalize_processing = MagicMock()
    return processor


def _post() -> Post:
    return Post(id=3, guid="g", title="Stammtisch", unprocessed_audio_path="/in.mp3")


def test_episode_without_chapters_uses_llm_detection() -> None:
    processor = _processor()
    post = _post()
    job = ProcessingJob(id="job", post_guid="g", status="running")

    with patch(
        "podcast_processor.podcast_processor.ChapterAdDetector.detect",
        side_effect=ChapterDetectionError("No chapters found"),
    ):
        processor._perform_chapter_based_processing(
            post, job, "/out.mp3", None, "werbung", True
        )

    llm_mock = cast(MagicMock, processor._perform_llm_based_processing)
    llm_mock.assert_called_once_with(
        post, job, "/out.mp3", None, True, polish_options=None
    )
    cast(MagicMock, processor._finalize_processing).assert_not_called()


def test_dispatch_passes_chapter_fallback_flag_to_chapter_strategy() -> None:
    processor = object.__new__(PodcastProcessor)
    chapter_mock = MagicMock()
    with patch.object(
        PodcastProcessor, "_perform_chapter_based_processing", chapter_mock
    ):
        processor._perform_processing_steps(
            _post(),
            ProcessingJob(),
            "/out.mp3",
            None,
            "chapter",
            "werbung",
            False,
        )

    assert chapter_mock.call_args.args[-2:] == ("werbung", False)

"""Transcripts in every mode and AI summaries."""

import json
import logging
from types import SimpleNamespace
from typing import Any, cast
from unittest import mock

from app.extensions import db
from app.feeds import build_post_feed_description_html
from app.models import Feed, Post, ProcessingJob
from app.routes.feed_routes import feed_bp
from podcast_processor.chapter_reader import Chapter
from podcast_processor.episode_extras import (
    ExtrasOptions,
    content_text,
    summarize_transcript,
)
from podcast_processor.podcast_processor import PodcastProcessor


def _seg(start: float, end: float, text: str) -> SimpleNamespace:
    return SimpleNamespace(start_time=start, end_time=end, text=text)


def _response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content), finish_reason="stop"
            )
        ]
    )


LLM = {
    "llm_model": "openai/fake",
    "llm_api_key": "k",
    "openai_base_url": None,
    "timeout_sec": 30,
}


def test_extras_from_feed() -> None:
    feed = SimpleNamespace(always_transcribe=None, generate_summary=True, language="de")
    extras = ExtrasOptions.from_feed(feed)
    assert extras == ExtrasOptions(False, True, "de")
    assert extras.needs_transcript
    assert not ExtrasOptions.from_feed(None).needs_transcript


def test_content_text_leaves_out_removed_parts() -> None:
    segments = [_seg(0, 5, "Intro"), _seg(5, 9, "Werbung"), _seg(9, 12, "Thema")]
    assert content_text(segments, [(5.0, 9.0)]) == "Intro\nThema"


def test_summary_single_request_in_feed_language() -> None:
    segments = [_seg(i, i + 1, f"Satz {i} über den Amiga 500.") for i in range(20)]
    with mock.patch(
        "podcast_processor.episode_extras.litellm.completion",
        return_value=_response("Überblick.\n\n- Amiga"),
    ) as completion:
        summary = summarize_transcript(
            segments,
            [],
            language="de",
            **LLM,  # type: ignore[arg-type]
        )

    assert summary == "Überblick.\n\n- Amiga"
    assert completion.call_count == 1
    prompt = completion.call_args.kwargs["messages"][1]["content"]
    assert "in German" in prompt
    assert "Satz 3 über den Amiga 500." in prompt


def test_long_transcript_is_summarized_in_parts() -> None:
    segments = [_seg(i, i + 1, "x" * 90) for i in range(30)]
    with mock.patch(
        "podcast_processor.episode_extras.litellm.completion",
        side_effect=[
            _response("- a"),
            _response("- b"),
            _response("- c"),
            _response("Fertig"),
        ],
    ) as completion:
        summary = summarize_transcript(
            segments,
            [],
            language="auto",
            chunk_chars=1000,
            **LLM,  # type: ignore[arg-type]
        )

    assert summary == "Fertig"
    assert completion.call_count == 4
    final_prompt = completion.call_args.kwargs["messages"][1]["content"]
    assert "Notes on the parts" in final_prompt
    assert "main language of the transcript" in final_prompt


def test_summary_failures_return_none() -> None:
    segments = [_seg(i, i + 1, "Ein ganz normaler Satz.") for i in range(20)]
    with mock.patch(
        "podcast_processor.episode_extras.litellm.completion",
        side_effect=RuntimeError("rate limited"),
    ):
        assert summarize_transcript(segments, [], language="de", **LLM) is None  # type: ignore[arg-type]
    assert summarize_transcript([_seg(0, 1, "kurz")], [], language="de", **LLM) is None  # type: ignore[arg-type]
    no_model = {**LLM, "llm_model": None}
    assert summarize_transcript(segments, [], language="de", **no_model) is None  # type: ignore[arg-type]


def _chapter_processor() -> PodcastProcessor:
    processor = object.__new__(PodcastProcessor)
    processor.logger = logging.getLogger("test")
    processor.status_manager = mock.MagicMock()
    processor.transcription_manager = mock.MagicMock()
    processor._finalize_processing = mock.MagicMock()
    return processor


def test_chapter_strategy_transcribes_when_enabled(tmp_path: Any) -> None:
    processor = _chapter_processor()
    source = tmp_path / "in.mp3"
    source.write_bytes(b"x")
    post = Post(id=5, guid="g", title="t", unprocessed_audio_path=str(source))
    job = ProcessingJob(id="j", post_guid="g", status="running")
    chapters = [Chapter("c", "Thema", 0, 1000)]
    extras = ExtrasOptions(always_transcribe=True, language="de")

    with (
        mock.patch(
            "podcast_processor.podcast_processor.ChapterAdDetector.detect",
            return_value=([], chapters, []),
        ),
        mock.patch("podcast_processor.podcast_processor.write_adjusted_chapters"),
    ):
        processor._perform_chapter_based_processing(
            post, job, str(tmp_path / "out.mp3"), None, "werbung", extras=extras
        )

    transcribe = cast(mock.MagicMock, processor.transcription_manager).transcribe
    transcribe.assert_called_once_with(post, language="de")
    finalize = cast(mock.MagicMock, processor._finalize_processing)
    assert finalize.call_args.kwargs["extras"] == extras


def test_chapter_strategy_survives_transcription_failure(tmp_path: Any) -> None:
    processor = _chapter_processor()
    cast(
        mock.MagicMock, processor.transcription_manager
    ).transcribe.side_effect = RuntimeError("quota")
    source = tmp_path / "in.mp3"
    source.write_bytes(b"x")
    post = Post(id=5, guid="g", title="t", unprocessed_audio_path=str(source))

    with (
        mock.patch(
            "podcast_processor.podcast_processor.ChapterAdDetector.detect",
            return_value=([], [Chapter("c", "Thema", 0, 1000)], []),
        ),
        mock.patch("podcast_processor.podcast_processor.write_adjusted_chapters"),
    ):
        processor._perform_chapter_based_processing(
            post,
            ProcessingJob(id="j"),
            str(tmp_path / "out.mp3"),
            None,
            "werbung",
            extras=ExtrasOptions(generate_summary=True),
        )

    cast(mock.MagicMock, processor._finalize_processing).assert_called_once()


def test_finalize_stores_summary_when_enabled() -> None:
    processor = object.__new__(PodcastProcessor)
    processor.logger = mock.MagicMock()
    processor.status_manager = mock.MagicMock()
    processor._remove_unprocessed_audio = mock.MagicMock()

    with (
        mock.patch.object(
            PodcastProcessor, "_summary_for_post", return_value="Kurz.\n- Punkt"
        ) as summary_mock,
        mock.patch(
            "podcast_processor.podcast_processor.get_audio_duration_ms",
            return_value=None,
        ),
        mock.patch("podcast_processor.podcast_processor.writer_client") as writer,
    ):
        writer.update.return_value = SimpleNamespace(success=True)
        processor._finalize_processing(
            Post(id=9, guid="g"),
            ProcessingJob(),
            "/o.mp3",
            removed_segments=[(1.0, 2.0)],
            extras=ExtrasOptions(generate_summary=True, language="de"),
        )

    summary_mock.assert_called_once_with(9, [(1.0, 2.0)], "de")
    assert writer.update.call_args.args[2]["summary"] == "Kurz.\n- Punkt"


def test_summary_is_rendered_first_and_escaped() -> None:
    post = Post(
        title="t",
        description="<p>Original</p>",
        summary="Überblick <b>fett</b>.\n\n- Amiga & Atari\n- C64",
    )

    html_text = build_post_feed_description_html(post)

    assert html_text.startswith("<p><strong>Podly Summary</strong></p>")
    assert "<p>Überblick &lt;b&gt;fett&lt;/b&gt;.</p>" in html_text
    assert "<ul><li>Amiga &amp; Atari</li><li>C64</li></ul>" in html_text
    assert html_text.index("Podly Summary") < html_text.index("<p>Original</p>")


def test_settings_accept_extras_flags(app: Any) -> None:
    app.testing = True
    app.register_blueprint(feed_bp)
    with app.app_context():
        feed = Feed(title="RK", rss_url="https://example.com/extras.xml")
        db.session.add(feed)
        db.session.commit()
        feed_id = feed.id

    def _update(model: str, model_id: int, updates: dict[str, Any], wait: bool = True):
        Feed.query.filter_by(id=model_id).update(updates)
        db.session.commit()
        return SimpleNamespace(success=True)

    with mock.patch("app.routes.feed_routes.writer_client") as writer:
        writer.update.side_effect = _update
        response = app.test_client().patch(
            f"/api/feeds/{feed_id}/settings",
            json={"always_transcribe": True, "generate_summary": True},
        )

    body = json.loads(response.get_data(as_text=True))
    assert body["always_transcribe"] is True
    assert body["generate_summary"] is True

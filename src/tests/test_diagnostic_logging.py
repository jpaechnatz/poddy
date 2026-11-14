"""Log lines that tell why something did not show up."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest

from podcast_processor import episode_extras
from podcast_processor.episode_extras import summarize_transcript


def test_feed_requests_are_logged_without_query(
    app: Any, caplog: pytest.LogCaptureFixture
) -> None:
    from app import _register_api_logging

    app.testing = True
    _register_api_logging(app)

    @app.route("/post/<path:guid>/transcript.vtt")
    def _vtt(guid: str) -> Any:
        return "WEBVTT"

    global_logger = logging.getLogger("global_logger")
    with caplog.at_level(logging.INFO, logger="global_logger"):
        global_logger.addHandler(caplog.handler)
        try:
            app.test_client().get(
                "/post/ep1/transcript.vtt?feed_token=abc&feed_secret=SECRET",
                headers={"User-Agent": "iCatcher!/15.2.2", "If-None-Match": '"x"'},
            )
        finally:
            global_logger.removeHandler(caplog.handler)

    lines = [r.getMessage() for r in caplog.records if "[FEED]" in r.getMessage()]
    assert lines == [
        "[FEED] GET /post/ep1/transcript.vtt status=200 cond=etag "
        "agent=iCatcher!/15.2.2"
    ]
    assert "SECRET" not in caplog.text


def test_empty_summary_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    segments = [
        SimpleNamespace(start_time=i, end_time=i + 1, text="Ein ganz normaler Satz.")
        for i in range(20)
    ]
    empty = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=""), finish_reason="length")
        ]
    )
    with (
        mock.patch.object(episode_extras.litellm, "completion", return_value=empty),
        caplog.at_level(logging.WARNING, logger="global_logger"),
    ):
        logging.getLogger("global_logger").addHandler(caplog.handler)
        try:
            result = summarize_transcript(
                segments,
                [],
                llm_model="openrouter/x",
                llm_api_key="k",
                openai_base_url=None,
                timeout_sec=30,
                language="de",
            )
        finally:
            logging.getLogger("global_logger").removeHandler(caplog.handler)

    assert result is None
    assert "Summary came back empty (finish_reason=length)" in caplog.text

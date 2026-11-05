"""Remote Whisper retries chunks that a routed provider cannot transcribe."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest import mock

import httpx
import pytest
from openai import BadRequestError
from openai.types.audio.transcription_segment import TranscriptionSegment

from podcast_processor import transcribe
from podcast_processor.transcribe import CHUNK_ATTEMPTS, OpenAIWhisperTranscriber
from shared.config import RemoteWhisperConfig


def _segment() -> TranscriptionSegment:
    return TranscriptionSegment(
        id=0,
        avg_logprob=0.0,
        compression_ratio=1.0,
        end=2.0,
        no_speech_prob=0.0,
        seek=0,
        start=0.0,
        temperature=0.0,
        text="Hallo",
        tokens=[1],
    )


def _bad_request(message: str) -> BadRequestError:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/audio/transcriptions")
    body = {"error": {"message": message, "code": 400}}
    return BadRequestError(
        f"Error code: 400 - {body}",
        response=httpx.Response(400, request=request, json=body),
        body=body,
    )


@pytest.fixture
def transcriber(tmp_path: Any) -> tuple[OpenAIWhisperTranscriber, str, mock.Mock]:
    chunk = tmp_path / "2.mp3"
    chunk.write_bytes(b"audio")
    t = OpenAIWhisperTranscriber(
        logging.getLogger("test"),
        RemoteWhisperConfig(
            api_key="k",
            base_url="https://openrouter.ai/api/v1",
            model="openai/whisper-large-v3-turbo",
        ),
    )
    create = mock.Mock()
    t.openai_client = SimpleNamespace(
        audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create))
    )
    return t, str(chunk), create


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transcribe.time, "sleep", lambda _s: None)


def test_missing_segments_are_retried(transcriber: Any) -> None:
    t, chunk, create = transcriber
    create.side_effect = [
        SimpleNamespace(segments=None),
        SimpleNamespace(segments=[_segment()]),
    ]
    assert [s.text for s in t.get_segments_for_chunk(chunk, "de")] == ["Hallo"]
    assert create.call_count == 2


def test_provider_400_is_retried(transcriber: Any) -> None:
    t, chunk, create = transcriber
    create.side_effect = [
        _bad_request("Provider returned 400"),
        SimpleNamespace(segments=[_segment()]),
    ]
    assert len(t.get_segments_for_chunk(chunk, "de")) == 1
    assert create.call_count == 2


def test_other_400_fails_at_once(transcriber: Any) -> None:
    t, chunk, create = transcriber
    create.side_effect = _bad_request("Invalid file format")
    with pytest.raises(BadRequestError):
        t.get_segments_for_chunk(chunk, "de")
    assert create.call_count == 1


def test_gives_up_after_all_attempts(transcriber: Any) -> None:
    t, chunk, create = transcriber
    create.side_effect = [SimpleNamespace(segments=None)] * CHUNK_ATTEMPTS
    with pytest.raises(RuntimeError, match="no segment timestamps"):
        t.get_segments_for_chunk(chunk, "de")
    assert create.call_count == CHUNK_ATTEMPTS

    create.reset_mock()
    create.side_effect = [_bad_request("Provider returned 400")] * CHUNK_ATTEMPTS
    with pytest.raises(BadRequestError):
        t.get_segments_for_chunk(chunk, "de")
    assert create.call_count == CHUNK_ATTEMPTS


def test_first_answer_with_segments_needs_one_request(transcriber: Any) -> None:
    t, chunk, create = transcriber
    create.return_value = SimpleNamespace(segments=[_segment()])
    assert len(t.get_segments_for_chunk(chunk, "auto")) == 1
    assert create.call_count == 1
    assert create.call_args.kwargs["response_format"] == "verbose_json"

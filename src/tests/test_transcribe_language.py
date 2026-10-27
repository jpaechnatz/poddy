"""Language "auto" lets the transcription model detect the language."""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from groq import Omit as GroqOmit
from openai import Omit

from app.whisper_languages import normalize_whisper_language
from podcast_processor.transcribe import (
    GroqWhisperTranscriber,
    OpenAIWhisperTranscriber,
    explicit_language,
)
from shared.config import GroqWhisperConfig, RemoteWhisperConfig


@pytest.mark.parametrize(
    ("language", "expected"),
    [("de", "de"), ("auto", None), ("AUTO", None), ("", None), (None, None)],
)
def test_explicit_language(language: str | None, expected: str | None) -> None:
    assert explicit_language(language) == expected


def test_auto_is_a_valid_feed_language() -> None:
    assert normalize_whisper_language("auto") == "auto"


def _remote(tmp_path) -> tuple[OpenAIWhisperTranscriber, MagicMock, str]:
    transcriber = OpenAIWhisperTranscriber(
        logging.getLogger("test"),
        RemoteWhisperConfig(
            api_key="sk-or",
            base_url="https://openrouter.ai/api/v1",
            model="mistralai/voxtral-small-transcribe-3-0",
        ),
    )
    client = MagicMock()
    client.audio.transcriptions.create.return_value = SimpleNamespace(segments=[])
    transcriber.openai_client = client
    chunk = tmp_path / "chunk.mp3"
    chunk.write_bytes(b"x")
    return transcriber, client, str(chunk)


def test_remote_auto_omits_language(tmp_path) -> None:
    transcriber, client, chunk = _remote(tmp_path)

    transcriber.get_segments_for_chunk(chunk, language="auto")

    kwargs = client.audio.transcriptions.create.call_args.kwargs
    assert isinstance(kwargs["language"], Omit)  # SDK leaves it out
    assert kwargs["response_format"] == "verbose_json"
    assert kwargs["model"] == "mistralai/voxtral-small-transcribe-3-0"


def test_remote_fixed_language_is_sent(tmp_path) -> None:
    transcriber, client, chunk = _remote(tmp_path)

    transcriber.get_segments_for_chunk(chunk, language="de")

    assert client.audio.transcriptions.create.call_args.kwargs["language"] == "de"


def test_groq_auto_omits_language(tmp_path) -> None:
    transcriber = GroqWhisperTranscriber(
        logging.getLogger("test"), GroqWhisperConfig(api_key="gsk")
    )
    client = MagicMock()
    client.audio.transcriptions.create.return_value = SimpleNamespace(segments=[])
    transcriber.client = client
    chunk = tmp_path / "c.mp3"
    chunk.write_bytes(b"x")

    transcriber.get_segments_for_chunk(str(chunk), language="auto")

    language = client.audio.transcriptions.create.call_args.kwargs["language"]
    assert isinstance(language, GroqOmit)

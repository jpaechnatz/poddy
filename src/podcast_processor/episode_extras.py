"""Optional per-feed extras: transcripts in every mode and AI summaries."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import litellm

from podcast_processor.llm_model_call_utils import (
    extract_litellm_content,
    extract_litellm_finish_reason,
)
from shared.llm_utils import model_uses_max_completion_tokens

logger = logging.getLogger("global_logger")

# Transcript characters per LLM request. Longer episodes are summarized in
# parts first (map) and the part notes are then summarized (reduce).
SUMMARY_CHUNK_CHARS = 40_000
SUMMARY_MAX_OUTPUT_TOKENS = 900

_LANGUAGE_NAMES = {
    "ar": "Arabic",
    "zh": "Chinese",
    "da": "Danish",
    "nl": "Dutch",
    "en": "English",
    "fi": "Finnish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "no": "Norwegian",
    "pl": "Polish",
    "pt": "Portuguese",
    "ru": "Russian",
    "es": "Spanish",
    "sv": "Swedish",
}

_SYSTEM_PROMPT = (
    "You write concise, factual summaries of podcast episodes for show notes. "
    "Only use what the transcript says. Never mention ads, sponsors or "
    "promo codes."
)


@dataclass(frozen=True)
class ExtrasOptions:
    always_transcribe: bool = False
    generate_summary: bool = False
    language: str | None = None

    @property
    def needs_transcript(self) -> bool:
        return self.always_transcribe or self.generate_summary

    @classmethod
    def from_feed(cls, feed: Any | None) -> "ExtrasOptions":
        if feed is None:
            return cls()
        return cls(
            always_transcribe=bool(getattr(feed, "always_transcribe", False)),
            generate_summary=bool(getattr(feed, "generate_summary", False)),
            language=getattr(feed, "language", None),
        )


def _inside(t: float, windows: Sequence[tuple[float, float]]) -> bool:
    return any(start <= t < end for start, end in windows)


def content_text(
    segments: Sequence[Any], removed_windows: Sequence[tuple[float, float]]
) -> str:
    """Transcript text without segments that were cut out (ads, music)."""
    lines = []
    for segment in sorted(segments, key=lambda s: float(s.start_time)):
        middle = (float(segment.start_time) + float(segment.end_time)) / 2.0
        text = " ".join(str(segment.text or "").split())
        if text and not _inside(middle, removed_windows):
            lines.append(text)
    return "\n".join(lines)


def _chunks(text: str, size: int) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for line in text.splitlines():
        if current and length + len(line) > size:
            chunks.append("\n".join(current))
            current, length = [], 0
        current.append(line)
        length += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


def _language_name(language: str | None) -> str:
    if language and language in _LANGUAGE_NAMES:
        return _LANGUAGE_NAMES[language]
    return "the main language of the transcript"


def _complete(prompt: str, llm: dict[str, Any]) -> tuple[str, str | None]:
    model = llm["llm_model"]
    args: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "timeout": int(llm.get("timeout_sec") or 300),
        "api_key": llm.get("llm_api_key"),
        "base_url": llm.get("openai_base_url"),
    }
    if model_uses_max_completion_tokens(model):
        args["max_completion_tokens"] = SUMMARY_MAX_OUTPUT_TOKENS
    else:
        args["max_tokens"] = SUMMARY_MAX_OUTPUT_TOKENS
    response = litellm.completion(**args)
    return extract_litellm_content(response).strip(), extract_litellm_finish_reason(
        response
    )


def summarize_transcript(
    segments: Sequence[Any],
    removed_windows: Sequence[tuple[float, float]],
    *,
    llm_model: str | None,
    llm_api_key: str | None,
    openai_base_url: str | None,
    timeout_sec: int,
    language: str | None,
    chunk_chars: int = SUMMARY_CHUNK_CHARS,
) -> str | None:
    """Return an episode summary (overview + "- " bullet lines) or None.

    Errors are logged, never raised: a summary is a bonus, not a requirement.
    """
    if not llm_model:
        return None
    text = content_text(segments, removed_windows)
    if len(text) < 200:
        logger.info("Transcript too short for a summary")
        return None
    llm = {
        "llm_model": llm_model,
        "llm_api_key": llm_api_key,
        "openai_base_url": openai_base_url,
        "timeout_sec": timeout_sec,
    }
    language_name = _language_name(language)
    try:
        parts = _chunks(text, chunk_chars)
        if len(parts) > 1:
            notes = []
            for index, part in enumerate(parts, start=1):
                note, _ = _complete(
                    f"This is part {index} of {len(parts)} of a podcast transcript. "
                    f"List its main topics and key points as 3-8 short bullet "
                    f"points in {language_name}.\n\nTranscript part:\n{part}",
                    llm,
                )
                notes.append(note)
            source = "Notes on the parts of the episode, in order:\n\n" + "\n\n".join(
                notes
            )
        else:
            source = "Transcript:\n" + text

        summary, finish_reason = _complete(
            f"Write show-notes for this podcast episode in {language_name}. "
            "Format: an overview of 2-4 sentences, then an empty line, then 3-7 "
            "bullet points starting with '- ' naming the main topics. No "
            f"headings, no preamble.\n\n{source}",
            llm,
        )
        if finish_reason == "length":
            logger.warning("Summary hit the output limit and may be cut off")
        return summary or None
    except Exception as e:  # noqa: BLE001
        logger.warning("Summary generation failed: %s", e)
        return None

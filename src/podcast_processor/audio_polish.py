"""Optional per-feed audio polishing: shorten long silences, normalize loudness.

Runs on the finished processed MP3. Shortening silences moves every later
moment, so chapters are rewritten with adjusted times and the removed windows
are returned for other timestamp consumers.
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

import ffmpeg

from podcast_processor.chapter_reader import read_chapters
from podcast_processor.chapter_writer import write_adjusted_chapters

logger = logging.getLogger("global_logger")

# Quieter than this counts as silence.
SILENCE_NOISE_DB = -50
# Only pauses at least this long are shortened; normal speech pauses stay.
SILENCE_MIN_SECONDS = 2.0
# How much of each long pause is kept, split evenly around the cut.
SILENCE_KEEP_SECONDS = 0.6
# EBU R128 podcast targets (Apple/Spotify recommend about -16 LUFS).
LOUDNORM_TARGET_I = -16.0
LOUDNORM_TARGET_TP = -1.5
LOUDNORM_TARGET_LRA = 11.0

_SILENCE_START_RE = re.compile(r"silence_start:\s*(-?[0-9.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*(-?[0-9.]+)")


@dataclass(frozen=True)
class PolishOptions:
    trim_silence: bool = False
    normalize_loudness: bool = False

    @property
    def enabled(self) -> bool:
        return self.trim_silence or self.normalize_loudness


def detect_silences(
    path: str,
    noise_db: float = SILENCE_NOISE_DB,
    min_seconds: float = SILENCE_MIN_SECONDS,
) -> list[tuple[float, float]]:
    """Return (start, end) seconds of silences at least min_seconds long."""
    _, stderr = (
        ffmpeg.input(path)
        .filter("silencedetect", noise=f"{noise_db}dB", d=min_seconds)
        .output("-", format="null")
        .run(capture_stdout=True, capture_stderr=True)
    )
    text = stderr.decode("utf-8", errors="replace")
    starts = [float(m) for m in _SILENCE_START_RE.findall(text)]
    ends = [float(m) for m in _SILENCE_END_RE.findall(text)]
    duration = _duration_seconds(path)
    silences: list[tuple[float, float]] = []
    for index, start in enumerate(starts):
        # A silence running to the end of the file has no silence_end line.
        end = ends[index] if index < len(ends) else duration
        if end is not None and end > start:
            silences.append((max(0.0, start), end))
    return silences


def silence_cut_windows(
    silences: list[tuple[float, float]],
    keep_seconds: float = SILENCE_KEEP_SECONDS,
) -> list[tuple[float, float]]:
    """Turn silences into windows to remove, keeping keep_seconds of each."""
    half_keep = keep_seconds / 2.0
    windows: list[tuple[float, float]] = []
    for start, end in silences:
        cut_start = round(start + half_keep, 3)
        cut_end = round(end - half_keep, 3)
        if cut_end > cut_start:
            windows.append((cut_start, cut_end))
    return windows


def polish_audio(path: str, options: PolishOptions) -> list[tuple[float, float]]:
    """Polish the MP3 at path in place.

    Returns the removed windows in seconds (relative to the file before
    polishing). Failures are logged and leave the file unchanged, because a
    missing polish step must not fail an otherwise processed episode.
    """
    if not options.enabled:
        return []

    try:
        windows = (
            silence_cut_windows(detect_silences(path)) if options.trim_silence else []
        )
        if not windows and not options.normalize_loudness:
            logger.info("No long silences found in %s", path)
            return []

        chapters = read_chapters(path)
        sample_rate, bitrate = _stream_format(path)
        loudnorm_args = (
            _measure_loudness(path, windows) if options.normalize_loudness else None
        )

        tmp_path = f"{path}.polish.mp3"
        stream = _apply_cuts(ffmpeg.input(path).audio, windows)
        if loudnorm_args is not None:
            stream = stream.filter("loudnorm", **loudnorm_args).filter(
                "aresample", sample_rate
            )
        try:
            (
                stream.output(tmp_path, acodec="libmp3lame", **{"b:a": bitrate})
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    except Exception as e:  # noqa: BLE001
        stderr = getattr(e, "stderr", b"") or b""
        logger.warning(
            "Audio polishing failed for %s, keeping unpolished audio: %s %s",
            path,
            e,
            stderr.decode("utf-8", errors="replace")[-500:],
        )
        return []

    # The file is polished now: callers must learn the removed windows even if
    # rewriting chapters fails, or transcript and chapter data would drift.
    if chapters:
        try:
            write_adjusted_chapters(path, chapters, windows)
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not rewrite chapters after polishing %s: %s", path, e)

    logger.info(
        "Polished %s: removed %d silences (%.1fs), loudness normalized=%s",
        path,
        len(windows),
        sum(end - start for start, end in windows),
        loudnorm_args is not None,
    )
    return windows


def _apply_cuts(stream: Any, windows: list[tuple[float, float]]) -> Any:
    if not windows:
        return stream
    removed = "+".join(f"between(t,{start:.3f},{end:.3f})" for start, end in windows)
    return stream.filter("aselect", f"not({removed})").filter("asetpts", "N/SR/TB")


def _measure_loudness(
    path: str, windows: list[tuple[float, float]]
) -> dict[str, object]:
    """First loudnorm pass; returns arguments for an accurate linear second pass."""
    target: dict[str, object] = {
        "I": LOUDNORM_TARGET_I,
        "TP": LOUDNORM_TARGET_TP,
        "LRA": LOUDNORM_TARGET_LRA,
    }
    _, stderr = (
        _apply_cuts(ffmpeg.input(path).audio, windows)
        .filter("loudnorm", print_format="json", **target)
        .output("-", format="null")
        .run(capture_stdout=True, capture_stderr=True)
    )
    text = stderr.decode("utf-8", errors="replace")
    json_start = text.rfind("{")
    json_end = text.rfind("}")
    try:
        measured = json.loads(text[json_start : json_end + 1])
        return {
            **target,
            "measured_I": measured["input_i"],
            "measured_TP": measured["input_tp"],
            "measured_LRA": measured["input_lra"],
            "measured_thresh": measured["input_thresh"],
            "offset": measured["target_offset"],
            "linear": "true",
        }
    except (ValueError, KeyError) as e:
        logger.warning("Loudness measurement unreadable, using one pass: %s", e)
        return target


def _stream_format(path: str) -> tuple[int, str]:
    probe = ffmpeg.probe(path)
    audio = next(s for s in probe["streams"] if s.get("codec_type") == "audio")
    sample_rate = int(audio.get("sample_rate") or 44100)
    bit_rate = int(audio.get("bit_rate") or probe["format"].get("bit_rate") or 0)
    # Keep the episode's bitrate (clamped to sane MP3 values) and use CBR so
    # chapter seeking stays accurate.
    kbps = min(320, max(64, round(bit_rate / 1000) if bit_rate else 128))
    return sample_rate, f"{kbps}k"


def _duration_seconds(path: str) -> float | None:
    try:
        return float(ffmpeg.probe(path)["format"]["duration"])
    except (ffmpeg.Error, KeyError, ValueError):
        return None

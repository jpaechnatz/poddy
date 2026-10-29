"""Build WebVTT and SRT transcripts that match the processed (ad-free) audio.

Transcript segments carry source-audio times. Post.audio_edits records what
each processing pass removed, so times can be mapped onto the processed file.
Segments whose middle falls inside removed ad audio are left out.
"""

import json
from collections.abc import Iterable, Sequence
from typing import Any

Window = tuple[float, float]
# Passes in the order they were applied to the audio.
_PASSES = ("ads", "silence")


def parse_audio_edits(raw: str | None) -> list[list[Window]] | None:
    """Return the removed windows per pass, or None when unknown/invalid."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    passes: list[list[Window]] = []
    for name in _PASSES:
        windows: list[Window] = []
        for item in data.get(name) or []:
            try:
                start, end = float(item[0]), float(item[1])
            except (TypeError, ValueError, IndexError):
                return None
            if end > start:
                windows.append((start, end))
        passes.append(_merge(windows))
    return passes


def _merge(windows: Iterable[Window]) -> list[Window]:
    merged: list[Window] = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def map_time(t: float, windows: Sequence[Window]) -> float:
    """Map a time before one pass to the time after it.

    Times inside a removed window collapse onto the cut point.
    """
    removed = 0.0
    for start, end in windows:
        if end <= t:
            removed += end - start
        elif start < t:
            removed += t - start
        else:
            break
    return max(0.0, t - removed)


def _inside(t: float, windows: Sequence[Window]) -> bool:
    return any(start <= t < end for start, end in windows)


Cue = tuple[float, float, str]

# Transcript formats served next to the processed audio: path suffix ->
# (MIME type for podcast:transcript and the HTTP response).
TRANSCRIPT_FORMATS: dict[str, str] = {
    "vtt": "text/vtt",
    "srt": "application/x-subrip",
}


def _timestamp(seconds: float, separator: str = ".") -> str:
    millis = round(max(0.0, seconds) * 1000)
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def _plain_cue_text(text: str) -> str:
    # "-->" marks a timing line in both WebVTT and SRT, so it never appears
    # in cue text.
    return " ".join(text.split()).replace("-->", "→")


def build_cues(
    segments: Iterable[Any], passes: Sequence[Sequence[Window]]
) -> list[Cue]:
    """Map segments (start_time, end_time, text) onto the processed audio.

    Shared by every format so WebVTT and SRT always carry the same times.
    """
    ad_windows = passes[0] if passes else []
    cues: list[Cue] = []
    last_end = 0.0
    for segment in sorted(segments, key=lambda s: float(s.start_time)):
        text = _plain_cue_text(str(segment.text or ""))
        start, end = float(segment.start_time), float(segment.end_time)
        if not text or end <= start:
            continue
        if _inside((start + end) / 2.0, ad_windows):
            continue
        for windows in passes:
            start, end = map_time(start, windows), map_time(end, windows)
        start = max(start, last_end)
        if end - start < 0.05:
            continue
        cues.append((start, end, text))
        last_end = end
    return cues


def build_vtt(segments: Iterable[Any], passes: Sequence[Sequence[Window]]) -> str:
    """Render segments as WebVTT for the processed audio."""
    lines = ["WEBVTT", ""]
    for start, end, text in build_cues(segments, passes):
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lines.extend([f"{_timestamp(start)} --> {_timestamp(end)}", escaped, ""])
    return "\n".join(lines)


def build_srt(segments: Iterable[Any], passes: Sequence[Sequence[Window]]) -> str:
    """Render segments as SubRip (SRT) for the processed audio."""
    lines: list[str] = []
    for number, (start, end, text) in enumerate(build_cues(segments, passes), 1):
        lines.extend(
            [
                str(number),
                f"{_timestamp(start, ',')} --> {_timestamp(end, ',')}",
                text,
                "",
            ]
        )
    return "\n".join(lines)


_BUILDERS = {"vtt": build_vtt, "srt": build_srt}


def transcript_ready(post: Any) -> bool:
    """True when the post's processed audio has a known mapping for transcripts."""
    return (
        bool(getattr(post, "processed_audio_path", None))
        and not getattr(post, "processing_failed", False)
        and parse_audio_edits(getattr(post, "audio_edits", None)) is not None
    )


def post_ids_with_transcripts(post_ids: Sequence[int]) -> set[int]:
    """Return the ids among post_ids that have stored transcript segments."""
    from app.extensions import db
    from app.models import TranscriptSegment

    if not post_ids:
        return set()
    rows = (
        db.session.query(TranscriptSegment.post_id)
        .filter(TranscriptSegment.post_id.in_(list(post_ids)))
        .distinct()
        .all()
    )
    return {int(row[0]) for row in rows}


def render_post_transcript(post: Any, fmt: str = "vtt") -> str | None:
    """Transcript (WebVTT or SRT) for a processed post, or None when it cannot
    be built correctly."""
    from app.models import TranscriptSegment

    if not transcript_ready(post):
        return None
    passes = parse_audio_edits(post.audio_edits)
    if passes is None:
        return None
    segments = (
        TranscriptSegment.query.filter_by(post_id=post.id)
        .order_by(TranscriptSegment.sequence_num)
        .all()
    )
    if not segments:
        return None
    return _BUILDERS[fmt](segments, passes)

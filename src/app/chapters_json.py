"""Podcasting 2.0 JSON chapters built from the processed MP3.

The processed file carries the final chapters (adjusted for removed ads and
silences), including chapter images (APIC) and links (WXXX) kept from the
source, so the JSON always matches the audio the feed serves.
"""

import os
from typing import Any

from podcast_processor.chapter_reader import Chapter, read_chapters

CHAPTERS_JSON_VERSION = "1.2.0"
CHAPTERS_MIME_TYPE = "application/json+chapters"

_CACHE_MAX_ENTRIES = 4096
_chapter_cache: dict[tuple[str, int, int], list[Chapter]] = {}


def processed_chapters(path: str | None) -> list[Chapter]:
    """Chapters of a processed file; cached by mtime/size (feed renders)."""
    if not path:
        return []
    try:
        stat = os.stat(path)
    except OSError:
        return []
    key = (path, stat.st_mtime_ns, stat.st_size)
    cached = _chapter_cache.get(key)
    if cached is None:
        cached = read_chapters(path)
        if len(_chapter_cache) >= _CACHE_MAX_ENTRIES:
            _chapter_cache.clear()
        _chapter_cache[key] = cached
    return cached


def _sub_frame(chapter: Chapter, frame_id: str) -> Any | None:
    return next((f for f in chapter.sub_frames if f.FrameID == frame_id), None)


def chapter_image(chapter: Chapter) -> tuple[bytes, str] | None:
    frame = _sub_frame(chapter, "APIC")
    if frame is None or not getattr(frame, "data", None):
        return None
    return bytes(frame.data), str(getattr(frame, "mime", "") or "image/jpeg")


def build_chapters_json(
    chapters: list[Chapter], image_url_for_index: Any
) -> dict[str, Any]:
    """JSON chapters document; image_url_for_index(i) builds image URLs."""
    entries: list[dict[str, Any]] = []
    for index, chapter in enumerate(chapters):
        entry: dict[str, Any] = {
            "startTime": round(chapter.start_time_ms / 1000.0, 3),
            "title": chapter.title,
        }
        if chapter.end_time_ms > chapter.start_time_ms:
            entry["endTime"] = round(chapter.end_time_ms / 1000.0, 3)
        if chapter_image(chapter) is not None:
            entry["img"] = image_url_for_index(index)
        link = _sub_frame(chapter, "WXXX")
        if link is not None and getattr(link, "url", None):
            entry["url"] = str(link.url)
        entries.append(entry)
    return {"version": CHAPTERS_JSON_VERSION, "chapters": entries}

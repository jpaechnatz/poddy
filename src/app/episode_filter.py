"""Per-feed episode exclusion by title."""

from typing import Any

from podcast_processor.chapter_filter import parse_filter_strings


def is_title_excluded(feed: Any | None, title: str | None) -> bool:
    """True when the title contains one of the feed's exclude strings.

    Matching is a case-insensitive substring match, like chapter filters.
    """
    if feed is None or not title:
        return False
    raw = getattr(feed, "episode_title_exclude_strings", None)
    if not raw:
        return False
    lowered = title.lower()
    return any(term.lower() in lowered for term in parse_filter_strings(raw))


def is_post_excluded(post: Any) -> bool:
    return is_title_excluded(getattr(post, "feed", None), getattr(post, "title", None))

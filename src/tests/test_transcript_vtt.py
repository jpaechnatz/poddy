"""Transcripts delivered with the feed match the processed audio."""

import json
from types import SimpleNamespace
from typing import Any
from unittest import mock

from app.auth.middleware import _is_token_protected_endpoint
from app.extensions import db
from app.feeds import generate_feed_xml
from app.models import Feed, Post, ProcessingJob, TranscriptSegment
from app.routes.post_routes import post_bp
from app.runtime_config import config as runtime_config
from app.transcript_vtt import build_vtt, map_time, parse_audio_edits
from podcast_processor.podcast_processor import PodcastProcessor


def _seg(start: float, end: float, text: str) -> SimpleNamespace:
    return SimpleNamespace(start_time=start, end_time=end, text=text)


def test_map_time_skips_removed_windows() -> None:
    windows = [(10.0, 20.0), (30.0, 35.0)]
    assert map_time(5.0, windows) == 5.0
    assert map_time(15.0, windows) == 10.0  # inside a cut: snaps to the cut
    assert map_time(25.0, windows) == 15.0
    assert map_time(40.0, windows) == 25.0


def test_build_vtt_drops_ads_and_applies_both_passes() -> None:
    segments = [
        _seg(0.0, 4.0, "Hallo und willkommen"),
        _seg(10.0, 18.0, "Werbung für etwas"),
        _seg(20.0, 24.0, "Zurück <b>&</b> weiter --> los"),
    ]
    # Ads removed 10-19 s, then a silence 6.5-8.0 s of the cut file.
    vtt = build_vtt(segments, [[(10.0, 19.0)], [(6.5, 8.0)]])

    assert vtt.startswith("WEBVTT\n\n")
    assert "Werbung" not in vtt
    assert "00:00:00.000 --> 00:00:04.000\nHallo und willkommen" in vtt
    # 20 s -> 11 s after the ad cut -> 9.5 s after the silence cut.
    assert (
        "00:00:09.500 --> 00:00:13.500\nZurück &lt;b&gt;&amp;&lt;/b&gt; weiter → los"
        in vtt
    )


def test_parse_audio_edits_rejects_unknown_or_broken_data() -> None:
    assert parse_audio_edits(None) is None
    assert parse_audio_edits("not json") is None
    assert parse_audio_edits(json.dumps({"ads": [["x", 1]]})) is None
    assert parse_audio_edits(json.dumps({"ads": [[5, 9], [1, 6]]})) == [
        [(1.0, 9.0)],
        [],
    ]


def test_transcript_path_requires_feed_token_auth() -> None:
    assert _is_token_protected_endpoint("/post/ep-1/transcript.vtt")
    assert not _is_token_protected_endpoint("/post/ep-1/transcript.txt")


def _processed_post(feed: Feed, guid: str, edits: str | None) -> Post:
    post = Post(
        feed_id=feed.id,
        title=f"Episode {guid}",
        guid=guid,
        download_url=f"http://example.com/{guid}.mp3",
        processed_audio_path=f"/tmp/{guid}.mp3",
        whitelisted=True,
        audio_edits=edits,
    )
    db.session.add(post)
    db.session.commit()
    return post


def _add_segments(post: Post) -> None:
    db.session.add_all(
        [
            TranscriptSegment(
                post_id=post.id, sequence_num=0, start_time=0, end_time=3, text="Hi"
            ),
            TranscriptSegment(
                post_id=post.id, sequence_num=1, start_time=3, end_time=6, text="Ad"
            ),
            TranscriptSegment(
                post_id=post.id, sequence_num=2, start_time=8, end_time=9, text="Bye"
            ),
        ]
    )
    db.session.commit()


def test_transcript_route_serves_vtt_for_processed_post(app: Any) -> None:
    app.testing = True
    app.register_blueprint(post_bp)
    with app.app_context():
        feed = Feed(title="RK", rss_url="http://example.com/rk-t")
        db.session.add(feed)
        db.session.commit()
        ready = _processed_post(feed, "ready", json.dumps({"ads": [[3, 6]]}))
        _add_segments(ready)
        unknown = _processed_post(feed, "legacy", None)
        _add_segments(unknown)

    client = app.test_client()
    ok = client.get("/post/ready/transcript.vtt")
    legacy = client.get("/post/legacy/transcript.vtt")
    missing = client.get("/post/nope/transcript.vtt")

    assert ok.status_code == 200
    assert ok.headers["Content-Type"] == "text/vtt; charset=utf-8"
    body = ok.get_data(as_text=True)
    assert "Ad" not in body
    assert "00:00:05.000 --> 00:00:06.000\nBye" in body
    assert legacy.status_code == 404  # no mapping stored: times would be wrong
    assert missing.status_code == 404


def test_feed_lists_transcript_only_where_available(app: Any) -> None:
    with app.app_context():
        original_flag = getattr(runtime_config, "autoprocess_on_download", False)
        runtime_config.autoprocess_on_download = False
        try:
            feed = Feed(
                title="RK",
                rss_url="http://example.com/rk-feed",
                image_url="http://example.com/rk.png",
                language="de",
            )
            db.session.add(feed)
            db.session.commit()
            with_transcript = _processed_post(feed, "with", json.dumps({"ads": []}))
            _add_segments(with_transcript)
            _processed_post(feed, "without", json.dumps({"ads": []}))

            with app.test_request_context(base_url="http://podly.local"):
                xml = str(generate_feed_xml(feed))
        finally:
            runtime_config.autoprocess_on_download = original_flag

    assert 'xmlns:podcast="https://podcastindex.org/namespace/1.0"' in xml
    assert xml.count("<podcast:transcript") == 1
    assert 'url="http://podly.local/post/with/transcript.vtt"' in xml
    assert 'type="text/vtt"' in xml
    assert 'language="de"' in xml


def test_finalize_stores_removed_windows_for_transcripts() -> None:
    processor = object.__new__(PodcastProcessor)
    processor.logger = mock.MagicMock()
    processor.status_manager = mock.MagicMock()
    processor._remove_unprocessed_audio = mock.MagicMock()

    with (
        mock.patch(
            "podcast_processor.podcast_processor.get_audio_duration_ms",
            return_value=None,
        ),
        mock.patch("podcast_processor.podcast_processor.writer_client") as writer,
    ):
        writer.update.return_value = SimpleNamespace(success=True)
        processor._finalize_processing(
            Post(id=1, guid="g"),
            ProcessingJob(),
            "/o.mp3",
            removed_segments=[(12.0, 18.0)],
        )

    stored = json.loads(writer.update.call_args.args[2]["audio_edits"])
    assert stored == {"ads": [[12.0, 18.0]], "silence": []}


def test_token_feed_resolution_keeps_dots_in_guids(app: Any) -> None:
    from app.auth.feed_tokens import _resolve_feed_id

    with app.app_context():
        feed = Feed(title="RK", rss_url="http://example.com/rk-dots")
        db.session.add(feed)
        db.session.commit()
        _processed_post(feed, "ep.42", None)
        other = Feed(title="Other", rss_url="http://example.com/other")
        db.session.add(other)
        db.session.commit()
        _processed_post(other, "ep", None)

        for path in (
            "/post/ep.42/transcript.vtt",
            "/post/ep.42.mp3",
            "/post/ep.42/original.mp3",
        ):
            assert _resolve_feed_id(path) == feed.id


def test_token_auth_covers_guids_with_slashes(app: Any) -> None:
    from app.auth.feed_tokens import _resolve_feed_id

    guid = "tag:audioboom.com,2026:/posts/42"
    with app.app_context():
        feed = Feed(title="RK", rss_url="http://example.com/rk-slash")
        db.session.add(feed)
        db.session.commit()
        _processed_post(feed, guid, json.dumps({"ads": []}))

        for suffix in (
            ".mp3",
            "/original.mp3",
            "/transcript.vtt",
            "/chapters.json",
            "/chapter-images/0",
        ):
            path = f"/post/{guid}{suffix}"
            assert _is_token_protected_endpoint(path), path
            assert _resolve_feed_id(path) == feed.id, path
        for suffix in ("/audio", "/download", "/download/original"):
            path = f"/api/posts/{guid}{suffix}"
            assert _is_token_protected_endpoint(path), path
            assert _resolve_feed_id(path) == feed.id, path

        # URL-style GUIDs that end in ".mp3" themselves.
        url_guid = "https://cdn.example.com/ep1.mp3"
        _processed_post(feed, url_guid, json.dumps({"ads": []}))
        for suffix in (
            ".mp3",
            "/transcript.vtt",
            "/chapters.json",
            "/chapter-images/0",
        ):
            path = f"/post/{url_guid}{suffix}"
            assert _resolve_feed_id(path) == feed.id, path


def test_transcript_route_handles_encoded_slash_guid_and_whitelist(
    app: Any,
) -> None:
    app.testing = True
    app.register_blueprint(post_bp)
    with app.app_context():
        feed = Feed(title="RK", rss_url="http://example.com/rk-wl")
        db.session.add(feed)
        db.session.commit()
        listed = _processed_post(feed, "tag:x/posts/1", json.dumps({"ads": []}))
        _add_segments(listed)
        hidden = _processed_post(feed, "hidden", json.dumps({"ads": []}))
        _add_segments(hidden)
        hidden.whitelisted = False
        db.session.commit()

    client = app.test_client()
    assert client.get("/post/tag%3Ax%2Fposts%2F1/transcript.vtt").status_code == 200
    assert client.get("/post/hidden/transcript.vtt").status_code == 404

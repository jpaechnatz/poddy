"""A feed must not answer 304 after an episode finished processing.

With unprocessed episodes left out of the feed, an episode appears only once
it is processed. Processing changes no feed column, so the conditional-GET
validators have to notice the change some other way, or readers keep their
cached copy without the new episode.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from unittest import mock

from app.extensions import db
from app.models import Feed, Post
from app.routes import feed_routes
from app.routes.feed_routes import feed_bp


def _setup(app: Any) -> tuple[Any, int, int]:
    app.testing = True
    if "feed" not in app.blueprints:
        app.register_blueprint(feed_bp)
    with feed_routes._BACKGROUND_REFRESH_LOCK:
        feed_routes._BACKGROUND_REFRESH_LAST_KICKOFF.clear()
    with app.app_context():
        feed = Feed(title="P", rss_url="https://example.com/p.xml")
        db.session.add(feed)
        db.session.commit()
        post = Post(
            feed_id=feed.id,
            guid="ep-1",
            download_url="https://example.com/ep1.mp3",
            title="Episode 1",
            whitelisted=True,
            release_date=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
        )
        db.session.add(post)
        db.session.commit()
        return app.test_client(), feed.id, post.id


def _get(client: Any, feed_id: int, **headers: str) -> Any:
    with (
        mock.patch("app.routes.feed_routes._spawn_async_refresh"),
        mock.patch("app.routes.feed_routes.generate_feed_xml", return_value=b"<rss/>"),
    ):
        return client.get(f"/feed/{feed_id}", headers=headers)


def _update_post(app: Any, post_id: int, **fields: Any) -> None:
    with app.app_context():
        Post.query.filter_by(id=post_id).update(fields)
        db.session.commit()


def test_processing_an_episode_changes_the_etag(app: Any) -> None:
    client, feed_id, post_id = _setup(app)
    before = _get(client, feed_id).headers["ETag"]

    _update_post(app, post_id, processed_audio_path="/srv/ep1.mp3")

    after = _get(client, feed_id, **{"If-None-Match": before})
    assert after.status_code == 200
    assert after.headers["ETag"] != before


def test_reprocessing_and_summary_change_the_etag(app: Any) -> None:
    client, feed_id, post_id = _setup(app)
    _update_post(app, post_id, processed_audio_path="/srv/ep1.mp3", duration=3600)
    first = _get(client, feed_id).headers["ETag"]

    _update_post(app, post_id, audio_edits='{"ads": [[1, 2]]}', duration=3590)
    second = _get(client, feed_id).headers["ETag"]
    _update_post(app, post_id, summary="Kurz gesagt")
    third = _get(client, feed_id).headers["ETag"]

    assert len({first, second, third}) == 3


def test_if_modified_since_alone_does_not_hide_a_processed_episode(app: Any) -> None:
    client, feed_id, post_id = _setup(app)
    last_modified = _get(client, feed_id).headers.get("Last-Modified")

    _update_post(app, post_id, processed_audio_path="/srv/ep1.mp3")

    if last_modified is not None:
        resp = _get(client, feed_id, **{"If-Modified-Since": last_modified})
        assert resp.status_code == 200


def test_unchanged_feed_still_answers_304(app: Any) -> None:
    client, feed_id, post_id = _setup(app)
    _update_post(app, post_id, processed_audio_path="/srv/ep1.mp3")
    etag = _get(client, feed_id).headers["ETag"]

    assert _get(client, feed_id, **{"If-None-Match": etag}).status_code == 304


# --- The validator moves exactly when the real rendered feed does -----------

import pytest  # noqa: E402

from app.models import TranscriptSegment  # noqa: E402
from app.runtime_config import config as runtime_config  # noqa: E402
from app.writer.actions.feeds import refresh_feed_action  # noqa: E402


def _rich_setup(app: Any) -> tuple[Any, int, int, int]:
    """A processed episode with transcript and an unprocessed one."""
    client, feed_id, done_id = _setup(app)
    with app.app_context():
        feed = db.session.get(Feed, feed_id)
        assert feed is not None
        feed.language = "de"
        Post.query.filter_by(id=done_id).update(
            {
                "processed_audio_path": "/srv/ep1.mp3",
                "duration": 3600,
                "audio_edits": '{"ads": [], "silence": []}',
            }
        )
        db.session.add(
            TranscriptSegment(
                post_id=done_id, sequence_num=0, start_time=0, end_time=2, text="Hallo"
            )
        )
        pending = Post(
            feed_id=feed_id,
            guid="ep-2",
            download_url="https://example.com/ep2.mp3",
            title="Episode 2",
            whitelisted=True,
            release_date=dt.datetime(2026, 1, 2, tzinfo=dt.UTC),
        )
        db.session.add(pending)
        db.session.commit()
        return client, feed_id, done_id, pending.id


def _render(client: Any, feed_id: int) -> tuple[str, bytes]:
    with mock.patch("app.routes.feed_routes._spawn_async_refresh"):
        resp = client.get(f"/feed/{feed_id}")
    assert resp.status_code == 200
    return resp.headers["ETag"], resp.data


def _set(model: Any, key: str, **fields: Any) -> Any:
    def apply(app: Any, ids: dict[str, int]) -> None:
        with app.app_context():
            model.query.filter_by(id=ids[key]).update(fields)
            db.session.commit()

    return apply


def _refresh_noop(app: Any, ids: dict[str, int]) -> None:
    with app.app_context():
        refresh_feed_action({"feed_id": ids["feed"], "updates": {}, "new_posts": []})
        db.session.commit()


VISIBLE = [
    ("processed", _set(Post, "pending", processed_audio_path="/srv/ep2.mp3")),
    ("summary", _set(Post, "done", summary="Kurz gesagt")),
    ("unwhitelisted", _set(Post, "done", whitelisted=False)),
    ("duration", _set(Post, "done", duration=3590)),
    ("language", _set(Feed, "feed", language="en")),
    ("failed", _set(Post, "done", processing_failed=True)),
]

# A reprocess also changes audio_edits, which the tag includes even where the
# feed XML stays the same (the transcript files change); that only costs a
# refetch and is covered by test_reprocessing_and_summary_change_the_etag.
INVISIBLE = [
    ("download_count", _set(Post, "done", download_count=7)),
    ("download_url", _set(Post, "done", download_url="https://example.com/x.mp3")),
    ("noop_refresh", _refresh_noop),
]


@pytest.fixture
def no_unprocessed(app: Any) -> Any:
    original = getattr(runtime_config, "autoprocess_on_download", False)
    runtime_config.autoprocess_on_download = False
    yield
    runtime_config.autoprocess_on_download = original


@pytest.mark.parametrize(("name", "mutate"), VISIBLE + INVISIBLE)
def test_etag_moves_exactly_when_the_rendered_feed_does(
    app: Any, no_unprocessed: Any, name: str, mutate: Any
) -> None:
    client, feed_id, done_id, pending_id = _rich_setup(app)
    ids = {"feed": feed_id, "done": done_id, "pending": pending_id}
    etag_before, body_before = _render(client, feed_id)

    mutate(app, ids)

    with mock.patch("app.routes.feed_routes._spawn_async_refresh"):
        conditional = client.get(
            f"/feed/{feed_id}", headers={"If-None-Match": etag_before}
        )
    etag_after, body_after = _render(client, feed_id)

    if body_after != body_before:
        assert conditional.status_code == 200, name
        assert etag_after != etag_before, name
    else:
        assert conditional.status_code == 304, name
        assert etag_after == etag_before, name
    # The cases are chosen so each group really exercises its branch.
    assert (body_after != body_before) == (name in dict(VISIBLE)), name


def test_aggregate_etag_follows_processing(app: Any) -> None:
    _, _, post_id = _setup(app)
    with app.test_request_context():
        before = feed_routes._compute_aggregate_etag(None)
    _update_post(app, post_id, processed_audio_path="/srv/ep1.mp3")
    with app.test_request_context():
        after = feed_routes._compute_aggregate_etag(None)
    assert before != after

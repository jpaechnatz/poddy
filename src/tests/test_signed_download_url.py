"""Signed enclosure links (Patreon & co.) stay current after a feed refresh."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any
from unittest import mock

from app.extensions import db
from app.feeds import get_guid, refresh_feed
from app.models import Feed, Post
from app.writer.actions.feeds import refresh_feed_action
from tests.test_feeds import (  # noqa: F401  (pytest fixtures)
    MockPost,
    mock_db_session,
    mock_feed,
    mock_feed_data,
)

OLD = "https://www.patreon.com/api/rss/u/x/e/1.mp3?sig=old"
NEW = "https://www.patreon.com/api/rss/u/x/e/1.mp3?sig=new"


@mock.patch("app.feeds.writer_client")
@mock.patch("app.feeds._should_auto_whitelist_new_posts", return_value=True)
@mock.patch("app.feeds.make_post")
@mock.patch("app.feeds.fetch_feed")
def test_refresh_sends_the_new_signed_link(
    mock_fetch_feed: Any,
    mock_make_post: Any,
    _auto: Any,
    mock_writer_client: Any,
    mock_feed: Any,  # noqa: F811
    mock_feed_data: Any,  # noqa: F811
    mock_db_session: Any,  # noqa: F811
) -> None:
    entry = mock_feed_data.entries[0]
    entry.links[0].href = NEW
    existing = MockPost(
        id=42,
        guid=get_guid(entry),
        title=entry.title,
        description=entry.description,
        image_url=mock_feed.image_url,
        download_url=OLD,
    )
    existing.processed_audio_path = "/tmp/done.mp3"  # also for reprocessing
    mock_feed.posts = [existing]
    mock_fetch_feed.return_value = mock_feed_data
    mock_make_post.return_value = MockPost(guid=str(uuid.uuid4()))

    refresh_feed(mock_feed)

    updates = mock_writer_client.action.call_args.args[1]["existing_post_updates"]
    assert {"post_id": 42, "download_url": NEW}.items() <= updates[0].items()


def test_new_link_is_stored_without_marking_the_feed_changed(app: Any) -> None:
    with app.app_context():
        before = dt.datetime(2026, 1, 1)
        feed = Feed(title="PoRN", rss_url="https://example.com/p.xml")
        feed.last_changed_at = before
        db.session.add(feed)
        db.session.commit()
        post = Post(feed_id=feed.id, guid="g1", download_url=OLD, title="#385")
        db.session.add(post)
        db.session.commit()

        result = refresh_feed_action(
            {
                "feed_id": feed.id,
                "existing_post_updates": [{"post_id": post.id, "download_url": NEW}],
            }
        )
        db.session.commit()
        db.session.refresh(post)
        db.session.refresh(feed)

        assert post.download_url == NEW
        assert result["updated_posts_count"] == 0
        assert feed.last_changed_at == before

        # A real content change still marks the feed as changed.
        refresh_feed_action(
            {
                "feed_id": feed.id,
                "existing_post_updates": [{"post_id": post.id, "title": "#385 neu"}],
            }
        )
        db.session.commit()
        db.session.refresh(feed)
        assert feed.last_changed_at != before

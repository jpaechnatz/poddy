"""Mark a feed's backlog as seen so only new episodes get processed."""

import datetime
from types import SimpleNamespace
from typing import Any
from unittest import mock

from app.extensions import db
from app.feeds import _should_whitelist_new_post
from app.models import Feed, Post
from app.routes.post_routes import post_bp
from app.writer.actions.feeds import mark_backlog_seen_action


def _posts(feed: Feed) -> dict[str, Post]:
    posts = {
        "queued": Post(
            feed_id=feed.id,
            guid="queued",
            title="Alt 1",
            download_url="http://e/1.mp3",
            whitelisted=True,
        ),
        "done": Post(
            feed_id=feed.id,
            guid="done",
            title="Alt 2",
            download_url="http://e/2.mp3",
            whitelisted=True,
            processed_audio_path="/tmp/done.mp3",
        ),
        "off": Post(
            feed_id=feed.id,
            guid="off",
            title="Alt 3",
            download_url="http://e/3.mp3",
            whitelisted=False,
        ),
    }
    db.session.add_all(posts.values())
    db.session.commit()
    return posts


def test_action_unwhitelists_only_unprocessed_posts(app: Any) -> None:
    with app.app_context():
        feed = Feed(title="F", rss_url="http://e/feed")
        db.session.add(feed)
        db.session.commit()
        posts = _posts(feed)

        result = mark_backlog_seen_action({"feed_id": feed.id})

        assert result == {"updated_count": 1, "post_guids": ["queued"]}
        assert posts["queued"].whitelisted is False
        assert posts["done"].whitelisted is True  # stays in the feed
        assert posts["off"].whitelisted is False


def test_route_cancels_jobs_of_the_backlog(app: Any) -> None:
    app.testing = True
    app.register_blueprint(post_bp)
    with app.app_context():
        feed = Feed(title="F", rss_url="http://e/feed2")
        db.session.add(feed)
        db.session.commit()
        feed_id = feed.id

    jobs = mock.MagicMock()
    with (
        mock.patch("app.routes.post_routes.writer_client") as writer,
        mock.patch("app.routes.post_routes.get_jobs_manager", return_value=jobs),
    ):
        writer.action.return_value = SimpleNamespace(
            success=True, data={"updated_count": 2, "post_guids": ["a", "b"]}
        )
        response = app.test_client().post(f"/api/feeds/{feed_id}/mark-backlog-seen")

    assert response.status_code == 200
    assert response.get_json()["updated_count"] == 2
    writer.action.assert_called_once_with(
        "mark_backlog_seen", {"feed_id": feed_id}, wait=True
    )
    assert [c.args[0] for c in jobs.cancel_post_jobs.call_args_list] == ["a", "b"]


def test_new_episode_after_marking_is_still_whitelisted() -> None:
    # After marking, no backlog post is whitelisted, so refresh uses the oldest
    # known release date as floor: anything newly published passes it.
    feed = Feed(title="F", rss_url="u")
    new_post = Post(
        title="Neue Folge",
        release_date=datetime.datetime(2026, 10, 30, tzinfo=datetime.UTC),
    )
    floor = datetime.date(2020, 1, 1)
    with mock.patch("app.feeds._should_auto_whitelist_new_posts", return_value=True):
        assert _should_whitelist_new_post(feed, new_post, floor) is True

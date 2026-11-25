"""Fork-specific parts of the per-feed title filter.

Matching, auto-whitelisting, the RSS feed and the settings route are covered
by upstream's test_episode_filters.py. These tests cover what Poddy adds:
saving a filter un-whitelists matching unprocessed episodes and bumps the feed
timestamp, and processed (whitelisted) episodes stay in the aggregate feed.
"""

import datetime
from types import SimpleNamespace
from typing import Any
from unittest import mock

from app.extensions import db
from app.feeds import get_user_aggregate_posts
from app.models import Feed, Post
from app.routes.feed_routes import feed_bp
from app.writer.actions.feeds import unwhitelist_excluded_posts_action


def _add_posts(feed: Feed) -> tuple[Post, Post]:
    main = Post(
        feed_id=feed.id,
        title="284 Raptor",
        guid="main",
        download_url="http://example.com/main.mp3",
        whitelisted=False,
        release_date=datetime.datetime(2026, 10, 19, tzinfo=datetime.UTC),
    )
    stammtisch = Post(
        feed_id=feed.id,
        title="Stammtisch 404",
        guid="stamm",
        download_url="http://example.com/stamm.mp3",
        whitelisted=False,
        release_date=datetime.datetime(2026, 10, 24, tzinfo=datetime.UTC),
    )
    db.session.add_all([main, stammtisch])
    db.session.commit()
    return main, stammtisch


def _settings_client(app: Any) -> tuple[Any, int]:
    app.testing = True
    app.register_blueprint(feed_bp)
    with app.app_context():
        feed = Feed(title="RK", rss_url="https://example.com/rk.xml")
        db.session.add(feed)
        db.session.commit()
        return app.test_client(), feed.id


def test_settings_store_and_clear_exclude_strings(app: Any) -> None:
    client, feed_id = _settings_client(app)
    seen: list[dict[str, Any]] = []

    def _update(model: str, model_id: int, updates: dict[str, Any], wait: bool = True):
        seen.append(updates)
        Feed.query.filter_by(id=model_id).update(updates)
        db.session.commit()
        return SimpleNamespace(success=True)

    with mock.patch("app.routes.feed_routes.writer_client") as writer:
        writer.update.side_effect = _update
        ok = client.patch(
            f"/api/feeds/{feed_id}/settings",
            json={"episode_title_exclude_strings": " Stammtisch "},
        )
        cleared = client.patch(
            f"/api/feeds/{feed_id}/settings",
            json={"episode_title_exclude_strings": "  "},
        )

    assert ok.status_code == 200
    # Saving a filter un-whitelists matching episodes; clearing it does not.
    writer.action.assert_called_once_with(
        "unwhitelist_excluded_posts", {"feed_id": feed_id}, wait=True
    )
    assert ok.get_json()["episode_title_exclude_strings"] == "Stammtisch"
    assert cleared.get_json()["episode_title_exclude_strings"] is None
    assert [u["episode_title_exclude_strings"] for u in seen] == ["Stammtisch", None]
    # The rendered feed changes, so the feed ETag/Last-Modified must change too.
    assert all("last_changed_at" in u for u in seen)


def test_saving_filter_unwhitelists_only_unprocessed_matches(app: Any) -> None:
    with app.app_context():
        feed = Feed(
            rss_url="http://example.com/rk3",
            title="RK",
            episode_title_exclude_strings="Stammtisch",
        )
        db.session.add(feed)
        db.session.commit()
        main, queued = _add_posts(feed)
        main.whitelisted = True
        queued.whitelisted = True
        done = Post(
            feed_id=feed.id,
            title="Stammtisch 400",
            guid="done",
            download_url="http://example.com/done.mp3",
            whitelisted=True,
            processed_audio_path="/tmp/done.mp3",
        )
        db.session.add(done)
        db.session.commit()

        result = unwhitelist_excluded_posts_action({"feed_id": feed.id})

        assert result == {"updated_count": 1}
        assert queued.whitelisted is False
        assert main.whitelisted is True
        assert done.whitelisted is True  # already processed: left alone


def test_aggregate_feed_keeps_processed_episodes_despite_title_filter(app: Any) -> None:
    # A processed episode was whitelisted (by hand or before the filter was
    # set); like the feed itself, the aggregate feed then keeps it.
    with app.app_context():
        feed = Feed(
            rss_url="http://example.com/rk4",
            title="RK",
            episode_title_exclude_strings="Stammtisch",
        )
        db.session.add(feed)
        db.session.commit()
        for i in range(5):
            db.session.add(
                Post(
                    feed_id=feed.id,
                    title=("Stammtisch " if i < 2 else "Folge ") + str(i),
                    guid=f"agg-{i}",
                    download_url=f"http://example.com/agg-{i}.mp3",
                    whitelisted=True,
                    processed_audio_path=f"/tmp/agg-{i}.mp3",
                    release_date=datetime.datetime(
                        2026, 10, 20 - i, tzinfo=datetime.UTC
                    ),
                )
            )
        db.session.commit()

        posts = get_user_aggregate_posts(0, limit_per_feed=3)

    assert [p.guid for p in posts] == ["agg-0", "agg-1", "agg-2"]

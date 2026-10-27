"""Per-feed episode exclusion by title (e.g. Retrokompott "Stammtisch")."""

import datetime
from types import SimpleNamespace
from typing import Any
from unittest import mock

from app.episode_filter import is_post_excluded, is_title_excluded
from app.extensions import db
from app.feeds import _should_whitelist_new_post, generate_feed_xml
from app.models import Feed, Post
from app.routes.feed_routes import feed_bp
from app.runtime_config import config as runtime_config
from app.writer.actions.feeds import whitelist_latest_post_for_feed_action


def test_title_match_is_case_insensitive_substring() -> None:
    feed = SimpleNamespace(episode_title_exclude_strings="stammtisch, Preview ")

    assert is_title_excluded(feed, "RETROKOMPOTT Stammtisch 404")
    assert is_title_excluded(feed, "Folge 12 (preview)")
    assert not is_title_excluded(feed, "Retrokompott 284 Raptor")
    assert not is_title_excluded(SimpleNamespace(), "Stammtisch")
    assert not is_title_excluded(None, "Stammtisch")
    assert is_post_excluded(SimpleNamespace(feed=feed, title="Stammtisch 1"))


def test_excluded_new_post_is_not_whitelisted() -> None:
    feed = Feed(title="RK", rss_url="u", episode_title_exclude_strings="Stammtisch")
    post = Post(title="Retrokompott Stammtisch 404")

    with mock.patch("app.feeds._should_auto_whitelist_new_posts", return_value=True):
        assert _should_whitelist_new_post(feed, post, None) is False
        assert _should_whitelist_new_post(feed, Post(title="284 Raptor"), None)


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


@mock.patch("app.feeds.feed_item")
@mock.patch("app.feeds.PyRSS2Gen.Image")
@mock.patch("app.feeds.PyRSS2Gen.RSS2")
def test_feed_xml_leaves_out_excluded_episodes(
    mock_rss_2: Any, mock_image: Any, mock_feed_item: Any, app: Any
) -> None:
    del mock_image
    with app.app_context():
        original_flag = getattr(runtime_config, "autoprocess_on_download", False)
        runtime_config.autoprocess_on_download = True
        try:
            feed = Feed(
                rss_url="http://example.com/rk",
                title="RK",
                episode_title_exclude_strings="stammtisch",
            )
            db.session.add(feed)
            db.session.commit()
            main, _ = _add_posts(feed)
            mock_rss_2.return_value.to_xml.return_value = "<rss></rss>"

            generate_feed_xml(feed)

            called = [call.args[0] for call in mock_feed_item.call_args_list]
            assert called == [main]
        finally:
            runtime_config.autoprocess_on_download = original_flag


def test_first_member_whitelist_skips_excluded_latest_episode(app: Any) -> None:
    with app.app_context():
        feed = Feed(
            rss_url="http://example.com/rk2",
            title="RK",
            episode_title_exclude_strings="Stammtisch",
        )
        db.session.add(feed)
        db.session.commit()
        main, stammtisch = _add_posts(feed)

        result = whitelist_latest_post_for_feed_action({"feed_id": feed.id})

        assert result == {"updated": True, "post_guid": "main"}
        assert main.whitelisted is True
        assert stammtisch.whitelisted is False


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
    assert ok.get_json()["episode_title_exclude_strings"] == "Stammtisch"
    assert cleared.get_json()["episode_title_exclude_strings"] is None
    assert seen == [
        {"episode_title_exclude_strings": "Stammtisch"},
        {"episode_title_exclude_strings": None},
    ]


def test_settings_reject_non_string_exclude_strings(app: Any) -> None:
    client, feed_id = _settings_client(app)

    response = client.patch(
        f"/api/feeds/{feed_id}/settings",
        json={"episode_title_exclude_strings": ["Stammtisch"]},
    )

    assert response.status_code == 400

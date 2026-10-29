"""Cached feeds are refetched after the feed format changes."""

from __future__ import annotations

import datetime as dt
from typing import Any
from unittest import mock

from werkzeug.http import http_date

from app.extensions import db
from app.models import Feed
from tests.test_feed_etag import (
    _make_feed_with_post,
    _register_feed_routes,
    _reset_kickoff_state,
)


def _feed_with_known_change(app: Any) -> int:
    app.testing = True
    _register_feed_routes(app)
    _reset_kickoff_state()
    with app.app_context():
        feed_id = _make_feed_with_post()
        feed = db.session.get(Feed, feed_id)
        assert feed is not None
        feed.last_changed_at = dt.datetime(2026, 1, 1, 0, 0, 0)
        db.session.commit()
    return feed_id


def _get(app: Any, feed_id: int, headers: dict[str, str]) -> Any:
    with (
        mock.patch("app.routes.feed_routes._spawn_async_refresh"),
        mock.patch("app.routes.feed_routes.generate_feed_xml", return_value=b"<rss/>"),
    ):
        return app.test_client().get(f"/feed/{feed_id}", headers=headers)


def test_new_render_version_changes_the_etag(app: Any) -> None:
    feed_id = _feed_with_known_change(app)
    current = _get(app, feed_id, {}).headers["ETag"]
    with mock.patch("app.routes.feed_routes.FEED_RENDER_VERSION", "old"):
        old = _get(app, feed_id, {}).headers["ETag"]
    assert current != old


def test_stale_etag_is_not_overruled_by_recent_if_modified_since(app: Any) -> None:
    feed_id = _feed_with_known_change(app)
    later = http_date(dt.datetime(2026, 1, 1, 1, 0, 0, tzinfo=dt.UTC))
    with mock.patch("app.routes.feed_routes.FEED_RENDER_VERSION", "old"):
        old_etag = _get(app, feed_id, {}).headers["ETag"]

    # The client still holds the copy from before the format change.
    resp = _get(app, feed_id, {"If-None-Match": old_etag, "If-Modified-Since": later})
    assert resp.status_code == 200
    assert resp.data == b"<rss/>"

    # With the current tag it is a 304, and If-Modified-Since alone still works.
    fresh = _get(app, feed_id, {}).headers["ETag"]
    assert _get(app, feed_id, {"If-None-Match": fresh}).status_code == 304
    assert _get(app, feed_id, {"If-Modified-Since": later}).status_code == 304

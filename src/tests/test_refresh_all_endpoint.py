"""Manual "refresh all" runs in the background and answers right away."""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest

from app.extensions import db
from app.models import Feed
from app.routes import feed_routes
from tests.test_feed_etag import _register_feed_routes


@pytest.fixture
def client(app: Any) -> Any:
    app.testing = True
    _register_feed_routes(app)
    with app.app_context():
        db.session.add_all(
            [
                Feed(title="A", rss_url="https://example.com/a.xml"),
                Feed(title="B", rss_url="https://example.com/b.xml"),
            ]
        )
        db.session.commit()
    yield app.test_client()
    if feed_routes._refresh_all_lock.locked():
        feed_routes._refresh_all_lock.release()


def test_returns_202_and_refreshes_in_a_thread(client: Any) -> None:
    manager = mock.Mock()
    manager.start_refresh_all_feeds.return_value = {"feeds_refreshed": 2, "enqueued": 1}
    with (
        mock.patch.object(feed_routes, "get_jobs_manager", return_value=manager),
        mock.patch.object(feed_routes, "Thread") as thread_cls,
    ):
        resp = client.post("/api/feeds/refresh-all")

        assert resp.status_code == 202
        body = resp.get_json()
        assert body["status"] == "accepted"
        assert body["feeds"] == 2
        assert "background" in body["message"]
        # Nothing ran inside the request.
        manager.start_refresh_all_feeds.assert_not_called()

        kwargs = thread_cls.call_args.kwargs
        kwargs["target"](*kwargs["args"])  # run the background job now

    manager.start_refresh_all_feeds.assert_called_once_with(trigger="manual_refresh")
    assert not feed_routes._refresh_all_lock.locked()


def test_second_click_while_running_gets_409(client: Any) -> None:
    with mock.patch.object(feed_routes, "Thread"):
        assert client.post("/api/feeds/refresh-all").status_code == 202
        second = client.post("/api/feeds/refresh-all")

    assert second.status_code == 409
    assert "already running" in second.get_json()["message"]


def test_failure_in_background_is_logged_and_unlocks(client: Any) -> None:
    manager = mock.Mock()
    manager.start_refresh_all_feeds.side_effect = RuntimeError("writer down")
    with (
        mock.patch.object(feed_routes, "get_jobs_manager", return_value=manager),
        mock.patch.object(feed_routes, "Thread") as thread_cls,
        mock.patch.object(feed_routes.logger, "exception") as log_exception,
    ):
        client.post("/api/feeds/refresh-all")
        kwargs = thread_cls.call_args.kwargs
        kwargs["target"](*kwargs["args"])

    log_exception.assert_called_once()
    assert not feed_routes._refresh_all_lock.locked()

"""Per-feed option to cut the show's own promotions like ads."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest

from app.extensions import db
from app.models import Feed
from app.routes.feed_routes import feed_bp
from podcast_processor.ad_classifier import AdClassifier
from podcast_processor.prompt import SELF_PROMO_AS_ADS_RULE, system_prompt_for_feed

BASE_PROMPT = "Find ads.\n"


def test_prompt_unchanged_by_default() -> None:
    assert system_prompt_for_feed(BASE_PROMPT, None) == BASE_PROMPT
    feed = SimpleNamespace(cut_self_promo=None)
    assert system_prompt_for_feed(BASE_PROMPT, feed) == BASE_PROMPT


def test_prompt_extended_when_enabled() -> None:
    prompt = system_prompt_for_feed(BASE_PROMPT, SimpleNamespace(cut_self_promo=True))
    assert prompt.startswith("Find ads.")
    assert SELF_PROMO_AS_ADS_RULE.strip() in prompt
    assert "promotional_external" in prompt


def _classifier(cut_self_promo: bool) -> AdClassifier:
    classifier = object.__new__(AdClassifier)
    classifier._cut_self_promo = cut_self_promo
    return classifier


@pytest.mark.parametrize(
    ("cut", "content_type", "expected"),
    [
        (False, "educational/self_promo", 0.7),
        (True, "educational/self_promo", 0.95),
        # Technical discussion stays demoted either way.
        (True, "technical_discussion", 0.7),
        (True, "promotional_external", 0.95),
    ],
)
def test_self_promo_confidence(cut: bool, content_type: str, expected: float) -> None:
    result = _classifier(cut)._adjust_confidence(
        base_confidence=0.95, content_type=content_type
    )
    assert result == pytest.approx(expected)


def test_settings_accept_cut_self_promo(app: Any) -> None:
    app.testing = True
    app.register_blueprint(feed_bp)
    with app.app_context():
        feed = Feed(title="KI", rss_url="https://example.com/ki.xml")
        db.session.add(feed)
        db.session.commit()
        feed_id = feed.id

    def _update(model: str, model_id: int, updates: dict[str, Any], wait: bool = True):
        Feed.query.filter_by(id=model_id).update(updates)
        db.session.commit()
        return SimpleNamespace(success=True)

    with mock.patch("app.routes.feed_routes.writer_client") as writer:
        writer.update.side_effect = _update
        response = app.test_client().patch(
            f"/api/feeds/{feed_id}/settings", json={"cut_self_promo": True}
        )

    body = json.loads(response.get_data(as_text=True))
    assert body["cut_self_promo"] is True

"""'Episodes to enable on new feeds' = 0 must mean no archive episodes."""

from __future__ import annotations

from typing import Any

from app.extensions import db
from app.models import AppSettings
from tests.test_env_var_authority import _create_default_settings


def _config_with_archive_count(app: Any, value: int) -> int | None:
    with app.app_context():
        from app.config_store import to_pydantic_config

        _create_default_settings()
        settings = db.session.get(AppSettings, 1)
        assert settings is not None
        settings.number_of_episodes_to_whitelist_from_archive_of_new_feed = value
        db.session.commit()
        return to_pydantic_config().number_of_episodes_to_whitelist_from_archive_of_new_feed


def test_zero_archive_episodes_is_kept(app: Any) -> None:
    assert _config_with_archive_count(app, 0) == 0


def test_other_values_are_kept(app: Any) -> None:
    assert _config_with_archive_count(app, 3) == 3

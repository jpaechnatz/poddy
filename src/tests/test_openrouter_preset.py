"""OPENROUTER_API_KEY sets up transcription and LLM with one key."""

from __future__ import annotations

import os
from typing import Any

from app.config_store import apply_openrouter_env_preset
from shared import defaults as DEFAULTS
from shared.config import RemoteWhisperConfig
from tests.test_env_var_authority import _create_default_settings

PRESET_VARS = (
    "OPENROUTER_API_KEY",
    "WHISPER_TYPE",
    "WHISPER_REMOTE_API_KEY",
    "WHISPER_REMOTE_BASE_URL",
    "WHISPER_REMOTE_MODEL",
    "WHISPER_REMOTE_CHUNKSIZE_MB",
    "LLM_API_KEY",
    "LLM_MODEL",
)


def _clean_env(monkeypatch: Any) -> None:
    # setenv("") records the original value so the preset's writes are undone.
    for name in PRESET_VARS:
        monkeypatch.setenv(name, "")


def test_preset_fills_all_settings_from_one_key(monkeypatch: Any) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-123")

    apply_openrouter_env_preset()

    assert os.environ["WHISPER_TYPE"] == "remote"
    assert os.environ["WHISPER_REMOTE_API_KEY"] == "sk-or-123"
    assert os.environ["WHISPER_REMOTE_BASE_URL"] == "https://openrouter.ai/api/v1"
    assert os.environ["WHISPER_REMOTE_MODEL"] == DEFAULTS.OPENROUTER_TRANSCRIBE_MODEL
    assert os.environ["WHISPER_REMOTE_CHUNKSIZE_MB"] == "10"
    assert os.environ["LLM_API_KEY"] == "sk-or-123"
    assert os.environ["LLM_MODEL"].startswith("openrouter/")


def test_explicit_settings_win_over_the_preset(monkeypatch: Any) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-123")
    monkeypatch.setenv("WHISPER_REMOTE_MODEL", "mistralai/voxtral-small-transcribe-3-0")
    monkeypatch.setenv("LLM_MODEL", "openrouter/anthropic/claude-haiku-5.5")

    apply_openrouter_env_preset()

    assert (
        os.environ["WHISPER_REMOTE_MODEL"] == "mistralai/voxtral-small-transcribe-3-0"
    )
    assert os.environ["LLM_MODEL"] == "openrouter/anthropic/claude-haiku-5.5"
    assert os.environ["LLM_API_KEY"] == "sk-or-123"


def test_no_key_changes_nothing(monkeypatch: Any) -> None:
    _clean_env(monkeypatch)

    apply_openrouter_env_preset()

    assert all(os.environ.get(name) == "" for name in PRESET_VARS)


def test_hydrated_runtime_config_uses_openrouter(app: Any, monkeypatch: Any) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-456")

    with app.app_context():
        from app.config_store import hydrate_runtime_config_inplace
        from app.runtime_config import config as runtime_config

        _create_default_settings()
        hydrate_runtime_config_inplace()

        whisper = runtime_config.whisper
        assert isinstance(whisper, RemoteWhisperConfig)
        assert whisper.api_key == "sk-or-456"
        assert whisper.base_url == "https://openrouter.ai/api/v1"
        assert whisper.model == DEFAULTS.OPENROUTER_TRANSCRIBE_MODEL
        assert whisper.chunksize_mb == 10
        assert runtime_config.llm_api_key == "sk-or-456"
        assert runtime_config.llm_model == DEFAULTS.OPENROUTER_LLM_MODEL


def test_whisper_language_env_sets_default_language(app: Any, monkeypatch: Any) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-789")
    monkeypatch.setenv("WHISPER_LANGUAGE", "de")

    with app.app_context():
        from app.config_store import hydrate_runtime_config_inplace
        from app.routes.config_routes import _get_whisper_overridden_fields
        from app.runtime_config import config as runtime_config

        _create_default_settings()
        hydrate_runtime_config_inplace()

        assert getattr(runtime_config.whisper, "language", None) == "de"
        assert "whisper.language" in _get_whisper_overridden_fields()

        monkeypatch.setenv("WHISPER_LANGUAGE", "klingonisch")
        hydrate_runtime_config_inplace()  # invalid value is ignored, not fatal
        assert getattr(runtime_config.whisper, "language", None) != "klingonisch"

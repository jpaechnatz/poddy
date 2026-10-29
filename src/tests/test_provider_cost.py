"""Provider-reported call costs (OpenRouter) and summaries in the cost dashboard."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest

from podcast_processor import episode_extras
from podcast_processor.episode_extras import (
    SUMMARY_MODEL_CALL_SEQ,
    summarize_transcript,
)
from podcast_processor.llm_model_call_utils import (
    compute_estimated_cost_usd,
    extract_litellm_usage,
    extract_provider_cost_usd,
    try_update_model_call,
)

_COST_HEADER = "llm_provider-x-litellm-response-cost"


def _usage(**extra: Any) -> SimpleNamespace:
    return SimpleNamespace(
        prompt_tokens=1000, completion_tokens=200, total_tokens=1200, **extra
    )


def test_cost_from_litellm_hidden_params() -> None:
    response = SimpleNamespace(
        usage=_usage(),
        _hidden_params={"additional_headers": {_COST_HEADER: 0.000321}},
    )
    assert extract_provider_cost_usd(response) == 0.000321
    assert extract_litellm_usage(response)["provider_cost_usd"] == 0.000321


def test_cost_from_usage_body() -> None:
    assert extract_provider_cost_usd({"usage": {"cost": "0.0015"}}) == 0.0015
    assert extract_provider_cost_usd(SimpleNamespace(usage=_usage(cost=0))) == 0.0


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(usage=_usage()),
        {"usage": {"cost": None}},
        {"usage": {"cost": "n/a"}},
        {"usage": {"cost": -1}},
        {"usage": {"cost": True}},
        {"usage": {"cost": "inf"}},
        {"usage": {"cost": "nan"}},
        # MagicMock supports float() (1.0); it must not read as a real cost.
        SimpleNamespace(usage=mock.MagicMock()),
        mock.MagicMock(),
    ],
)
def test_no_cost_without_a_real_number(response: Any) -> None:
    assert extract_provider_cost_usd(response) is None


def test_provider_cost_beats_the_price_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.llm_pricing.compute_model_call_cost", lambda _c: 0.0)
    cost = compute_estimated_cost_usd(
        model_name="openrouter/~deepseek/deepseek-flash-latest",
        service_tier=None,
        prompt="classify",
        usage={"prompt_tokens": 1000, "provider_cost_usd": 0.00042},
        logger=logging.getLogger("test"),
        log_prefix="t",
    )
    assert cost == 0.00042


def test_price_table_still_used_without_provider_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.llm_pricing.compute_model_call_cost", lambda _c: 0.0042)
    cost = compute_estimated_cost_usd(
        model_name="gpt-4o-mini",
        service_tier=None,
        prompt="classify",
        usage={"prompt_tokens": 100, "provider_cost_usd": None},
        logger=logging.getLogger("test"),
        log_prefix="t",
    )
    assert cost == 0.0042


def test_whisper_rows_stay_unpriced() -> None:
    cost = compute_estimated_cost_usd(
        model_name="openai/whisper-large-v3-turbo",
        service_tier=None,
        prompt=None,
        usage={"provider_cost_usd": 0.01},
        logger=logging.getLogger("test"),
        log_prefix="t",
    )
    assert cost is None


def test_update_stores_provider_cost_not_as_its_own_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_update(
        model: str, pk: Any, data: dict[str, Any], wait: bool = True
    ) -> Any:
        captured.update(data)
        return SimpleNamespace(success=True, error=None)

    from podcast_processor import llm_model_call_utils

    monkeypatch.setattr(llm_model_call_utils.writer_client, "update", fake_update)
    response = SimpleNamespace(
        usage=_usage(), _hidden_params={"additional_headers": {_COST_HEADER: 0.002}}
    )
    try_update_model_call(
        5,
        status="success",
        response="ok",
        error_message=None,
        logger=logging.getLogger("test"),
        log_prefix="t",
        usage=extract_litellm_usage(response),
        model_name="openrouter/~deepseek/deepseek-flash-latest",
        prompt="classify",
    )
    assert captured["estimated_cost_usd"] == 0.002
    assert captured["prompt_tokens"] == 1000
    assert "provider_cost_usd" not in captured


def _response(content: str, cost: float) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content), finish_reason="stop"
            )
        ],
        usage=_usage(),
        _hidden_params={"additional_headers": {_COST_HEADER: cost}},
    )


_LLM: dict[str, Any] = {
    "llm_model": "openrouter/~deepseek/deepseek-flash-latest",
    "llm_api_key": "k",
    "openai_base_url": None,
    "timeout_sec": 30,
}


def test_summary_calls_are_recorded_with_their_cost() -> None:
    segments = [
        SimpleNamespace(start_time=i, end_time=i + 1, text="x" * 90) for i in range(30)
    ]
    responses = [
        _response("- a", 0.001),
        _response("- b", 0.001),
        _response("- c", 0.001),
    ]
    responses.append(_response("Fertig", 0.002))
    with (
        mock.patch.object(episode_extras.litellm, "completion", side_effect=responses),
        mock.patch.object(
            episode_extras, "try_upsert_model_call", side_effect=[11, 12, 13, 14]
        ) as upsert,
        mock.patch.object(episode_extras, "try_update_model_call") as update,
    ):
        summary = summarize_transcript(
            segments, [], language="de", chunk_chars=1000, post_id=7, **_LLM
        )

    assert summary == "Fertig"
    seqs = [c.kwargs["first_seq_num"] for c in upsert.call_args_list]
    assert seqs == [
        SUMMARY_MODEL_CALL_SEQ - 1,
        SUMMARY_MODEL_CALL_SEQ - 2,
        SUMMARY_MODEL_CALL_SEQ - 3,
        SUMMARY_MODEL_CALL_SEQ,
    ]
    assert all(c.kwargs["post_id"] == 7 for c in upsert.call_args_list)
    assert [c.args[0] for c in update.call_args_list] == [11, 12, 13, 14]
    final = update.call_args_list[-1].kwargs
    assert final["status"] == "success"
    assert final["usage"]["provider_cost_usd"] == 0.002
    assert final["model_name"] == _LLM["llm_model"]


def test_failed_summary_call_is_marked_failed() -> None:
    segments = [
        SimpleNamespace(start_time=i, end_time=i + 1, text="Ein Satz.")
        for i in range(40)
    ]
    with (
        mock.patch.object(
            episode_extras.litellm, "completion", side_effect=RuntimeError("429")
        ),
        mock.patch.object(episode_extras, "try_upsert_model_call", return_value=21),
        mock.patch.object(episode_extras, "try_update_model_call") as update,
    ):
        assert (
            summarize_transcript(segments, [], language="de", post_id=7, **_LLM) is None
        )

    assert update.call_args.args[0] == 21
    assert update.call_args.kwargs["status"] == "failed_permanent"
    assert "429" in update.call_args.kwargs["error_message"]


def test_usage_has_no_cost_key_when_provider_reports_none() -> None:
    usage = extract_litellm_usage(SimpleNamespace(usage=_usage()))
    assert "provider_cost_usd" not in usage
    assert usage["prompt_tokens"] == 1000

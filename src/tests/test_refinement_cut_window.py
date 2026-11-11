"""Boundary refinement must not cut content or drop parts of an ad group."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest import mock

from app.models import ModelCall, Post, TranscriptSegment
from podcast_processor import ad_classifier
from podcast_processor.ad_classifier import AdClassifier
from podcast_processor.audio_processor import AudioProcessor

_window = AudioProcessor._refined_overlap_window_for_group


def _group(start: float, end: float) -> SimpleNamespace:
    return SimpleNamespace(start_time=start, end_time=end)


def test_refined_block_inside_group_keeps_group_start() -> None:
    # "Werbung" at 49 s is too short to be refined; the spot 64-95 s is.
    refined = [(64.3, 95.0, 64.3, 92.0)]
    assert _window(_group(49.7, 95.0), refined) == (None, 92.0)


def test_refined_block_covering_group_applies_both_edges() -> None:
    refined = [(64.0, 95.0, 66.0, 90.0)]
    assert _window(_group(64.0, 95.0), refined) == (66.0, 90.0)


def test_no_overlap_leaves_group_alone() -> None:
    assert _window(_group(10.0, 20.0), [(30.0, 40.0, 31.0, 39.0)]) is None


def test_apply_refined_boundaries_keeps_announcement() -> None:
    processor = object.__new__(AudioProcessor)
    group = _group(49.7, 95.0)
    with mock.patch.object(
        AudioProcessor,
        "_safe_get_post_row",
        return_value=SimpleNamespace(
            refined_ad_boundaries=[
                {
                    "orig_start": 64.3,
                    "orig_end": 95.0,
                    "refined_start": 64.3,
                    "refined_end": 92.0,
                }
            ]
        ),
    ):
        processor._apply_refined_boundaries(Post(id=1), [group])
    assert (group.start_time, group.end_time) == (49.7, 92.0)


def _ident(seg_id: int, confidence: float) -> SimpleNamespace:
    return SimpleNamespace(
        id=seg_id * 10, transcript_segment_id=seg_id, confidence=confidence
    )


def test_refinement_keeps_each_segment_confidence() -> None:
    """A weak neighbor (0.75) must not be lifted to the block average (0.91)."""
    segments = [
        TranscriptSegment(id=1, start_time=64.3, end_time=72.0),
        TranscriptSegment(id=2, start_time=73.2, end_time=78.0),
        TranscriptSegment(id=3, start_time=81.0, end_time=95.0),
        TranscriptSegment(id=4, start_time=96.0, end_time=97.0),
    ]
    idents = [_ident(1, 0.98), _ident(2, 0.99), _ident(3, 0.75)]
    block = {"identifications": idents, "confidence": 0.907}
    refinement = SimpleNamespace(refined_start=64.3, refined_end=96.5)
    captured: dict[str, Any] = {}

    def fake_action(name: str, payload: dict[str, Any], wait: bool = True) -> Any:
        captured.update(payload)
        return SimpleNamespace(success=True)

    classifier = object.__new__(AdClassifier)
    with mock.patch.object(ad_classifier.writer_client, "action", fake_action):
        classifier._apply_refinement(
            block, refinement, segments, Post(id=7), ModelCall(id=5)
        )

    confidences = {
        i["transcript_segment_id"]: i["confidence"]
        for i in captured["new_identifications"]
    }
    # Existing segments keep their own value; a segment the refinement adds
    # gets the block confidence as before.
    assert confidences == {1: 0.98, 2: 0.99, 3: 0.75, 4: 0.907}
    assert captured["delete_ids"] == [10, 20, 30]


def _gap_processor(previous_end: float | None) -> AudioProcessor:
    processor = object.__new__(AudioProcessor)
    processor.logger = mock.MagicMock()
    session = mock.MagicMock()
    session.query.return_value.filter.return_value.scalar.return_value = previous_end
    processor.db_session = session
    return processor


def test_cut_starts_earlier_into_untranscribed_gap() -> None:
    # Speech ends at 1349.7, the spot starts at 1352.6: the 2.9 s gap held
    # the spoken "Werbung" that the transcription dropped.
    group = _group(1352.6, 1378.9)
    _gap_processor(1349.7)._extend_into_preceding_gap(Post(id=1), [group])
    assert group.start_time == 1349.7


def test_gap_extension_is_capped() -> None:
    group = _group(2609.6, 2634.5)
    _gap_processor(2604.4)._extend_into_preceding_gap(Post(id=1), [group])
    assert group.start_time == 2605.6


def test_no_extension_when_speech_runs_up_to_the_ad() -> None:
    group = _group(64.0, 78.0)
    _gap_processor(64.5)._extend_into_preceding_gap(Post(id=1), [group])
    assert group.start_time == 64.0


def test_extension_at_episode_start_stops_at_zero() -> None:
    group = _group(2.0, 30.0)
    _gap_processor(None)._extend_into_preceding_gap(Post(id=1), [group])
    assert group.start_time == 0.0

import shutil
from pathlib import Path

from podcast_processor.chapter_reader import Chapter, read_chapters
from podcast_processor.chapter_writer import (
    recalculate_chapter_times,
    write_adjusted_chapters,
    write_chapters,
)


def test_recalculate_chapter_times_shrinks_chapter_when_cut_occurs_inside() -> None:
    chapters = [
        Chapter("c1", "Long section", 0, 600_000),
        Chapter("c2", "Later section", 600_000, 900_000),
    ]

    adjusted = recalculate_chapter_times(chapters, removed_segments=[(100.0, 130.0)])

    assert [c.start_time_ms for c in adjusted] == [0, 570_000]
    assert [c.end_time_ms for c in adjusted] == [570_000, 870_000]


def test_recalculate_chapter_times_offsets_each_marker_by_prior_removed_audio() -> None:
    chapters = [
        Chapter("c1", "Intro", 0, 120_000),
        Chapter("c2", "Segment A", 120_000, 240_000),
        Chapter("c3", "Segment B", 240_000, 360_000),
    ]

    adjusted = recalculate_chapter_times(
        chapters,
        removed_segments=[
            (30.0, 40.0),
            (150.0, 170.0),
        ],
    )

    assert [c.start_time_ms for c in adjusted] == [0, 110_000, 210_000]
    assert [c.end_time_ms for c in adjusted] == [110_000, 210_000, 330_000]


def test_recalculate_chapter_times_merges_overlapping_removed_windows() -> None:
    chapters = [
        Chapter("c1", "Part 1", 0, 400_000),
        Chapter("c2", "Part 2", 400_000, 800_000),
    ]

    adjusted = recalculate_chapter_times(
        chapters,
        removed_segments=[
            (100.0, 180.0),
            (150.0, 220.0),
        ],
    )

    # Unique removed duration is 120 seconds, not 150 seconds.
    assert [c.start_time_ms for c in adjusted] == [0, 280_000]
    assert [c.end_time_ms for c in adjusted] == [280_000, 680_000]


def test_recalculate_chapter_times_drops_chapter_fully_inside_removed_audio() -> None:
    chapters = [
        Chapter("c1", "Intro", 0, 60_000),
        Chapter("c2", "Werbung", 60_000, 90_000),
        Chapter("c3", "Topic", 90_000, 200_000),
    ]

    adjusted = recalculate_chapter_times(chapters, removed_segments=[(60.0, 90.0)])

    assert [c.title for c in adjusted] == ["Intro", "Topic"]
    assert [c.start_time_ms for c in adjusted] == [0, 60_000]
    assert [c.end_time_ms for c in adjusted] == [60_000, 170_000]


def test_drop_windows_remove_chapters_inside_an_ad() -> None:
    chapters = [
        Chapter("c1", "Intro", 0, 60_000),
        Chapter("c2", "Sponsor", 60_000, 90_000),
        Chapter("c3", "Topic", 90_000, 200_000),
    ]

    # Fades kept 3 s of the ad on both sides; the ad window covers the chapter.
    adjusted = recalculate_chapter_times(
        chapters, removed_segments=[(63.0, 87.0)], drop_windows=[(59.5, 90.5)]
    )

    assert [c.title for c in adjusted] == ["Intro", "Topic"]
    assert adjusted[1].start_time_ms == 66_000


def test_writing_no_chapters_clears_stale_frames(tmp_path: Path) -> None:
    path = tmp_path / "e.mp3"
    shutil.copyfile(Path(__file__).parent / "data" / "count_0_99.mp3", path)
    write_chapters(str(path), [Chapter("c", "Werbung", 0, 10_000)])

    write_adjusted_chapters(
        str(path), [Chapter("c", "Werbung", 0, 10_000)], [(0.0, 10.0)]
    )

    assert read_chapters(str(path)) == []

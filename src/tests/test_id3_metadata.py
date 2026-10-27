"""Cover art, chapter images and links survive processing."""

import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from mutagen.id3 import APIC, COMM, ID3, TIT2, TLEN, WXXX

from app.models import Post, ProcessingJob
from podcast_processor.audio import clip_segments_with_fade
from podcast_processor.chapter_reader import Chapter, read_chapters
from podcast_processor.chapter_writer import write_adjusted_chapters, write_chapters
from podcast_processor.id3_metadata import copy_id3_metadata
from podcast_processor.podcast_processor import PodcastProcessor

DATA = Path(__file__).parent / "data"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "source.mp3"
    shutil.copyfile(DATA / "count_0_99.mp3", source)
    write_chapters(
        str(source),
        [
            Chapter(
                "c0",
                "Intro",
                0,
                10_000,
                sub_frames=[
                    APIC(encoding=3, mime="image/png", type=0, desc="c0", data=PNG),
                    WXXX(encoding=3, desc="", url="https://example.com/intro"),
                ],
            ),
            Chapter("c1", "Werbung", 10_000, 20_000),
            Chapter("c2", "Thema", 20_000, 40_000),
        ],
    )
    tags = ID3(str(source))
    tags.add(TIT2(encoding=3, text=["Original title"]))
    tags.add(APIC(encoding=3, mime="image/png", type=3, desc="cover", data=PNG))
    tags.add(COMM(encoding=3, lang="deu", desc="", text=["Shownotes"]))
    tags.add(TLEN(encoding=3, text=["66000"]))
    tags.save()
    return source


def test_cover_comment_and_chapter_artwork_survive_a_cut(tmp_path: Path) -> None:
    source = _source(tmp_path)
    out = tmp_path / "out.mp3"
    clip_segments_with_fade([(10_000, 20_000)], 0, str(source), str(out))
    assert not ID3(str(out)).getall("APIC")  # ffmpeg drops the cover

    write_adjusted_chapters(str(out), read_chapters(str(source)), [(10.0, 20.0)])
    copied = copy_id3_metadata(str(source), str(out))

    tags = ID3(str(out))
    assert copied >= 2
    assert tags.getall("APIC")[0].data == PNG
    assert str(tags.getall("COMM")[0].text[0]) == "Shownotes"
    assert not tags.getall("TLEN")  # length of the uncut file would be wrong

    chapters = read_chapters(str(out))
    assert [c.title for c in chapters] == ["Intro", "Thema"]
    intro_frames = {f.FrameID: f for f in chapters[0].sub_frames}
    assert intro_frames["APIC"].data == PNG
    assert intro_frames["WXXX"].url == "https://example.com/intro"


def test_existing_destination_frames_win(tmp_path: Path) -> None:
    source = _source(tmp_path)
    out = tmp_path / "out.mp3"
    shutil.copyfile(DATA / "count_0_99.mp3", out)
    dest_tags = ID3()
    dest_tags.add(TIT2(encoding=3, text=["Podly title"]))
    dest_tags.save(str(out))

    copy_id3_metadata(str(source), str(out))

    assert str(ID3(str(out))["TIT2"].text[0]) == "Podly title"


def test_copy_never_raises_on_untagged_source_or_bad_dest(tmp_path: Path) -> None:
    untagged = tmp_path / "untagged.mp3"
    shutil.copyfile(DATA / "count_0_99.mp3", untagged)
    ID3(str(untagged)).delete()
    dest = tmp_path / "dest.mp3"
    shutil.copyfile(DATA / "count_0_99.mp3", dest)
    not_mp3 = tmp_path / "notes.txt"
    not_mp3.write_text("not audio")
    source = _source(tmp_path)

    assert copy_id3_metadata(str(untagged), str(dest)) == 0
    assert copy_id3_metadata(str(source), str(not_mp3)) == 0
    assert copy_id3_metadata(str(source), str(tmp_path / "missing.mp3")) == 0


def test_finalize_copies_metadata_from_source(tmp_path: Path) -> None:
    source = tmp_path / "in.mp3"
    source.write_bytes(b"x")
    processor = object.__new__(PodcastProcessor)
    processor.logger = MagicMock()
    processor.status_manager = MagicMock()
    processor._remove_unprocessed_audio = MagicMock()
    post = Post(id=1, guid="g", unprocessed_audio_path=str(source))

    with (
        patch("podcast_processor.podcast_processor.copy_id3_metadata") as copy_mock,
        patch(
            "podcast_processor.podcast_processor.get_audio_duration_ms",
            return_value=None,
        ),
        patch("podcast_processor.podcast_processor.writer_client") as writer,
    ):
        writer.update.return_value = SimpleNamespace(success=True)
        processor._finalize_processing(post, ProcessingJob(), "/out/ep.mp3")

    copy_mock.assert_called_once_with(str(source), "/out/ep.mp3")

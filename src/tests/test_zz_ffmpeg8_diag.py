"""TEMPORARY diagnostics for the FFmpeg 8 silence-trim failure. Not for merge."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import ffmpeg
import pytest

from podcast_processor import audio_polish
from podcast_processor.audio_polish import PolishOptions, _apply_cuts

from .test_audio_polish import _tone_silence_tone


def _probe(path: Path) -> str:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_packets",
            "-show_entries",
            "format=duration,bit_rate:stream=duration,nb_read_packets,codec_name,"
            "sample_rate,start_time:format_tags:chapter=start_time,end_time",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.replace("\n", " ") + out.stderr[-300:]


def test_ffmpeg8_diagnostics(tmp_path: Path) -> None:
    report: list[str] = []
    add = report.append
    add(
        subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, check=False
        ).stdout.splitlines()[0]
    )
    src = _tone_silence_tone(tmp_path)
    add("INPUT " + _probe(src))
    windows = audio_polish.silence_cut_windows(audio_polish.detect_silences(str(src)))
    add(f"WINDOWS {windows}")

    for label, build in {
        "aselect_t": lambda i: _apply_cuts(i, windows),
        "aselect_only": lambda i: i.filter(
            "aselect", f"not(between(t,{windows[0][0]:.3f},{windows[0][1]:.3f}))"
        ),
        "aselect_pts": lambda i: i.filter(
            "aselect", f"not(between(pts*TB,{windows[0][0]:.3f},{windows[0][1]:.3f}))"
        ).filter("asetpts", "N/SR/TB"),
        "atrim_first": lambda i: i.filter("atrim", end=windows[0][0]),
        "asetpts_first": lambda i: (
            i.filter("asetpts", "N/SR/TB")
            .filter(
                "aselect", f"not(between(t,{windows[0][0]:.3f},{windows[0][1]:.3f}))"
            )
            .filter("asetpts", "N/SR/TB")
        ),
    }.items():
        out = tmp_path / f"{label}.mp3"
        stream = (
            build(ffmpeg.input(str(src)).audio)
            .output(str(out), acodec="libmp3lame", **{"b:a": "128k"})
            .overwrite_output()
        )
        add(f"{label} ARGS {' '.join(stream.compile())}")
        try:
            _, err = stream.run(capture_stdout=True, capture_stderr=True)
            add(f"{label} OK " + _probe(out))
            add(
                f"{label} STDERR "
                + err.decode(errors="replace")[-600:].replace("\n", " | ")
            )
        except ffmpeg.Error as e:
            add(
                f"{label} ERROR "
                + (e.stderr or b"").decode(errors="replace")[-800:].replace("\n", " | ")
            )

    polished = tmp_path / "polished.mp3"
    shutil.copy(src, polished)
    real_write = audio_polish.write_adjusted_chapters
    seen: dict[str, str] = {}

    def spy(path, chapters, windows_):
        seen["before_chapters"] = _probe(Path(path))
        return real_write(path, chapters, windows_)

    audio_polish.write_adjusted_chapters = spy
    try:
        result = audio_polish.polish_audio(
            str(polished), PolishOptions(trim_silence=True)
        )
    finally:
        audio_polish.write_adjusted_chapters = real_write
    add(f"POLISH result={result}")
    add("POLISH before chapter rewrite " + seen.get("before_chapters", "n/a"))
    add("POLISH final " + _probe(polished))
    pytest.fail("\n".join(report))

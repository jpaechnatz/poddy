"""TEMPORARY diagnostics for the FFmpeg 8 silence-trim failure. Not for merge."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from podcast_processor import audio_polish
from podcast_processor.audio_polish import PolishOptions

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

    long_src = tmp_path / "long.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=f=440:d=60",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(long_src),
        ],
        check=True,
    )
    many = [(round(k * 0.4 + 0.1, 3), round(k * 0.4 + 0.3, 3)) for k in range(150)]
    for label, source, wins, expect in [
        ("asegment_one", src, windows, 16.0 - sum(e - s for s, e in windows)),
        ("asegment_many", long_src, many, 60.0 - sum(e - s for s, e in many)),
    ]:
        out = tmp_path / f"{label}.mp3"
        graph = audio_polish._cut_filtergraph(wins, "anull")
        run = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-i",
                str(source),
                "-filter_complex",
                graph,
                "-map",
                "[out]",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "128k",
                str(out),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        add(f"{label} rc={run.returncode} expect={expect:.2f} graph_len={len(graph)}")
        add(f"{label} RESULT " + _probe(out)[:260])
        add(f"{label} STDERR " + run.stderr[-500:].replace("\n", " | "))

    out = tmp_path / "concat_atrim.mp3"
    run = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-i",
            str(src),
            "-filter_complex",
            "[0:a]asplit[x][y];[x]atrim=end=5.3[a];[y]atrim=start=10.7,asetpts=PTS-STARTPTS[b];"
            "[a][b]concat=n=2:v=0:a=1[out]",
            "-map",
            "[out]",
            "-c:a",
            "libmp3lame",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    add(f"concat_atrim rc={run.returncode} RESULT " + _probe(out)[:260])
    add("concat_atrim STDERR " + run.stderr[-300:].replace("\n", " | "))

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

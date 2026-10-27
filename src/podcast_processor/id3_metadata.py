"""Carry ID3 metadata from the source episode into the processed MP3.

ffmpeg keeps text tags when it re-encodes, but drops the cover image (APIC),
comments, lyrics and link frames. Chapters are written separately with
adjusted times, so they are not copied here.
"""

import logging
from typing import cast

from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.mp3 import MP3, HeaderNotFoundError

logger = logging.getLogger("global_logger")

# Frames that describe positions or lengths in the original audio. They would
# be wrong after cutting: they are never copied, and copies ffmpeg made are
# removed. Chapters are excluded from removal because Podly rewrites them.
_STALE_TIMING_FRAME_IDS = frozenset(
    {"TLEN", "ETCO", "MLLT", "SYTC", "SYLT", "POSS", "ASPI", "SEEK"}
)
_NEVER_COPIED_FRAME_IDS = _STALE_TIMING_FRAME_IDS | {"CHAP", "CTOC"}


# Volume adjustment frames; stale once Podly has normalized the loudness.
_LOUDNESS_FRAME_IDS = frozenset({"RVA2", "RVAD", "EQU2"})


def _is_loudness_frame(key: str, frame: object) -> bool:
    frame_id = getattr(frame, "FrameID", "")
    if frame_id in _LOUDNESS_FRAME_IDS:
        return True
    return frame_id == "TXXX" and key.lower().startswith("txxx:replaygain")


def copy_id3_metadata(
    source_path: str, dest_path: str, skip_loudness_frames: bool = False
) -> int:
    """Copy ID3 frames missing from dest_path out of source_path.

    Stale timing frames (such as TLEN) in dest_path are removed first.

    Frames already present in the destination (same ID3 key) are left alone,
    so values written by Podly win. Returns the number of copied frames.
    Errors are logged and never raised: metadata must not fail processing.
    """
    try:
        source_tags = ID3(source_path)
    except ID3NoHeaderError:
        return 0
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not read ID3 tags from %s: %s", source_path, e)
        return 0

    try:
        audio = MP3(dest_path)
        if audio.tags is None:
            audio.add_tags()
        dest_tags = cast(ID3, audio.tags)

        stale_keys = [
            key
            for key, frame in dest_tags.items()
            if frame.FrameID in _STALE_TIMING_FRAME_IDS
        ]
        for key in stale_keys:
            del dest_tags[key]

        copied = 0
        for key, frame in source_tags.items():
            if frame.FrameID in _NEVER_COPIED_FRAME_IDS or key in dest_tags:
                continue
            if skip_loudness_frames and _is_loudness_frame(key, frame):
                continue
            dest_tags.add(frame)
            copied += 1

        if copied or stale_keys:
            audio.save()
        logger.info("Copied %d ID3 frames from %s", copied, source_path)
        return copied
    except HeaderNotFoundError:
        logger.info("Skipping ID3 metadata copy: %s is not an MP3", dest_path)
        return 0
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not copy ID3 tags into %s: %s", dest_path, e)
        return 0

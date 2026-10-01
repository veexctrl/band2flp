"""Bounded inspection of loop metadata carried by a CAF audio source."""

from __future__ import annotations

import math
import struct
from typing import BinaryIO


# Observed on one supplied CAF. The UUID payload schema needs other fixtures.
LOOP_METADATA_UUID = bytes.fromhex("29819273b5bf4aefb78d62d1ef90bb2c")
MAX_METADATA_CHUNK = 4096


def _discard(stream: BinaryIO, count: int) -> bool:
    while count:
        block = stream.read(min(count, 64 * 1024))
        if not block:
            return False
        count -= len(block)
    return True


def _metadata_pairs(payload: bytes) -> dict[str, str] | None:
    if len(payload) < 4:
        return None
    count = int.from_bytes(payload[:4], "big")
    if count > 64:
        return None
    parts = payload[4:].split(b"\0")
    if len(parts) != 2 * count + 1 or parts[-1] or any(not p for p in parts[:-1]):
        return None
    try:
        values = [part.decode("utf-8") for part in parts[:-1]]
    except UnicodeDecodeError:
        return None
    keys = values[::2]
    if len(set(keys)) != len(keys):
        return None
    return dict(zip(keys, values[1::2]))


def inspect_caf_loop_metadata(stream: BinaryIO) -> dict[str, object] | None:
    """Return source metadata candidates; never infer an arrangement loop flag."""
    if stream.read(8) != b"caff\0\x01\0\0":
        return None
    rate: float | None = None
    valid_frames: int | None = None
    fields: dict[str, str] | None = None
    while True:
        header = stream.read(12)
        if not header:
            break
        if len(header) != 12:
            return None
        tag, size = header[:4], int.from_bytes(header[4:], "big", signed=True)
        if size < 0:
            break  # CAF permits an indefinite final data chunk.
        if tag in (b"desc", b"pakt", b"uuid") and size <= MAX_METADATA_CHUNK:
            payload = stream.read(size)
            if len(payload) != size:
                return None
            if tag == b"desc" and len(payload) >= 8:
                candidate = struct.unpack_from(">d", payload)[0]
                if math.isfinite(candidate) and candidate > 0:
                    rate = candidate
            elif tag == b"pakt" and len(payload) >= 16:
                valid_frames = int.from_bytes(payload[8:16], "big", signed=True)
            elif tag == b"uuid" and payload[:16] == LOOP_METADATA_UUID:
                fields = _metadata_pairs(payload[16:])
        elif not _discard(stream, size):
            return None
    if not fields:
        return None
    result: dict[str, object] = {
        "source": "CAF UUID metadata candidate",
        "confidence": "HIGH CONFIDENCE for literal key/value strings in this source; HYPOTHESIS for Apple Loop library classification",
        "fields": fields,
    }
    beats = fields.get("beat count")
    if beats is not None and beats.isdecimal() and 0 < int(beats) <= 100000:
        result["beat_count"] = int(beats)
        if rate is not None and valid_frames is not None and valid_frames > 0:
            result["source_tempo_bpm_from_frames_candidate"] = round(
                int(beats) * 60 * rate / valid_frames, 6
            )
            result["tempo_confidence"] = "HYPOTHESIS: valid CAF frames may include edits or codec padding"
    return result

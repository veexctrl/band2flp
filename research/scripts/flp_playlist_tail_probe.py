"""Create a local 80-byte playlist probe using opaque tails from FLP references.

Only playlist-event bytes are read from reference projects; referenced media is
never opened. The generated FLP inherits its candidate's private sample paths
and should remain local.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import struct
import tempfile
import warnings
from typing import Any

from band2flp.flp_export import FLPExportError, _pyflp_module
from research.scripts.flp_playlist_inventory import (
    PLAYLIST_EVENT_ID,
    _audio_clip_channel_ids,
)


def _read_varint(data: bytes, offset: int, end: int) -> tuple[int, int]:
    value = shift = 0
    while offset < end and shift <= 63:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
    raise ValueError("invalid or truncated FLP variable-length event size")


def _playlist_spans(data: bytes) -> list[tuple[int, int]]:
    if len(data) < 22 or data[:4] != b"FLhd" or data[14:18] != b"FLdt":
        raise ValueError("invalid FLP header")
    event_bytes = struct.unpack_from("<I", data, 18)[0]
    end = 22 + event_bytes
    if end != len(data):
        raise ValueError("FLP event-data length does not match the file")
    spans = []
    offset = 22
    while offset < end:
        event_id = data[offset]
        offset += 1
        if event_id < 64:
            size = 1
        elif event_id < 128:
            size = 2
        elif event_id < 192:
            size = 4
        else:
            size, offset = _read_varint(data, offset, end)
        if size > end - offset:
            raise ValueError("FLP event extends beyond the file boundary")
        if event_id == PLAYLIST_EVENT_ID:
            spans.append((offset, size))
        offset += size
    return spans


def replace_opaque_tails(candidate: bytes, reference_tails: list[bytes]) -> tuple[bytes, dict[str, int]]:
    """Replace only bytes 32..79 of each explicitly targeted 80-byte row."""
    try:
        spans = _playlist_spans(candidate)
    except ValueError as exc:
        raise FLPExportError(f"invalid candidate FLP: {exc}") from exc
    if len(spans) != 1:
        raise FLPExportError("candidate must contain exactly one playlist event")
    start, size = spans[0]
    if size == 0 or size % 80:
        raise FLPExportError("candidate playlist payload is not a sequence of 80-byte rows")
    row_count = size // 80
    if len(reference_tails) != row_count or any(len(tail) != 48 for tail in reference_tails):
        raise FLPExportError("one 48-byte reference tail is required for each candidate row")

    output = bytearray(candidate)
    changed_byte_count = 0
    changed_row_count = 0
    for index, tail in enumerate(reference_tails):
        tail_start = start + index * 80 + 32
        before = output[tail_start:tail_start + 48]
        if before != tail:
            changed_row_count += 1
            changed_byte_count += sum(left != right for left, right in zip(before, tail))
            output[tail_start:tail_start + 48] = tail

    result = bytes(output)
    check_start, check_size = _playlist_spans(result)[0]
    if check_size != size or result[:check_start] != candidate[:start] or result[check_start + size:] != candidate[start + size:]:
        raise FLPExportError("playlist-tail rewrite changed bytes outside the target rows")
    return result, {
        "playlist_rows": row_count,
        "rows_with_changed_tails": changed_row_count,
        "changed_tail_bytes": changed_byte_count,
    }


def replace_one_tail_byte(
    candidate: bytes, reference_tails: list[bytes], tail_offset: int
) -> tuple[bytes, dict[str, int]]:
    """Copy one opaque tail byte per row, preserving every other serialized byte."""
    if not 0 <= tail_offset < 48:
        raise FLPExportError("tail byte offset must be between 0 and 47")
    try:
        spans = _playlist_spans(candidate)
    except ValueError as exc:
        raise FLPExportError(f"invalid candidate FLP: {exc}") from exc
    if len(spans) != 1:
        raise FLPExportError("candidate must contain exactly one playlist event")
    start, size = spans[0]
    if size == 0 or size % 80:
        raise FLPExportError("candidate playlist payload is not a sequence of 80-byte rows")
    row_count = size // 80
    if len(reference_tails) != row_count or any(len(tail) != 48 for tail in reference_tails):
        raise FLPExportError("one 48-byte reference tail is required for each candidate row")
    output = bytearray(candidate)
    changed_rows = changed_bytes = 0
    for index, tail in enumerate(reference_tails):
        offset = start + index * 80 + 32 + tail_offset
        if output[offset] != tail[tail_offset]:
            output[offset] = tail[tail_offset]
            changed_rows += 1
            changed_bytes += 1
    return bytes(output), {
        "playlist_rows": row_count,
        "rows_with_changed_tails": changed_rows,
        "changed_tail_bytes": changed_bytes,
    }


def _reference_tails(reference_root: Path, limit: int, required: int) -> tuple[list[bytes], int, int]:
    pyflp, _ = _pyflp_module()
    from pyflp.channel import ChannelID

    selected: list[bytes] = []
    seen: set[bytes] = set()
    projects_examined = rows_examined = 0
    for path in sorted(reference_root.rglob("*.flp")):
        if projects_examined >= limit or len(selected) >= required:
            break
        projects_examined += 1
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                project = pyflp.parse(str(path))
            audio_ids = _audio_clip_channel_ids(project, ChannelID)
            data = path.read_bytes()
            for start, size in _playlist_spans(data):
                if size == 0 or size % 80:
                    continue
                for offset in range(start, start + size, 80):
                    row = data[offset:offset + 80]
                    _, pattern_base, item_index = struct.unpack_from("<IHH", row)
                    if item_index > pattern_base or item_index not in audio_ids:
                        continue
                    rows_examined += 1
                    tail = row[32:80]
                    if tail not in seen:
                        seen.add(tail)
                        selected.append(tail)
                        if len(selected) >= required:
                            break
                if len(selected) >= required:
                    break
        except Exception:
            continue
    if len(selected) < required:
        raise FLPExportError("references did not contain enough distinct 80-byte audio-row tails")
    return selected, projects_examined, rows_examined


def create_probe(
    candidate: str | Path,
    reference_root: str | Path,
    output: str | Path,
    limit: int = 100,
    tail_byte_offset: int | None = None,
) -> dict[str, Any]:
    candidate_path = Path(candidate)
    root = Path(reference_root)
    output_path = Path(output)
    if not candidate_path.is_file():
        raise FLPExportError("candidate FLP does not exist")
    if not root.is_dir():
        raise FLPExportError("reference root is not a directory")
    if limit < 1:
        raise FLPExportError("reference limit must be positive")
    if output_path.exists() or output_path.is_symlink():
        raise FLPExportError("output already exists; choose a new path")

    try:
        candidate_bytes = candidate_path.read_bytes()
        spans = _playlist_spans(candidate_bytes)
    except (OSError, ValueError) as exc:
        raise FLPExportError(f"cannot inspect candidate FLP: {type(exc).__name__}") from exc
    if len(spans) != 1 or spans[0][1] == 0 or spans[0][1] % 80:
        raise FLPExportError("candidate must have exactly one nonempty 80-byte playlist event")
    row_count = spans[0][1] // 80
    tails, projects_examined, rows_examined = _reference_tails(root, limit, row_count)
    if tail_byte_offset is None:
        result, changes = replace_opaque_tails(candidate_bytes, tails)
        tail_mode = "full_48_byte_tail"
    else:
        result, changes = replace_one_tail_byte(candidate_bytes, tails, tail_byte_offset)
        tail_mode = "single_tail_byte"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".band2flp-tail-", suffix=".flp", dir=output_path.parent, delete=False) as temp:
            temp_path = Path(temp.name)
            temp.write(result)
        os.link(temp_path, output_path)
    except FileExistsError as exc:
        raise FLPExportError("output appeared during write; choose a new path") from exc
    except OSError as exc:
        raise FLPExportError(f"cannot publish tail probe: {type(exc).__name__}") from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

    return {
        "output_written": True,
        "tail_mode": tail_mode,
        "tail_byte_offset": tail_byte_offset,
        **changes,
        "reference_projects_examined": projects_examined,
        "reference_audio_rows_examined": rows_examined,
        "distinct_reference_tails_used": len(tails),
        "privacy_note": "Only FLP structures were read; referenced media was not opened. The output retains the candidate's private sample paths.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path, help="local candidate FLP with 80-byte playlist rows")
    parser.add_argument("reference_root", type=Path, help="local folder of FLP references")
    parser.add_argument("output", type=Path, help="new local probe FLP")
    parser.add_argument("--limit", type=int, default=100, help="maximum reference projects to scan")
    parser.add_argument("--tail-byte-offset", type=int, help="copy only this opaque byte offset (0-47) per row")
    args = parser.parse_args(argv)
    try:
        result = create_probe(args.candidate, args.reference_root, args.output, args.limit, args.tail_byte_offset)
    except (FLPExportError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

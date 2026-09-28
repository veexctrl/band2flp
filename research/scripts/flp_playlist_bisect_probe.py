"""Keep selected fixed-width playlist rows in a local FLP diagnostic copy.

This is a framing experiment, not a converter. The source FLP may contain
private sample paths; both source and output must remain local.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct

from band2flp.flp_export import FLPExportError
from research.scripts.flp_playlist_state_probe import parse_events


def _varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("negative event length")
    result = bytearray()
    while True:
        byte = value & 0x7f
        value >>= 7
        result.append(byte | 0x80 if value else byte)
        if not value:
            return bytes(result)


def keep_playlist_rows(data: bytes, row_indices: tuple[int, ...], stride: int = 80) -> bytes:
    """Rewrite only the playlist event, keeping chosen rows byte-for-byte."""
    if stride not in (32, 60, 80):
        raise FLPExportError("unsupported diagnostic playlist stride")
    events = parse_events(data)
    playlist = [event for event in events if event["id"] == 233]
    if len(playlist) != 1:
        raise FLPExportError("source must contain exactly one playlist event")
    event = playlist[0]
    payload = data[event["payload_start"]:event["end"]]
    if not payload or len(payload) % stride:
        raise FLPExportError("playlist payload does not match the requested stride")
    count = len(payload) // stride
    if not row_indices or len(row_indices) != len(set(row_indices)) or any(i < 0 or i >= count for i in row_indices):
        raise FLPExportError("row indices must be distinct and within the playlist")
    selected = b"".join(payload[i * stride:(i + 1) * stride] for i in row_indices)
    replacement = bytes((233,)) + _varint(len(selected)) + selected
    output = bytearray(data[:event["start"]] + replacement + data[event["end"]:])
    struct.pack_into("<I", output, 18, len(output) - 22)
    checked = parse_events(output)
    new_event = [item for item in checked if item["id"] == 233]
    if len(new_event) != 1 or output[new_event[0]["payload_start"]:new_event[0]["end"]] != selected:
        raise FLPExportError("playlist rewrite failed validation")
    before = [(item["id"], data[item["payload_start"]:item["end"]]) for item in events if item["id"] != 233]
    after = [(item["id"], output[item["payload_start"]:item["end"]]) for item in checked if item["id"] != 233]
    if before != after:
        raise FLPExportError("playlist rewrite changed a surrounding event")
    return bytes(output)


def create_probe(source: str | Path, output: str | Path, row_indices: tuple[int, ...], stride: int = 80) -> dict[str, int]:
    source_path, output_path = Path(source), Path(output)
    if output_path.exists() or output_path.is_symlink():
        raise FLPExportError("output already exists")
    result = keep_playlist_rows(source_path.read_bytes(), row_indices, stride)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(result)
    return {"selected_rows": len(row_indices), "playlist_stride": stride}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("row", type=int, nargs="+")
    parser.add_argument("--stride", type=int, default=80, choices=(32, 60, 80))
    args = parser.parse_args(argv)
    try:
        report = create_probe(args.source, args.output, tuple(args.row), args.stride)
    except (OSError, ValueError, FLPExportError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

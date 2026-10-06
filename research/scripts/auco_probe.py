"""Test a Logic-like AuCO record pattern without assigning GarageBand semantics."""

from __future__ import annotations

import argparse
import base64
import json
import struct
from collections import Counter
from pathlib import Path
from typing import Any

from band2flp.parser import BandFormatError, parse_band


VARIANT = bytes.fromhex("07000e00")
RECORD_OFFSET = 60
RECORD_SIZE = 24


def probe_logic_payload(raw: bytes, stream: dict[str, Any]) -> dict[str, Any]:
    """Summarize chunks matching the candidate AuCO marker and record layout.

    Names are validated but never included in the output, keeping project
    content out of routine research reports.
    """
    candidates: list[dict[str, Any]] = []
    marker_candidate_count = 0
    for chunk in stream.get("chunks", []):
        if chunk.get("type") != "AuCO":
            continue
        offset = chunk["offset"]
        payload_start = chunk["payload_offset"]
        payload_size = chunk["payload_size"]
        if (
            not 0 <= offset <= len(raw) - 36
            or payload_start != offset + 36
            or not 0 <= payload_size <= len(raw) - payload_start
        ):
            raise BandFormatError("AuCO chunk header or payload offset is invalid")
        header = raw[offset:offset + 36]
        if header[4:8] != VARIANT or payload_size < RECORD_OFFSET + RECORD_SIZE:
            continue
        marker_candidate_count += 1
        record = raw[payload_start + RECORD_OFFSET:payload_start + RECORD_OFFSET + RECORD_SIZE]
        if len(record) != RECORD_SIZE:
            raise BandFormatError("AuCO candidate record is truncated")
        field = record[:16]
        name_storage = field[1:]
        terminator = name_storage.find(b"\x00")
        name = name_storage if terminator < 0 else name_storage[:terminator]
        padding = b"" if terminator < 0 else name_storage[terminator:]
        if not name or any(byte < 0x20 or byte > 0x7E for byte in name) or any(padding):
            continue
        candidates.append({
            "chunk_index": chunk["index"],
            "group_id_candidate": struct.unpack_from("<I", header, 8)[0],
            "strip_index_candidate": struct.unpack_from("<H", header, 14)[0],
            "payload_size": payload_size,
            "name_length": len(name),
            "descriptor_hex": record[16:24].hex(),
        })
    strip_ids = [item["strip_index_candidate"] for item in candidates]
    return {
        "candidate_marker_hex": VARIANT.hex(),
        "candidate_payload_record_offset": RECORD_OFFSET,
        "candidate_payload_record_size": RECORD_SIZE,
        "marker_candidate_count": marker_candidate_count,
        "validated_record_count": len(candidates),
        "group_id_candidate_counts": {
            f"0x{group:08X}": count
            for group, count in sorted(Counter(item["group_id_candidate"] for item in candidates).items())
        },
        "strip_index_candidates": strip_ids,
        "strip_indices_unique": len(set(strip_ids)) == len(strip_ids),
        "strip_indices_contiguous_from_zero": sorted(strip_ids) == list(range(len(strip_ids))),
        "records": candidates,
        "interpretation": "HYPOTHESIS; Logic Pro layout match does not establish GarageBand track semantics",
    }


def probe_project(path: str | Path) -> dict[str, Any]:
    project = parse_band(path)
    data = project.project_data
    stream = data.get("logic_song_chunk_stream")
    if not isinstance(stream, dict):
        raise BandFormatError("project has no validated logic-song chunk stream")
    object_index = data.get("logic_song_object_index")
    for blob in data.get("opaque_data_objects", []):
        if blob.get("object_index") != object_index or not isinstance(blob.get("base64"), str):
            continue
        raw = base64.b64decode(blob["base64"], validate=True)
        if len(raw) != blob.get("length") or stream.get("end_offset") != len(raw):
            raise BandFormatError("retained logic-song payload is inconsistent")
        return probe_logic_payload(raw, stream)
    raise BandFormatError("logic-song NSData payload was not retained")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="auco_probe")
    parser.add_argument("project", help="GarageBand .band package")
    args = parser.parse_args(argv)
    try:
        report = probe_project(args.project)
    except (BandFormatError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

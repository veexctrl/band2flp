"""Summarize MSeq payload shapes without exposing payload bytes or project data."""

from __future__ import annotations

import argparse
import base64
from collections import Counter
import json
from pathlib import Path
import struct
from typing import Any

from band2flp.parser import BandFormatError, parse_band


def summarize_payloads(payloads: list[bytes]) -> dict[str, Any]:
    """Return shape counts and unassigned tail-word profiles only."""
    if any(not isinstance(payload, bytes) for payload in payloads):
        raise BandFormatError("MSeq payloads must be bytes")
    prefix_length = 0
    if payloads:
        prefix_length = min(map(len, payloads))
        for index in range(prefix_length):
            if len({payload[index] for payload in payloads}) != 1:
                prefix_length = index
                break

    tail_profiles: dict[str, dict[str, int]] = {}
    for tail in (219, 55):
        values = []
        for payload in payloads:
            offset = len(payload) - tail
            if offset < 0:
                continue
            values.append(struct.unpack_from("<I", payload, offset)[0])
        tail_profiles[str(tail)] = {
            "readable_count": len(values),
            "distinct_value_count": len(set(values)),
            "zero_count": values.count(0),
            "all_ones_count": values.count(0xFFFFFFFF),
        }

    return {
        "mseq_count": len(payloads),
        "payload_size_counts": {
            str(size): count for size, count in sorted(Counter(map(len, payloads)).items())
        },
        "longest_common_prefix_length": prefix_length,
        "standard_midi_header_count": sum(payload.startswith(b"MThd") for payload in payloads),
        "unassigned_tail_word_profiles": tail_profiles,
        "semantics": "UNKNOWN; tail positions are exploratory and are not decoded",
        "privacy_note": "Counts only; payload bytes, strings, identifiers, and values are omitted.",
    }


def probe_logic_payload(raw: bytes, stream: dict[str, Any]) -> dict[str, Any]:
    chunks = stream.get("chunks", [])
    payloads = []
    for chunk in chunks:
        if chunk.get("type") != "MSeq":
            continue
        start = chunk.get("payload_offset")
        size = chunk.get("payload_size")
        if (
            not isinstance(start, int)
            or not isinstance(size, int)
            or size < 0
            or not 0 <= start <= len(raw) - size
        ):
            raise BandFormatError("MSeq payload bounds are invalid")
        payloads.append(raw[start:start + size])
    return summarize_payloads(payloads)


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
    parser = argparse.ArgumentParser(prog="mseq_probe")
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

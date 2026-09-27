"""Summarize Trak header and payload shapes without exposing project content."""

from __future__ import annotations

import argparse
import base64
from collections import Counter
import json
from pathlib import Path
import struct
from typing import Any

from band2flp.parser import BandFormatError, parse_band


def _prefix_summary(payloads: list[bytes]) -> dict[str, int]:
    if not payloads:
        return {
            "record_count": 0,
            "distinct_first_8_byte_prefixes": 0,
            "most_common_first_8_byte_prefix_count": 0,
            "longest_common_prefix_length": 0,
        }
    prefix_counts = Counter(payload[:8] for payload in payloads)
    common_length = min(map(len, payloads))
    for offset in range(common_length):
        if len({payload[offset] for payload in payloads}) != 1:
            common_length = offset
            break
    return {
        "record_count": len(payloads),
        "distinct_first_8_byte_prefixes": len(prefix_counts),
        "most_common_first_8_byte_prefix_count": max(prefix_counts.values()),
        "longest_common_prefix_length": common_length,
    }


def probe_logic_payload(raw: bytes, stream: dict[str, Any]) -> dict[str, Any]:
    """Report aggregate Trak structure; never emit group IDs or payload bytes."""
    chunks = stream.get("chunks", [])
    traks: list[tuple[dict[str, Any], bytes]] = []
    for chunk in chunks:
        if chunk.get("type") != "Trak":
            continue
        offset = chunk.get("offset")
        payload_start = chunk.get("payload_offset")
        payload_size = chunk.get("payload_size")
        if (
            not isinstance(offset, int)
            or not isinstance(payload_start, int)
            or not isinstance(payload_size, int)
            or not 0 <= offset <= len(raw) - 36
            or payload_start != offset + 36
            or not 0 <= payload_size <= len(raw) - payload_start
        ):
            raise BandFormatError("Trak chunk header or payload offset is invalid")
        header = raw[offset:offset + 36]
        payload = raw[payload_start:payload_start + payload_size]
        traks.append(({
            "header": header,
            "payload_size": payload_size,
            "group_id_candidate": chunk.get("group_id_candidate"),
        }, payload))

    field_counts = Counter(
        struct.unpack_from("<H", item["header"], 0x0E)[0]
        for item, _ in traks
    )
    size_counts = Counter(item["payload_size"] for item, _ in traks)
    mseq_groups = Counter(
        chunk.get("group_id_candidate")
        for chunk in chunks
        if chunk.get("type") == "MSeq"
    )
    empty_trak_groups = Counter(
        chunk.get("group_id_candidate")
        for chunk, _ in traks
        if chunk["payload_size"] == 0
    )
    prefix_summaries = {
        str(size): _prefix_summary([payload for item, payload in traks if item["payload_size"] == size])
        for size in sorted(size_counts)
        if size > 0
    }
    return {
        "trak_count": len(traks),
        "payload_size_counts": {str(size): count for size, count in sorted(size_counts.items())},
        "header_u16_at_0x0e_counts": {
            f"0x{value:04X}": count for value, count in sorted(field_counts.items())
        },
        "mseq_empty_trak_group_candidates": {
            "mseq_chunk_count": sum(mseq_groups.values()),
            "empty_trak_chunk_count": sum(empty_trak_groups.values()),
            "distinct_mseq_group_values": len(mseq_groups),
            "distinct_empty_trak_group_values": len(empty_trak_groups),
            "group_value_multiplicities_match": mseq_groups == empty_trak_groups,
            "mseq_groups_without_empty_trak": len(mseq_groups.keys() - empty_trak_groups.keys()),
            "empty_trak_groups_without_mseq": len(empty_trak_groups.keys() - mseq_groups.keys()),
            "interpretation": "UNKNOWN; same-group occurrence does not establish track or region identity",
        },
        "payload_prefix_summaries": prefix_summaries,
        "interpretation": "UNKNOWN; aggregate structure only, with no track identity or field semantics assigned",
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
    parser = argparse.ArgumentParser(prog="trak_probe")
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

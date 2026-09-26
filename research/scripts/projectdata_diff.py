"""Compare GarageBand logic-song chunk streams without trusting ZIP offsets."""

from __future__ import annotations

import argparse
import base64
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from band2flp.parser import BandFormatError, parse_band


def _logic_payload_from_project(project: Any) -> bytes:
    data = project.project_data
    object_index = data.get("logic_song_object_index")
    if not isinstance(object_index, int):
        raise BandFormatError("projectData has no recognized logic-song object")
    blobs = data.get("opaque_data_objects", [])
    for blob in blobs:
        if blob.get("object_index") == object_index and isinstance(blob.get("base64"), str):
            try:
                payload = base64.b64decode(blob["base64"], validate=True)
            except (ValueError, TypeError) as exc:
                raise BandFormatError("retained logic-song payload is invalid base64") from exc
            if len(payload) != blob.get("length"):
                raise BandFormatError("retained logic-song payload length does not match its summary")
            return payload
    raise BandFormatError("logic-song NSData payload was not retained")


def load_logic_payload(path: str | Path) -> bytes:
    """Load the retained logic-song NSData payload from a GarageBand package."""
    return _logic_payload_from_project(parse_band(path))


def _chunk_payloads(data: dict[str, Any], raw: bytes) -> list[dict[str, Any]]:
    stream = data.get("logic_song_chunk_stream")
    if not isinstance(stream, dict) or stream.get("end_offset") != len(raw):
        raise BandFormatError("logic-song chunk boundaries are unavailable or inconsistent")
    chunks: list[dict[str, Any]] = []
    occurrences: defaultdict[tuple[str, int], int] = defaultdict(int)
    for chunk in stream.get("chunks", []):
        tag = chunk.get("type") or f"raw:{chunk['raw_type_hex']}"
        group = chunk.get("group_id_candidate")
        if not isinstance(group, int):
            raise BandFormatError("chunk has no integer candidate group field")
        key = (tag, group)
        ordinal = occurrences[key]
        occurrences[key] += 1
        start = chunk["payload_offset"]
        end = start + chunk["payload_size"]
        chunk_offset = chunk["offset"]
        if not 0 <= chunk_offset <= len(raw) - 36 or not chunk_offset + 36 <= start <= end <= len(raw):
            raise BandFormatError("chunk payload range is outside the logic-song data")
        chunks.append({
            "index": chunk["index"],
            "offset": chunk_offset,
            "type": tag,
            "group_id_candidate": group,
            "ordinal_within_type_and_group": ordinal,
            "header": raw[chunk_offset:chunk_offset + 36],
            "payload": raw[start:end],
        })
    return chunks


def _changed_ranges(before: bytes, after: bytes) -> list[dict[str, Any]]:
    common = min(len(before), len(after))
    ranges: list[dict[str, Any]] = []
    index = 0
    while index < common:
        if before[index] == after[index]:
            index += 1
            continue
        start = index
        while index < common and before[index] != after[index]:
            index += 1
        ranges.append({
            "offset_start": start,
            "offset_end_exclusive": index,
            "before_hex": before[start:index].hex(),
            "after_hex": after[start:index].hex(),
        })
    if len(before) != len(after):
        ranges.append({
            "offset_start": common,
            "offset_end_exclusive": max(len(before), len(after)),
            "before_hex": before[common:].hex(),
            "after_hex": after[common:].hex(),
            "kind": "appended_or_truncated_tail",
        })
    return ranges


def compare_payloads(before_data: dict[str, Any], before: bytes, after_data: dict[str, Any], after: bytes) -> dict[str, Any]:
    """Compare chunk payloads using a cautious type/group/ordinal alignment."""
    left = _chunk_payloads(before_data, before)
    right = _chunk_payloads(after_data, after)
    key = lambda chunk: (chunk["type"], chunk["group_id_candidate"], chunk["ordinal_within_type_and_group"])
    old_map = {key(chunk): chunk for chunk in left}
    new_map = {key(chunk): chunk for chunk in right}
    common_keys = sorted(old_map.keys() & new_map.keys())
    modified: list[dict[str, Any]] = []
    unchanged_count = 0
    for identity in common_keys:
        old_chunk = old_map[identity]
        new_chunk = new_map[identity]
        if old_chunk["payload"] == new_chunk["payload"] and old_chunk["header"] == new_chunk["header"]:
            unchanged_count += 1
            continue
        modified.append({
            "type": identity[0],
            "group_id_candidate": identity[1],
            "ordinal_within_type_and_group": identity[2],
            "before_chunk_index": old_chunk["index"],
            "after_chunk_index": new_chunk["index"],
            "before_payload_size": len(old_chunk["payload"]),
            "after_payload_size": len(new_chunk["payload"]),
            "changed_header_ranges": _changed_ranges(old_chunk["header"], new_chunk["header"]),
            "changed_ranges": _changed_ranges(old_chunk["payload"], new_chunk["payload"]),
        })
    return {
        "alignment": "chunk type + candidate group field + ordinal within that pair",
        "alignment_confidence": "HYPOTHESIS; ordinal correspondence is not a semantic identity",
        "insertion_warning": "Adding or deleting a same-type chunk in a group can shift later ordinal matches.",
        "before_chunk_count": len(left),
        "after_chunk_count": len(right),
        "unchanged_matched_count": unchanged_count,
        "modified": modified,
        "added": [
            {"type": identity[0], "group_id_candidate": identity[1], "ordinal": identity[2], "chunk_index": new_map[identity]["index"]}
            for identity in sorted(new_map.keys() - old_map.keys())
        ],
        "removed": [
            {"type": identity[0], "group_id_candidate": identity[1], "ordinal": identity[2], "chunk_index": old_map[identity]["index"]}
            for identity in sorted(old_map.keys() - new_map.keys())
        ],
    }


def compare_projects(before_path: str | Path, after_path: str | Path) -> dict[str, Any]:
    before_project = parse_band(before_path)
    after_project = parse_band(after_path)
    before_data = before_project.project_data
    after_data = after_project.project_data
    before_raw = _logic_payload_from_project(before_project)
    after_raw = _logic_payload_from_project(after_project)
    return compare_payloads(before_data, before_raw, after_data, after_raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="projectdata_diff")
    parser.add_argument("before", help="first GarageBand .band package")
    parser.add_argument("after", help="second GarageBand .band package")
    args = parser.parse_args(argv)
    try:
        report = compare_projects(args.before, args.after)
    except BandFormatError as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

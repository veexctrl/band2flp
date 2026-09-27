"""Probe placement-tick candidates in linked GarageBand MSeq payloads.

The probe checks an exploratory payload-relative field and the translated
record-relative Logic candidates after the observed 36-byte GarageBand chunk
header. The output contains aggregate counts by default. ``--ida-offsets`` also
prints selected fixture offsets and values for IDA checks; do not commit those
fixture-specific values as format facts.
"""

from __future__ import annotations

import argparse
import plistlib
import struct
import zipfile
from pathlib import Path
from typing import Any

from band2flp.parser import (
    _parse_chunk_stream,
    _parse_event_sequences,
    _parse_midi_region_placement_candidates,
    _uid_index,
)


def _payload_from_archive(path: Path) -> bytes:
    with zipfile.ZipFile(path) as archive:
        matches = [name for name in archive.namelist() if name.endswith("/projectData")]
        if len(matches) != 1:
            raise ValueError("expected one projectData package member")
        root = plistlib.loads(archive.read(matches[0]))
    objects = root.get("$objects") if isinstance(root, dict) else None
    top = root.get("$top") if isinstance(root, dict) else None
    if not isinstance(objects, list) or not isinstance(top, dict):
        raise ValueError("projectData is not a keyed archive")
    model_index = _uid_index(top.get("DfDocument logic model"))
    model = objects[model_index] if model_index is not None and model_index < len(objects) else None
    song_index = _uid_index(model.get("DfLogicModelLogicSong")) if isinstance(model, dict) else None
    song = objects[song_index] if song_index is not None and song_index < len(objects) else None
    payload = song.get("NS.data") if isinstance(song, dict) else None
    if not isinstance(payload, bytes):
        raise ValueError("logic-song NSData was not found")
    return payload


def profile_record_relative_mseq_candidates(
    payload: bytes,
    chunks: list[dict[str, Any]],
    placements: list[dict[str, Any]],
) -> dict[str, Any]:
    """Test Logic record-relative region fields after removing the 36-byte chunk header."""
    chunks_by_index = {chunk.get("index"): chunk for chunk in chunks}
    eligible = 0
    start_equal = 0
    start_zero_equal = 0
    start_nonzero_equal = 0
    nonzero_starts = 0
    length_values: list[int] = []
    for placement in placements:
        linked = placement.get("candidate_mseq_chunk_indices")
        if not isinstance(linked, list) or len(linked) != 1:
            continue
        chunk = chunks_by_index.get(linked[0])
        if chunk is None or chunk.get("type") != "MSeq":
            raise ValueError("placement references a missing MSeq chunk")
        base, size = chunk.get("payload_offset"), chunk.get("payload_size")
        ticks = placement.get("position_ticks_from_origin_candidate")
        if not isinstance(base, int) or not isinstance(size, int) or size < 0xFC:
            continue
        if not isinstance(ticks, int) or base < 0 or base + size > len(payload):
            raise ValueError("linked MSeq payload bounds or placement position are invalid")

        # Logic's documented +0x11c and +0x78 are record-relative. GarageBand
        # chunks have a 36-byte header, so test payload-relative +0xf8 and +0x54.
        candidate_start = struct.unpack_from("<I", payload, base + 0xF8)[0]
        candidate_length = struct.unpack_from("<I", payload, base + 0x54)[0]
        eligible += 1
        length_values.append(candidate_length)
        if ticks != 0:
            nonzero_starts += 1
        if candidate_start == ticks:
            start_equal += 1
            if ticks == 0:
                start_zero_equal += 1
            else:
                start_nonzero_equal += 1

    return {
        "linked_mseqs_eligible_for_record_relative_fields": eligible,
        "record_plus_0x11c_candidate_equals_placement_ticks": start_equal,
        "record_plus_0x11c_zero_to_zero_equalities": start_zero_equal,
        "record_plus_0x11c_nonzero_position_equalities": start_nonzero_equal,
        "record_relative_candidates_with_nonzero_placement_ticks": nonzero_starts,
        "record_plus_0x78_candidate_zero_count": length_values.count(0),
        "record_plus_0x78_candidate_distinct_value_count": len(set(length_values)),
    }


def probe(path: Path) -> dict[str, Any]:
    payload = _payload_from_archive(path)
    stream = _parse_chunk_stream(payload)
    events = _parse_event_sequences(payload, stream)
    placements = _parse_midi_region_placement_candidates(events, stream)
    chunks = {chunk["index"]: chunk for chunk in stream["chunks"]}
    eligible = 0
    equal = 0
    nonzero_equal = 0
    zero_equal = 0
    nonzero_ticks = 0
    contains_nearby = 0
    ambiguous_groups = 0
    offsets: list[dict[str, int]] = []
    for placement in placements:
        linked = placement["candidate_mseq_chunk_indices"]
        if len(linked) != 1:
            ambiguous_groups += 1
            continue
        chunk = chunks[linked[0]]
        start = chunk["payload_offset"]
        size = chunk["payload_size"]
        if size < 0x120:
            continue
        eligible += 1
        ticks = placement["position_ticks_from_origin_candidate"]
        field = struct.unpack_from("<I", payload, start + 0x11C)[0]
        if field == ticks:
            equal += 1
            if ticks == 0:
                zero_equal += 1
            else:
                nonzero_equal += 1
        if ticks:
            nonzero_ticks += 1
        low = max(0, start + 0x100)
        high = min(len(payload) - 4, start + min(size - 4, 0x140))
        if any(struct.unpack_from("<I", payload, offset)[0] == ticks
               for offset in range(low, high + 1, 4)):
            contains_nearby += 1
        if len(offsets) < 8 and (ticks != 0 or field != 0):
            offsets.append({"payload_offset": start + 0x11C, "field_value": field,
                            "placement_ticks_candidate": ticks})
    record_relative = profile_record_relative_mseq_candidates(payload, stream["chunks"], placements)
    return {
        "placements": len(placements),
        "unique_mseq_links": sum(len(p["candidate_mseq_chunk_indices"]) == 1 for p in placements),
        "ambiguous_or_missing_links": ambiguous_groups,
        "linked_mseq_payloads_at_least_0x120": eligible,
        "u32_at_payload_plus_0x11c_equals_placement_ticks": equal,
        "zero_to_zero_equalities": zero_equal,
        "nonzero_equalities": nonzero_equal,
        "nonzero_placement_tick_candidates": nonzero_ticks,
        "placement_ticks_appear_in_aligned_words_from_plus_0x100_to_plus_0x140": contains_nearby,
        **record_relative,
        "ida_samples": offsets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", nargs="+", type=Path, help="local .band project archives")
    parser.add_argument("--ida-offsets", action="store_true",
                        help="include fixture-specific offsets and candidate values for manual IDA checking")
    args = parser.parse_args()
    for index, project in enumerate(args.projects, start=1):
        result = probe(project)
        if not args.ida_offsets:
            result.pop("ida_samples")
        print(f"fixture_{index}: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

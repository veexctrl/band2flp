"""Compare exploratory MSeq tail words with linked event timing; counts only.

The tail positions come from the independent Logic Pro implementation listed
in the research references. Neither their meaning nor the event timing units
are established for GarageBand. Equalities and containment are tests of a
hypothesis, not a duration decoder.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter
import json
from pathlib import Path
import struct
from typing import Any

from band2flp.parser import (
    BandFormatError,
    _parse_event_sequences,
    _parse_midi_note_candidates,
    _parse_midi_region_placement_candidates,
    parse_band,
)


def profile_relations(raw: bytes, stream: dict[str, Any]) -> dict[str, Any]:
    """Test end-relative words without returning bytes, identifiers or music."""
    chunks = stream.get("chunks", [])
    for chunk in chunks:
        start, size = chunk.get("payload_offset"), chunk.get("payload_size")
        if (not isinstance(start, int) or not isinstance(size, int)
                or size < 0 or not 0 <= start <= len(raw) - size):
            raise BandFormatError("chunk payload bounds are invalid")
    events = _parse_event_sequences(raw, stream)
    notes = _parse_midi_note_candidates(events, stream)
    placements = _parse_midi_region_placement_candidates(events, stream)
    linked_notes: dict[int, list[dict[str, Any]]] = {}
    ambiguous_notes = 0
    for note in notes:
        links = note["candidate_mseq_chunk_indices_for_group"]
        if len(links) == 1:
            linked_notes.setdefault(links[0], []).append(note)
        else:
            ambiguous_notes += 1

    counts: Counter[str] = Counter()
    for chunk in chunks:
        if chunk.get("type") != "MSeq":
            continue
        counts["mseq_count"] += 1
        start, size = chunk["payload_offset"], chunk["payload_size"]
        if size < 219:
            counts["mseq_too_short_for_tail_words"] += 1
            continue
        length_word = struct.unpack_from("<I", raw, start + size - 219)[0]
        offset_word = struct.unpack_from("<i", raw, start + size - 55)[0]
        counts["tail_length_word_zero_count"] += length_word == 0
        counts["tail_offset_word_zero_count"] += offset_word == 0
        group_notes = linked_notes.get(chunk["index"], [])
        if group_notes:
            counts["note_bearing_unique_mseq_count"] += 1
            # Deliberately use integer words only: +2 fraction scaling remains
            # unknown, so this is an integer-bound comparison, not exact time.
            ends = [n["position_ticks_from_38400_candidate"]
                    + n["duration_ticks_candidate"] for n in group_notes]
            counts["tail_length_equals_max_integer_note_end"] += length_word == max(ends)
            counts["tail_length_contains_all_integer_note_ends"] += all(
                0 <= n["position_ticks_from_38400_candidate"] <= end <= length_word
                for n, end in zip(group_notes, ends)
            )
            counts["tail_length_contains_all_offset_integer_note_ends"] += all(
                0 <= n["position_ticks_from_38400_candidate"] + offset_word
                <= end + offset_word <= length_word
                for n, end in zip(group_notes, ends)
            )
        for placement in placements:
            if placement["candidate_mseq_chunk_indices"] != [chunk["index"]]:
                continue
            counts["unique_placement_tail_comparison_count"] += 1
            counts["tail_offset_equals_placement_integer_ticks"] += (
                offset_word == placement["position_ticks_from_origin_candidate"]
            )
            ticks = placement["position_ticks_from_origin_candidate"]
            counts["nonzero_placement_integer_ticks_count"] += ticks != 0
            counts["tail_offset_equals_nonzero_placement_integer_ticks"] += ticks != 0 and offset_word == ticks
            word = struct.unpack_from("<I", bytes.fromhex(placement["raw_hex"]), 28)[0]
            if word != 0x3FFFFFFF:
                counts["nonsentinel_placement_word_count"] += 1
                counts["tail_length_equals_nonsentinel_placement_word"] += length_word == word

    keys = (
        "mseq_count", "mseq_too_short_for_tail_words", "tail_length_word_zero_count",
        "tail_offset_word_zero_count", "note_bearing_unique_mseq_count",
        "tail_length_equals_max_integer_note_end", "tail_length_contains_all_integer_note_ends",
        "tail_length_contains_all_offset_integer_note_ends",
        "unique_placement_tail_comparison_count", "tail_offset_equals_placement_integer_ticks",
        "nonzero_placement_integer_ticks_count", "tail_offset_equals_nonzero_placement_integer_ticks",
        "nonsentinel_placement_word_count", "tail_length_equals_nonsentinel_placement_word",
    )
    return {
        **{key: counts[key] for key in keys},
        "note_candidate_count": len(notes),
        "notes_without_unique_mseq_link": ambiguous_notes,
        "note_fraction_word_nonzero_count": sum(n["position_fraction_raw"] != 0 for n in notes),
        "note_fraction_word_distinct_count": len({n["position_fraction_raw"] for n in notes}),
        "confidence": "UNKNOWN: tail meanings, fraction scaling, origins and units are unverified",
        "privacy_note": "Aggregate counts only; no music, labels, identifiers or raw values.",
    }


def probe_project(path: str | Path) -> dict[str, Any]:
    project = parse_band(path)
    data = project.project_data
    stream = data.get("logic_song_chunk_stream")
    if not isinstance(stream, dict):
        raise BandFormatError("project has no validated logic-song chunk stream")
    for blob in data.get("opaque_data_objects", []):
        if blob.get("object_index") != data.get("logic_song_object_index"):
            continue
        raw = base64.b64decode(blob["base64"], validate=True)
        if len(raw) != blob.get("length") or len(raw) != stream.get("end_offset"):
            raise BandFormatError("retained logic-song payload is inconsistent")
        return profile_relations(raw, stream)
    raise BandFormatError("logic-song NSData payload was not retained")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project")
    args = parser.parse_args()
    try:
        report = probe_project(args.project)
    except (BandFormatError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

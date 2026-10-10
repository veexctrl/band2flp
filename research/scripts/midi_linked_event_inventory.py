"""Inventory event-type and record-size candidates in placed MIDI groups.

The report contains aggregate counts only. It omits event payloads, group IDs,
note values, names, paths, and media references. Event-type semantics remain
unknown; values resembling MIDI status bytes are not decoded as MIDI messages.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any

from band2flp.parser import BandFormatError, parse_band


def inventory(
    records: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    placements: list[dict[str, Any]],
    note_group_ids: set[int] | None = None,
) -> dict[str, Any]:
    """Summarize records sharing a uniquely linked MIDI MSeq group."""
    mseq_by_index: dict[int, dict[str, Any]] = {}
    for chunk in chunks:
        if chunk.get("type") != "MSeq":
            continue
        index = chunk.get("index")
        group = chunk.get("group_id_candidate")
        if not isinstance(index, int) or not isinstance(group, int):
            raise BandFormatError("MSeq chunk has invalid candidate metadata")
        if index in mseq_by_index:
            raise BandFormatError("MSeq chunk indices are not unique")
        mseq_by_index[index] = chunk

    groups: set[int] = set()
    unique_placements = 0
    ambiguous_placements = 0
    for placement in placements:
        links = placement.get("candidate_mseq_chunk_indices")
        if not isinstance(links, list):
            raise BandFormatError("MIDI placement has invalid MSeq links")
        if len(links) != 1:
            ambiguous_placements += 1
            continue
        index = links[0]
        if not isinstance(index, int) or index not in mseq_by_index:
            raise BandFormatError("MIDI placement references a missing MSeq chunk")
        groups.add(mseq_by_index[index]["group_id_candidate"])
        unique_placements += 1

    by_type: dict[int, Counter[int]] = defaultdict(Counter)
    groups_by_type: dict[int, set[int]] = defaultdict(set)
    for record in records:
        group = record.get("group_id_candidate")
        if group not in groups:
            continue
        event_type = record.get("type_byte")
        length = record.get("length")
        if not isinstance(event_type, int) or not 0 <= event_type <= 0xFF:
            raise BandFormatError("event record has an invalid type byte")
        if not isinstance(length, int) or length <= 0:
            raise BandFormatError("event record has an invalid length")
        by_type[event_type][length] += 1
        groups_by_type[event_type].add(group)

    note_group_ids = note_group_ids or set()
    event_types = {
        f"0x{event_type:02x}": {
            "record_count": sum(length_counts.values()),
            "distinct_group_count": len(groups_by_type[event_type]),
            "groups_with_note_candidates": len(groups_by_type[event_type] & note_group_ids),
            "groups_without_note_candidates": len(groups_by_type[event_type] - note_group_ids),
            "record_length_counts": {
                str(length): length_counts[length]
                for length in sorted(length_counts)
            },
        }
        for event_type, length_counts in sorted(by_type.items())
    }
    return {
        "midi_placement_count": len(placements),
        "placements_with_unique_mseq_link": unique_placements,
        "placements_with_ambiguous_or_missing_mseq_link": ambiguous_placements,
        "distinct_uniquely_linked_midi_groups": len(groups),
        "linked_groups_with_note_candidates": len(groups & note_group_ids),
        "linked_groups_without_note_candidates": len(groups - note_group_ids),
        "groups_with_event_records": len({
            record["group_id_candidate"]
            for record in records
            if record.get("group_id_candidate") in groups
        }),
        "linked_event_record_count": sum(sum(counts.values()) for counts in by_type.values()),
        "event_types": event_types,
        "interpretation": (
            "UNKNOWN; event types and payloads are preserved candidates. "
            "MIDI-status-like values and record lengths do not establish message semantics."
        ),
        "privacy_note": "Only event-type, group-count, and record-length aggregates are emitted.",
    }


def probe_project(path: Path) -> dict[str, Any]:
    project = parse_band(path)
    data = project.project_data
    stream = data.get("logic_song_chunk_stream")
    events = data.get("event_sequences")
    placements = data.get("midi_region_placement_candidates")
    note_candidates = data.get("midi_note_event_candidates")
    if (
        not isinstance(stream, dict)
        or not isinstance(events, dict)
        or not isinstance(placements, list)
        or not isinstance(note_candidates, list)
    ):
        raise BandFormatError("project does not contain validated MIDI placement candidates")
    records = events.get("records")
    chunks = stream.get("chunks")
    if not isinstance(records, list) or not isinstance(chunks, list):
        raise BandFormatError("project has invalid event or chunk records")
    note_group_ids = {
        note["source_group_id_candidate"]
        for note in note_candidates
        if isinstance(note, dict) and isinstance(note.get("source_group_id_candidate"), int)
    }
    return inventory(records, chunks, placements, note_group_ids)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", nargs="+", type=Path, help="local .band project archives")
    args = parser.parse_args(argv)
    for index, path in enumerate(args.projects, 1):
        try:
            result = probe_project(path)
        except (BandFormatError, OSError, ValueError) as exc:
            parser.error(f"fixture_{index} could not be inspected: {type(exc).__name__}")
        print(f"fixture_{index}: {json.dumps(result, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

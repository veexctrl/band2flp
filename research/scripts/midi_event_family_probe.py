"""Profile opaque event families that share candidate MIDI-region groups."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from band2flp.parser import (
    BandFormatError,
    _parse_midi_region_placement_candidates,
    parse_band,
)


FAMILY_TYPES = tuple(range(0x91, 0x9F))


def profile_midi_event_families(
    records: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    placements: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize opaque event group overlap without returning group values."""
    mseq_by_group: dict[int, list[int]] = {}
    for chunk in chunks:
        if chunk.get("type") == "MSeq":
            group = chunk.get("group_id_candidate")
            index = chunk.get("index")
            if not isinstance(group, int) or not isinstance(index, int):
                raise BandFormatError("MSeq chunk has invalid group or index")
            mseq_by_group.setdefault(group, []).append(index)

    placements_by_group: dict[int, set[tuple[int, int]]] = {}
    for placement in placements:
        linked_indices = placement.get("candidate_mseq_chunk_indices")
        source_chunk = placement.get("source_chunk_index")
        source_event = placement.get("source_event_index")
        if not isinstance(linked_indices, list):
            raise BandFormatError("MIDI placement has invalid MSeq links")
        if not isinstance(source_chunk, int) or not isinstance(source_event, int):
            raise BandFormatError("MIDI placement has invalid source location")
        for index in linked_indices:
            if not isinstance(index, int):
                raise BandFormatError("MIDI placement has an invalid MSeq index")
            chunk = next((item for item in chunks if item.get("index") == index), None)
            if chunk is None or chunk.get("type") != "MSeq":
                raise BandFormatError("MIDI placement references a missing MSeq chunk")
            placements_by_group.setdefault(chunk["group_id_candidate"], set()).add(
                (source_chunk, source_event)
            )

    by_type: dict[int, list[dict[str, Any]]] = {event_type: [] for event_type in FAMILY_TYPES}
    for record in records:
        event_type = record.get("type_byte")
        if event_type not in by_type:
            continue
        if not isinstance(record.get("length"), int):
            raise BandFormatError("opaque MIDI-family event has invalid length")
        if not isinstance(record.get("group_id_candidate"), int):
            raise BandFormatError("opaque MIDI-family event has invalid group")
        by_type[event_type].append(record)

    families = {}
    for event_type, family_records in by_type.items():
        groups = {item["group_id_candidate"] for item in family_records}
        unique_links = sum(
            len(mseq_by_group.get(group, [])) == 1
            and len(placements_by_group.get(group, set())) == 1
            for group in groups
        )
        families[f"0x{event_type:02x}"] = {
            "record_count": len(family_records),
            "record_length_counts": {
                str(length): sum(item["length"] == length for item in family_records)
                for length in sorted({item["length"] for item in family_records})
            },
            "distinct_group_count": len(groups),
            "groups_with_one_MSeq_and_one_placement": unique_links,
        }

    return {
        "event_families": families,
        "semantics": "UNKNOWN; shared candidate groups do not establish event meaning",
        "privacy_note": "Counts only; group values, event bytes, paths, names, and media are omitted.",
    }


def probe_project(path: str | Path) -> dict[str, Any]:
    project = parse_band(path)
    data = project.project_data
    events = data.get("event_sequences")
    stream = data.get("logic_song_chunk_stream")
    if not isinstance(events, dict) or not isinstance(events.get("records"), list):
        raise BandFormatError("project has no validated event sequence records")
    if not isinstance(stream, dict) or not isinstance(stream.get("chunks"), list):
        raise BandFormatError("project has no validated logic-song chunk stream")
    placements = _parse_midi_region_placement_candidates(events, stream)
    return profile_midi_event_families(events["records"], stream["chunks"], placements)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="local GarageBand .band package")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(probe_project(args.project), indent=2))
    except (BandFormatError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

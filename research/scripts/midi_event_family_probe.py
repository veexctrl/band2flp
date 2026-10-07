"""Profile opaque event families and sizes in candidate MIDI-region groups."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
from typing import Any

from band2flp.parser import (
    BandFormatError,
    _parse_midi_region_placement_candidates,
    parse_band,
)


FAMILY_TYPES = tuple(range(0x91, 0x9F))
PPQ_CANDIDATE = 960


def profile_note_field_shapes(records: list[dict[str, Any]]) -> dict[str, int | str]:
    """Count MIDI-domain matches at unconfirmed Logic-derived byte offsets.

    The PPQ-divisibility count is descriptive only. A note duration expressed
    in ticks need not be an integer number of beats (and thus need not be a
    multiple of PPQ).
    """
    selected: list[bytes] = []
    for record in records:
        event_type = record.get("type_byte")
        if event_type not in FAMILY_TYPES:
            continue
        raw_hex = record.get("raw_hex")
        if not isinstance(raw_hex, str):
            raise BandFormatError("MIDI-family event has no raw bytes")
        try:
            raw = bytes.fromhex(raw_hex)
        except ValueError as exc:
            raise BandFormatError("MIDI-family event has invalid raw bytes") from exc
        if len(raw) != record.get("length") or not raw or raw[0] != event_type:
            raise BandFormatError("MIDI-family event bytes do not match their record metadata")
        if len(raw) >= 0x20 and raw[0x17] == 0x89:
            selected.append(raw)

    durations = [struct.unpack_from("<I", raw, 0x1C)[0] for raw in selected]
    return {
        "candidate_record_count": len(selected),
        "candidate_pitch_byte_in_midi_range_count": sum(raw[0x0C] <= 127 for raw in selected),
        "candidate_velocity_byte_in_nonzero_midi_range_count": sum(1 <= raw[0x0B] <= 127 for raw in selected),
        "candidate_duration_word_nonzero_count": sum(value != 0 for value in durations),
        "candidate_duration_word_on_960_tick_grid_count": sum(
            value != 0 and value % PPQ_CANDIDATE == 0 for value in durations
        ),
        "duration_ppq_divisibility_note": (
            "descriptive only; an integer tick duration need not be divisible by PPQ"
        ),
    }


def profile_midi_event_families(
    records: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    placements: list[dict[str, Any]],
    note_group_ids: set[int] | None = None,
) -> dict[str, Any]:
    """Summarize opaque event group overlap without returning group values."""
    mseq_by_group: dict[int, list[int]] = {}
    mseq_by_index: dict[int, dict[str, Any]] = {}
    for chunk in chunks:
        if chunk.get("type") == "MSeq":
            group = chunk.get("group_id_candidate")
            index = chunk.get("index")
            if not isinstance(group, int) or not isinstance(index, int):
                raise BandFormatError("MSeq chunk has invalid group or index")
            if not isinstance(chunk.get("payload_size"), int) or chunk["payload_size"] < 0:
                raise BandFormatError("MSeq chunk has invalid payload size")
            mseq_by_group.setdefault(group, []).append(index)
            mseq_by_index[index] = chunk

    placements_by_group: dict[int, set[tuple[int, int]]] = {}
    placement_sizes_by_group: dict[int, set[int]] = {}
    unique_link_count = 0
    ambiguous_link_count = 0
    for placement in placements:
        linked_indices = placement.get("candidate_mseq_chunk_indices")
        source_chunk = placement.get("source_chunk_index")
        source_event = placement.get("source_event_index")
        if not isinstance(linked_indices, list):
            raise BandFormatError("MIDI placement has invalid MSeq links")
        if not isinstance(source_chunk, int) or not isinstance(source_event, int):
            raise BandFormatError("MIDI placement has invalid source location")
        if len(linked_indices) != 1:
            ambiguous_link_count += 1
            continue
        for index in linked_indices:
            if not isinstance(index, int):
                raise BandFormatError("MIDI placement has an invalid MSeq index")
            chunk = mseq_by_index.get(index)
            if chunk is None:
                raise BandFormatError("MIDI placement references a missing MSeq chunk")
            group = chunk["group_id_candidate"]
            placements_by_group.setdefault(group, set()).add((source_chunk, source_event))
            placement_sizes_by_group.setdefault(group, set()).add(chunk["payload_size"])
            unique_link_count += 1

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

    note_group_ids = note_group_ids or set()
    opaque_group_ids = {
        group for family_records in by_type.values()
        for group in (record["group_id_candidate"] for record in family_records)
    }
    size_profiles: dict[str, dict[str, Any]] = {}
    for group, placement_ids in placements_by_group.items():
        sizes = placement_sizes_by_group[group]
        if len(mseq_by_group[group]) != 1 or len(sizes) != 1:
            continue
        has_note = group in note_group_ids
        has_opaque_family = group in opaque_group_ids
        category = (
            "both" if has_note and has_opaque_family else
            "note_only" if has_note else
            "opaque_family_only" if has_opaque_family else
            "neither"
        )
        profile = size_profiles.setdefault(category, {"group_count": 0, "payload_size_counts": {}})
        profile["group_count"] += 1
        size = next(iter(sizes))
        counts = profile["payload_size_counts"]
        counts[str(size)] = counts.get(str(size), 0) + 1

    return {
        "event_families": families,
        "note_field_shape_candidates": profile_note_field_shapes(records),
        "placed_mseq_clusters": {
            "placement_count_with_unique_mseq_link": unique_link_count,
            "placement_count_with_ambiguous_or_missing_mseq_link": ambiguous_link_count,
            "payload_size_counts_by_event_presence": size_profiles,
        },
        "semantics": (
            "UNKNOWN; MIDI-domain byte ranges and group links are candidate evidence only; "
            "Logic-derived offsets and duration units are not confirmed"
        ),
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
    note_candidates = data.get("midi_note_event_candidates", [])
    if not isinstance(note_candidates, list):
        raise BandFormatError("project has invalid MIDI note candidates")
    note_groups = {
        candidate["source_group_id_candidate"]
        for candidate in note_candidates
        if isinstance(candidate, dict)
        and isinstance(candidate.get("source_group_id_candidate"), int)
    }
    return profile_midi_event_families(
        events["records"], stream["chunks"], placements, note_groups
    )


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

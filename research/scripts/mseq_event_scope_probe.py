"""Summarize event-0x32 distribution across all MSeq groups.

This aggregate-only research probe distinguishes uniquely placed MSeq groups
from ambiguous and unplaced candidates. It does not assign event semantics or
emit group identifiers, names, payloads, or media references.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any

from band2flp.parser import BandFormatError, parse_band


def inventory_scope(
    records: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    placements: list[dict[str, Any]],
    note_group_ids: set[int] | None = None,
    note_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Aggregate type-0x32 records by MSeq placement-link confidence."""
    mseq_by_index: dict[int, dict[str, Any]] = {}
    mseq_count_by_group: Counter[int] = Counter()
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
        mseq_count_by_group[group] += 1

    unique_groups: set[int] = set()
    ambiguous_groups: set[int] = set()
    unique_placement_counts: Counter[int] = Counter()
    missing_or_ambiguous_placements = 0
    for placement in placements:
        links = placement.get("candidate_mseq_chunk_indices")
        if not isinstance(links, list):
            raise BandFormatError("MIDI placement has invalid MSeq links")
        linked_groups: set[int] = set()
        for index in links:
            if not isinstance(index, int) or index not in mseq_by_index:
                raise BandFormatError("MIDI placement references a missing MSeq chunk")
            linked_groups.add(mseq_by_index[index]["group_id_candidate"])
        if len(links) == 1:
            unique_groups.update(linked_groups)
            unique_placement_counts.update(linked_groups)
        else:
            missing_or_ambiguous_placements += 1
            ambiguous_groups.update(linked_groups)
    ambiguous_groups.update(
        group for group, count in unique_placement_counts.items() if count > 1
    )

    mseq_groups = set(mseq_count_by_group)
    groups_by_type_32: Counter[int] = Counter()
    type_32_lengths_by_group: dict[int, Counter[int]] = defaultdict(Counter)
    type_32_payloads_by_length: dict[int, list[tuple[dict[str, Any], bytes]]] = defaultdict(list)
    type_32_event_records: list[tuple[dict[str, Any], bytes]] = []
    note_group_ids = note_group_ids or set()
    for record in records:
        group = record.get("group_id_candidate")
        if group not in mseq_groups or record.get("type_byte") != 0x32:
            continue
        length = record.get("length")
        if not isinstance(length, int) or length <= 0:
            raise BandFormatError("type-0x32 event has an invalid length")
        groups_by_type_32[group] += 1
        type_32_lengths_by_group[group][length] += 1
        raw_hex = record.get("raw_hex")
        if not isinstance(raw_hex, str):
            raise BandFormatError("type-0x32 event has invalid raw bytes")
        try:
            raw = bytes.fromhex(raw_hex)
        except ValueError as exc:
            raise BandFormatError("type-0x32 event has invalid raw bytes") from exc
        if len(raw) != length:
            raise BandFormatError("type-0x32 event length does not match raw bytes")
        type_32_payloads_by_length[length].append((record, raw))
        type_32_event_records.append((record, raw))

    payload_profiles: dict[str, dict[str, Any]] = {}
    for length, entries in sorted(type_32_payloads_by_length.items()):
        payload_counts = Counter(raw for _record, raw in entries)
        profile: dict[str, Any] = {
            "record_count": len(entries),
            "distinct_payload_count": len(payload_counts),
            "duplicate_record_count": len(entries) - len(payload_counts),
            "distinct_payload_multiplicity_counts": {
                str(multiplicity): count
                for multiplicity, count in sorted(Counter(payload_counts.values()).items())
            },
        }
        varying_positions = [
            index for index in range(length)
            if len({raw[index] for _record, raw in entries}) > 1
        ]
        profile["varying_byte_positions"] = varying_positions
        if len(entries) > 1:
            field_matches: list[str] = []
            for index in varying_positions:
                candidates = [
                    (f"group_id_candidate:u32le_byte{lane}",
                     lambda record, lane=lane: (record["group_id_candidate"] >> (8 * lane)) & 0xFF)
                    for lane in range(4)
                ]
                candidates.extend([
                    ("chunk_index:u8", lambda record: record["chunk_index"] & 0xFF),
                    ("event_index:u8", lambda record: record["event_index"] & 0xFF),
                ])
                for label, get_candidate in candidates:
                    if all(raw[index] == get_candidate(record) for record, raw in entries):
                        field_matches.append(f"byte_{index}:{label}")
            profile["varying_byte_candidate_field_matches"] = field_matches
        payload_profiles[str(length)] = profile

    notes_by_group: dict[int, list[dict[str, int]]] = defaultdict(list)
    for note in note_candidates or []:
        if not isinstance(note, dict):
            continue
        group = note.get("source_group_id_candidate")
        position = note.get("position_raw")
        fraction = note.get("position_fraction_raw")
        if all(type(value) is int for value in (group, position, fraction)):
            notes_by_group[group].append({"position_raw": position, "fraction_raw": fraction})

    timestamp_candidate_counts: Counter[str] = Counter()
    timestamp_candidate_note_types: Counter[int] = Counter()
    event_position_counts: dict[int, Counter[str]] = defaultdict(Counter)
    all_notes = [note for group_notes in notes_by_group.values() for note in group_notes]
    for record, raw in type_32_event_records:
        if len(raw) < 8:
            continue
        timestamp_candidate_counts["eligible_record_count"] += 1
        position = int.from_bytes(raw[4:8], "little")
        fraction = int.from_bytes(raw[2:4], "little")
        group_notes = notes_by_group.get(record["group_id_candidate"], [])
        timestamp_candidate_counts["same_group_note_candidate_record_count"] += bool(group_notes)
        group_position_matches = [
            note for note in group_notes if note["position_raw"] == position
        ]
        group_exact_matches = [
            note for note in group_position_matches if note["fraction_raw"] == fraction
        ]
        any_group_position_matches = any(note["position_raw"] == position for note in all_notes)
        any_group_exact_matches = any(
            note["position_raw"] == position and note["fraction_raw"] == fraction
            for note in all_notes
        )
        timestamp_candidate_counts["same_group_position_word_match_record_count"] += bool(group_position_matches)
        timestamp_candidate_counts["same_group_exact_fractional_position_match_record_count"] += bool(group_exact_matches)
        timestamp_candidate_counts["any_group_position_word_match_record_count"] += any_group_position_matches
        timestamp_candidate_counts["any_group_exact_fractional_position_match_record_count"] += any_group_exact_matches
        if group_exact_matches:
            timestamp_candidate_note_types.update(
                note.get("event_type_byte") for note in (note_candidates or [])
                if isinstance(note, dict)
                and note.get("source_group_id_candidate") == record["group_id_candidate"]
                and note.get("position_raw") == position
                and note.get("position_fraction_raw") == fraction
                and isinstance(note.get("event_type_byte"), int)
            )

    for record in records:
        event_type = record.get("type_byte")
        group = record.get("group_id_candidate")
        if not isinstance(event_type, int) or 0x90 <= event_type <= 0x9F:
            continue
        if not notes_by_group.get(group):
            continue
        length = record.get("length")
        if not isinstance(length, int) or length < 8:
            continue
        raw_hex = record.get("raw_hex")
        if not isinstance(raw_hex, str):
            raise BandFormatError("event in a note-candidate group has invalid raw bytes")
        try:
            raw = bytes.fromhex(raw_hex)
        except ValueError as exc:
            raise BandFormatError("event in a note-candidate group has invalid raw bytes") from exc
        if len(raw) != length:
            raise BandFormatError("event length does not match raw bytes")
        position = int.from_bytes(raw[4:8], "little")
        fraction = int.from_bytes(raw[2:4], "little")
        group_notes = notes_by_group[group]
        counts = event_position_counts[event_type]
        counts["eligible_record_count"] += 1
        counts["same_group_position_word_match_record_count"] += any(
            note["position_raw"] == position for note in group_notes
        )
        counts["same_group_exact_fractional_position_match_record_count"] += any(
            note["position_raw"] == position and note["fraction_raw"] == fraction
            for note in group_notes
        )

    categories: dict[str, dict[str, Any]] = {}
    for category in ("unique_placement", "ambiguous_placement", "no_placement_candidate"):
        if category == "unique_placement":
            selected = (mseq_groups & unique_groups) - ambiguous_groups
        elif category == "ambiguous_placement":
            selected = mseq_groups & ambiguous_groups
        else:
            selected = mseq_groups - unique_groups - ambiguous_groups
        matching_groups = selected & groups_by_type_32.keys()
        length_counts: Counter[int] = Counter()
        for group in matching_groups:
            length_counts.update(type_32_lengths_by_group[group])
        multiplicity_counts = Counter(mseq_count_by_group[group] for group in matching_groups)
        categories[category] = {
            "mseq_group_count": len(selected),
            "groups_with_note_candidates": len(selected & note_group_ids),
            "groups_with_type_32": len(matching_groups),
            "type_32_record_count": sum(groups_by_type_32[group] for group in matching_groups),
            "type_32_record_length_counts": {
                str(length): length_counts[length] for length in sorted(length_counts)
            },
            "mseq_chunk_multiplicity_counts_for_type_32_groups": {
                str(count): multiplicity_counts[count] for count in sorted(multiplicity_counts)
            },
        }

    return {
        "mseq_group_count": len(mseq_groups),
        "placement_count_with_missing_or_ambiguous_mseq_link": missing_or_ambiguous_placements,
        "scope_categories": categories,
        "type_32_payload_profiles": payload_profiles,
        "type_32_timestamp_candidate_counts": dict(sorted(timestamp_candidate_counts.items())),
        "type_32_matching_note_event_type_counts": {
            f"0x{event_type:02x}": count
            for event_type, count in sorted(timestamp_candidate_note_types.items())
        },
        "non_note_event_position_candidate_matches": {
            f"0x{event_type:02x}": dict(sorted(counts.items()))
            for event_type, counts in sorted(event_position_counts.items())
        },
        "type_32_timestamp_candidate_interpretation": (
            "HYPOTHESIS: payload +0x02/+0x04 words match candidate note positions in one fixture; "
            "timing semantics and generality are unconfirmed."
        ),
        "interpretation": (
            "UNKNOWN; type-0x32 co-occurrence with MSeq or placement groups does not establish "
            "note, region, or event semantics."
        ),
        "privacy_note": "Only aggregate counts and record lengths are emitted; identifiers and payloads are omitted.",
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
    return inventory_scope(records, chunks, placements, note_group_ids, note_candidates)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", nargs="+", type=Path, help="local .band project archives")
    args = parser.parse_args(argv)
    for fixture_index, path in enumerate(args.projects, 1):
        try:
            result = probe_project(path)
        except (BandFormatError, OSError, ValueError) as exc:
            parser.error(f"fixture {fixture_index}: {exc}")
        print(json.dumps({"fixture_index": fixture_index, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

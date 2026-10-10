"""Compare opaque F1 event group counts with MSeq and empty Trak chunks."""

from __future__ import annotations

import argparse
import base64
from collections import Counter
import json
from pathlib import Path
from typing import Any

from band2flp.parser import BandFormatError, parse_band


def _group_counts(chunks: list[dict[str, Any]], kind: str) -> Counter[int]:
    counts: Counter[int] = Counter()
    for chunk in chunks:
        if chunk.get("type") != kind:
            continue
        group = chunk.get("group_id_candidate")
        if not isinstance(group, int):
            raise BandFormatError(f"{kind} chunk has invalid group candidate")
        counts[group] += 1
    return counts


def profile_f1_groups(
    records: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    payload: bytes | None = None,
) -> tuple[dict[str, Any], frozenset[bytes]]:
    """Return aggregate F1/group relationships and an internal raw-byte set.

    Group values and event bytes are used for comparisons but never included in
    the returned JSON-ready profile.
    """
    f1_records = [item for item in records if item.get("type_byte") == 0xF1]
    f1_groups: Counter[int] = Counter()
    f1_group_order: list[int] = []
    note_candidate_groups: set[int] = set()
    raw_records: set[bytes] = set()
    lengths: Counter[int] = Counter()
    zero_group_count = 0
    f1_offsets: set[int] = set()
    for record in f1_records:
        group = record.get("group_id_candidate")
        length = record.get("length")
        raw_hex = record.get("raw_hex")
        if not isinstance(group, int) or not isinstance(length, int) or length < 0:
            raise BandFormatError("F1 event has invalid group or length")
        if not isinstance(raw_hex, str):
            raise BandFormatError("F1 event has no validated raw record")
        try:
            raw = bytes.fromhex(raw_hex)
        except ValueError as exc:
            raise BandFormatError("F1 event has malformed raw record hex") from exc
        if len(raw) != length:
            raise BandFormatError("F1 event length differs from its raw record")
        f1_groups[group] += 1
        f1_group_order.append(group)
        raw_records.add(raw)
        lengths[length] += 1
        zero_group_count += group == 0
        offset = record.get("offset")
        if offset is not None:
            if not isinstance(offset, int) or offset < 0:
                raise BandFormatError("F1 event has invalid payload offset")
            f1_offsets.add(offset)

    # Mirror the parser's current note-candidate shape filter. This is only a
    # structural overlap check; it does not identify GarageBand MIDI semantics.
    for record in records:
        if not isinstance(record, dict):
            continue
        raw_hex = record.get("raw_hex")
        group = record.get("group_id_candidate")
        if not isinstance(raw_hex, str) or not isinstance(group, int):
            continue
        try:
            raw = bytes.fromhex(raw_hex)
        except ValueError:
            continue
        if len(raw) >= 32 and 0x90 <= raw[0] <= 0x9F and raw[0x17] == 0x89:
            note_candidate_groups.add(group)
    f1_note_group_overlap = f1_groups.keys() & note_candidate_groups

    payload_scan: dict[str, Any] | None = None
    if payload is not None:
        if len(f1_offsets) != len(f1_records):
            raise BandFormatError("F1 event payload offsets are missing or duplicated")
        for item in f1_records:
            offset = item.get("offset")
            if not isinstance(offset, int) or offset < 0:
                raise BandFormatError("F1 event has no valid payload offset")
            record = bytes.fromhex(item["raw_hex"])
            if offset + len(record) > len(payload):
                raise BandFormatError("F1 event offset lies outside the logic-song payload")
            if payload[offset:offset + len(record)] != record:
                raise BandFormatError("F1 event bytes disagree with the logic-song payload")
        occurrences: set[int] = set()
        for record in raw_records:
            if not record:
                continue
            offset = payload.find(record)
            while offset >= 0:
                occurrences.add(offset)
                offset = payload.find(record, offset + 1)
        matched_starts = occurrences & f1_offsets
        payload_scan = {
            "raw_record_occurrence_count": len(occurrences),
            "occurrences_at_f1_event_starts": len(matched_starts),
            "all_occurrences_at_f1_event_starts": occurrences == f1_offsets,
        }

    mseq_groups = _group_counts(chunks, "MSeq")
    mseq_group_order = [
        chunk["group_id_candidate"] for chunk in chunks if chunk.get("type") == "MSeq"
    ]
    empty_trak_groups = Counter(
        chunk.get("group_id_candidate")
        for chunk in chunks
        if chunk.get("type") == "Trak" and chunk.get("payload_size") == 0
    )
    if any(not isinstance(group, int) for group in empty_trak_groups):
        raise BandFormatError("empty Trak chunk has invalid group candidate")
    empty_trak_group_order = [
        chunk["group_id_candidate"] for chunk in chunks
        if chunk.get("type") == "Trak" and chunk.get("payload_size") == 0
    ]
    comparisons = {
        "MSeq": mseq_groups,
        "empty_Trak": empty_trak_groups,
    }
    profile = {
        "f1_record_count": len(f1_records),
        "f1_record_length_counts": {
            str(size): count for size, count in sorted(lengths.items())
        },
        "distinct_f1_raw_record_count": len(raw_records),
        "distinct_f1_group_count": len(f1_groups),
        "f1_groups_with_note_candidate_events": len(f1_note_group_overlap),
        "f1_groups_without_note_candidate_events": len(f1_groups.keys() - note_candidate_groups),
        "group_zero_record_count": zero_group_count,
        "group_order_comparisons": {
            "MSeq": {
                "related_chunk_count": len(mseq_group_order),
                "group_sequence_matches_in_order": f1_group_order == mseq_group_order,
                "f1_group_sequence_decrease_count": sum(
                    left > right for left, right in zip(f1_group_order, f1_group_order[1:])
                ),
                "related_group_sequence_decrease_count": sum(
                    left > right for left, right in zip(mseq_group_order, mseq_group_order[1:])
                ),
            },
            "empty_Trak": {
                "related_chunk_count": len(empty_trak_group_order),
                "group_sequence_matches_in_order": f1_group_order == empty_trak_group_order,
                "f1_group_sequence_decrease_count": sum(
                    left > right for left, right in zip(f1_group_order, f1_group_order[1:])
                ),
                "related_group_sequence_decrease_count": sum(
                    left > right for left, right in zip(empty_trak_group_order, empty_trak_group_order[1:])
                ),
            },
        },
        **({"payload_occurrence_scan": payload_scan} if payload_scan is not None else {}),
        "group_multiplicity_comparisons": {
            name: {
                "related_chunk_count": sum(counts.values()),
                "distinct_related_group_count": len(counts),
                "multiplicities_match": f1_groups == counts,
                "groups_in_both_families": len(f1_groups.keys() & counts.keys()),
                "groups_only_in_f1": len(f1_groups.keys() - counts.keys()),
                "groups_only_in_related_family": len(counts.keys() - f1_groups.keys()),
            }
            for name, counts in comparisons.items()
        },
        "interpretation": (
            "UNKNOWN; repeated group co-occurrence does not assign F1 event semantics"
        ),
        "privacy_note": "Counts only; group values, event bytes, paths, and names are omitted.",
    }
    return profile, frozenset(raw_records)


def probe_project(path: str | Path) -> tuple[dict[str, Any], frozenset[bytes]]:
    project = parse_band(path)
    events = project.project_data.get("event_sequences")
    stream = project.project_data.get("logic_song_chunk_stream")
    if not isinstance(events, dict) or not isinstance(events.get("records"), list):
        raise BandFormatError("project has no validated event sequence records")
    if not isinstance(stream, dict) or not isinstance(stream.get("chunks"), list):
        raise BandFormatError("project has no validated logic-song chunk stream")
    object_index = project.project_data.get("logic_song_object_index")
    for blob in project.project_data.get("opaque_data_objects", []):
        if blob.get("object_index") != object_index or not isinstance(blob.get("base64"), str):
            continue
        payload = base64.b64decode(blob["base64"], validate=True)
        if len(payload) != blob.get("length") or len(payload) != stream.get("end_offset"):
            raise BandFormatError("retained logic-song payload is inconsistent")
        return profile_f1_groups(events["records"], stream["chunks"], payload)
    raise BandFormatError("logic-song NSData payload was not retained")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", nargs="+", type=Path, help="local GarageBand .band archives")
    args = parser.parse_args(argv)
    reports = []
    payload_sets = []
    try:
        for index, path in enumerate(args.projects, start=1):
            report, payloads = probe_project(path)
            reports.append({"fixture": index, **report})
            payload_sets.append(payloads)
    except (BandFormatError, ValueError) as exc:
        parser.error(f"fixture_{index} could not be inspected: {type(exc).__name__}")
    print(json.dumps({
        "fixtures": reports,
        "all_fixtures_share_same_f1_raw_record_set": (
            bool(payload_sets) and all(payloads == payload_sets[0] for payloads in payload_sets[1:])
        ),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


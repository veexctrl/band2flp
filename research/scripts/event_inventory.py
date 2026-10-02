"""Summarize event type/record shapes without exposing event bytes or labels."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any

from band2flp.parser import BandFormatError, parse_band


def inventory_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Return aggregate counts only; omit raw values, strings, and group IDs."""
    by_type: dict[int, Counter[int]] = defaultdict(Counter)
    groups: dict[int, set[int]] = defaultdict(set)
    zero_group_counts: Counter[int] = Counter()
    for record in records:
        event_type = record.get("type_byte")
        length = record.get("length")
        group = record.get("group_id_candidate")
        if not isinstance(event_type, int) or not 0 <= event_type <= 0xFF:
            raise BandFormatError("event inventory contains an invalid type byte")
        if not isinstance(length, int) or length < 16 or length % 16:
            raise BandFormatError("event inventory contains an invalid atom-aligned record length")
        if not isinstance(group, int) or group < 0:
            raise BandFormatError("event inventory contains an invalid group candidate")
        by_type[event_type][length] += 1
        groups[event_type].add(group)
        if group == 0:
            zero_group_counts[event_type] += 1

    result = {}
    for event_type in sorted(by_type):
        result[f"0x{event_type:02x}"] = {
            "record_count": sum(by_type[event_type].values()),
            "record_lengths": {
                str(length): count for length, count in sorted(by_type[event_type].items())
            },
            "distinct_group_candidate_count": len(groups[event_type]),
            "zero_group_record_count": zero_group_counts[event_type],
            "semantics": "UNKNOWN unless independently documented",
        }
    return {
        "event_record_count": len(records),
        "event_types": result,
        "privacy_note": "Aggregate counts only; event bytes, names, and group values are omitted.",
    }


def profile_tempo_group_associations(
    tempo_candidates: list[dict[str, Any]],
    records: list[dict[str, Any]],
    audio_placements: list[dict[str, Any]],
    midi_placements: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    summary_tempo: float | None,
) -> dict[str, dict[str, int]]:
    """Aggregate event/container associations for global and nonzero tempo groups."""
    result: dict[str, dict[str, int]] = {}
    for scope in ("group_zero", "nonzero_group"):
        selected = [
            item for item in tempo_candidates
            if (item.get("source_group_id_candidate") == 0) == (scope == "group_zero")
        ]
        metrics = Counter()
        for item in selected:
            group = item["source_group_id_candidate"]
            group_records = [record for record in records if record.get("group_id_candidate") == group]
            event20 = [record for record in group_records if record.get("type_byte") == 0x20]
            event24 = [record for record in group_records if record.get("type_byte") == 0x24]
            event20_ids = {(record.get("chunk_index"), record.get("event_index")) for record in event20}
            event24_ids = {(record.get("chunk_index"), record.get("event_index")) for record in event24}
            midi = [
                placement for placement in midi_placements
                if (placement.get("source_chunk_index"), placement.get("source_event_index")) in event20_ids
            ]
            audio = [
                placement for placement in audio_placements
                if (placement.get("source_chunk_index"), placement.get("source_event_index")) in event24_ids
            ]
            same_group_chunks = [chunk for chunk in chunks if chunk.get("group_id_candidate") == group]
            metrics["tempo_candidate_count"] += 1
            metrics["tempo_candidates_matching_summary_count"] += int(
                isinstance(summary_tempo, (int, float))
                and abs(item.get("bpm", float("inf")) - summary_tempo) <= 0.0001
            )
            metrics["source_event_record_count"] += len(group_records)
            metrics["source_type20_record_count"] += len(event20)
            metrics["source_type24_record_count"] += len(event24)
            metrics["linked_midi_placement_count"] += len(midi)
            metrics["linked_audio_placement_count"] += len(audio)
            metrics["tempo_position_matches_audio_start_count"] += sum(
                placement.get("position_raw") == item.get("position_raw") for placement in audio
            )
            metrics["tempo_position_matches_midi_start_count"] += sum(
                placement.get("position_raw") == item.get("position_raw") for placement in midi
            )
            metrics["same_group_mseq_chunk_count"] += sum(chunk.get("type") == "MSeq" for chunk in same_group_chunks)
            metrics["same_group_empty_trak_chunk_count"] += sum(
                chunk.get("type") == "Trak" and chunk.get("payload_size") == 0
                for chunk in same_group_chunks
            )
        result[scope] = dict(sorted(metrics.items()))
    return result


def probe_project(path: str | Path) -> dict[str, Any]:
    project = parse_band(path)
    events = project.project_data.get("event_sequences")
    if not isinstance(events, dict) or not isinstance(events.get("records"), list):
        raise BandFormatError("project has no validated event sequence records")
    report = inventory_records(events["records"])
    report["tempo_group_associations"] = profile_tempo_group_associations(
        events.get("tempo_candidates", []),
        events["records"],
        project.project_data.get("audio_placements", []),
        project.project_data.get("midi_region_placement_candidates", []),
        project.project_data.get("logic_song_chunk_stream", {}).get("chunks", []),
        project.tempo_bpm,
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="event_inventory")
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

"""Compare Trak payload groups with event and audio-chunk groups anonymously."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

from band2flp.parser import BandFormatError, parse_band


def summarize_trak_groups(chunks: list[dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Report per-group family counts, replacing opaque IDs with local buckets."""
    trak_groups = Counter(
        chunk["group_id_candidate"]
        for chunk in chunks
        if chunk.get("type") == "Trak" and chunk.get("payload_size") == 58
    )
    event_groups = {
        event_type: Counter(
            event["group_id_candidate"]
            for event in events
            if event.get("type_byte") == event_type
        )
        for event_type in (0x20, 0x24)
    }
    chunk_groups = {
        tag: Counter(
            chunk["group_id_candidate"]
            for chunk in chunks
            if chunk.get("type") == tag
        )
        for tag in ("AuCO", "AuFl", "AuRg", "MSeq")
    }
    profiles = []
    for bucket, group in enumerate(sorted(trak_groups), start=1):
        profile = {
            "group_bucket": bucket,
            "trak58_count": trak_groups[group],
            "midi_type20_event_count": event_groups[0x20][group],
            "audio_type24_event_count": event_groups[0x24][group],
        }
        profile.update({f"{tag}_chunk_count": counts[group] for tag, counts in chunk_groups.items()})
        profiles.append(profile)
    return {
        "trak58_group_count": len(trak_groups),
        "profiles": profiles,
        "privacy_note": "Opaque group values, payload bytes, identifiers, names, and media are omitted.",
    }


def profile_midi_track_value_ordinals(
    chunks: list[dict[str, Any]], placements: list[dict[str, Any]]
) -> dict[str, int]:
    """Test whether MIDI placement track-byte candidates equal serialized ordinals."""
    mseq_chunks = [chunk for chunk in chunks if chunk.get("type") == "MSeq"]
    empty_trak_chunks = [
        chunk for chunk in chunks
        if chunk.get("type") == "Trak" and chunk.get("payload_size") == 0
    ]
    mseq_order = {chunk["index"]: index for index, chunk in enumerate(mseq_chunks)}
    empty_trak_order = {chunk["index"]: index for index, chunk in enumerate(empty_trak_chunks)}
    first_group_order: dict[int, int] = {}
    for chunk in mseq_chunks:
        first_group_order.setdefault(chunk["group_id_candidate"], len(first_group_order))

    def unique_empty_trak_ordinal(placement: dict[str, Any]) -> int | None:
        ordinals = [
            empty_trak_order[index]
            for index in placement.get("same_group_trak_chunk_indices_candidate", [])
            if index in empty_trak_order
        ]
        return ordinals[0] if len(ordinals) == 1 else None

    schemes = {
        "mseq_chunk": lambda placement: (
            mseq_order.get(placement["candidate_mseq_chunk_indices"][0])
            if len(placement.get("candidate_mseq_chunk_indices", [])) == 1 else None
        ),
        "empty_trak_chunk": unique_empty_trak_ordinal,
        "unique_mseq_group": lambda placement: (
            first_group_order.get(
                mseq_chunks[mseq_order[placement["candidate_mseq_chunk_indices"][0]]]["group_id_candidate"]
            )
            if len(placement.get("candidate_mseq_chunk_indices", [])) == 1
            and placement["candidate_mseq_chunk_indices"][0] in mseq_order
            else None
        ),
    }
    result: dict[str, int] = {"placement_count": len(placements)}
    for scheme, ordinal_for in schemes.items():
        eligible = zero_based = one_based = 0
        for placement in placements:
            value = placement.get("track_value_candidate")
            ordinal = ordinal_for(placement)
            if not isinstance(value, int) or not isinstance(ordinal, int):
                continue
            eligible += 1
            zero_based += value == ordinal
            one_based += value == ordinal + 1
        result[f"{scheme}_eligible_count"] = eligible
        result[f"{scheme}_zero_based_exact_match_count"] = zero_based
        result[f"{scheme}_one_based_exact_match_count"] = one_based
    return result


def probe(path: str | Path) -> dict[str, Any]:
    project = parse_band(path)
    chunks = project.project_data.get("logic_song_chunk_stream", {}).get("chunks")
    events = project.project_data.get("event_sequences", {}).get("records")
    if not isinstance(chunks, list) or not isinstance(events, list):
        raise BandFormatError("project has no validated chunk and event inventories")
    report = summarize_trak_groups(chunks, events)
    placements = project.project_data.get("midi_region_placement_candidates", [])
    report["midi_track_value_ordinal_candidates"] = profile_midi_track_value_ordinals(
        chunks, placements if isinstance(placements, list) else []
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", nargs="+", type=Path, help="local .band project archives")
    args = parser.parse_args(argv)
    for index, path in enumerate(args.projects, start=1):
        try:
            report = probe(path)
        except Exception as exc:
            parser.error(f"fixture_{index} could not be inspected: {type(exc).__name__}")
        print(f"fixture_{index}: {json.dumps(report, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

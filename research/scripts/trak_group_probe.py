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


def probe(path: str | Path) -> dict[str, Any]:
    project = parse_band(path)
    chunks = project.project_data.get("logic_song_chunk_stream", {}).get("chunks")
    events = project.project_data.get("event_sequences", {}).get("records")
    if not isinstance(chunks, list) or not isinstance(events, list):
        raise BandFormatError("project has no validated chunk and event inventories")
    return summarize_trak_groups(chunks, events)


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

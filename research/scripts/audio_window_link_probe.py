"""Scan source-matched audio regions for candidate placement field equalities.

Only aggregate offset/count results are printed. No project paths, source names,
field values, raw bytes, or audio are emitted.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any

from band2flp.parser import BandFormatError, parse_band


def scan_window_links(
    groups: list[tuple[list[bytes], list[bytes]]],
    *,
    widths: tuple[int, ...] = (4, 8),
    step: int = 2,
) -> dict[str, list[dict[str, int]]]:
    """Count one-to-one nonzero, varying equalities within each source group."""
    if step <= 0 or any(width <= 0 for width in widths):
        raise ValueError("window widths and step must be positive")
    result: dict[str, list[dict[str, int]]] = {}
    for width in widths:
        totals: Counter[tuple[int, int]] = Counter()
        matching_groups: Counter[tuple[int, int]] = Counter()
        for regions, placements in groups:
            if len(regions) < 2 or len(placements) < 2:
                continue
            for region_offset in range(0, min(map(len, regions)) - width + 1, step):
                region_values = [record[region_offset:region_offset + width] for record in regions]
                for placement_offset in range(0, min(map(len, placements)) - width + 1, step):
                    matches = [
                        (ri, pi, value)
                        for ri, value in enumerate(region_values)
                        if any(value)
                        for pi, record in enumerate(placements)
                        if value == record[placement_offset:placement_offset + width]
                    ]
                    region_counts = Counter(ri for ri, _, _ in matches)
                    placement_counts = Counter(pi for _, pi, _ in matches)
                    unique = [
                        (ri, pi, value) for ri, pi, value in matches
                        if region_counts[ri] == 1 and placement_counts[pi] == 1
                    ]
                    if len({value for _, _, value in unique}) < 2:
                        continue
                    key = (region_offset, placement_offset)
                    totals[key] += len(unique)
                    matching_groups[key] += 1
        result[str(width)] = [
            {
                "region_payload_offset": region_offset,
                "placement_event_offset": placement_offset,
                "one_to_one_matches": count,
                "source_groups": matching_groups[(region_offset, placement_offset)],
            }
            for (region_offset, placement_offset), count in sorted(
                totals.items(), key=lambda item: (-item[1], item[0])
            )
        ]
    return result


def probe_project(
    path: str | Path,
    *,
    widths: tuple[int, ...] = (4, 8),
    step: int = 2,
) -> dict[str, Any]:
    project = parse_band(path)
    song_index = project.project_data.get("logic_song_object_index")
    blob = next(
        (item for item in project.project_data.get("opaque_data_objects", [])
         if item.get("object_index") == song_index),
        None,
    )
    if not isinstance(blob, dict) or not isinstance(blob.get("base64"), str):
        raise BandFormatError("retained logic-song payload was not found")
    payload = base64.b64decode(blob["base64"], validate=True)
    if len(payload) != blob.get("length"):
        raise BandFormatError("retained logic-song payload length is inconsistent")
    chunks = project.project_data["logic_song_chunk_stream"]["chunks"]
    records = {
        (item["chunk_index"], item["event_index"]): bytes.fromhex(item["raw_hex"])
        for item in project.project_data["event_sequences"]["records"]
    }
    placements: dict[int, list[bytes]] = defaultdict(list)
    for item in project.project_data.get("audio_placements", []):
        identity = (item["source_chunk_index"], item["source_event_index"])
        if identity in records:
            placements[item["media_group_id_candidate"]].append(records[identity][:80])
    groups: list[tuple[list[bytes], list[bytes]]] = []
    for reference in project.media_references:
        if reference.category != "AudioFiles":
            continue
        regions = []
        for index in reference.name_matched_region_chunk_indices:
            chunk = chunks[index]
            start, size = chunk["payload_offset"], chunk["payload_size"]
            if start < 0 or size < 0 or start + size > len(payload):
                raise BandFormatError("audio region chunk lies outside the logic-song payload")
            regions.append(payload[start:start + size])
        source_placements = placements[reference.group_id_candidate]
        if len(regions) > 1 and len(source_placements) > 1:
            groups.append((regions, source_placements))
    return {
        "multi_region_source_groups": len(groups),
        "window_links": scan_window_links(groups, widths=widths, step=step),
        "interpretation": "Candidate exact byte equalities only; absence of a match does not disprove a structural link.",
        "privacy_note": "Only offsets and aggregate counts are reported.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", nargs="+", type=Path)
    parser.add_argument("--widths", nargs="+", type=int, default=(4, 8))
    parser.add_argument("--step", type=int, default=2)
    args = parser.parse_args(argv)
    for index, path in enumerate(args.projects, 1):
        try:
            result = probe_project(path, widths=tuple(args.widths), step=args.step)
        except (BandFormatError, OSError, ValueError, KeyError, IndexError) as exc:
            parser.error(f"fixture_{index} could not be inspected: {type(exc).__name__}")
        print(f"fixture_{index}: {json.dumps(result, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

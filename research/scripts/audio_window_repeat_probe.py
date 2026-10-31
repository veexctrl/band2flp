"""Compare repeated linked source-window candidates without deriving duration.

Only aggregate counts leave this probe. It consumes parsed metadata; raw
source names, positions, word values and region payloads are not emitted.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from fractions import Fraction
import json

from band2flp.model import Project
from band2flp.parser import parse_band


def profile_project(project: Project) -> dict[str, int]:
    buckets = defaultdict(list)
    skipped = 0
    for track in project.tracks:
        for region in track.regions:
            if region.kind != "audio":
                continue
            links = region.unknown.get("region_chunk_indices_matching_0x8a_to_0x28_candidate", [])
            if len(links) != 1 or region.source is None:
                skipped += 1
                continue
            metadata = [item for item in region.unknown.get(
                "candidate_region_chunk_metadata_for_source", []
            ) if item.get("chunk_index") == links[0] and item.get("filename_stem_matches")]
            if len(metadata) != 1:
                skipped += 1
                continue
            first = metadata[0].get("payload_u32_at_0x06_candidate")
            second = metadata[0].get("payload_u32_at_0x16_candidate")
            extent = region.unknown.get("placement", {}).get("u32_at_0x1c_candidate")
            if any(type(word) is not int or not 0 <= word <= 0xFFFFFFFF
                   for word in (first, second, extent)) or region.start_beats is None:
                skipped += 1
                continue
            try:
                start = Fraction(region.start_beats)
            except (ValueError, ZeroDivisionError):
                skipped += 1
                continue
            buckets[(region.source, first, second)].append((start, extent))
    repeated = [rows for rows in buckets.values() if len(rows) > 1]
    return {
        "linked_records": sum(map(len, buckets.values())),
        "skipped_audio_regions": skipped,
        "distinct_source_window_buckets": len(buckets),
        "repeated_buckets": len(repeated),
        "repeated_buckets_with_different_starts": sum(len({r[0] for r in rows}) > 1 for rows in repeated),
        "repeated_buckets_with_different_extent_words": sum(len({r[1] for r in rows}) > 1 for rows in repeated),
        "repeated_buckets_with_finite_and_sentinel_extents": sum(
            any(r[1] == 0x3FFFFFFF for r in rows)
            and any(r[1] not in (0, 0x3FFFFFFF) for r in rows)
            for rows in repeated
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", nargs="+")
    args = parser.parse_args()
    for index, path in enumerate(args.projects, 1):
        print(json.dumps({"fixture_index": index, **profile_project(parse_band(path))}))


if __name__ == "__main__":
    main()

"""Aggregate source-frame and extended-placement links without exposing media."""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
import zipfile
from typing import Any

from band2flp.parser import BandFormatError, parse_band
from research.scripts.audio_frame_probe import audio_frame_count


def profile_source_link_candidates(
    source_frames: int | None,
    region_frame_candidates: list[int],
    placement_suffix_candidates: list[int | None],
) -> dict[str, Any]:
    """Count candidate relations without treating them as decoded semantics."""
    relations: collections.Counter[str] = collections.Counter()
    for candidate in region_frame_candidates:
        if source_frames is None:
            relations["source_length_unknown"] += 1
        elif candidate < source_frames:
            relations["below_source"] += 1
        elif candidate == source_frames:
            relations["equal_source"] += 1
        else:
            relations["above_source"] += 1

    suffix_matches = 0
    suffix_match_candidate_count = 0
    ambiguous_suffix_matches = 0
    extended_placements = 0
    candidate_set = set(region_frame_candidates)
    for suffix in placement_suffix_candidates:
        if suffix is None:
            continue
        extended_placements += 1
        if suffix in candidate_set:
            suffix_matches += 1
            match_count = region_frame_candidates.count(suffix)
            suffix_match_candidate_count += match_count
            ambiguous_suffix_matches += match_count > 1

    return {
        "region_frame_candidate_relations": dict(sorted(relations.items())),
        "extended_placement_count": extended_placements,
        "placement_suffixes_matching_source_region_candidates": suffix_matches,
        "matching_region_candidates_for_those_suffixes": suffix_match_candidate_count,
        "suffix_matches_with_multiple_candidate_regions": ambiguous_suffix_matches,
        "interpretation": (
            "UNKNOWN; suffix equality links candidate values only. It does not establish a unique region, "
            "trim, loop, or timeline duration."
        ),
    }


def probe_project(path: str | Path) -> dict[str, Any]:
    project = parse_band(path)
    placements = project.project_data.get("audio_placements", [])
    placement_by_group: dict[int, list[dict[str, Any]]] = {}
    for placement in placements:
        group = placement.get("media_group_id_candidate")
        if isinstance(group, int):
            placement_by_group.setdefault(group, []).append(placement)

    aggregates: collections.Counter[str] = collections.Counter()
    source_count = 0
    decoded_source_count = 0
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise BandFormatError(f"not a readable .band ZIP package: {path}") from exc

    with archive:
        for reference in project.media_references:
            if reference.category != "AudioFiles" or reference.package_member is None:
                continue
            source_count += 1
            frames, _format = audio_frame_count(archive.read(reference.package_member))
            if frames is not None:
                decoded_source_count += 1
            regions = [
                item.get("payload_u32_at_0x16_candidate")
                for item in reference.region_chunk_metadata_candidates
                if item.get("filename_stem_matches")
                and isinstance(item.get("payload_u32_at_0x16_candidate"), int)
            ]
            linked_placements = placement_by_group.get(reference.group_id_candidate, [])
            suffixes = [
                item.get("trailing_u32_at_0_candidate")
                if isinstance(item.get("trailing_u32_at_0_candidate"), int) else None
                for item in linked_placements
            ]
            result = profile_source_link_candidates(frames, regions, suffixes)
            for key, value in result["region_frame_candidate_relations"].items():
                aggregates[f"region_candidates_{key}"] += value
            for key in (
                "extended_placement_count",
                "placement_suffixes_matching_source_region_candidates",
                "matching_region_candidates_for_those_suffixes",
                "suffix_matches_with_multiple_candidate_regions",
            ):
                aggregates[key] += result[key]

    return {
        "embedded_audio_sources": source_count,
        "sources_with_decoded_frame_counts": decoded_source_count,
        "audio_placement_count": len(placements),
        **dict(sorted(aggregates.items())),
        "interpretation": (
            "Aggregate only. A suffix match is a candidate association, not proof of a region mapping or duration."
        ),
        "privacy_note": "Project paths, source names, raw values, event bytes, and audio are omitted.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", nargs="+", type=Path, help="local .band project archives")
    args = parser.parse_args(argv)
    for index, path in enumerate(args.projects, start=1):
        try:
            result = probe_project(path)
        except (BandFormatError, OSError, ValueError, zipfile.BadZipFile) as exc:
            parser.error(f"fixture_{index} could not be inspected: {type(exc).__name__}")
        print(f"fixture_{index}: {json.dumps(result, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

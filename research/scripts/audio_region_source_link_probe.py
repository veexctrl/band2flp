"""Aggregate audio source, region, and placement candidates without exposing media."""

from __future__ import annotations

import argparse
import base64
import collections
from itertools import combinations
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


def profile_candidate_region_payloads(
    candidate_payloads: list[tuple[int, bytes]],
) -> dict[str, Any]:
    """Count whether equal frame candidates have identical full payloads.

    The report contains counts and relative payload offsets only. It does not
    return candidate field values, payload bytes, identifiers, or filenames.
    """
    buckets: dict[int, list[bytes]] = {}
    for frame_candidate, payload in candidate_payloads:
        if isinstance(frame_candidate, int) and isinstance(payload, bytes):
            buckets.setdefault(frame_candidate, []).append(payload)

    repeated_buckets = [values for values in buckets.values() if len(values) > 1]
    pairs = [pair for values in repeated_buckets for pair in combinations(values, 2)]
    identical_pairs = sum(left == right for left, right in pairs)
    unequal_size_pairs = sum(len(left) != len(right) for left, right in pairs)
    changed_offset_counts: collections.Counter[str] = collections.Counter()
    for left, right in pairs:
        if len(left) == len(right):
            changed_offset_counts.update(
                str(offset)
                for offset, (left_byte, right_byte) in enumerate(zip(left, right))
                if left_byte != right_byte
            )
    repeated_region_link_fields = [
        [payload[0x8A:0x92] for payload in values if len(payload) >= 0x92]
        for values in repeated_buckets
    ]
    repeated_region_link_fields = [fields for fields in repeated_region_link_fields if fields]
    varying_link_field_positions: collections.Counter[str] = collections.Counter()
    for fields in repeated_region_link_fields:
        for offset in range(8):
            if len({field[offset] for field in fields}) > 1:
                varying_link_field_positions[str(offset)] += 1
    link_field_nonzero_byte_counts = collections.Counter(
        str(sum(byte != 0 for byte in field))
        for fields in repeated_region_link_fields for field in fields
    )
    differing_bytes = [
        sum(a != b for a, b in zip(left, right)) + abs(len(left) - len(right))
        for left, right in pairs
    ]
    return {
        "repeated_frame_candidate_bucket_count": len(repeated_buckets),
        "repeated_frame_candidate_pair_count": len(pairs),
        "identical_payload_pair_count": identical_pairs,
        "distinct_payload_pair_count": len(pairs) - identical_pairs,
        "unequal_payload_size_pair_count": unequal_size_pairs,
        "pair_byte_difference_counts": dict(sorted(
            collections.Counter(str(count) for count in differing_bytes).items()
        )),
        "changed_payload_offset_pair_counts": dict(sorted(
            changed_offset_counts.items(), key=lambda item: int(item[0])
        )),
        "repeated_candidate_0x8a_field_count": sum(map(len, repeated_region_link_fields)),
        "repeated_candidate_0x8a_varying_byte_position_bucket_counts": dict(sorted(
            varying_link_field_positions.items(), key=lambda item: int(item[0])
        )),
        "repeated_candidate_0x8a_nonzero_byte_count_histogram": dict(sorted(
            link_field_nonzero_byte_counts.items(), key=lambda item: int(item[0])
        )),
        "interpretation": "UNKNOWN; equal frame candidates need not be identical region records.",
    }


def profile_source_frame_window_candidates(
    source_frames: int | None, region_payloads: list[bytes]
) -> dict[str, int]:
    """Compare AuRg +0x06 and +0x16 words with source frames, without naming them."""
    counts: collections.Counter[str] = collections.Counter()
    pairs: list[tuple[int, int]] = []
    for payload in region_payloads:
        if len(payload) < 0x1A:
            counts["too_short"] += 1
            continue
        first = int.from_bytes(payload[0x06:0x0A], "little")
        second = int.from_bytes(payload[0x16:0x1A], "little")
        pairs.append((first, second))
        counts["candidate_pair_count"] += 1
        counts["first_nonzero" if first else "first_zero"] += 1
        if source_frames is None:
            counts["source_length_unknown"] += 1
        elif first + second == source_frames:
            counts["sum_equals_source_frames"] += 1
        else:
            counts["sum_differs_from_source_frames"] += 1
    zero_baselines = {second for first, second in pairs if first == 0}
    if len(zero_baselines) == 1:
        baseline = next(iter(zero_baselines))
        for first, second in pairs:
            if first == 0:
                continue
            relation = (
                "equals" if first + second == baseline
                else "below" if first + second < baseline
                else "above"
            )
            counts[f"nonzero_sum_{relation}_zero_baseline"] += 1
    elif any(first for first, _ in pairs):
        counts["nonzero_without_unique_zero_baseline"] += sum(first != 0 for first, _ in pairs)
    return dict(sorted(counts.items()))


def profile_region_placement_field_links(
    region_payloads: list[bytes], placement_records: list[bytes]
) -> dict[str, Any]:
    """Compare unconfirmed AuRg +0x8a with 0x24 placement +0x28, per source."""
    region_fields = [
        payload[0x8A:0x92] if len(payload) >= 0x92 else None
        for payload in region_payloads
    ]
    placement_fields = [
        record[0x28:0x30] if len(record) >= 0x30 else None
        for record in placement_records
    ]
    links = [
        (region_index, placement_index)
        for region_index, region_field in enumerate(region_fields)
        if region_field is not None and region_field != bytes(8)
        for placement_index, placement_field in enumerate(placement_fields)
        if region_field == placement_field
    ]
    region_counts = collections.Counter(region_index for region_index, _ in links)
    placement_counts = collections.Counter(placement_index for _, placement_index in links)
    return {
        "region_field_count": sum(field is not None for field in region_fields),
        "zero_region_field_count": sum(field == bytes(8) for field in region_fields),
        "nonzero_region_field_count": sum(
            field is not None and field != bytes(8) for field in region_fields
        ),
        "same_source_field_match_count": len(links),
        "one_to_one_field_match_count": sum(
            region_counts[region_index] == 1 and placement_counts[placement_index] == 1
            for region_index, placement_index in links
        ),
        "interpretation": (
            "HYPOTHESIS; exact field equality is a candidate region-to-placement link, "
            "not a confirmed object identity or duration."
        ),
    }


def profile_region_candidate_overlap(
    fixed_field_candidates: list[list[int]],
    suffix_candidates: list[list[int]],
) -> dict[str, int]:
    """Compare candidate region identities without returning chunk indices."""
    if len(fixed_field_candidates) != len(suffix_candidates):
        raise ValueError("fixed-field and suffix candidate lists must cover the same placements")
    fixed_sets = [set(items) for items in fixed_field_candidates]
    suffix_sets = [set(items) for items in suffix_candidates]
    return {
        "placement_count": len(fixed_sets),
        "placements_with_fixed_field_candidates": sum(bool(items) for items in fixed_sets),
        "placements_with_suffix_candidates": sum(bool(items) for items in suffix_sets),
        "placements_with_both_candidate_types": sum(
            bool(fixed) and bool(suffix) for fixed, suffix in zip(fixed_sets, suffix_sets)
        ),
        "overlapping_region_candidate_count": sum(
            len(fixed & suffix) for fixed, suffix in zip(fixed_sets, suffix_sets)
        ),
        "fixed_candidates_fully_covered_by_suffix_candidates": sum(
            bool(fixed) and fixed <= suffix for fixed, suffix in zip(fixed_sets, suffix_sets)
        ),
        "placements_with_ambiguous_suffix_candidates": sum(len(items) > 1 for items in suffix_sets),
        "placements_with_equal_nonempty_candidate_sets": sum(
            bool(fixed) and fixed == suffix for fixed, suffix in zip(fixed_sets, suffix_sets)
        ),
    }


def _logic_song_payload(project_data: dict[str, Any]) -> bytes:
    object_index = project_data.get("logic_song_object_index")
    for item in project_data.get("opaque_data_objects", []):
        if item.get("object_index") == object_index and isinstance(item.get("base64"), str):
            payload = base64.b64decode(item["base64"], validate=True)
            if len(payload) != item.get("length"):
                raise BandFormatError("retained logic-song payload has an inconsistent length")
            return payload
    raise BandFormatError("retained logic-song NSData payload was not found")


def probe_project(path: str | Path) -> dict[str, Any]:
    project = parse_band(path)
    placements = project.project_data.get("audio_placements", [])
    event_records = project.project_data.get("event_sequences", {}).get("records", [])
    event_bytes_by_identity = {
        (record.get("chunk_index"), record.get("event_index")): bytes.fromhex(record["raw_hex"])
        for record in event_records
        if isinstance(record.get("raw_hex"), str)
    }
    logic_payload = _logic_song_payload(project.project_data)
    chunks = project.project_data["logic_song_chunk_stream"]["chunks"]
    placement_by_group: dict[int, list[dict[str, Any]]] = {}
    for placement in placements:
        group = placement.get("media_group_id_candidate")
        if isinstance(group, int):
            placement_by_group.setdefault(group, []).append(placement)

    aggregates: collections.Counter[str] = collections.Counter()
    region_payload_aggregates: collections.Counter[str] = collections.Counter()
    audio_reference_count = 0
    source_count = 0
    decoded_source_count = 0
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise BandFormatError(f"not a readable .band ZIP package: {path}") from exc

    with archive:
        for reference in project.media_references:
            if reference.category != "AudioFiles":
                continue
            audio_reference_count += 1
            frames = None
            if reference.package_member is not None:
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

            candidate_payloads: list[tuple[int, bytes]] = []
            for item in reference.region_chunk_metadata_candidates:
                chunk_index = item.get("chunk_index")
                frame_candidate = item.get("payload_u32_at_0x16_candidate")
                if (
                    not item.get("filename_stem_matches")
                    or not isinstance(chunk_index, int)
                    or not isinstance(frame_candidate, int)
                    or not 0 <= chunk_index < len(chunks)
                ):
                    continue
                chunk = chunks[chunk_index]
                start, size = chunk.get("payload_offset"), chunk.get("payload_size")
                if (
                    not isinstance(start, int) or not isinstance(size, int)
                    or start < 0 or size < 0 or start + size > len(logic_payload)
                ):
                    raise BandFormatError("region chunk payload lies outside the logic-song data")
                candidate_payloads.append((frame_candidate, logic_payload[start:start + size]))

            related_records = [
                event_bytes_by_identity[(item.get("source_chunk_index"), item.get("source_event_index"))]
                for item in linked_placements
                if (item.get("source_chunk_index"), item.get("source_event_index")) in event_bytes_by_identity
            ]
            duplicate_report = profile_candidate_region_payloads(candidate_payloads)
            for key, value in duplicate_report.items():
                if key == "interpretation":
                    continue
                if isinstance(value, dict):
                    for size, count in value.items():
                        region_payload_aggregates[f"{key}_{size}"] += count
                elif isinstance(value, int):
                    region_payload_aggregates[key] += value

            link_report = profile_region_placement_field_links(
                [payload for _, payload in candidate_payloads], related_records
            )
            for key, value in link_report.items():
                if key != "interpretation":
                    region_payload_aggregates[f"fixed_field_{key}"] += value
            frame_window_report = profile_source_frame_window_candidates(
                frames, [payload for _, payload in candidate_payloads]
            )
            for key, value in frame_window_report.items():
                region_payload_aggregates[f"frame_window_{key}"] += value

    return {
        "audio_reference_count": audio_reference_count,
        "embedded_audio_sources": source_count,
        "sources_with_decoded_frame_counts": decoded_source_count,
        "audio_placement_count": len(placements),
        "region_candidate_overlap": profile_region_candidate_overlap(
            [
                region.unknown["region_chunk_indices_matching_0x8a_to_0x28_candidate"]
                for track in project.tracks for region in track.regions if region.kind == "audio"
            ],
            [
                region.unknown["region_chunk_indices_matching_trailing_u32_candidate"]
                for track in project.tracks for region in track.regions if region.kind == "audio"
            ],
        ),
        **dict(sorted(aggregates.items())),
        **dict(sorted(region_payload_aggregates.items())),
        "interpretation": (
            "Aggregate only. Suffix, fixed-field, and source-frame-sum equalities are candidates, "
            "not proof of GarageBand object identity, source offset, duration, or loop semantics."
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


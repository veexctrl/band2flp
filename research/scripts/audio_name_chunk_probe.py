"""Trace audio-reference filename stems into other Logic-song chunk types."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from itertools import combinations
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit
from typing import Any

from band2flp.parser import BandFormatError, parse_band
from research.scripts.audio_region_source_link_probe import _logic_song_payload


def profile_audio_name_chunks(
    references: list[Any], chunks: list[dict[str, Any]], payload: bytes
) -> dict[str, Any]:
    """Count exact UTF-8 stem matches without returning names, paths, or group IDs."""
    by_index = {chunk.get("index"): chunk for chunk in chunks}
    reference_count = 0
    ignored_stem_count = 0
    filename_stems: set[bytes] = set()
    per_type: dict[str, dict[str, Any]] = {}
    matched_references: dict[str, set[int]] = defaultdict(set)
    matched_chunks: dict[str, set[int]] = defaultdict(set)
    totals: dict[str, Counter[str]] = defaultdict(Counter)
    reference_order_by_stem: dict[bytes, int] = {}
    source_order_by_stem: dict[bytes, int] = {}
    match_order_by_type: dict[str, dict[bytes, tuple[int, int]]] = defaultdict(dict)
    group_candidates_by_type: dict[str, dict[bytes, set[Any]]] = defaultdict(
        lambda: defaultdict(set)
    )
    family_pattern_counts_by_reference: dict[int, Counter[str]] = defaultdict(Counter)

    for reference_index, reference in enumerate(references):
        if getattr(reference, "category", None) != "AudioFiles":
            continue
        raw_reference = getattr(reference, "reference", None)
        if not isinstance(raw_reference, str):
            continue
        reference_count += 1
        path_text = urlsplit(raw_reference).path.replace("\\", "/")
        basename = unquote(path_text.rsplit("/", 1)[-1])
        stem = basename.rsplit(".", 1)[0] if "." in basename else basename
        needle = stem.encode("utf-8")
        if not needle or len(needle) > 255:
            ignored_stem_count += 1
            continue
        filename_stems.add(needle)
        reference_order_by_stem.setdefault(needle, reference_index)

        source_chunk_index = getattr(reference, "source_chunk_index", None)
        source_chunk = by_index.get(source_chunk_index)
        source_group = source_chunk.get("group_id_candidate") if source_chunk else None
        source_order = source_chunk.get("index") if source_chunk else None
        if isinstance(source_order, int):
            source_order_by_stem.setdefault(needle, source_order)
        for chunk in chunks:
            start = chunk.get("payload_offset")
            size = chunk.get("payload_size")
            chunk_index = chunk.get("index")
            if (
                not isinstance(start, int) or not isinstance(size, int)
                or not isinstance(chunk_index, int) or start < 0 or size < 0
                or start + size > len(payload)
            ):
                raise BandFormatError("audio-name probe found a chunk outside the payload bounds")
            end = start + size
            chunk_type = chunk.get("type") or "untyped"
            offset = start
            found_in_chunk = False
            while True:
                offset = payload.find(needle, offset, end)
                if offset < 0:
                    break
                found_in_chunk = True
                totals[chunk_type]["string_occurrence_count"] += 1
                totals[chunk_type]["preceding_byte_equals_utf8_length_count"] += int(
                    offset > start and payload[offset - 1] == len(needle)
                )
                has_extended_ascii_marker = (
                    offset >= start + 3
                    and payload[offset - 3:offset]
                    == b"\x5f\x10" + bytes((len(needle),))
                )
                totals[chunk_type]["bplist_extended_ascii_string_marker_match_count"] += int(
                    has_extended_ascii_marker
                )
                if has_extended_ascii_marker and offset >= start + 4:
                    totals[chunk_type]["name_after_bplist_true_marker_count"] += int(
                        payload[offset - 4] == 0x09
                    )
                    totals[chunk_type]["name_after_bplist_false_marker_count"] += int(
                        payload[offset - 4] == 0x08
                    )
                loop_metadata_prefix = (
                    b"\\IsFamilyLoop^LoopFamilyName\x09\x5f\x10"
                    + bytes((len(needle),))
                )
                family_pattern_match = (
                    offset >= start + len(loop_metadata_prefix)
                    and payload[offset - len(loop_metadata_prefix):offset]
                    == loop_metadata_prefix
                )
                totals[chunk_type]["loop_metadata_record_pattern_match_count"] += int(
                    family_pattern_match
                )
                family_pattern_counts_by_reference[reference_index][chunk_type] += int(
                    family_pattern_match
                )
                totals[chunk_type]["same_source_group_occurrence_count"] += int(
                    source_group is not None
                    and chunk.get("group_id_candidate") == source_group
                )
                order_candidate = (chunk_index, offset)
                previous_order = match_order_by_type[chunk_type].get(needle)
                if previous_order is None or order_candidate < previous_order:
                    match_order_by_type[chunk_type][needle] = order_candidate
                offset += len(needle)
            if found_in_chunk:
                matched_references[chunk_type].add(reference_index)
                matched_chunks[chunk_type].add(chunk_index)
                group_candidate = chunk.get("group_id_candidate")
                if group_candidate is not None:
                    group_candidates_by_type[chunk_type][needle].add(group_candidate)

    ordering_comparisons: dict[str, dict[str, int]] = {}
    for chunk_type in sorted(matched_references):
        context_counts = Counter()
        for chunk_index in matched_chunks[chunk_type]:
            chunk = by_index[chunk_index]
            start = chunk["payload_offset"]
            end = start + chunk["payload_size"]
            chunk_payload = payload[start:end]
            context_counts["matched_chunk_with_loop_family_name_key_count"] += int(
                b"^LoopFamilyName" in chunk_payload
            )
            context_counts["matched_chunk_with_is_family_loop_key_count"] += int(
                b"\\IsFamilyLoop" in chunk_payload
            )
            context_counts["matched_chunk_with_both_loop_keys_count"] += int(
                b"^LoopFamilyName" in chunk_payload
                and b"\\IsFamilyLoop" in chunk_payload
            )
        per_type[chunk_type] = {
            "matched_reference_count": len(matched_references[chunk_type]),
            "matched_chunk_count": len(matched_chunks[chunk_type]),
            **dict(sorted(totals[chunk_type].items())),
            **dict(sorted(context_counts.items())),
        }
        stems = list(match_order_by_type[chunk_type])
        source_agreements = reference_agreements = 0
        source_pair_count = reference_pair_count = 0
        for left, right in combinations(stems, 2):
            left_match, right_match = match_order_by_type[chunk_type][left], match_order_by_type[chunk_type][right]
            if left_match == right_match:
                continue
            reference_pair = (reference_order_by_stem[left], reference_order_by_stem[right])
            if reference_pair[0] == reference_pair[1]:
                continue
            reference_pair_count += 1
            reference_agreements += int(
                (reference_pair[0] < reference_pair[1]) == (left_match < right_match)
            )
            if left in source_order_by_stem and right in source_order_by_stem:
                left_source, right_source = source_order_by_stem[left], source_order_by_stem[right]
                if left_source == right_source:
                    continue
                source_pair_count += 1
                source_agreements += int(
                    (left_source < right_source) == (left_match < right_match)
                )
        ordering_comparisons[chunk_type] = {
            "matched_stem_count": len(stems),
            "pairwise_order_pair_count_with_reference_list": reference_pair_count,
            "pairwise_order_agreements_with_reference_list": reference_agreements,
            "pairwise_order_pair_count_with_source_chunks": source_pair_count,
            "pairwise_order_agreements_with_source_chunks": source_agreements,
        }

    group_intersections: dict[str, dict[str, int]] = {}
    chunk_types = sorted(group_candidates_by_type)
    for left_index, left_type in enumerate(chunk_types):
        for right_type in chunk_types[left_index + 1:]:
            common_stems = (
                set(group_candidates_by_type[left_type])
                & set(group_candidates_by_type[right_type])
            )
            comparable_stems = [
                stem for stem in common_stems
                if group_candidates_by_type[left_type][stem]
                and group_candidates_by_type[right_type][stem]
            ]
            shared_group_count = sum(
                bool(
                    group_candidates_by_type[left_type][stem]
                    & group_candidates_by_type[right_type][stem]
                )
                for stem in comparable_stems
            )
            group_intersections[f"{left_type}/{right_type}"] = {
                "common_stem_count": len(comparable_stems),
                "stems_with_shared_group_candidate_count": shared_group_count,
            }

    source_indices = [
        index for index, reference in enumerate(references)
        if getattr(reference, "category", None) == "AudioFiles"
    ]
    genm_counts = [family_pattern_counts_by_reference[index]["GenM"] for index in source_indices]
    sngo_counts = [family_pattern_counts_by_reference[index]["SngO"] for index in source_indices]
    family_join_counts = {
        "audio_reference_count": len(source_indices),
        "references_with_at_least_one_family_pattern_in_both_count": sum(
            genm > 0 and sngo > 0 for genm, sngo in zip(genm_counts, sngo_counts)
        ),
        "references_with_exactly_one_family_pattern_in_both_count": sum(
            genm == 1 and sngo == 1 for genm, sngo in zip(genm_counts, sngo_counts)
        ),
        "references_with_multiple_family_patterns_in_either_count": sum(
            genm > 1 or sngo > 1 for genm, sngo in zip(genm_counts, sngo_counts)
        ),
        "references_missing_a_family_pattern_in_either_count": sum(
            genm == 0 or sngo == 0 for genm, sngo in zip(genm_counts, sngo_counts)
        ),
    }

    return {
        "audio_reference_count": reference_count,
        "unique_filename_stem_count": len(filename_stems),
        "stems_skipped_for_length": ignored_stem_count,
        "chunk_type_matches": per_type,
        "ordering_comparisons": ordering_comparisons,
        "group_candidate_intersections": group_intersections,
        "loop_family_source_join_candidates": family_join_counts,
        "privacy_note": "Reference text, paths, group IDs, payload bytes, and media are omitted.",
    }


def probe_project(path: str | Path) -> dict[str, Any]:
    project = parse_band(path)
    chunks = project.project_data.get("logic_song_chunk_stream", {}).get("chunks", [])
    if not isinstance(chunks, list):
        raise BandFormatError("project has no validated logic-song chunks")
    payload = _logic_song_payload(project.project_data)
    return profile_audio_name_chunks(project.media_references, chunks, payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", nargs="+", type=Path, help="local .band project archives")
    args = parser.parse_args(argv)
    for index, path in enumerate(args.projects, start=1):
        try:
            result = probe_project(path)
        except (BandFormatError, OSError, ValueError) as exc:
            parser.error(f"fixture_{index} could not be inspected: {type(exc).__name__}")
        print(f"fixture_{index}: {json.dumps(result, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

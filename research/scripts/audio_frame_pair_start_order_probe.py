"""Compare source-frame pair candidates with linked audio placement start order.

This aggregate-only probe tests whether distinct, source-frame-validated
``AuRg +0x06/+0x16`` pairs order consistently with starts on placements linked
through the existing ``+0x8a``/``+0x28`` field candidate. It reads audio
container metadata only and emits counts, not source data or field values.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
from fractions import Fraction
import json
from pathlib import Path
import zipfile
from typing import Any

from band2flp.parser import (
    BandFormatError,
    _unique_candidate_region_field_pairs,
    parse_band,
)
from research.scripts.audio_frame_probe import audio_frame_metadata_stream


def _order(first_value: int, first_start: Fraction,
           second_value: int, second_start: Fraction) -> str:
    if first_value == second_value or first_start == second_start:
        return "ties"
    return "concordant" if (first_value < second_value) == (first_start < second_start) else "discordant"


def profile_pair_start_order(
    observations: list[tuple[int, int, str]], source_frames: int
) -> dict[str, int]:
    """Return order counts for source-frame-valid pairs and their starts."""
    if type(source_frames) is not int or source_frames < 0:
        raise BandFormatError("source frame count is invalid")
    valid: list[tuple[int, int, Fraction]] = []
    for first, second, start_text in observations:
        if type(first) is not int or first < 0 or type(second) is not int or second < 0:
            raise BandFormatError("frame-pair candidate is invalid")
        if not isinstance(start_text, str):
            continue
        try:
            start = Fraction(start_text)
        except (ValueError, ZeroDivisionError) as exc:
            raise BandFormatError("placement start candidate is invalid") from exc
        if first + second == source_frames:
            valid.append((first, second, start))

    record_orders: Counter[str] = Counter()
    for index, (first, _second, start) in enumerate(valid):
        for other_first, _other_second, other_start in valid[index + 1:]:
            record_orders[_order(first, start, other_first, other_start)] += 1

    starts_by_pair: dict[tuple[int, int], list[Fraction]] = defaultdict(list)
    for first, second, start in valid:
        starts_by_pair[(first, second)].append(start)
    group_orders: Counter[str] = Counter()
    group_values = [
        (pair[0], sum(starts, Fraction()) / len(starts))
        for pair, starts in starts_by_pair.items()
    ]
    for index, (value, start) in enumerate(group_values):
        for other_value, other_start in group_values[index + 1:]:
            group_orders[_order(value, start, other_value, other_start)] += 1

    return {
        "source_frame_valid_linked_record_count": len(valid),
        "distinct_source_frame_pair_count": len(starts_by_pair),
        "record_order_concordant_count": record_orders["concordant"],
        "record_order_discordant_count": record_orders["discordant"],
        "record_order_tie_count": record_orders["ties"],
        "window_group_order_concordant_count": group_orders["concordant"],
        "window_group_order_discordant_count": group_orders["discordant"],
        "window_group_order_tie_count": group_orders["ties"],
    }


def _logic_song_payload(project_data: dict[str, Any]) -> bytes:
    object_index = project_data.get("logic_song_object_index")
    for item in project_data.get("opaque_data_objects", []):
        if item.get("object_index") == object_index and isinstance(item.get("base64"), str):
            try:
                payload = base64.b64decode(item["base64"], validate=True)
            except (ValueError, TypeError) as exc:
                raise BandFormatError("Logic Song NSData is invalid Base64") from exc
            if len(payload) != item.get("length"):
                raise BandFormatError("Logic Song NSData length is inconsistent")
            return payload
    raise BandFormatError("Logic Song NSData was not found")


def probe_project(path: str | Path) -> dict[str, Any]:
    project = parse_band(path)
    data = project.project_data
    chunks = data.get("logic_song_chunk_stream", {}).get("chunks")
    if not isinstance(chunks, list):
        raise BandFormatError("project has no validated Logic Song chunks")
    song_data = _logic_song_payload(data)
    event_bytes = {
        (item.get("chunk_index"), item.get("event_index")): bytes.fromhex(item["raw_hex"])
        for item in data.get("event_sequences", {}).get("records", [])
        if isinstance(item.get("raw_hex"), str)
    }
    placements_by_group: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for placement in data.get("audio_placements", []):
        group = placement.get("media_group_id_candidate")
        if type(group) is int:
            placements_by_group[group].append(placement)

    source_results: list[dict[str, int]] = []
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise BandFormatError("project is not a readable ZIP package") from exc

    with archive:
        for reference in project.media_references:
            if reference.category != "AudioFiles" or reference.package_member is None:
                continue
            info = archive.getinfo(reference.package_member)
            with archive.open(info) as media_stream:
                source_frames, _format, _rate = audio_frame_metadata_stream(media_stream, info.file_size)
            if source_frames is None:
                continue

            region_payloads = []
            for candidate in reference.region_chunk_metadata_candidates:
                chunk_index = candidate.get("chunk_index")
                if not candidate.get("filename_stem_matches") or type(chunk_index) is not int:
                    continue
                if not 0 <= chunk_index < len(chunks):
                    raise BandFormatError("region chunk index is out of range")
                chunk = chunks[chunk_index]
                start, size = chunk.get("payload_offset"), chunk.get("payload_size")
                if (
                    type(start) is not int or type(size) is not int or size < 0
                    or start < 0 or start > len(song_data) - size
                ):
                    raise BandFormatError("region payload is outside Logic Song NSData")
                region_payloads.append(song_data[start:start + size])

            placement_rows = []
            for placement in placements_by_group.get(reference.group_id_candidate, []):
                identity = (placement.get("source_chunk_index"), placement.get("source_event_index"))
                raw = event_bytes.get(identity)
                if raw is not None:
                    placement_rows.append((placement, raw[:80]))
            if len(region_payloads) < 2 or len(placement_rows) < 2:
                continue
            if any(len(payload) < 0x92 for payload in region_payloads):
                continue

            region_fields = [payload[0x8A:0x92] for payload in region_payloads]
            placement_fields = [payload[0x28:0x30] for _, payload in placement_rows]
            linked = _unique_candidate_region_field_pairs(region_fields, placement_fields)
            observations = []
            for region_index, placement_index in linked:
                region = region_payloads[region_index]
                placement = placement_rows[placement_index][0]
                start = placement.get("start_beats")
                if not isinstance(start, str):
                    continue
                first = int.from_bytes(region[0x06:0x0A], "little")
                second = int.from_bytes(region[0x16:0x1A], "little")
                observations.append((first, second, start))
            if len(observations) < 2:
                continue
            report = profile_pair_start_order(observations, source_frames)
            if report["distinct_source_frame_pair_count"] >= 2:
                source_results.append(report)

    keys = (
        "source_frame_valid_linked_record_count",
        "distinct_source_frame_pair_count",
        "record_order_concordant_count",
        "record_order_discordant_count",
        "record_order_tie_count",
        "window_group_order_concordant_count",
        "window_group_order_discordant_count",
        "window_group_order_tie_count",
    )
    return {
        "source_groups_with_multiple_linked_frame_pairs": len(source_results),
        **{key: sum(result[key] for result in source_results) for key in keys},
        "interpretation": (
            "HYPOTHESIS only. Pair/start ordering compares existing source and placement candidates; "
            "it does not identify source-offset, duration, trim, or timeline semantics."
        ),
        "privacy_note": "Only aggregate counts are emitted; no media bytes, names, paths, IDs, or exact field values.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", nargs="+", type=Path, help="local .band project archives")
    args = parser.parse_args(argv)
    for index, path in enumerate(args.projects, start=1):
        try:
            report = probe_project(path)
        except (BandFormatError, KeyError, OSError, ValueError, zipfile.BadZipFile) as exc:
            parser.error(f"fixture_{index} could not be inspected: {type(exc).__name__}")
        print(json.dumps({"fixture_index": index, **report}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


"""Rank AuRg byte-offset pairs against embedded source frame counts.

This aggregate-only probe tests whether the observed +0x06/+0x16 sum is
distinctive among other 32-bit little-endian field-pair candidates. It reads
only audio container metadata through ZIP streams and never emits raw project
or media data.
"""

from __future__ import annotations

import argparse
import base64
from collections import defaultdict
import json
from pathlib import Path
from typing import Any
import zipfile

from band2flp.parser import BandFormatError, parse_band
from research.scripts.audio_frame_probe import audio_frame_metadata_stream

MAX_FIELD_SCAN_PAYLOAD_SIZE = 4096


def profile_frame_field_pairs(
    sources: list[tuple[int, list[bytes]]],
) -> dict[str, Any]:
    """Rank non-overlapping byte-offset pairs whose u32 values sum to frames."""
    record_hits: dict[tuple[int, int], int] = defaultdict(int)
    source_hits: dict[tuple[int, int], set[int]] = defaultdict(set)
    maximum_payload = 0
    record_count = 0
    oversized_record_count = 0

    for source_index, (frame_count, payloads) in enumerate(sources):
        if type(frame_count) is not int or frame_count < 0:
            raise BandFormatError("source frame count is invalid")
        source_record_hits: set[tuple[int, int]] = set()
        for payload in payloads:
            if not isinstance(payload, bytes):
                raise BandFormatError("AuRg payload is not bytes")
            maximum_payload = max(maximum_payload, len(payload))
            record_count += 1
            if len(payload) > MAX_FIELD_SCAN_PAYLOAD_SIZE:
                oversized_record_count += 1
                continue
            words = {
                offset: int.from_bytes(payload[offset:offset + 4], "little")
                for offset in range(max(0, len(payload) - 3))
            }
            offsets = sorted(words)
            for index, first_offset in enumerate(offsets):
                first = words[first_offset]
                for second_offset in offsets[index + 1:]:
                    if second_offset < first_offset + 4:
                        continue
                    if first + words[second_offset] == frame_count:
                        pair = (first_offset, second_offset)
                        record_hits[pair] += 1
                        source_record_hits.add(pair)
        for pair in source_record_hits:
            source_hits[pair].add(source_index)

    ranked = sorted(
        record_hits,
        key=lambda pair: (-record_hits[pair], -len(source_hits[pair]), pair[0], pair[1]),
    )
    candidate = (0x06, 0x16)
    candidate_rank = ranked.index(candidate) + 1 if candidate in record_hits else None
    max_hits = record_hits[ranked[0]] if ranked else 0
    return {
        "source_count": len(sources),
        "region_record_count": record_count,
        "oversized_record_count": oversized_record_count,
        "maximum_payload_size": maximum_payload,
        "candidate_offset_pair": [candidate[0], candidate[1]],
        "candidate_pair_rank": candidate_rank,
        "candidate_pair_record_match_count": record_hits.get(candidate, 0),
        "candidate_pair_source_match_count": len(source_hits.get(candidate, set())),
        "maximum_record_match_count": max_hits,
        "pairs_tied_for_maximum": sum(record_hits[pair] == max_hits for pair in ranked),
        "top_matching_offset_pairs": [
            {
                "offsets": [first, second],
                "record_match_count": record_hits[(first, second)],
                "source_match_count": len(source_hits[(first, second)]),
            }
            for first, second in ranked[:10]
        ],
        "interpretation": (
            "Ranking is a byte-pattern specificity check only. It does not identify "
            "the fields as source offset, duration, or any other GarageBand semantics."
        ),
    }


def _logic_song_payload(project_data: dict[str, Any]) -> bytes:
    object_index = project_data.get("logic_song_object_index")
    blobs = project_data.get("opaque_data_objects")
    if not isinstance(blobs, list):
        raise BandFormatError("project has no retained NSData objects")
    for blob in blobs:
        if blob.get("object_index") == object_index and isinstance(blob.get("base64"), str):
            try:
                payload = base64.b64decode(blob["base64"], validate=True)
            except (ValueError, TypeError) as exc:
                raise BandFormatError("Logic Song NSData is invalid Base64") from exc
            if len(payload) != blob.get("length"):
                raise BandFormatError("Logic Song NSData has an inconsistent length")
            return payload
    raise BandFormatError("Logic Song NSData was not found")


def probe_project(path: str | Path) -> dict[str, Any]:
    project = parse_band(path)
    chunks = project.project_data.get("logic_song_chunk_stream", {}).get("chunks")
    if not isinstance(chunks, list):
        raise BandFormatError("project has no validated Logic Song chunks")
    song_data = _logic_song_payload(project.project_data)
    sources: list[tuple[int, list[bytes]]] = []

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
                frames, _format, _rate = audio_frame_metadata_stream(media_stream, info.file_size)
            if frames is None:
                continue
            region_payloads: list[bytes] = []
            for item in reference.region_chunk_metadata_candidates:
                chunk_index = item.get("chunk_index")
                if not item.get("filename_stem_matches") or type(chunk_index) is not int:
                    continue
                if not 0 <= chunk_index < len(chunks):
                    raise BandFormatError("region chunk index is outside the validated stream")
                chunk = chunks[chunk_index]
                start, size = chunk.get("payload_offset"), chunk.get("payload_size")
                if (
                    type(start) is not int or type(size) is not int or size < 0
                    or start < 0 or start > len(song_data) - size
                ):
                    raise BandFormatError("region payload is outside Logic Song NSData")
                region_payloads.append(song_data[start:start + size])
            if region_payloads:
                sources.append((frames, region_payloads))

    return profile_frame_field_pairs(sources)


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

"""Compare GarageBand AuRg frame-count candidates with embedded audio lengths.

The probe reads audio members in memory and reports aggregate counts only. It
does not extract, play, copy, or print project audio or member names.
"""

from __future__ import annotations

import argparse
import collections
import json
import struct
import zipfile
from pathlib import Path
from typing import Any

from band2flp.parser import BandFormatError, parse_band


def _caf_frame_count(data: bytes) -> tuple[int | None, str]:
    offset = 8
    packet_frame_count: int | None = None
    description_offset: int | None = None
    audio_packet_bytes: int | None = None
    while offset + 12 <= len(data):
        tag = data[offset:offset + 4]
        size = struct.unpack_from(">q", data, offset + 4)[0]
        offset += 12
        if size < 0 or size > len(data) - offset:
            break
        if tag == b"pakt" and size >= 24:
            packet_frame_count = struct.unpack_from(">q", data, offset + 8)[0]
        elif tag == b"desc" and size >= 32:
            description_offset = offset
        elif tag == b"data" and size >= 4:
            audio_packet_bytes = size - 4
        offset += size
    if packet_frame_count is not None and packet_frame_count >= 0:
        return packet_frame_count, "CAF-packet-table"
    if description_offset is not None and audio_packet_bytes is not None:
        bytes_per_packet = struct.unpack_from(">I", data, description_offset + 16)[0]
        frames_per_packet = struct.unpack_from(">I", data, description_offset + 20)[0]
        if bytes_per_packet and frames_per_packet:
            return audio_packet_bytes // bytes_per_packet * frames_per_packet, "CAF-fixed-packet"
    return None, "CAF-variable-or-unrecognized-layout"


def audio_frame_count(data: bytes) -> tuple[int | None, str | None]:
    """Return decodable source frames and a format label, without audio decode."""
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        offset = 12
        block_align: int | None = None
        data_size: int | None = None
        while offset + 8 <= len(data):
            tag = data[offset:offset + 4]
            size = struct.unpack_from("<I", data, offset + 4)[0]
            offset += 8
            if size > len(data) - offset:
                break
            if tag == b"fmt " and size >= 16:
                block_align = struct.unpack_from("<H", data, offset + 12)[0]
            elif tag == b"data":
                data_size = size
            offset += size + (size & 1)
        if block_align and data_size is not None:
            return data_size // block_align, "WAVE"
        return None, "WAVE-unrecognized-layout"

    if data.startswith(b"FORM") and data[8:12] in (b"AIFF", b"AIFC"):
        offset = 12
        while offset + 8 <= len(data):
            tag = data[offset:offset + 4]
            size = struct.unpack_from(">I", data, offset + 4)[0]
            offset += 8
            if size > len(data) - offset:
                break
            if tag == b"COMM" and size >= 18:
                frames = struct.unpack_from(">I", data, offset + 2)[0]
                return frames, "AIFF"
            offset += size + (size & 1)
        return None, "AIFF-unrecognized-layout"

    if data.startswith(b"caff"):
        return _caf_frame_count(data)

    return None, None


def probe_project(path: str | Path) -> dict[str, Any]:
    project = parse_band(path)
    compared_sources = 0
    decoded_sources = 0
    candidate_count = 0
    exact_match_count = 0
    close_match_count = 0
    sources_with_any_match = 0
    formats: collections.Counter[str] = collections.Counter()
    unmatched_layout_count = 0

    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise BandFormatError(f"not a readable .band ZIP package: {path}") from exc

    with archive:
        for reference in project.media_references:
            if reference.category != "AudioFiles" or reference.package_member is None:
                continue
            compared_sources += 1
            frame_count, format_name = audio_frame_count(archive.read(reference.package_member))
            if frame_count is None or format_name is None:
                unmatched_layout_count += 1
                continue
            decoded_sources += 1
            formats[format_name] += 1
            source_match_count = 0
            for region in reference.region_chunk_metadata_candidates:
                candidate = region.get("payload_u32_at_0x16_candidate")
                if not isinstance(candidate, int):
                    continue
                candidate_count += 1
                if candidate == frame_count:
                    exact_match_count += 1
                    source_match_count += 1
                if abs(candidate - frame_count) <= max(1, frame_count * 0.001):
                    close_match_count += 1
            if source_match_count:
                sources_with_any_match += 1

    return {
        "embedded_audio_sources": compared_sources,
        "sources_with_decoded_frame_counts": decoded_sources,
        "unsupported_audio_layouts": unmatched_layout_count,
        "AuRg_frame_count_candidates_compared": candidate_count,
        "exact_candidate_matches": exact_match_count,
        "candidates_within_0_1_percent": close_match_count,
        "sources_with_at_least_one_exact_candidate": sources_with_any_match,
        "decoded_formats": dict(sorted(formats.items())),
        "interpretation": "Aggregate comparison only; a frame-count match does not establish arrangement duration or trim semantics.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="audio_frame_probe")
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

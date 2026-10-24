"""Compare GarageBand AuRg frame-count candidates with embedded audio lengths.

The probe reads only container headers and frame metadata from embedded audio
members, and reports aggregate counts. It does not read sample payloads,
extract, play, copy, or print project audio or member names.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import struct
import zipfile
from pathlib import Path
from typing import Any, BinaryIO

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
        sample_rate: int | None = None
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


def audio_frame_metadata_stream(
    stream: BinaryIO, file_size: int
) -> tuple[int | None, str | None, int | None]:
    """Read frame metadata from a media stream without reading sample payloads.

    The supported layouts put the needed metadata before their audio-data
    chunks: WAVE ``fmt `` before ``data``, AIFF ``COMM`` before ``SSND``, and
    CAF ``desc``/``pakt`` before ``data``. Unknown large chunks and unusual
    orderings are reported as unsupported instead of being consumed.
    """
    if file_size < 12:
        return None, None, None
    try:
        header = stream.read(12)
    except (OSError, ValueError):
        return None, None, None
    if len(header) != 12:
        return None, None, None

    def seek_metadata_chunk(size: int, pad: int = 0) -> bool:
        # Refuse to walk potentially large opaque chunks. In particular, this
        # prevents an unusual chunk order from consuming audio samples.
        if size < 0 or size + pad > 1_048_576:
            return False
        try:
            stream.seek(size + pad, 1)
            return True
        except (AttributeError, OSError, ValueError):
            return False

    if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        offset = 12
        block_align: int | None = None
        while offset + 8 <= min(file_size, 1_048_576):
            chunk_header = stream.read(8)
            if len(chunk_header) != 8:
                break
            tag = chunk_header[:4]
            size = struct.unpack_from("<I", chunk_header, 4)[0]
            offset += 8
            if size > file_size - offset:
                break
            if tag == b"fmt " and size >= 16:
                fmt = stream.read(16)
                if len(fmt) != 16:
                    break
                block_align = struct.unpack_from("<H", fmt, 12)[0]
                sample_rate = struct.unpack_from("<I", fmt, 4)[0]
                if not seek_metadata_chunk(size - 16, size & 1):
                    break
            elif tag == b"data":
                # Standard WAVE places fmt before data. Do not seek over the
                # sample bytes if the file has an unusual chunk ordering.
                if block_align and size >= 0:
                    rate = sample_rate if sample_rate and sample_rate > 0 else None
                    return size // block_align, "WAVE", rate
                break
            elif not seek_metadata_chunk(size, size & 1):
                break
            offset += size + (size & 1)
        return None, "WAVE-unrecognized-layout", None

    if header[:4] == b"FORM" and header[8:12] in (b"AIFF", b"AIFC"):
        offset = 12
        while offset + 8 <= min(file_size, 1_048_576):
            chunk_header = stream.read(8)
            if len(chunk_header) != 8:
                break
            tag = chunk_header[:4]
            size = struct.unpack_from(">I", chunk_header, 4)[0]
            offset += 8
            if size > file_size - offset:
                break
            if tag == b"COMM" and size >= 18:
                comm = stream.read(18)
                if len(comm) != 18:
                    break
                frames = struct.unpack_from(">I", comm, 2)[0]
                sign_exp = struct.unpack_from(">H", comm, 8)[0]
                mantissa = struct.unpack_from(">Q", comm, 10)[0]
                exponent = sign_exp & 0x7FFF
                exponent_value = exponent - 16383
                if exponent == 0x7FFF or mantissa == 0 or not -63 <= exponent_value <= 32:
                    return frames, "AIFF", None
                rate_value = mantissa / (1 << 63) * (2.0 ** exponent_value)
                rate = round(-rate_value if sign_exp & 0x8000 else rate_value)
                return frames, "AIFF", rate if rate > 0 else None
            if not seek_metadata_chunk(size, size & 1):
                break
            offset += size + (size & 1)
        return None, "AIFF-unrecognized-layout", None

    if header[:4] == b"caff":
        # The CAF file header is eight bytes; the initial common header read
        # also consumed four bytes from the first chunk header.
        try:
            stream.seek(8)
        except (AttributeError, OSError, ValueError):
            return None, "CAF-variable-or-unrecognized-layout", None
        offset = 8
        packet_frames: int | None = None
        bytes_per_packet: int | None = None
        frames_per_packet: int | None = None
        sample_rate: int | None = None
        while offset + 12 <= min(file_size, 1_048_576):
            chunk_header = stream.read(12)
            if len(chunk_header) != 12:
                break
            tag = chunk_header[:4]
            size = struct.unpack_from(">q", chunk_header, 4)[0]
            offset += 12
            if size < 0 or size > file_size - offset:
                break
            if tag == b"desc" and size >= 32:
                desc = stream.read(32)
                if len(desc) != 32:
                    break
                rate_value = struct.unpack_from(">d", desc, 0)[0]
                if math.isfinite(rate_value) and rate_value > 0:
                    sample_rate = round(rate_value)
                bytes_per_packet = struct.unpack_from(">I", desc, 16)[0]
                frames_per_packet = struct.unpack_from(">I", desc, 20)[0]
                if not seek_metadata_chunk(size - 32):
                    break
            elif tag == b"pakt" and size >= 24:
                packet = stream.read(24)
                if len(packet) != 24:
                    break
                value = struct.unpack_from(">q", packet, 8)[0]
                if value >= 0:
                    packet_frames = value
                if not seek_metadata_chunk(size - 24):
                    break
            elif tag == b"data":
                if packet_frames is not None:
                    return packet_frames, "CAF-packet-table", sample_rate
                if bytes_per_packet and frames_per_packet:
                    return ((size - 4) // bytes_per_packet * frames_per_packet,
                            "CAF-fixed-packet", sample_rate)
                break
            elif not seek_metadata_chunk(size):
                break
            offset += size
        if packet_frames is not None:
            return packet_frames, "CAF-packet-table", sample_rate
        return None, "CAF-variable-or-unrecognized-layout", sample_rate

    return None, None, None


def audio_sample_rate(data: bytes) -> int | None:
    """Read a source sample rate without decoding audio samples."""
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        offset = 12
        while offset + 8 <= len(data):
            tag = data[offset:offset + 4]
            size = struct.unpack_from("<I", data, offset + 4)[0]
            offset += 8
            if size > len(data) - offset:
                return None
            if tag == b"fmt " and size >= 8:
                rate = struct.unpack_from("<I", data, offset + 4)[0]
                return rate if rate > 0 else None
            offset += size + (size & 1)
        return None

    if data.startswith(b"FORM") and data[8:12] in (b"AIFF", b"AIFC"):
        offset = 12
        while offset + 8 <= len(data):
            tag = data[offset:offset + 4]
            size = struct.unpack_from(">I", data, offset + 4)[0]
            offset += 8
            if size > len(data) - offset:
                return None
            if tag == b"COMM" and size >= 18:
                sign_exp = struct.unpack_from(">H", data, offset + 8)[0]
                mantissa = struct.unpack_from(">Q", data, offset + 10)[0]
                exponent = sign_exp & 0x7FFF
                exponent_value = exponent - 16383
                if exponent == 0x7FFF or mantissa == 0 or not -63 <= exponent_value <= 32:
                    return None
                value = mantissa / (1 << 63) * (2.0 ** exponent_value)
                if sign_exp & 0x8000:
                    value = -value
                rate = round(value)
                return rate if rate > 0 else None
            offset += size + (size & 1)
        return None

    if data.startswith(b"caff"):
        offset = 8
        while offset + 12 <= len(data):
            tag = data[offset:offset + 4]
            size = struct.unpack_from(">q", data, offset + 4)[0]
            offset += 12
            if size < 0 or size > len(data) - offset:
                return None
            if tag == b"desc" and size >= 8:
                value = struct.unpack_from(">d", data, offset)[0]
                if not math.isfinite(value):
                    return None
                rate = round(value)
                return rate if rate > 0 else None
            offset += size
    return None


def probe_project(path: str | Path) -> dict[str, Any]:
    project = parse_band(path)
    compared_sources = 0
    decoded_sources = 0
    candidate_count = 0
    exact_match_count = 0
    close_match_count = 0
    sources_with_any_match = 0
    formats: collections.Counter[str] = collections.Counter()
    sample_rates: collections.Counter[str] = collections.Counter()
    candidate_frame_relations: collections.Counter[str] = collections.Counter()
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
            info = archive.getinfo(reference.package_member)
            with archive.open(info) as audio_stream:
                frame_count, format_name, sample_rate = audio_frame_metadata_stream(
                    audio_stream, info.file_size
                )
            if frame_count is None or format_name is None:
                unmatched_layout_count += 1
                continue
            decoded_sources += 1
            formats[format_name] += 1
            if sample_rate is not None:
                sample_rates[str(sample_rate)] += 1
            source_match_count = 0
            for region in reference.region_chunk_metadata_candidates:
                candidate = region.get("payload_u32_at_0x16_candidate")
                if not isinstance(candidate, int):
                    continue
                candidate_count += 1
                if candidate < frame_count:
                    candidate_frame_relations["below_source"] += 1
                elif candidate == frame_count:
                    candidate_frame_relations["equal_source"] += 1
                else:
                    candidate_frame_relations["above_source"] += 1
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
        "decoded_sample_rates_hz": dict(sorted(sample_rates.items())),
        "candidate_vs_full_source_frame_counts": dict(sorted(candidate_frame_relations.items())),
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

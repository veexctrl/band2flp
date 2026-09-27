"""Compare generated playlist audio-row shapes with FLP references safely."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import struct
import warnings
from typing import Any

from band2flp.flp_export import FLPExportError, _pyflp_module


PLAYLIST_EVENT_ID = 233
_STATIC_FIELDS = ("pattern_base", "group", "u1", "flags", "u2", "start_offset", "end_offset")


def _read_varint(data: bytes, offset: int, end: int) -> tuple[int, int]:
    """Read a bounded little-endian base-128 event length."""
    value = shift = 0
    while offset < end and shift <= 63:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
    raise ValueError("invalid or truncated FLP variable-length event size")


def playlist_event_data(data: bytes) -> list[bytes]:
    """Extract raw playlist event payloads from a bounded FLP event stream."""
    if len(data) < 22 or data[:4] != b"FLhd" or data[14:18] != b"FLdt":
        raise ValueError("invalid FLP header")
    event_bytes = struct.unpack_from("<I", data, 18)[0]
    end = 22 + event_bytes
    if end != len(data):
        raise ValueError("FLP event-data length does not match the file")

    payloads: list[bytes] = []
    offset = 22
    while offset < end:
        event_id = data[offset]
        offset += 1
        if event_id < 64:
            size = 1
        elif event_id < 128:
            size = 2
        elif event_id < 192:
            size = 4
        else:
            size, offset = _read_varint(data, offset, end)
        if size > end - offset:
            raise ValueError("FLP event extends beyond the file boundary")
        if event_id == PLAYLIST_EVENT_ID:
            payloads.append(data[offset:offset + size])
        offset += size
    return payloads


def _audio_clip_channel_ids(project: Any, channel_id: Any) -> set[int]:
    result = set()
    for channel in project.channels:
        type_event = next((event for event in channel.events if event.id == channel_id.Type), None)
        if (
            type_event is not None
            and int(type_event.value) == 4
            and channel.internal_name == ""
            and channel_id.SamplePath in channel.events.ids
        ):
            result.add(int(channel.iid))
    return result


def _decode_stride(payloads: list[bytes], size: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for payload in payloads:
        if not payload or len(payload) % size:
            continue
        for offset in range(0, len(payload), size):
            record = payload[offset:offset + size]
            position, pattern_base, item_index, length, track_rvidx, group = struct.unpack_from("<IHHIHH", record)
            records.append({
                "size": size,
                "position": position,
                "pattern_base": pattern_base,
                "item_index": item_index,
                "length": length,
                "track_rvidx": track_rvidx,
                "group": group,
                "u1": record[16:18],
                "flags": struct.unpack_from("<H", record, 18)[0],
                "u2": record[20:24],
                "start_offset": struct.unpack_from("<f", record, 24)[0],
                "end_offset": struct.unpack_from("<f", record, 28)[0],
            })
    return records


def stride_hypotheses(payloads: list[bytes], audio_channel_ids: set[int]) -> dict[str, dict[str, int]]:
    """Count plausible rows and audio-channel links at observed candidate strides."""
    results: dict[str, dict[str, int]] = {}
    for size in (32, 60, 80):
        compatible_payloads = [payload for payload in payloads if payload and len(payload) % size == 0]
        records = _decode_stride(compatible_payloads, size)
        linked = [
            record for record in records
            if record["item_index"] <= record["pattern_base"]
            and record["item_index"] in audio_channel_ids
        ]
        results[str(size)] = {
            "compatible_payload_count": len(compatible_payloads),
            "record_count": len(records),
            "audio_channel_link_count": len(linked),
        }
    return results


def _static_profile(record: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(record[field] for field in _STATIC_FIELDS)


def _profile_metrics(
    candidate: list[dict[str, Any]], references: list[dict[str, Any]], stride: int
) -> dict[str, Any]:
    """Compare known playlist fields without mixing ambiguous record strides."""
    candidate = [record for record in candidate if record["size"] == stride]
    references = [record for record in references if record["size"] == stride]
    profiles = Counter(_static_profile(record) for record in references)
    per_field_matches = {
        field: sum(any(reference[field] == record[field] for reference in references) for record in candidate)
        for field in _STATIC_FIELDS
    }
    reference_rows = {record["track_rvidx"] for record in references}
    candidate_rows = {record["track_rvidx"] for record in candidate}
    return {
        "candidate_audio_rows": len(candidate),
        "reference_audio_rows": len(references),
        "candidate_rows_with_reference_static_profile": sum(profiles[_static_profile(record)] > 0 for record in candidate),
        "candidate_field_matches_any_reference_row": per_field_matches,
        "candidate_track_rows_seen_in_references": len(candidate_rows & reference_rows),
    }


def compare_playlist_shapes(candidate_path: str | Path, reference_root: str | Path, limit: int = 100) -> dict[str, Any]:
    """Compare audio-row constants while omitting timing and project-specific data."""
    if limit < 1:
        raise ValueError("reference limit must be positive")
    pyflp, _ = _pyflp_module()
    from pyflp.channel import ChannelID

    def read_audio_records(path: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, int]]]:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                project = pyflp.parse(str(path))
            audio_ids = _audio_clip_channel_ids(project, ChannelID)
            data = path.read_bytes()
            payloads = playlist_event_data(data)
            records_by_stride = {}
            for size in (32, 60, 80):
                records_by_stride[str(size)] = [
                    record for record in _decode_stride(payloads, size)
                    if record["item_index"] <= record["pattern_base"]
                    and record["item_index"] in audio_ids
                ]
            return records_by_stride, stride_hypotheses(payloads, audio_ids)
        except Exception as exc:
            raise FLPExportError(f"cannot inspect FLP structure: {type(exc).__name__}") from exc

    candidate_by_stride, candidate_strides = read_audio_records(Path(candidate_path))
    if not any(candidate_by_stride.values()):
        raise FLPExportError("candidate FLP contains no sample-backed rows under the tested strides")
    root = Path(reference_root)
    if not root.is_dir():
        raise FLPExportError("reference root is not a directory")

    references_by_stride: dict[str, list[dict[str, Any]]] = {str(size): [] for size in (32, 60, 80)}
    reference_strides = {
        str(size): {"compatible_payload_count": 0, "record_count": 0, "audio_channel_link_count": 0}
        for size in (32, 60, 80)
    }
    projects_examined = parse_failures = 0
    for path in sorted(root.rglob("*.flp")):
        if projects_examined >= limit:
            break
        projects_examined += 1
        try:
            records_by_stride, strides = read_audio_records(path)
            for size, records in records_by_stride.items():
                references_by_stride[size].extend(records)
            for size, counts in strides.items():
                for key, value in counts.items():
                    reference_strides[size][key] += value
        except FLPExportError:
            parse_failures += 1

    profile_metrics = {
        size: _profile_metrics(candidate_by_stride[size], references_by_stride[size], int(size))
        for size in ("32", "60", "80")
    }
    return {
        "candidate_static_profile_comparison_by_stride": profile_metrics,
        "candidate_record_stride_hypotheses": candidate_strides,
        "reference_record_stride_hypotheses": reference_strides,
        "reference_projects_examined": projects_examined,
        "reference_parse_failures": parse_failures,
        "reference_audio_row_count_by_stride": {
            size: len(records) for size, records in references_by_stride.items()
        },
        "privacy_note": "Aggregate counts only; project names, paths, timing, media paths, and field values are omitted.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path, help="Generated FLP to compare")
    parser.add_argument("reference_root", type=Path, help="Folder containing FLP references")
    parser.add_argument("--limit", type=int, default=100, help="Maximum references to parse (default: 100)")
    args = parser.parse_args(argv)
    try:
        result = compare_playlist_shapes(args.candidate, args.reference_root, args.limit)
    except (FLPExportError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

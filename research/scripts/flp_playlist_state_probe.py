"""Create a local FL Studio probe with stable pre-playlist events from references.

The probe copies only two opaque top-level events from a sample-backed FLP
reference into a generated candidate. It never opens referenced audio. The
candidate inherits its original sample paths and must remain local.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import struct
import warnings
from typing import Any

from band2flp.flp_export import FLPExportError, _pyflp_module
from research.scripts.flp_playlist_inventory import (
    PLAYLIST_EVENT_ID,
    _audio_clip_channel_ids,
    _decode_stride,
    playlist_event_data,
)


REFERENCE_CONTEXT = (170, 51, 99, 241, 36, PLAYLIST_EVENT_ID)
CANDIDATE_CONTEXT = (99, 241, 36, PLAYLIST_EVENT_ID)


def parse_events(data: bytes) -> list[dict[str, Any]]:
    """Parse bounded FLP top-level event spans without interpreting values."""
    if len(data) < 22 or data[:4] != b"FLhd" or data[14:18] != b"FLdt":
        raise FLPExportError("invalid FLP header")
    event_size = struct.unpack_from("<I", data, 18)[0]
    end = 22 + event_size
    if end != len(data):
        raise FLPExportError("FLP event-data length does not match the file")
    events = []
    offset = 22
    while offset < end:
        start = offset
        event_id = data[offset]
        offset += 1
        if event_id < 64:
            size = 1
        elif event_id < 128:
            size = 2
        elif event_id < 192:
            size = 4
        else:
            value = shift = 0
            while offset < end and shift <= 63:
                byte = data[offset]
                offset += 1
                value |= (byte & 0x7F) << shift
                if not byte & 0x80:
                    break
                shift += 7
            else:
                raise FLPExportError("invalid or truncated FLP variable-length event size")
            size = value
        payload_start = offset
        if size > end - offset:
            raise FLPExportError("FLP event extends beyond the file boundary")
        offset += size
        events.append({
            "id": event_id,
            "start": start,
            "payload_start": payload_start,
            "end": offset,
        })
    return events


def _audio_rows(path: Path) -> tuple[Any, int]:
    pyflp, _ = _pyflp_module()
    from pyflp.channel import ChannelID

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            project = pyflp.parse(str(path))
        audio_ids = _audio_clip_channel_ids(project, ChannelID)
        payloads = playlist_event_data(path.read_bytes())
        rows = [
            record for record in _decode_stride(payloads, 80)
            if record["item_index"] <= record["pattern_base"]
            and record["item_index"] in audio_ids
        ]
        return project, len(rows)
    except Exception as exc:
        raise FLPExportError(f"cannot inspect FLP reference: {type(exc).__name__}") from exc


def _reference_event_bytes(data: bytes) -> tuple[bytes, bytes] | None:
    events = parse_events(data)
    ids = [event["id"] for event in events]
    for playlist_index, event_id in enumerate(ids):
        if event_id != PLAYLIST_EVENT_ID or playlist_index < 5:
            continue
        if tuple(ids[playlist_index - 5:playlist_index + 1]) != REFERENCE_CONTEXT:
            continue
        first, second = events[playlist_index - 5:playlist_index - 3]
        if first["id"] != 170 or second["id"] != 51:
            continue
        first_raw = data[first["start"]:first["end"]]
        second_raw = data[second["start"]:second["end"]]
        if first["end"] - first["payload_start"] != 4 or second["end"] - second["payload_start"] != 1:
            continue
        return first_raw, second_raw
    return None


def create_probe(candidate: str | Path, reference_root: str | Path, output: str | Path, limit: int = 25) -> dict[str, Any]:
    candidate_path, root, output_path = Path(candidate), Path(reference_root), Path(output)
    if not candidate_path.is_file() or not root.is_dir():
        raise FLPExportError("candidate and reference folder must exist")
    if output_path.exists() or output_path.is_symlink():
        raise FLPExportError("output already exists; choose a new path")
    if limit < 1:
        raise FLPExportError("reference limit must be positive")

    candidate_data = candidate_path.read_bytes()
    candidate_events = parse_events(candidate_data)
    candidate_ids = [event["id"] for event in candidate_events]
    playlist_indices = [i for i, event_id in enumerate(candidate_ids) if event_id == PLAYLIST_EVENT_ID]
    if len(playlist_indices) != 1:
        raise FLPExportError("candidate must contain exactly one playlist event")
    playlist_index = playlist_indices[0]
    if playlist_index < 3 or tuple(candidate_ids[playlist_index - 3:playlist_index + 1]) != CANDIDATE_CONTEXT:
        raise FLPExportError("candidate playlist does not have the expected arrangement preamble")
    candidate_playlist_payload = candidate_data[
        candidate_events[playlist_index]["payload_start"]:candidate_events[playlist_index]["end"]
    ]

    pyflp, _ = _pyflp_module()
    from pyflp.channel import ChannelID
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            candidate_project = pyflp.parse(str(candidate_path))
        candidate_audio_ids = _audio_clip_channel_ids(candidate_project, ChannelID)
        candidate_rows = [
            row for row in _decode_stride(playlist_event_data(candidate_data), 80)
            if row["item_index"] <= row["pattern_base"] and row["item_index"] in candidate_audio_ids
        ]
    except Exception as exc:
        raise FLPExportError(f"cannot inspect candidate FLP: {type(exc).__name__}") from exc
    if not candidate_rows:
        raise FLPExportError("candidate has no sample-backed 80-byte playlist rows")

    signatures: dict[tuple[bytes, bytes], int] = Counter()
    eligible_references = parse_failures = examined = 0
    selected_events: tuple[bytes, bytes] | None = None
    for path in sorted(root.rglob("*.flp")):
        if examined >= limit:
            break
        examined += 1
        try:
            _, row_count = _audio_rows(path)
            if not row_count:
                continue
            reference_data = path.read_bytes()
            raw_events = _reference_event_bytes(reference_data)
            if raw_events is None:
                continue
            eligible_references += 1
            signatures[raw_events] += 1
            selected_events = selected_events or raw_events
        except (OSError, FLPExportError):
            parse_failures += 1
    if not eligible_references or len(signatures) != 1 or selected_events is None:
        raise FLPExportError("references do not establish one stable pre-playlist event pair")

    insert_at = candidate_events[playlist_index - 3]["start"]
    result = bytearray(candidate_data[:insert_at] + selected_events[0] + selected_events[1] + candidate_data[insert_at:])
    struct.pack_into("<I", result, 18, len(result) - 22)
    result_bytes = bytes(result)
    checked = parse_events(result_bytes)
    checked_ids = [event["id"] for event in checked]
    checked_playlist = [i for i, event_id in enumerate(checked_ids) if event_id == PLAYLIST_EVENT_ID]
    if len(checked_playlist) != 1 or tuple(checked_ids[checked_playlist[0] - 5:checked_playlist[0] + 1]) != REFERENCE_CONTEXT:
        raise FLPExportError("inserted reference events did not produce the expected playlist context")
    final_playlist = checked[checked_playlist[0]]
    if result_bytes[final_playlist["payload_start"]:final_playlist["end"]] != candidate_playlist_payload:
        raise FLPExportError("probe unexpectedly changed the playlist payload")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(result_bytes)
    return {
        "candidate_sample_backed_80byte_rows": len(candidate_rows),
        "reference_projects_examined": examined,
        "reference_projects_with_matching_context": eligible_references,
        "reference_parse_failures": parse_failures,
        "distinct_reference_event_pairs": len(signatures),
        "event_170_distinct_payload_count": len({pair[0][1:] for pair in signatures}),
        "event_51_distinct_payload_count": len({pair[1][1:] for pair in signatures}),
        "event_51_zero_payload_count": sum(
            count for (event_170, event_51), count in signatures.items() if event_51[1:] == bytes(1)
        ),
        "reference_context": list(REFERENCE_CONTEXT),
        "candidate_context_before": list(CANDIDATE_CONTEXT),
        "playlist_payload_unchanged": True,
        "added_event_count": 2,
        "added_serialized_bytes": len(selected_events[0]) + len(selected_events[1]),
        "privacy_note": "Output retains candidate sample paths and copies opaque reference events; keep candidate and output private.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("reference_root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args(argv)
    try:
        report = create_probe(args.candidate, args.reference_root, args.output, args.limit)
    except (FLPExportError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Inventory recursively embedded Logic-family chunk streams, without values."""

from __future__ import annotations

import argparse
import base64
from collections import Counter
import json
from pathlib import Path
from typing import Any

from band2flp.parser import BandFormatError, _parse_chunk_stream, parse_band


_MAGIC = bytes.fromhex("2347c0ab")
_MAX_DEPTH = 8


def profile_nested_chunk_streams(data: bytes) -> dict[str, Any]:
    """Report stream/chunk counts for nested payloads beginning with magic.

    Malformed embedded candidates are counted, not interpreted. No raw bytes,
    offsets, group values, chunk IDs, or project names are returned.
    """
    try:
        root = _parse_chunk_stream(data)
    except BandFormatError as exc:
        raise BandFormatError("root logic-song stream is not valid") from exc

    streams_by_depth: dict[int, list[dict[str, Any]]] = {}
    malformed_candidate_count = 0
    visited: set[tuple[int, int]] = set()

    def walk(start: int, size: int, depth: int) -> None:
        nonlocal malformed_candidate_count
        if depth > _MAX_DEPTH or (start, size) in visited:
            return
        visited.add((start, size))
        payload = data[start:start + size]
        if not payload.startswith(_MAGIC):
            return
        try:
            stream = _parse_chunk_stream(payload)
        except BandFormatError:
            malformed_candidate_count += 1
            return
        streams_by_depth.setdefault(depth, []).append(stream)
        for chunk in stream["chunks"]:
            child_start = start + chunk["payload_offset"]
            child_size = chunk["payload_size"]
            if child_size >= 24 and data[child_start:child_start + 4] == _MAGIC:
                walk(child_start, child_size, depth + 1)

    for chunk in root["chunks"]:
        start, size = chunk["payload_offset"], chunk["payload_size"]
        if size >= 24 and data[start:start + 4] == _MAGIC:
            walk(start, size, 1)

    depth_profiles: dict[str, dict[str, Any]] = {}
    for depth, streams in sorted(streams_by_depth.items()):
        type_counts: Counter[str] = Counter()
        for stream in streams:
            type_counts.update(stream["type_counts"])
        depth_profiles[str(depth)] = {
            "stream_count": len(streams),
            "chunk_count": sum(stream["chunk_count"] for stream in streams),
            "type_counts": dict(sorted(type_counts.items())),
        }

    return {
        "root_chunk_count": root["chunk_count"],
        "nested_stream_count": sum(len(streams) for streams in streams_by_depth.values()),
        "nested_streams_by_depth": depth_profiles,
        "malformed_magic_candidate_count": malformed_candidate_count,
        "max_depth_limit": _MAX_DEPTH,
        "interpretation": "UNKNOWN; nested framing does not assign child chunk semantics.",
        "privacy_note": "Counts and chunk type tags only; values, offsets, names, and media are omitted.",
    }


def probe_project(path: str | Path) -> dict[str, Any]:
    project = parse_band(path)
    object_index = project.project_data.get("logic_song_object_index")
    blob = next(
        (item for item in project.project_data.get("opaque_data_objects", [])
         if item.get("object_index") == object_index),
        None,
    )
    if not isinstance(blob, dict) or not isinstance(blob.get("base64"), str):
        raise BandFormatError("retained logic-song payload was not found")
    payload = base64.b64decode(blob["base64"], validate=True)
    if len(payload) != blob.get("length"):
        raise BandFormatError("retained logic-song payload length is inconsistent")
    return profile_nested_chunk_streams(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", nargs="+", type=Path)
    args = parser.parse_args(argv)
    reports = []
    for index, path in enumerate(args.projects, start=1):
        try:
            reports.append({"fixture": index, **probe_project(path)})
        except (BandFormatError, OSError, ValueError, KeyError, IndexError) as exc:
            parser.error(f"fixture_{index} could not be inspected: {type(exc).__name__}")
    print(json.dumps({"fixtures": reports}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
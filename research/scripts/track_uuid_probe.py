"""Find serialized occurrences of the selected-track UUID without printing it."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import uuid
import zipfile
from typing import Any

from band2flp.parser import (
    BandFormatError,
    _find_member,
    _parse_chunk_stream,
    _read_member,
    _safe_plist,
    _uid_index,
)


def selected_track_uuid(root: Any) -> uuid.UUID | None:
    """Resolve the saved previous-current-track UI UUID from a keyed archive."""
    if not isinstance(root, dict) or not isinstance(root.get("$objects"), list):
        return None
    objects = root["$objects"]
    top = root.get("$top")
    if not isinstance(top, dict):
        return None
    arrange_index = _uid_index(top.get("DfDocument arrange model"))
    if arrange_index is None or not 0 <= arrange_index < len(objects):
        return None
    arrange = objects[arrange_index]
    if not isinstance(arrange, dict):
        return None
    cb_index = _uid_index(arrange.get("CBData"))
    if cb_index is None or not 0 <= cb_index < len(objects):
        return None
    cb_data = objects[cb_index]
    if not isinstance(cb_data, dict):
        return None
    keys, values = cb_data.get("NS.keys"), cb_data.get("NS.objects")
    if not isinstance(keys, list) or not isinstance(values, list) or len(keys) != len(values):
        return None

    selected_value = None
    for key_ref, value_ref in zip(keys, values):
        key_index = _uid_index(key_ref)
        if key_index is None or not 0 <= key_index < len(objects):
            continue
        if objects[key_index] != "previousCurrentTrackUUID":
            continue
        value_index = _uid_index(value_ref)
        if value_index is not None and 0 <= value_index < len(objects):
            selected_value = objects[value_index]
        else:
            selected_value = value_ref
        break

    if isinstance(selected_value, dict):
        selected_value = selected_value.get("NS.string")
    if not isinstance(selected_value, str):
        return None
    try:
        return uuid.UUID(selected_value.strip("{} "))
    except ValueError:
        return None


def find_uuid_payload_matches(
    payload: bytes, chunk_stream: dict[str, Any], value: uuid.UUID
) -> list[dict[str, Any]]:
    """Locate canonical and mixed-endian UUID bytes in bounded chunk payloads."""
    encodings = (("uuid_bytes", value.bytes), ("uuid_bytes_le", value.bytes_le))
    matches: list[dict[str, Any]] = []
    for chunk_index, chunk in enumerate(chunk_stream.get("chunks", [])):
        start = chunk["payload_offset"]
        size = chunk["payload_size"]
        invalid_bounds = (
            not isinstance(start, int)
            or not isinstance(size, int)
            or start < 0
            or size < 0
            or start + size > len(payload)
        )
        if invalid_bounds:
            raise BandFormatError("chunk payload lies outside the logic-song data")
        data = payload[start:start + size]
        for encoding, needle in encodings:
            offset = data.find(needle)
            if offset >= 0:
                matches.append({
                    "chunk_index": chunk_index,
                    "chunk_type": chunk["type"],
                    "chunk_payload_size": size,
                    "payload_offset": offset,
                    "encoding": encoding,
                })
    return matches


def trak_uuid_field_profile(payload: bytes, chunk_stream: dict[str, Any]) -> dict[str, Any]:
    """Summarize the 16-byte +0x18 fields in 58-byte Trak payloads only."""
    fields: list[bytes] = []
    for chunk in chunk_stream.get("chunks", []):
        if chunk.get("type") != "Trak" or chunk.get("payload_size") != 58:
            continue
        start = chunk.get("payload_offset")
        if not isinstance(start, int) or start < 0 or start + 58 > len(payload):
            raise BandFormatError("Trak payload lies outside the logic-song data")
        fields.append(payload[start + 0x18:start + 0x28])
    parsed = [uuid.UUID(bytes=value) for value in fields]
    return {
        "58_byte_trak_count": len(fields),
        "unique_payload_0x18_values": len(set(fields)),
        "payload_0x18_uuid_variant_counts": dict(Counter(str(value.variant) for value in parsed)),
        "payload_0x18_uuid_version_counts": dict(Counter(
            str(value.version) if value.version is not None else "none" for value in parsed
        )),
    }


def probe(path: str | Path) -> dict[str, Any]:
    project_path = Path(path)
    with zipfile.ZipFile(project_path) as archive:
        names = [info.filename for info in archive.infolist()]
        member = _find_member(names, "/projectData")
        if member is None:
            raise BandFormatError("projectData member was not found")
        info = archive.getinfo(member)
        root = _safe_plist(_read_member(archive, info), member)
    track_uuid = selected_track_uuid(root)
    if track_uuid is None:
        return {
            "selected_track_uuid_found": False,
            "matching_chunk_count": 0,
            "matching_chunk_types": {},
            "matching_payload_sizes": [],
            "matching_payload_offsets": [],
            "matched_encodings": [],
            "privacy_note": "Project paths, identifiers, and media data are omitted.",
        }
    objects = root.get("$objects", [])
    top = root.get("$top", {})
    logic_index = _uid_index(top.get("DfDocument logic model")) if isinstance(top, dict) else None
    logic_model = (
        objects[logic_index]
        if logic_index is not None and 0 <= logic_index < len(objects)
        else None
    )
    song_index = (
        _uid_index(logic_model.get("DfLogicModelLogicSong"))
        if isinstance(logic_model, dict)
        else None
    )
    song = (
        objects[song_index]
        if song_index is not None and 0 <= song_index < len(objects)
        else None
    )
    payload = song.get("NS.data") if isinstance(song, dict) else None
    if not isinstance(payload, bytes):
        raise BandFormatError("logic-song NSData was not found")
    chunk_stream = _parse_chunk_stream(payload)
    matches = find_uuid_payload_matches(payload, chunk_stream, track_uuid)
    matched_chunks = {match["chunk_index"]: match for match in matches}
    return {
        "selected_track_uuid_found": True,
        **trak_uuid_field_profile(payload, chunk_stream),
        "matching_chunk_count": len(matched_chunks),
        "matching_chunk_types": {
            tag: sum(match["chunk_type"] == tag for match in matched_chunks.values())
            for tag in sorted({match["chunk_type"] for match in matched_chunks.values()})
        },
        "matching_payload_sizes": sorted({match["chunk_payload_size"] for match in matches}),
        "matching_payload_offsets": sorted({match["payload_offset"] for match in matches}),
        "matched_encodings": sorted({match["encoding"] for match in matches}),
        "privacy_note": "UUID value, project path, project name, and media data are omitted.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", nargs="+", type=Path, help="local .band project archives")
    args = parser.parse_args(argv)
    for index, path in enumerate(args.projects, start=1):
        try:
            result = probe(path)
        except Exception as exc:
            parser.error(f"fixture_{index} could not be inspected: {type(exc).__name__}")
        print(f"fixture_{index}: {json.dumps(result, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

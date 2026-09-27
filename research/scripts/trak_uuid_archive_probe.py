"""Find track UUID references in keyed-archive strings and companion plists."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import plistlib
import uuid
from typing import Any, Iterator
import zipfile

from band2flp.parser import (
    BandFormatError,
    _find_member,
    _parse_chunk_stream,
    _read_member,
    _safe_plist,
    _uid_index,
)
from research.scripts.track_uuid_probe import selected_track_uuid


def _resolve(objects: list[Any], reference: Any) -> Any:
    index = _uid_index(reference)
    if index is None or not 0 <= index < len(objects):
        return None
    return objects[index]


def _logic_song_data(archive: Any) -> bytes:
    if not isinstance(archive, dict) or not isinstance(archive.get("$objects"), list):
        raise BandFormatError("projectData is not a recognized keyed archive")
    objects, top = archive["$objects"], archive.get("$top")
    if not isinstance(top, dict):
        raise BandFormatError("keyed archive has no top-level references")
    logic_model = _resolve(objects, top.get("DfDocument logic model"))
    song = _resolve(objects, logic_model.get("DfLogicModelLogicSong")) if isinstance(logic_model, dict) else None
    data = song.get("NS.data") if isinstance(song, dict) else None
    if not isinstance(data, bytes):
        raise BandFormatError("logic-song NSData was not found")
    return data


def _track_uuids(payload: bytes, chunks: dict[str, Any]) -> set[uuid.UUID]:
    values = set()
    for chunk in chunks.get("chunks", []):
        if chunk.get("type") != "Trak" or chunk.get("payload_size") != 58:
            continue
        start = chunk.get("payload_offset")
        if not isinstance(start, int) or start < 0 or start + 58 > len(payload):
            raise BandFormatError("Trak payload lies outside the logic-song data")
        values.add(uuid.UUID(bytes=payload[start + 0x18:start + 0x28]))
    return values


def _archive_strings(root: dict[str, Any]) -> Iterator[str]:
    for item in root.get("$objects", []):
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict) and isinstance(item.get("NS.string"), str):
            yield item["NS.string"]


def _scalars(value: Any) -> Iterator[str | bytes]:
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, (str, bytes)):
                yield key
            yield from _scalars(item)
    elif isinstance(value, list):
        for item in value:
            yield from _scalars(item)
    elif isinstance(value, (str, bytes)):
        yield value


def _string_match(value: str, identifier: uuid.UUID) -> bool:
    forms = (str(identifier), str(identifier).upper(), "{" + str(identifier) + "}", "{" + str(identifier).upper() + "}")
    return any(form in value for form in forms)


def _bytes_match(value: bytes, identifier: uuid.UUID) -> bool:
    patterns = [identifier.bytes, identifier.bytes_le]
    for text in (str(identifier), str(identifier).upper(), "{" + str(identifier) + "}", "{" + str(identifier).upper() + "}"):
        patterns.extend((text.encode("ascii"), text.encode("utf-16-le"), text.encode("utf-16-be")))
    return any(pattern in value for pattern in patterns)


def profile_archive_references(
    root: Any, track_uuids: set[uuid.UUID], companion_plists: list[Any]
) -> dict[str, Any]:
    """Count UUID matches without returning identifiers or source field values."""
    if not isinstance(root, dict) or not isinstance(root.get("$objects"), list):
        raise BandFormatError("projectData is not a recognized keyed archive")
    strings = list(_archive_strings(root))
    projectdata_matches = {
        identifier for identifier in track_uuids
        if any(_string_match(value, identifier) for value in strings)
    }
    selected_track = selected_track_uuid(root)
    companion_text_matches: set[uuid.UUID] = set()
    companion_bytes_matches: set[uuid.UUID] = set()
    for component in companion_plists:
        for value in _scalars(component):
            if isinstance(value, str):
                companion_text_matches.update(
                    identifier for identifier in track_uuids
                    if _string_match(value, identifier)
                )
            else:
                companion_bytes_matches.update(
                    identifier for identifier in track_uuids
                    if _bytes_match(value, identifier)
                )
    return {
        "track_uuid_count": len(track_uuids),
        "projectdata_string_matched_uuid_count": len(projectdata_matches),
        "previous_current_track_uuid_matches_trak_field": selected_track in track_uuids,
        "companion_plist_count": len(companion_plists),
        "companion_plist_string_matched_uuid_count": len(companion_text_matches),
        "companion_plist_bytes_matched_uuid_count": len(companion_bytes_matches),
        "privacy_note": "UUIDs, field names, component paths, project names, and media are omitted.",
    }


def probe(path: str | Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        names = [info.filename for info in archive.infolist()]
        member = _find_member(names, "/projectData")
        if member is None:
            raise BandFormatError("projectData member was not found")
        root = _safe_plist(_read_member(archive, archive.getinfo(member)), member)
        payload = _logic_song_data(root)
        chunks = _parse_chunk_stream(payload)
        identifiers = _track_uuids(payload, chunks)
        companions = []
        for name in names:
            if name == member or not name.endswith(".plist"):
                continue
            companions.append(_safe_plist(_read_member(archive, archive.getinfo(name)), name))
    return profile_archive_references(root, identifiers, companions)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", nargs="+", type=Path, help="local .band project archives")
    args = parser.parse_args(argv)
    for index, path in enumerate(args.projects, start=1):
        try:
            report = probe(path)
        except Exception as exc:
            parser.error(f"fixture_{index} could not be inspected: {type(exc).__name__}")
        print(f"fixture_{index}: {json.dumps(report, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

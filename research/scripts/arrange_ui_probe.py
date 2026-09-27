"""Profile arrange-model inspector UI state without exposing project values."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
import zipfile

from band2flp.parser import BandFormatError, _find_member, _read_member, _safe_plist, _uid_index


def _resolve(objects: list[Any], reference: Any) -> Any:
    index = _uid_index(reference)
    if index is None or not 0 <= index < len(objects):
        return None
    return objects[index]


def _archive_string(objects: list[Any], reference: Any) -> str | None:
    value = _resolve(objects, reference)
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("NS.string"), str):
        return value["NS.string"]
    return None


def _entries(objects: list[Any], value: Any) -> list[tuple[str, Any]]:
    if not isinstance(value, dict):
        return []
    keys, values = value.get("NS.keys"), value.get("NS.objects")
    if not isinstance(keys, list) or not isinstance(values, list) or len(keys) != len(values):
        return []
    result = []
    for key_ref, value_ref in zip(keys, values):
        key = _archive_string(objects, key_ref)
        if key is None:
            continue
        result.append((key, _resolve(objects, value_ref)))
    return result


def profile_arrange_ui(archive: Any) -> dict[str, Any]:
    """Return inspector-state keys and value types, never serialized values."""
    if not isinstance(archive, dict) or not isinstance(archive.get("$objects"), list):
        raise BandFormatError("projectData is not a recognized keyed archive")
    objects = archive["$objects"]
    top = archive.get("$top")
    arrange = _resolve(objects, top.get("DfDocument arrange model")) if isinstance(top, dict) else None
    cb_data = _resolve(objects, arrange.get("CBData")) if isinstance(arrange, dict) else None
    state = next(
        (value for key, value in _entries(objects, cb_data) if key == "CbTrackInspectorInternalState"),
        None,
    )
    fields = _entries(objects, state)
    return {
        "arrange_model_found": isinstance(arrange, dict),
        "cbdata_found": isinstance(cb_data, dict),
        "track_inspector_state_found": state is not None,
        "track_inspector_state_field_count": len(fields),
        "track_inspector_state_fields": [
            {"key": key, "value_type": type(value).__name__}
            for key, value in fields
        ],
        "privacy_note": "Project values, identifiers, paths, names, and media are omitted.",
    }


def probe(path: str | Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        member = _find_member(archive.namelist(), "/projectData")
        if member is None:
            raise BandFormatError("projectData member was not found")
        info = archive.getinfo(member)
        root = _safe_plist(_read_member(archive, info), member)
    return profile_arrange_ui(root)


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

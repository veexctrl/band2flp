"""Inventory NSKeyedArchiver object classes and field names without values."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any
import zipfile

from band2flp.parser import BandFormatError, _find_member, _read_member, _safe_plist, _uid_index


def _resolve(objects: list[Any], value: Any) -> Any:
    index = _uid_index(value)
    if index is None or not 0 <= index < len(objects):
        return None
    return objects[index]


def _string(objects: list[Any], value: Any) -> str | None:
    resolved = _resolve(objects, value)
    if isinstance(resolved, str):
        return resolved
    if isinstance(resolved, dict) and isinstance(resolved.get("NS.string"), str):
        return resolved["NS.string"]
    return None


def _class_name(objects: list[Any], value: Any) -> str:
    class_object = _resolve(objects, value)
    if not isinstance(class_object, dict):
        return "unknown"
    name = class_object.get("$classname")
    return name if isinstance(name, str) else "unknown"


def profile_archive(archive: Any) -> dict[str, Any]:
    """Return schema-shaped counts only; serialized project values are omitted."""
    if not isinstance(archive, dict) or not isinstance(archive.get("$objects"), list):
        raise BandFormatError("projectData is not a recognized keyed archive")
    objects = archive["$objects"]
    class_counts: Counter[str] = Counter()
    fields_by_class: dict[str, Counter[str]] = defaultdict(Counter)
    value_types_by_class: dict[str, Counter[str]] = defaultdict(Counter)
    dictionary_key_length_counts: Counter[str] = Counter()
    dictionary_value_types: Counter[str] = Counter()

    for obj in objects:
        if not isinstance(obj, dict):
            continue
        class_ref = obj.get("$class")
        if class_ref is None:
            continue
        class_name = _class_name(objects, class_ref)
        class_counts[class_name] += 1
        fields_by_class[class_name].update(key for key in obj if key != "$class")
        value_types_by_class[class_name].update(type(value).__name__ for key, value in obj.items() if key != "$class")

        keys, values = obj.get("NS.keys"), obj.get("NS.objects")
        if isinstance(keys, list) and isinstance(values, list) and len(keys) == len(values):
            for key_ref, value_ref in zip(keys, values):
                key = _string(objects, key_ref)
                if key is not None:
                    dictionary_key_length_counts[str(len(key))] += 1
                dictionary_value_types[type(value_ref).__name__] += 1

    return {
        "object_count": len(objects),
        "class_counts": dict(sorted(class_counts.items())),
        "fields_by_class": {
            name: dict(sorted(counts.items())) for name, counts in sorted(fields_by_class.items())
        },
        "value_types_by_class": {
            name: dict(sorted(counts.items())) for name, counts in sorted(value_types_by_class.items())
        },
        "keyed_dictionary_key_length_counts": dict(sorted(dictionary_key_length_counts.items())),
        "keyed_dictionary_value_reference_types": dict(sorted(dictionary_value_types.items())),
        "privacy_note": "Dictionary key text, project values, identifiers, user strings, paths, media, and archive object indices are omitted.",
    }


def profile_project(path: str | Path) -> dict[str, Any]:
    """Read only the projectData member; do not open or extract media members."""
    with zipfile.ZipFile(path) as package:
        member = _find_member(package.namelist(), "/projectData")
        if member is None:
            raise BandFormatError("projectData member was not found")
        info = package.getinfo(member)
        archive = _safe_plist(_read_member(package, info), member)
    return profile_archive(archive)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", nargs="+", type=Path, help="local .band project archives")
    args = parser.parse_args(argv)
    for index, path in enumerate(args.projects, start=1):
        try:
            result = profile_project(path)
        except Exception as exc:
            parser.error(f"fixture_{index} could not be inspected: {type(exc).__name__}")
        print(f"fixture_{index}: {json.dumps(result, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

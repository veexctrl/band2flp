"""Search Trak UUID fields for additional references in the logic-song chunks."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import uuid
from typing import Any

from band2flp.parser import BandFormatError, parse_band


def _uuid_forms(value: uuid.UUID) -> tuple[tuple[str, bytes], ...]:
    forms: list[tuple[str, bytes]] = [
        ("uuid_bytes", value.bytes),
        ("uuid_bytes_le", value.bytes_le),
    ]
    texts = (
        str(value),
        str(value).upper(),
        "{" + str(value) + "}",
        "{" + str(value).upper() + "}",
    )
    for index, text in enumerate(texts):
        label = ("ascii", "ascii_upper", "ascii_braced", "ascii_braced_upper")[index]
        forms.extend((
            ("uuid_" + label, text.encode("ascii")),
            ("uuid_utf16le" + label[5:], text.encode("utf-16-le")),
            ("uuid_utf16be" + label[5:], text.encode("utf-16-be")),
        ))
    return tuple(forms)


def additional_uuid_occurrences(
    payload: bytes, chunks: list[dict[str, Any]]
) -> dict[str, Any]:
    """Count references outside each source UUID field; never return UUIDs."""
    fields: list[tuple[int, uuid.UUID]] = []
    for chunk in chunks:
        if chunk.get("type") != "Trak" or chunk.get("payload_size") != 58:
            continue
        start = chunk.get("payload_offset")
        if not isinstance(start, int) or start < 0 or start + 58 > len(payload):
            raise BandFormatError("Trak payload lies outside the logic-song data")
        fields.append((chunk["index"], uuid.UUID(bytes=payload[start + 0x18:start + 0x28])))

    occurrences_by_type: Counter[str] = Counter()
    fields_with_additional_occurrences = 0
    total_occurrences = 0
    for source_index, identifier in fields:
        has_additional_occurrence = False
        for chunk in chunks:
            start = chunk["payload_offset"]
            size = chunk["payload_size"]
            if (
                not isinstance(start, int)
                or not isinstance(size, int)
                or start < 0
                or size < 0
                or start + size > len(payload)
            ):
                raise BandFormatError("chunk payload lies outside the logic-song data")
            data = payload[start:start + size]
            for form, needle in _uuid_forms(identifier):
                offset = -1
                while True:
                    offset = data.find(needle, offset + 1)
                    if offset < 0:
                        break
                    if chunk["index"] == source_index and form == "uuid_bytes" and offset == 0x18:
                        continue
                    has_additional_occurrence = True
                    total_occurrences += 1
                    occurrences_by_type[str(chunk.get("type") or "unknown")] += 1
        if has_additional_occurrence:
            fields_with_additional_occurrences += 1
    return {
        "track_uuid_field_count": len(fields),
        "distinct_track_uuid_count": len({identifier for _, identifier in fields}),
        "track_uuid_fields_with_additional_payload_occurrences": fields_with_additional_occurrences,
        "additional_payload_occurrence_count": total_occurrences,
        "additional_occurrences_by_chunk_type": dict(sorted(occurrences_by_type.items())),
        "privacy_note": "UUID values, payload bytes, project names, paths, and media are omitted.",
    }


def probe(path: str | Path) -> dict[str, Any]:
    project = parse_band(path)
    project_data = project.project_data
    stream = project_data.get("logic_song_chunk_stream")
    if not isinstance(stream, dict):
        raise BandFormatError("project has no validated logic-song chunk stream")
    object_index = project_data.get("logic_song_object_index")
    for blob in project_data.get("opaque_data_objects", []):
        if blob.get("object_index") != object_index or not isinstance(blob.get("base64"), str):
            continue
        import base64

        payload = base64.b64decode(blob["base64"], validate=True)
        if len(payload) != blob.get("length") or stream.get("end_offset") != len(payload):
            raise BandFormatError("retained logic-song payload is inconsistent")
        return additional_uuid_occurrences(payload, stream["chunks"])
    raise BandFormatError("logic-song NSData payload was not retained")


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

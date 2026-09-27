"""Profile byte-position variation within grouped MIDI-like event records.

Only event type, record size, aggregate group counts, and byte offsets are
reported. Event bytes, group values, names, and project identifiers are omitted.
Variation is descriptive evidence, not a field decoder.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Any

from band2flp.parser import BandFormatError, parse_band


def profile_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Count byte offsets that vary within repeated type/size/group buckets."""
    buckets: dict[tuple[int, int], dict[int, list[bytes]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for record in records:
        event_type = record.get("type_byte")
        group = record.get("group_id_candidate")
        raw_hex = record.get("raw_hex")
        if not isinstance(event_type, int) or not 0 <= event_type <= 0xFF:
            raise BandFormatError("event variation profile contains an invalid type byte")
        if not isinstance(group, int) or group < 0:
            raise BandFormatError("event variation profile contains an invalid group candidate")
        if not isinstance(raw_hex, str):
            raise BandFormatError("event variation profile is missing raw record bytes")
        try:
            raw = bytes.fromhex(raw_hex)
        except ValueError as exc:
            raise BandFormatError("event variation profile contains invalid record bytes") from exc
        if len(raw) < 16 or len(raw) % 16:
            raise BandFormatError("event variation profile contains a non-atom-aligned record")
        buckets[(event_type, len(raw))][group].append(raw)

    families: dict[str, Any] = {}
    for (event_type, size), groups in sorted(buckets.items()):
        comparable_groups = [rows for rows in groups.values() if len(rows) > 1]
        varying_groups_by_offset: dict[int, int] = defaultdict(int)
        for rows in comparable_groups:
            for offset in range(size):
                if len({row[offset] for row in rows}) > 1:
                    varying_groups_by_offset[offset] += 1
        families[f"0x{event_type:02x}/{size}"] = {
            "record_count": sum(map(len, groups.values())),
            "distinct_group_count": len(groups),
            "groups_with_multiple_records": len(comparable_groups),
            "varying_byte_offset_group_counts": {
                str(offset): count
                for offset, count in sorted(varying_groups_by_offset.items())
            },
            "interpretation": "UNKNOWN; variation can reflect unrelated event fields or mixed subtypes",
        }
    return {
        "family_count": len(families),
        "families": families,
        "privacy_note": "Event bytes and group values are omitted; only structural counts and byte offsets are reported.",
    }


def probe_project(path: str | Path) -> dict[str, Any]:
    project = parse_band(path)
    events = project.project_data.get("event_sequences")
    if not isinstance(events, dict) or not isinstance(events.get("records"), list):
        raise BandFormatError("project has no validated event sequence records")
    return profile_records(events["records"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
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

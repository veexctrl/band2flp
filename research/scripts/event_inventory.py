"""Summarize event type/record shapes without exposing event bytes or labels."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any

from band2flp.parser import BandFormatError, parse_band


def inventory_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Return aggregate counts only; omit raw values, strings, and group IDs."""
    by_type: dict[int, Counter[int]] = defaultdict(Counter)
    groups: dict[int, set[int]] = defaultdict(set)
    zero_group_counts: Counter[int] = Counter()
    for record in records:
        event_type = record.get("type_byte")
        length = record.get("length")
        group = record.get("group_id_candidate")
        if not isinstance(event_type, int) or not 0 <= event_type <= 0xFF:
            raise BandFormatError("event inventory contains an invalid type byte")
        if not isinstance(length, int) or length < 16 or length % 16:
            raise BandFormatError("event inventory contains an invalid atom-aligned record length")
        if not isinstance(group, int) or group < 0:
            raise BandFormatError("event inventory contains an invalid group candidate")
        by_type[event_type][length] += 1
        groups[event_type].add(group)
        if group == 0:
            zero_group_counts[event_type] += 1

    result = {}
    for event_type in sorted(by_type):
        result[f"0x{event_type:02x}"] = {
            "record_count": sum(by_type[event_type].values()),
            "record_lengths": {
                str(length): count for length, count in sorted(by_type[event_type].items())
            },
            "distinct_group_candidate_count": len(groups[event_type]),
            "zero_group_record_count": zero_group_counts[event_type],
            "semantics": "UNKNOWN unless independently documented",
        }
    return {
        "event_record_count": len(records),
        "event_types": result,
        "privacy_note": "Aggregate counts only; event bytes, names, and group values are omitted.",
    }


def probe_project(path: str | Path) -> dict[str, Any]:
    project = parse_band(path)
    events = project.project_data.get("event_sequences")
    if not isinstance(events, dict) or not isinstance(events.get("records"), list):
        raise BandFormatError("project has no validated event sequence records")
    return inventory_records(events["records"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="event_inventory")
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

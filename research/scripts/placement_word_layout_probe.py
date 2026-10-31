"""Audit placement word variation without requiring zero-valued prefix fields.

Counts are observations, not evidence that a word is fractional time. This
probe reads raw Logic Song metadata components and emits no raw field values.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from band2flp.parser import _parse_chunk_stream, _parse_event_sequences


def profile_records(records: list[dict]) -> dict:
    result = {}
    for label, event_type, markers in (
        ("audio", 0x24, (0x89, 0xBC, 0x8A, 0x89)),
        ("midi", 0x20, (0x89, 0x88, 0x8A, 0x88)),
    ):
        rows = []
        for record in records:
            raw = bytes.fromhex(record["raw_hex"])
            if len(raw) < 80 or raw[0] != event_type:
                continue
            if tuple(raw[i] for i in (0x17, 0x27, 0x37, 0x47)) == markers:
                rows.append(raw)
        result[label] = {
            "marker_selected_count": len(rows),
            "nonzero_byte_0x01_count": sum(raw[1] != 0 for raw in rows),
            "nonzero_word_0x02_count": sum(raw[2:4] != bytes(2) for raw in rows),
            "nonzero_word_0x1a_count": sum(raw[0x1A:0x1C] != bytes(2) for raw in rows),
            "zero_prefix_filter_exclusion_count": sum(raw[1:4] != bytes(3) for raw in rows),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("components", nargs="+", type=Path)
    args = parser.parse_args()
    reports = []
    for path in args.components:
        data = path.read_bytes()
        events = _parse_event_sequences(data, _parse_chunk_stream(data))
        reports.append(profile_records(events["records"]))
    print(json.dumps({"components_in_input_order": reports}, indent=2))


if __name__ == "__main__":
    main()

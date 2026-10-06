"""Profile the unconfirmed 0x24 event word at offset +0x1c without naming it."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from band2flp.parser import parse_band


SENTINEL = 0x3FFFFFFF
PPQ_CANDIDATE = 960


def profile_candidates(placements: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize +0x1c candidate shape without printing project values."""
    values = [
        item.get("u32_at_0x1c_candidate")
        for item in placements
        if isinstance(item.get("u32_at_0x1c_candidate"), int)
        and not isinstance(item.get("u32_at_0x1c_candidate"), bool)
    ]
    finite = [value for value in values if value != SENTINEL]
    nonzero = [value for value in finite if value != 0]
    return {
        "placement_count": len(placements),
        "candidate_count": len(values),
        "sentinel_count": sum(value == SENTINEL for value in values),
        "finite_nonzero_count": len(nonzero),
        "finite_values_on_960_tick_grid": sum(value % PPQ_CANDIDATE == 0 for value in nonzero),
        "interpretation": (
            "UNKNOWN; PPQ-grid alignment is a candidate only. Duration, endpoint, "
            "and sentinel semantics remain unresolved."
        ),
        "privacy_note": "Project paths, event values, track numbers, and media references are omitted.",
    }


def probe(path: str | Path) -> dict[str, Any]:
    project = parse_band(path)
    return profile_candidates(project.project_data.get("audio_placements", []))


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

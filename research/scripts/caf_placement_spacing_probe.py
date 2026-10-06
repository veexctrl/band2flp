"""Compare beat-tagged CAF sources with candidate audio-placement spacing."""

from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
from typing import Any

from band2flp.parser import parse_band


def profile_spacing(
    media_references: list[Any], placements: list[dict[str, Any]]
) -> dict[str, Any]:
    """Summarize phrase-spacing candidates without printing project values."""
    tagged = [
        reference for reference in media_references
        if reference.category == "AudioFiles"
        and isinstance(reference.source_loop_metadata, dict)
        and isinstance(reference.source_loop_metadata.get("beat_count"), int)
        and not isinstance(reference.source_loop_metadata.get("beat_count"), bool)
        and reference.source_loop_metadata["beat_count"] > 0
    ]
    linked_source_count = 0
    linked_placement_count = 0
    interval_count = 0
    phrase_interval_count = 0

    for reference in tagged:
        group = reference.group_id_candidate
        if group is None:
            continue
        linked = [
            placement for placement in placements
            if placement.get("media_group_id_candidate") == group
        ]
        if linked:
            linked_source_count += 1
        linked_placement_count += len(linked)
        starts: list[Fraction] = []
        for placement in linked:
            value = placement.get("start_beats")
            if not isinstance(value, str):
                continue
            try:
                starts.append(Fraction(value))
            except (ValueError, ZeroDivisionError):
                continue
        starts.sort()
        beat_count = reference.source_loop_metadata["beat_count"]
        for previous, current in zip(starts, starts[1:]):
            interval = current - previous
            interval_count += 1
            if interval > 0 and (interval / beat_count).denominator == 1:
                phrase_interval_count += 1

    return {
        "beat_tagged_source_count": len(tagged),
        "tagged_sources_with_linked_placements": linked_source_count,
        "linked_placement_count": linked_placement_count,
        "adjacent_start_interval_count": interval_count,
        "intervals_equal_integer_source_beat_count_multiples": phrase_interval_count,
        "interpretation": (
            "HYPOTHESIS: placement starts use an unvalidated timing conversion; "
            "spacing does not establish region length or loop behavior."
        ),
        "privacy_note": (
            "Project paths, source labels, identifiers, tag values, exact positions, "
            "and media bytes are omitted."
        ),
    }


def probe(path: str | Path) -> dict[str, Any]:
    project = parse_band(path)
    return profile_spacing(
        project.media_references,
        project.project_data.get("audio_placements", []),
    )


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

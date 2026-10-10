"""Compare songDuration with provisional MIDI region-end candidates.

This is a falsification probe only. Its output omits project paths, metadata
values, names, note values, and media references. The current PPQ and timing
fields remain hypotheses; no duration is assigned by the converter.
"""

from __future__ import annotations

import argparse
import json
from fractions import Fraction
from pathlib import Path
from typing import Any

from band2flp.parser import parse_band


def _fraction(value: Any) -> Fraction | None:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return None
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError):
        return None


def _close(left: float, right: float) -> bool:
    return abs(left - right) <= max(0.05, abs(right) * 0.01)


def profile(project: Any) -> dict[str, Any]:
    """Return only aggregate match counts for candidate MIDI boundaries."""
    summary = project.duration_value
    tempo = project.tempo_bpm
    regions = project.unplaced_midi_regions
    candidates: list[Fraction] = []
    regions_with_notes = 0

    for region in regions:
        start = _fraction(region.start_beats_candidate)
        if start is None:
            continue
        if region.notes:
            regions_with_notes += 1
            note_ends = [
                onset + duration
                for note in region.notes
                if (onset := _fraction(note.onset_beats_candidate)) is not None
                and (duration := _fraction(note.duration_beats_candidate)) is not None
            ]
            if note_ends:
                candidates.append(start + max(note_ends))

        extent_candidates = region.unknown.get("extent_candidates", {})
        for key in ("source_duration_beats_candidate", "placement_extent_beats_candidate"):
            extent = _fraction(extent_candidates.get(key))
            if extent is not None:
                candidates.append(start + extent)

    second_ends = [float(beats) * 60.0 / tempo for beats in candidates] if tempo else []
    seconds_match = bool(summary is not None and any(_close(value, summary) for value in second_ends))
    milliseconds_match = bool(
        summary is not None and any(_close(value * 1000.0, summary) for value in second_ends)
    )
    return {
        "has_summary": summary is not None,
        "has_tempo": tempo is not None,
        "midi_region_count": len(regions),
        "midi_regions_with_note_candidates": regions_with_notes,
        "candidate_boundary_count": len(candidates),
        "matches_seconds_within_tolerance": seconds_match,
        "matches_milliseconds_within_tolerance": milliseconds_match,
        "tolerance": "max(0.05 seconds, 1% of summary), applied to each hypothesis",
        "interpretation": (
            "No duration semantics inferred; both the 960-PPQ basis and MIDI boundary candidates remain hypotheses."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", nargs="+", type=Path, help="local .band project archives")
    args = parser.parse_args(argv)
    for index, path in enumerate(args.projects, 1):
        try:
            result = profile(parse_band(path))
        except Exception as exc:
            parser.error(f"fixture_{index} could not be inspected: {type(exc).__name__}")
        print(f"fixture_{index}: {json.dumps(result, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Aggregate ordering of note-shaped event position candidates by serialized order.

This probe reports only counts. The positions remain Logic-derived candidates;
it does not infer GarageBand timing semantics or normalize notes.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from band2flp.parser import BandFormatError, parse_band


def inventory_note_order(notes: list[dict[str, Any]]) -> dict[str, int]:
    """Count adjacent onset comparisons in event order, separately per group."""
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for note in notes:
        group_id = note.get("source_group_id_candidate")
        if not isinstance(group_id, int):
            continue
        if not all(isinstance(note.get(key), int) for key in (
            "source_chunk_index", "source_event_index", "position_raw", "position_fraction_raw"
        )):
            continue
        groups[group_id].append(note)

    counts: Counter[str] = Counter()
    for group_notes in groups.values():
        by_position: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for note in group_notes:
            by_position[(note["position_raw"], note["position_fraction_raw"])].append(note)
        for tied_notes in by_position.values():
            if len(tied_notes) < 2:
                continue
            counts["shared_onset_groups"] += 1
            counts["extra_events_at_shared_onsets"] += len(tied_notes) - 1
            pitches = [note.get("pitch_candidate") for note in tied_notes]
            if all(isinstance(pitch, int) for pitch in pitches):
                if len(set(pitches)) == len(pitches):
                    counts["distinct_pitch_shared_onsets"] += 1
                else:
                    counts["repeated_pitch_shared_onsets"] += 1
        ordered = sorted(group_notes, key=lambda note: (
            note["source_chunk_index"], note["source_event_index"]
        ))
        for left, right in zip(ordered, ordered[1:]):
            left_time = (left["position_raw"], left["position_fraction_raw"])
            right_time = (right["position_raw"], right["position_fraction_raw"])
            counts["adjacent_pairs"] += 1
            if left_time < right_time:
                counts["strictly_increasing"] += 1
                counts["nondecreasing"] += 1
            elif left_time == right_time:
                counts["ties"] += 1
                counts["nondecreasing"] += 1
            else:
                counts["decreases"] += 1
    return {"groups": len(groups), **{key: counts[key] for key in (
        "adjacent_pairs", "nondecreasing", "strictly_increasing", "ties", "decreases",
        "shared_onset_groups", "extra_events_at_shared_onsets",
        "distinct_pitch_shared_onsets", "repeated_pitch_shared_onsets",
    )}}


def probe_project(path: Path) -> dict[str, int]:
    project = parse_band(path)
    notes = project.project_data.get("midi_note_event_candidates")
    if not isinstance(notes, list):
        raise BandFormatError("project has no validated note-shaped event candidates")
    return inventory_note_order(notes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", nargs="+", type=Path, help="local .band project archives")
    args = parser.parse_args(argv)
    for fixture_index, path in enumerate(args.projects, 1):
        try:
            result = probe_project(path)
        except (BandFormatError, OSError, ValueError) as exc:
            parser.error(f"fixture {fixture_index}: {exc}")
        print(json.dumps({"fixture_index": fixture_index, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

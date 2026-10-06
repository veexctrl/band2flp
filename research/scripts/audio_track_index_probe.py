"""Summarize recovered audio placement track indices without project content."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from band2flp.parser import BandFormatError, parse_band


def profile_audio_track_indices(project: Any) -> dict[str, Any]:
    """Report index bounds and counts without track labels or region sources."""
    audio_tracks = [
        track for track in project.tracks
        if any(region.kind == "audio" for region in track.regions)
    ]
    indices = [track.index for track in audio_tracks]
    declared = project.declared_track_count
    return {
        "declared_track_count": declared,
        "audio_track_count": len(indices),
        "audio_region_count": sum(
            region.kind == "audio"
            for track in project.tracks
            for region in track.regions
        ),
        "audio_track_index_min": min(indices) if indices else None,
        "audio_track_index_max": max(indices) if indices else None,
        "all_audio_indices_below_declared_count": (
            bool(indices)
            and isinstance(declared, int)
            and all(isinstance(index, int) and 0 <= index < declared for index in indices)
        ),
        "privacy_note": "Track labels, region positions, identifiers, sources, and paths are omitted.",
    }


def probe(path: str | Path) -> dict[str, Any]:
    return profile_audio_track_indices(parse_band(path))


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

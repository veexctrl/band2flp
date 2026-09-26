"""Command line interface."""

from __future__ import annotations

import argparse
import json
import sys

from .parser import BandFormatError, parse_band


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="band2flp")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect = subparsers.add_parser("inspect", help="inspect a GarageBand project package")
    inspect.add_argument("project")
    inspect.add_argument("--json", action="store_true", help="emit the neutral model as JSON")
    args = parser.parse_args(argv)

    try:
        project = parse_band(args.project)
    except BandFormatError as exc:
        print(f"band2flp: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(project.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"Format: {project.source_format}")
        print(f"Package members: {len(project.package_members)}")
        print(f"Tempo: {project.tempo_bpm if project.tempo_bpm is not None else 'unknown'} BPM")
        meter = f"{project.time_signature[0]}/{project.time_signature[1]}" if project.time_signature else "unknown"
        print(f"Time signature: {meter}")
        duration = project.duration_value if project.duration_value is not None else "unknown"
        print(f"Reported duration: {duration} (unit not established)")
        print(f"Declared arrange tracks: {project.declared_track_count if project.declared_track_count is not None else 'unknown'}")
        print(f"Decoded tracks and regions: {sum(len(track.regions) for track in project.tracks)} regions")
        if project.project_data.get("opaque_data_objects"):
            sizes = [item["length"] for item in project.project_data["opaque_data_objects"]]
            print(f"Opaque data objects: {len(sizes)} ({sum(sizes)} bytes)")
        for warning in project.warnings:
            print(f"Warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

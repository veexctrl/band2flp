"""Command line interface."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

from .parser import BandFormatError, parse_band
from .media import MediaExtractionError, extract_referenced_audio
from .flp_export import FLPExportError, export_flp


def _print_json(value: object) -> None:
    """Emit standards-compliant JSON without relying on console Unicode support."""
    print(json.dumps(value, indent=2, ensure_ascii=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="band2flp")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect = subparsers.add_parser("inspect", help="inspect a GarageBand project package")
    inspect.add_argument("project")
    inspect.add_argument("--json", action="store_true", help="emit the neutral model as JSON")
    inspect.add_argument(
        "--groups", action="store_true",
        help="show chunks grouped by the opaque candidate group field",
    )
    extract_audio = subparsers.add_parser(
        "extract-audio", help="extract audio files explicitly referenced by a project"
    )
    extract_audio.add_argument("project", help="GarageBand .band package")
    extract_audio.add_argument("output_dir", help="new directory for the extracted audio files")
    extract_audio.add_argument(
        "--to-wav", action="store_true",
        help="transcode referenced audio to 16-bit PCM WAV with FFmpeg",
    )
    extract_audio.add_argument(
        "--transcoder", default="ffmpeg",
        help="FFmpeg executable name or path used with --to-wav (default: ffmpeg)",
    )
    export = subparsers.add_parser("export-flp", help="export recovered audio starts to an FL Studio project")
    export.add_argument("project", help="GarageBand .band package")
    export.add_argument("output", help="new FL Studio .flp output path")
    export.add_argument("--template", required=True, help="path to a blank FL Studio project template")
    export.add_argument("--media-dir", required=True, help="new directory for referenced audio used by the FLP")
    export.add_argument(
        "--to-wav", action="store_true",
        help="transcode referenced audio to 16-bit PCM WAV with FFmpeg before linking it",
    )
    export.add_argument(
        "--transcoder", default="ffmpeg",
        help="FFmpeg executable name or path used with --to-wav (default: ffmpeg)",
    )
    export.add_argument(
        "--length-policy", choices=("reject-unknown", "source-full"), default="reject-unknown",
        help="reject unknown region lengths, or use full source-file lengths as explicit placeholders",
    )
    args = parser.parse_args(argv)

    try:
        if args.command == "extract-audio":
            report = extract_referenced_audio(
                args.project,
                args.output_dir,
                to_wav=args.to_wav,
                transcoder=args.transcoder,
            )
            _print_json(report)
            return 0
        project = parse_band(args.project)
        if args.command == "export-flp":
            if args.length_policy == "reject-unknown" and any(
                region.kind == "audio" and region.duration_beats is None
                for track in project.tracks for region in track.regions
            ):
                raise FLPExportError(
                    "GarageBand audio region lengths are unknown; rerun with --length-policy source-full "
                    "to use full-source placeholders explicitly"
                )
            extraction = extract_referenced_audio(
                args.project,
                args.media_dir,
                to_wav=args.to_wav,
                transcoder=args.transcoder,
            )
            media_root = Path(args.media_dir).expanduser().resolve()
            media_by_reference = {
                entry["reference"]: media_root / entry["file"]
                for entry in extraction.get("extracted", [])
            }
            report = export_flp(
                project,
                template_path=args.template,
                output_path=args.output,
                media_by_reference=media_by_reference,
                length_policy=args.length_policy,
            )
            report["media_extraction"] = {
                "file_count": len(extraction.get("extracted", [])),
                "unresolved_reference_count": extraction.get("unresolved_audio_reference_count", 0),
            }
            _print_json(report)
            return 0
    except (BandFormatError, MediaExtractionError, FLPExportError, OSError) as exc:
        print(f"band2flp: {exc}", file=sys.stderr)
        return 2

    if args.json:
        _print_json(project.to_dict())
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
        placements = project.project_data.get("audio_placements", [])
        if placements:
            print(
                f"Audio placement events decoded: {len(placements)} "
                "(candidate beat starts; origin/PPQ transfer is preview-checked in one research fixture; region durations unknown)"
            )
            for track in project.tracks:
                for region in track.regions:
                    source_name = region.source.rsplit("/", 1)[-1] if region.source else "unknown source"
                    print(f"  Track {track.index + 1}: {region.name or source_name} at beat {region.start_beats}; source {source_name}")
        if project.media_references:
            embedded = sum(reference.package_member is not None for reference in project.media_references)
            print(f"Media references: {len(project.media_references)} ({embedded} matched to package members)")
            beat_tagged = sum(reference.source_loop_metadata is not None for reference in project.media_references)
            if beat_tagged:
                print(f"Beat-tagged CAF sources: {beat_tagged} (source metadata; arrangement looping unknown)")
        if project.project_data.get("opaque_data_objects"):
            sizes = [item["length"] for item in project.project_data["opaque_data_objects"]]
            print(f"Opaque data objects: {len(sizes)} ({sum(sizes)} bytes)")
        chunks = project.project_data.get("logic_song_chunk_stream")
        if chunks:
            print(f"Validated logic-song chunks: {chunks['chunk_count']}")
            top_types = sorted(chunks["type_counts"].items(), key=lambda item: (-item[1], item[0]))[:12]
            print("Chunk tags (top): " + ", ".join(f"{name}={count}" for name, count in top_types))
            if args.groups:
                grouped: dict[int, list[dict[str, object]]] = defaultdict(list)
                for chunk in chunks["chunks"]:
                    grouped[chunk["group_id_candidate"]].append(chunk)
                print("Chunk groups (candidate field; meaning unknown):")
                for group_id, group_chunks in sorted(grouped.items()):
                    counts = Counter(
                        chunk["type"] if chunk["type"] is not None else f"raw:{chunk['raw_type_hex']}"
                        for chunk in group_chunks
                    )
                    types = ", ".join(f"{tag}={count}" for tag, count in sorted(counts.items()))
                    indices = ",".join(str(chunk["index"]) for chunk in group_chunks)
                    chunk_word = "chunk" if len(group_chunks) == 1 else "chunks"
                    print(f"  0x{group_id:08X} ({len(group_chunks)} {chunk_word}): {types}")
                    print(f"    indices: {indices}")
        event_sequences = project.project_data.get("event_sequences")
        if event_sequences:
            print(f"Event records: {event_sequences['record_count']}")
        midi_candidates = project.project_data.get("midi_note_event_candidates", [])
        if midi_candidates:
            print(
                f"MIDI note-shaped events: {len(midi_candidates)} (field meanings and region/track associations are hypotheses)"
            )
        midi_placements = project.project_data.get("midi_region_placement_candidates", [])
        if midi_placements:
            linked = sum(len(item["candidate_mseq_chunk_indices"]) == 1 for item in midi_placements)
            print(
                f"MIDI region placement candidates: {len(midi_placements)} ({linked} uniquely linked to an MSeq group; track/timing semantics unconfirmed)"
            )
        if project.tempo_map:
            values = ", ".join(f"{item['bpm']:g} BPM @ raw {item['position_raw']}" for item in project.tempo_map)
            print(f"Group-zero tempo candidates: {values}")
        if project.time_signatures:
            values = ", ".join(f"{item['numerator']}/{item['denominator']} @ raw {item['position_raw']}" for item in project.time_signatures)
            print(f"Group-zero meter candidates: {values}")
        matches = project.project_data.get("audio_file_reference_matches", [])
        if matches:
            grouped = {index for match in matches for index in match["related_AuRg_chunk_indices"]}
            name_matched = {index for match in matches for index in match["name_matched_AuRg_chunk_indices"]}
            asset_values = project.project_data.get("assetsmetadata_plist", {}).get("values", {})
            references = asset_values.get("AudioFiles", []) if isinstance(asset_values, dict) else []
            print(f"Audio resource names matched in AuFl chunks: {len(matches)} of {len(references)}")
            print(f"Related AuRg chunks by shared header field: {len(grouped)}")
            print(f"Same-group AuRg chunks also matching audio filename stem: {len(name_matched)}")
        for warning in project.warnings:
            print(f"Warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


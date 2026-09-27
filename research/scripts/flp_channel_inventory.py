"""Compare audio-clip channel event shapes without exposing project data."""

from __future__ import annotations

import argparse
from collections import Counter
import enum
import json
from pathlib import Path
import warnings
from typing import Any

from band2flp.flp_export import FLPExportError, _pyflp_module


def _audio_clip_channels(project: Any, channel_id: Any) -> list[Any]:
    """Select type-4 channels with empty native-plugin names and a sample path."""
    result = []
    for channel in project.channels:
        type_event = next((event for event in channel.events if event.id == channel_id.Type), None)
        if (
            type_event is not None
            and int(type_event.value) == 4
            and channel.internal_name == ""
            and channel_id.SamplePath in channel.events.ids
        ):
            result.append(channel)
    return result


def _simple_scalar(value: Any) -> bool:
    if isinstance(value, enum.Enum):
        value = value.value
    return isinstance(value, (bool, int, float))


def compare_channel_shapes(candidate_path: str | Path, reference_root: str | Path, limit: int = 100) -> dict[str, Any]:
    """Return aggregate event-shape statistics; omit filenames, paths, and values."""
    if limit < 1:
        raise ValueError("reference limit must be positive")
    pyflp, _ = _pyflp_module()
    from pyflp.channel import ChannelID
    from pyflp.plugin import PluginID

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            candidate_project = pyflp.parse(str(Path(candidate_path)))
    except Exception as exc:
        raise FLPExportError(f"cannot parse candidate FLP: {type(exc).__name__}") from exc
    candidates = _audio_clip_channels(candidate_project, ChannelID)
    if not candidates:
        raise FLPExportError("candidate FLP contains no sample-backed audio-clip channels")

    candidate_order = tuple(int(event.id) for event in candidates[0].events)
    candidate_ids = set(candidate_order)
    candidate_signature_matches = sum(
        tuple(int(event.id) for event in channel.events) == candidate_order
        for channel in candidates
    )
    ref_projects = ref_parse_failures = ref_channels = order_matches = idset_matches = 0
    event_order_counts: Counter[tuple[int, ...]] = Counter()
    data_event_counts: Counter[str] = Counter()
    reference_event_ids: set[int] = set()
    comparable: dict[int, tuple[type, Any]] = {}
    dynamic = {
        int(ChannelID.New), int(ChannelID.Type), int(ChannelID.SamplerFlags),
        int(ChannelID.Polyphony), int(ChannelID.SamplePath),
        int(PluginID.InternalName), int(PluginID.Name),
    }
    for event in candidates[0].events:
        event_id = int(event.id)
        if event_id not in dynamic and _simple_scalar(event.value):
            comparable[event_id] = (type(event.value), event.value)
    scalar_presence: Counter[int] = Counter()
    scalar_matches: Counter[int] = Counter()
    plugin_data_id = int(PluginID.Data)

    root = Path(reference_root)
    if not root.is_dir():
        raise FLPExportError("reference root is not a directory")
    for path in sorted(root.rglob("*.flp")):
        if ref_projects >= limit:
            break
        ref_projects += 1
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                project = pyflp.parse(str(path))
        except Exception:
            ref_parse_failures += 1
            continue
        for channel in _audio_clip_channels(project, ChannelID):
            ref_channels += 1
            order = tuple(int(event.id) for event in channel.events)
            reference_event_ids.update(order)
            event_order_counts[order] += 1
            order_matches += order == candidate_order
            idset_matches += set(order) == candidate_ids
            data_event_counts["present" if plugin_data_id in channel.events.ids else "absent"] += 1
            if order != candidate_order:
                continue
            for event_id, (value_type, value) in comparable.items():
                event = next((event for event in channel.events if int(event.id) == event_id), None)
                if event is None:
                    continue
                scalar_presence[event_id] += 1
                if type(event.value) is value_type and event.value == value:
                    scalar_matches[event_id] += 1

    return {
        "candidate_audio_channel_count": len(candidates),
        "candidate_channels_matching_first_signature": candidate_signature_matches,
        "candidate_event_id_count": len(candidate_ids),
        "candidate_event_ids_seen_in_references": len(candidate_ids & reference_event_ids),
        "reference_projects_examined": ref_projects,
        "reference_parse_failures": ref_parse_failures,
        "reference_audio_channel_count": ref_channels,
        "exact_event_order_matches": order_matches,
        "exact_event_id_set_matches": idset_matches,
        "most_common_event_order_counts": sorted(event_order_counts.values(), reverse=True)[:8],
        "plugin_data_presence": dict(data_event_counts),
        "candidate_scalar_field_matches": {
            str(event_id): {"present": count, "equal": scalar_matches[event_id]}
            for event_id, count in sorted(scalar_presence.items())
        },
        "privacy_note": "Aggregate counts only; project names, paths, media paths, and field values are omitted.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path, help="Generated FLP to compare")
    parser.add_argument("reference_root", type=Path, help="Folder containing FLP references")
    parser.add_argument("--limit", type=int, default=100, help="Maximum references to parse (default: 100)")
    args = parser.parse_args(argv)
    try:
        result = compare_channel_shapes(args.candidate, args.reference_root, args.limit)
    except (FLPExportError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

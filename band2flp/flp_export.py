"""Optional PyFLP backend for exporting audio placement candidates."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from fractions import Fraction
import importlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import wave
from typing import Any

from .model import Project


class FLPExportError(ValueError):
    """An FLP cannot be safely generated from the supplied model and inputs."""


@dataclass(frozen=True)
class AudioInfo:
    frames: int
    sample_rate: int


def _select_base_playlist_record_layout(playlist: Any) -> None:
    """Use PyFLP's 32-byte base clip layout instead of inventing its newer tail."""
    params = getattr(playlist, "_kwds", None)
    if not isinstance(params, dict) or "new" not in params:
        raise FLPExportError("installed PyFLP cannot select the base playlist record layout")
    params["new"] = False


def _validate_clock_roundtrip(roundtrip: Any, project: Project) -> dict[str, Any]:
    """Verify project-level tempo and meter after FLP save/reload."""
    tempo = roundtrip.tempo
    signature = roundtrip.arrangements.time_signature
    actual_meter = (int(signature.num), int(signature.beat))
    tempo_matches = None
    meter_matches = None
    if project.tempo_bpm is not None:
        try:
            tempo_matches = math.isclose(float(tempo), float(project.tempo_bpm), rel_tol=0, abs_tol=0.0001)
        except (TypeError, ValueError, OverflowError):
            tempo_matches = False
        if not tempo_matches:
            raise FLPExportError("PyFLP round-trip changed or lost the project tempo")
    if project.time_signature is not None:
        meter_matches = actual_meter == project.time_signature
        if not meter_matches:
            raise FLPExportError("PyFLP round-trip changed or lost the project time signature")
    return {
        "tempo_bpm": tempo,
        "tempo_matches_input": tempo_matches,
        "time_signature": list(actual_meter),
        "time_signature_matches_input": meter_matches,
    }


def _beats_to_ticks(value: str, ppq: int, label: str) -> int:
    """Convert an exact beat string to ticks without an intermediate float."""
    try:
        return round(Fraction(value) * ppq)
    except (ValueError, ZeroDivisionError, TypeError, OverflowError) as exc:
        raise FLPExportError(f"an audio region {label} is not a finite beat value") from exc


def audio_info(path: str | Path) -> AudioInfo:
    """Read bounded WAVE or CAF timing metadata without decoding audio."""
    path = Path(path)
    if path.suffix.lower() in {".wav", ".wave"}:
        try:
            with wave.open(str(path), "rb") as source:
                frames, rate = source.getnframes(), source.getframerate()
        except (OSError, EOFError, wave.Error) as exc:
            raise FLPExportError(f"cannot read WAVE timing metadata: {path.name}") from exc
        if frames <= 0 or rate <= 0:
            raise FLPExportError(f"WAVE file has invalid frame or rate metadata: {path.name}")
        return AudioInfo(frames, rate)

    if path.suffix.lower() != ".caf":
        raise FLPExportError(f"audio timing probe supports WAVE and CAF only: {path.suffix or 'no extension'}")

    try:
        with path.open("rb") as source:
            header = source.read(1024 * 1024)
    except OSError as exc:
        raise FLPExportError(f"cannot read CAF timing metadata: {path.name}") from exc
    if not header.startswith(b"caff"):
        raise FLPExportError(f"invalid CAF header: {path.name}")

    offset = 8
    sample_rate: int | None = None
    frames: int | None = None
    while offset + 12 <= len(header):
        tag = header[offset:offset + 4]
        size = struct.unpack_from(">q", header, offset + 4)[0]
        offset += 12
        if size < 0:
            break
        if size > len(header) - offset:
            # The audio data is often larger than this metadata-only read.
            if tag == b"desc" and size >= 32 and offset + 32 <= len(header):
                sample_rate = round(struct.unpack_from(">d", header, offset)[0])
            elif tag == b"pakt" and size >= 24 and offset + 24 <= len(header):
                frames = struct.unpack_from(">q", header, offset + 8)[0]
            break
        if tag == b"desc" and size >= 32:
            sample_rate = round(struct.unpack_from(">d", header, offset)[0])
        elif tag == b"pakt" and size >= 24:
            frames = struct.unpack_from(">q", header, offset + 8)[0]
        offset += size

    if sample_rate is None or frames is None or sample_rate <= 0 or frames <= 0:
        raise FLPExportError(f"CAF lacks a supported sample rate or valid-frame count: {path.name}")
    return AudioInfo(frames, sample_rate)


def _pyflp_module() -> tuple[Any, bool]:
    try:
        pyflp = importlib.import_module("pyflp")
    except ImportError as exc:
        raise FLPExportError(
            "FLP export needs the optional PyFLP package; install pyflp==2.2.1 separately"
        ) from exc

    try:
        event_module = importlib.import_module("pyflp._events")
        event_enum = event_module.EventEnum
        version = importlib.metadata.version("pyflp")
    except (ImportError, importlib.metadata.PackageNotFoundError, AttributeError) as exc:
        raise FLPExportError("the installed PyFLP package is missing expected event metadata") from exc

    shim_used = False
    if sys.version_info >= (3, 12) and not event_enum._member_map_:
        if version != "2.2.1":
            raise FLPExportError(
                f"PyFLP {version} has an empty EventEnum base under Python {sys.version_info.major}.{sys.version_info.minor}; "
                "the compatibility shim is verified only for PyFLP 2.2.1"
            )
        # PyFLP 2.2.1 calls EventEnum(value) for unknown IDs. Python 3.12+
        # rejects calling an empty base Enum before its _missing_ handler runs.
        seed = int.__new__(event_enum, 256)
        seed._name_ = "_band2flp_compat_seed"
        seed._value_ = 256
        event_enum._member_map_[seed._name_] = seed
        event_enum._member_names_.append(seed._name_)
        event_enum._value2member_map_[256] = seed
        shim_used = True
    return pyflp, shim_used


def _atomic_publish(temp_path: Path, destination: Path) -> None:
    try:
        os.link(temp_path, destination)
    except FileExistsError as exc:
        raise FLPExportError(f"output already exists: {destination}") from exc
    except OSError as exc:
        raise FLPExportError(f"could not publish output without overwriting: {destination}") from exc
    temp_path.unlink()


def export_flp(
    project: Project,
    *,
    template_path: str | Path,
    output_path: str | Path,
    media_by_reference: dict[str, str | Path],
    length_policy: str = "reject-unknown",
) -> dict[str, Any]:
    """Export recovered audio starts using a user-supplied blank FLP template.

    ``source-full`` is an explicit approximation: when a GarageBand region has
    no known duration, the full source-file duration determines the FL clip
    length. No trim or loop information is inferred.
    """
    if length_policy not in {"reject-unknown", "source-full"}:
        raise FLPExportError("length policy must be 'reject-unknown' or 'source-full'")
    template = Path(template_path).expanduser().resolve()
    output = Path(output_path).expanduser().absolute()
    report_path = output.with_suffix(output.suffix + ".band2flp.json")
    if not template.is_file():
        raise FLPExportError("template FLP does not exist")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.is_symlink() or report_path.exists() or report_path.is_symlink():
        raise FLPExportError("FLP or report output already exists; choose new paths")

    regions = [region for track in project.tracks for region in track.regions if region.kind == "audio"]
    if not regions:
        raise FLPExportError("the neutral model contains no audio regions to export")
    if length_policy == "reject-unknown" and any(region.duration_beats is None for region in regions):
        raise FLPExportError(
            "one or more GarageBand audio durations are unknown; pass --length-policy source-full "
            "to export full-source placeholders explicitly"
        )

    reference_to_source = {
        ref.reference: ref for ref in project.media_references
        if ref.category == "AudioFiles"
    }
    source_paths: dict[str, Path] = {}
    source_info: dict[str, AudioInfo] = {}
    for region in regions:
        if not region.source or region.source not in reference_to_source:
            raise FLPExportError("an audio region has no resolved AudioFiles reference")
        if region.source_offset_beats not in (None, "0", "0.0"):
            raise FLPExportError("nonzero audio source offsets are not supported yet")
        reference = reference_to_source[region.source]
        candidate_path = media_by_reference.get(reference.reference)
        if candidate_path is None:
            raise FLPExportError("an audio region has no extracted media path")
        path = Path(candidate_path).expanduser().resolve()
        if reference.package_member is None or not path.is_file():
            raise FLPExportError("an audio region source is not uniquely embedded and extracted")
        source_paths[region.source] = path
        if region.source not in source_info:
            source_info[region.source] = audio_info(path)

    pyflp, shim_used = _pyflp_module()
    try:
        from pyflp._events import UnicodeEvent
        from pyflp.arrangement import ArrangementID, TrackID
        from pyflp.channel import ChannelID, ChannelType
        from pyflp.plugin import PluginID
    except ImportError as exc:
        raise FLPExportError("PyFLP does not expose the expected channel and playlist API") from exc

    try:
        fl_project = pyflp.parse(str(template))
    except Exception as exc:
        raise FLPExportError(f"PyFLP could not parse the supplied blank template: {type(exc).__name__}") from exc
    if len(fl_project.arrangements) != 1:
        raise FLPExportError("template must contain exactly one arrangement")
    arrangement = fl_project.arrangements[0]
    playlist = next((event for event in arrangement.events if event.id == ArrangementID.Playlist), None)
    if playlist is None or len(playlist):
        raise FLPExportError("template arrangement playlist must be empty")
    _select_base_playlist_record_layout(playlist)

    channels = list(fl_project.channels)
    if len(channels) != 1 or type(channels[0]).__name__ != "Sampler":
        raise FLPExportError("template must contain exactly one blank sampler channel")
    base_channel = channels[0]
    type_event = next((event for event in base_channel.events if event.id == ChannelID.Type), None)
    if type_event is None or PluginID.InternalName not in base_channel.events.ids:
        raise FLPExportError("template sampler lacks the channel type or internal-name events needed for audio clips")
    # FL Studio stores playlist audio clips as Instrument channels with an
    # empty native-plugin name; PyFLP then recognizes a loaded sample path as
    # an audio clip/Sampler model. A regular type-0 Sampler is not equivalent.
    type_event.value = ChannelType.Instrument
    base_channel.internal_name = ""
    base_events = [copy.deepcopy(event) for event in base_channel.events]
    unique_sources = list(dict.fromkeys(region.source for region in regions))
    source_iid: dict[str, int] = {}
    for iid, source in enumerate(unique_sources):
        name = f"Audio source {iid + 1:02d}"
        media_path = source_paths[source]
        sample_event = UnicodeEvent(
            ChannelID.SamplePath,
            str(media_path).encode("utf-16-le") + b"\0\0",
        )
        if iid == 0:
            channel = base_channel
            channel.name = name
            channel.events.insert(len(channel.events) - 1, sample_event)
        else:
            cloned = [copy.deepcopy(event) for event in base_events]
            for event in cloned:
                if event.id == ChannelID.New:
                    event.value = iid
                elif event.id == PluginID.Name:
                    event.value = name
            for event in cloned:
                fl_project.events.insert(len(fl_project.events) - 1, event)
            channel = next(channel for channel in fl_project.channels if channel.iid == iid)
            channel.name = name
            channel.events.insert(len(channel.events) - 1, sample_event)
        source_iid[source] = iid
    fl_project.channel_count = len(source_iid)

    if project.tempo_bpm is not None:
        fl_project.tempo = project.tempo_bpm
    if project.time_signature is not None:
        fl_project.arrangements.time_signature.num = project.time_signature[0]
        fl_project.arrangements.time_signature.beat = project.time_signature[1]

    track_models = {track.index: track for track in project.tracks}
    fl_tracks = list(arrangement.tracks)
    max_tracks = fl_project.arrangements.max_tracks
    if any(index < 0 or index >= max_tracks for index in track_models):
        raise FLPExportError("a recovered audio track index is outside the template playlist range")
    for index in sorted({track.index for track in project.tracks if any(r.kind == "audio" for r in track.regions)}):
        fl_tracks[index].events.insert(
            len(fl_tracks[index].events) - 1,
            UnicodeEvent(TrackID.Name, f"GarageBand Track {index + 1:02d}".encode("utf-16-le") + b"\0\0"),
        )

    ppq = fl_project.ppq
    exported_items: list[dict[str, Any]] = []
    for track in project.tracks:
        for region in track.regions:
            if region.kind != "audio":
                continue
            if region.start_beats is None:
                raise FLPExportError("an audio region has no recovered start position")
            start_ticks = _beats_to_ticks(region.start_beats, ppq, "start")
            if start_ticks < 0:
                raise FLPExportError("negative audio region starts are not supported")
            if region.duration_beats is not None:
                length_ticks = _beats_to_ticks(region.duration_beats, ppq, "duration")
            else:
                info = source_info[region.source]
                length_ticks = round(
                    Fraction(info.frames, info.sample_rate)
                    * Fraction(str(fl_project.tempo))
                    * ppq
                    / 60
                )
            length_ticks = max(1, length_ticks)
            iid = source_iid[region.source]
            playlist.append({
                "position": start_ticks,
                "pattern_base": 20480,
                "item_index": iid,
                "length": length_ticks,
                "track_rvidx": (max_tracks - 1) - track.index,
                "group": 0,
                "_u1": bytes((120, 0)),
                "item_flags": 64,
                "_u2": bytes((64, 100, 128, 128)),
                "start_offset": 0.0,
                "end_offset": 0.0,
                "_u3": None,
            })
            exported_items.append({
                "track_index": track.index,
                "start_beats": region.start_beats,
                "start_ticks": start_ticks,
                "length_ticks": length_ticks,
                "length_basis": "region-duration" if region.duration_beats is not None else "full-source-placeholder",
                "media_file": source_paths[region.source].name,
            })

    if length_policy == "source-full":
        comment = "Some audio clip lengths use full source files; GarageBand trim and loop lengths were not decoded."
        if fl_project.comments is not None:
            fl_project.comments = comment

    flp_tmp: Path | None = None
    report_tmp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".band2flp-", suffix=".flp", dir=output.parent, delete=False) as temp:
            flp_tmp = Path(temp.name)
        with tempfile.NamedTemporaryFile(prefix=".band2flp-", suffix=".json", dir=output.parent, delete=False) as temp:
            report_tmp = Path(temp.name)
        pyflp.save(fl_project, str(flp_tmp))
        roundtrip = pyflp.parse(str(flp_tmp))
        clock_report = _validate_clock_roundtrip(roundtrip, project)
        channels_by_iid = {channel.iid: channel for channel in roundtrip.channels}
        for iid in source_iid.values():
            channel = channels_by_iid.get(iid)
            if channel is None:
                raise FLPExportError("PyFLP round-trip lost an audio clip channel")
            type_event = next((event for event in channel.events if event.id == ChannelID.Type), None)
            if (
                type_event is None
                or type_event.value != ChannelType.Instrument
                or channel.sample_path is None
                or channel.internal_name != ""
            ):
                raise FLPExportError("PyFLP round-trip changed an FL Studio audio clip channel")
        roundtrip_playlist = next(
            event for event in roundtrip.arrangements[0].events
            if event.id == ArrangementID.Playlist
        )
        if len(roundtrip_playlist) != len(exported_items):
            raise FLPExportError("PyFLP round-trip changed the playlist item count")
        if getattr(roundtrip_playlist, "_struct_size", None) != 32:
            raise FLPExportError("PyFLP round-trip did not preserve base-size playlist records")
        for expected, actual in zip(exported_items, roundtrip_playlist):
            if actual["position"] != expected["start_ticks"] or actual["length"] != expected["length_ticks"]:
                raise FLPExportError("PyFLP round-trip changed a playlist position or length")
            if actual["item_index"] >= roundtrip.channel_count:
                raise FLPExportError("PyFLP round-trip left an audio clip without a channel")

        report = {
            "flp_version": str(roundtrip.version),
            **clock_report,
            "ppq": roundtrip.ppq,
            "audio_channels": roundtrip.channel_count,
            "playlist_items": len(exported_items),
            "playlist_record_size": roundtrip_playlist._struct_size,
            "duration_policy": length_policy,
            "compatibility_shim_used": shim_used,
            "project_warnings": list(project.warnings),
            "items": exported_items,
            "warnings": ([
                "Full-source placeholder lengths do not represent GarageBand trims, loops, or playback stretching."
            ] if length_policy == "source-full" else []),
        }
        report_tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
        _atomic_publish(flp_tmp, output)
        flp_tmp = None
        _atomic_publish(report_tmp, report_path)
        report_tmp = None
    except FLPExportError:
        raise
    except Exception as exc:
        raise FLPExportError(f"PyFLP could not build or validate the project: {type(exc).__name__}") from exc
    finally:
        for temp_path in (flp_tmp, report_tmp):
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass
    # Keep the machine-specific directory out of the JSON printed by the CLI.
    return {"output": output.name, "report": report_path.name, "summary": report}

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


def _fl_playlist_track_index(gb_track_index: int, max_tracks: int) -> int:
    """Map the recovered zero-based arrange index to FL's one-based playlist rows."""
    fl_index = gb_track_index + 1
    if gb_track_index < 0 or fl_index >= max_tracks:
        raise FLPExportError("a recovered audio track index is outside the template playlist range")
    return fl_index


def _fl_track_event_storage_index(fl_playlist_row: int, max_tracks: int) -> int:
    """Map a visible playlist row to PyFLP's track-event collection index."""
    storage_index = fl_playlist_row + 1
    if fl_playlist_row < 0 or storage_index >= max_tracks:
        raise FLPExportError("a recovered audio track index is outside the template playlist range")
    return storage_index


def _move_sample_path_after_pingpong(channel: Any, sample_event: Any, channel_id: Any) -> None:
    """Place SamplePath after PingPongLoop, as observed in sample-backed clips."""
    events = channel.events
    pingpong = next((event for event in events if event.id == channel_id.PingPongLoop), None)
    if pingpong is None:
        raise FLPExportError("audio clip channel lacks the PingPongLoop event needed for sample-path ordering")

    # EventTree.append cannot append to its sorted view, so first insert before
    # the final channel event, then move its index just after PingPongLoop.
    events.insert(len(events) - 1, sample_event)
    root = events.root
    sample_indexed = next(indexed for indexed in events.lst if indexed.e is sample_event)
    pingpong_indexed = next(indexed for indexed in events.lst if indexed.e is pingpong)
    for tree in (root, events):
        tree.lst.remove(sample_indexed)
    sample_indexed.r = pingpong_indexed.r + 0.5
    for tree in (root, events):
        tree.lst.add(sample_indexed)


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


def _pack_midi_note_candidate(
    position: int,
    duration: int,
    key: int,
    velocity: int,
    channel_iid: int,
) -> bytes:
    """Encode one editable FL note linked to its containing channel IID.

    FL Studio 25 requires the note flags word to include 0x4000 for notes
    created in a pattern to be editable rather than displayed as ghost notes.
    The flag meaning itself is not identified.
    """
    return struct.pack(
        "<IHHIHH8B",
        position, 0x4000, channel_iid, duration, key, 0,
        120, 0, 64, 0, 64, velocity, 128, 128,
    )


def _midi_candidate_display_name(region: Any, index: int) -> str:
    """Use an MSeq label as a provisional display label, never a track identity."""
    base = f"MIDI candidate {index + 1:02d}"
    label = getattr(region, "label_candidate", None)
    if not isinstance(label, str):
        return base
    label = " ".join(label.split())
    label = "".join(character for character in label if character.isprintable())[:80]
    return f"{base} - {label}" if label else base


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


def _validate_sample_path_roundtrip(actual_path: str | Path | None, expected_path: Path) -> None:
    """Reject a saved FLP whose audio channel points at a different source."""
    if actual_path is None or str(actual_path) != str(expected_path):
        raise FLPExportError("PyFLP round-trip changed an audio clip sample path")


def _flp_event_spans(data: bytes) -> list[tuple[int, int, int, int]]:
    """Return (ID, event start, payload start, event end) with bounded framing."""
    if len(data) < 22 or data[:4] != b"FLhd" or data[14:18] != b"FLdt":
        raise FLPExportError("invalid FLP header after serialization")
    if struct.unpack_from("<I", data, 18)[0] != len(data) - 22:
        raise FLPExportError("FLP event-data size differs from its header")
    spans = []
    offset = 22
    while offset < len(data):
        start = offset
        event_id = data[offset]
        offset += 1
        if event_id < 64:
            size = 1
        elif event_id < 128:
            size = 2
        elif event_id < 192:
            size = 4
        else:
            size = shift = 0
            for _ in range(10):
                if offset >= len(data):
                    raise FLPExportError("truncated FLP event size")
                byte = data[offset]
                offset += 1
                size |= (byte & 0x7f) << shift
                if not byte & 0x80:
                    break
                shift += 7
            else:
                raise FLPExportError("invalid FLP event size")
        payload_start = offset
        if size > len(data) - offset:
            raise FLPExportError("FLP event extends beyond its file")
        offset += size
        spans.append((event_id, start, payload_start, offset))
    return spans


def _place_audio_channels_before_playlist(data: bytes, expected_channels: int) -> bytes:
    """Move PyFLP-appended channel and pattern blocks before the playlist."""
    spans = _flp_event_spans(data)
    playlist = [i for i, span in enumerate(spans) if span[0] == 233]
    channels = [i for i, span in enumerate(spans) if span[0] == 64]
    if len(playlist) != 1 or len(channels) != expected_channels or not channels or channels[0] >= playlist[0]:
        raise FLPExportError("serialized FLP has an unexpected channel or playlist layout")
    if expected_channels == 1:
        return data
    if any(i < playlist[0] for i in channels[1:]) or spans[-1][0] != 47:
        raise FLPExportError("serialized FLP channel blocks do not match the supported template layout")
    base_paths = [i for i in range(channels[0], playlist[0]) if spans[i][0] == 196]
    if len(base_paths) > 1:
        raise FLPExportError("serialized base channel has multiple sample paths")
    insertion = spans[base_paths[0]][3] if base_paths else spans[playlist[0]][1]
    moved_start = spans[channels[1]][1]
    moved_end = spans[-1][1]
    if not insertion <= spans[playlist[0]][1] < moved_start < moved_end:
        raise FLPExportError("serialized channel move offsets are out of order")
    moved = data[moved_start:moved_end]
    result = data[:insertion] + moved + data[insertion:moved_start] + data[moved_end:]
    checked = _flp_event_spans(result)
    new_playlist = [i for i, span in enumerate(checked) if span[0] == 233]
    if len(result) != len(data) or len(new_playlist) != 1 or sum(
        span[0] == 64 for span in checked[:new_playlist[0]]
    ) != expected_channels:
        raise FLPExportError("serialized channel move failed validation")
    return result


def export_flp(
    project: Project,
    *,
    template_path: str | Path,
    output_path: str | Path,
    media_by_reference: dict[str, str | Path],
    length_policy: str = "reject-unknown",
    include_midi_candidates: bool = False,
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
    midi_regions = list(project.unplaced_midi_regions) if include_midi_candidates else []
    if not regions and not midi_regions:
        raise FLPExportError("the neutral model contains no supported audio or MIDI candidates to export")
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
        from pyflp._events import U16Event, U32Event, UnicodeEvent
        from pyflp.arrangement import ArrangementID, TrackID
        from pyflp.channel import ChannelID, ChannelType
        from pyflp.pattern import NotesEvent, PatternID
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
    midi_base_events = [copy.deepcopy(event) for event in base_channel.events]
    unique_sources = list(dict.fromkeys(region.source for region in regions))
    source_iid: dict[str, int] = {}
    if regions:
        type_event = next((event for event in base_channel.events if event.id == ChannelID.Type), None)
        if type_event is None or PluginID.InternalName not in base_channel.events.ids:
            raise FLPExportError("template sampler lacks the channel type or internal-name events needed for audio clips")
        # FL Studio stores playlist audio clips as Instrument channels with an
        # empty native-plugin name; PyFLP then recognizes a loaded sample path as an audio clip.
        type_event.value = ChannelType.Instrument
        base_channel.internal_name = ""
        sampler_flags = next((event for event in base_channel.events if event.id == ChannelID.SamplerFlags), None)
        if sampler_flags is None:
            raise FLPExportError("template sampler lacks the sample flags event needed for audio clips")
        sampler_flags.value = int(sampler_flags.value) & ~0x01
        polyphony = next((event for event in base_channel.events if event.id == ChannelID.Polyphony), None)
        if polyphony is None:
            raise FLPExportError("template sampler lacks the polyphony event needed for audio clips")
        polyphony.value["slide"] = 500
        base_events = [copy.deepcopy(event) for event in base_channel.events]
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
                _move_sample_path_after_pingpong(channel, sample_event, ChannelID)
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
                _move_sample_path_after_pingpong(channel, sample_event, ChannelID)
            source_iid[source] = iid
        fl_project.channel_count = len(source_iid)

    if project.tempo_bpm is not None:
        fl_project.tempo = project.tempo_bpm
    if project.time_signature is not None:
        fl_project.arrangements.time_signature.num = project.time_signature[0]
        fl_project.arrangements.time_signature.beat = project.time_signature[1]

    fl_tracks = list(arrangement.tracks)
    max_tracks = fl_project.arrangements.max_tracks
    for index in sorted({track.index for track in project.tracks if any(r.kind == "audio" for r in track.regions)}):
        fl_index = _fl_playlist_track_index(index, max_tracks)
        storage_index = _fl_track_event_storage_index(fl_index, max_tracks)
        fl_tracks[storage_index].events.insert(
            len(fl_tracks[storage_index].events) - 1,
            UnicodeEvent(TrackID.Name, f"GarageBand Track {index + 1:02d}".encode("utf-16-le") + b"\0\0"),
        )

    ppq = fl_project.ppq
    midi_preview_items: list[dict[str, Any]] = []
    if midi_regions:
        next_channel_iid = len(source_iid) if source_iid else max(channel.iid for channel in channels) + 1
        next_pattern_iid = max((pattern.iid for pattern in fl_project.patterns), default=0) + 1
        audio_rows = [
            _fl_playlist_track_index(track.index, max_tracks)
            for track in project.tracks if any(region.kind == "audio" for region in track.regions)
        ]
        first_midi_row = max(audio_rows, default=0) + 1
        for index, region in enumerate(midi_regions):
            use_template_channel = not regions and index == 0
            channel_iid = (
                0 if use_template_channel
                else next_channel_iid + index - (1 if not regions else 0)
            )
            pattern_iid = next_pattern_iid + index
            midi_name = _midi_candidate_display_name(region, index)
            if use_template_channel:
                midi_channel = base_channel
            else:
                channel_events = [
                    copy.deepcopy(event) for event in midi_base_events
                    if event.id != ChannelID.SamplePath
                ]
                for event in channel_events:
                    if event.id == ChannelID.New:
                        event.value = channel_iid
                    elif event.id == PluginID.Name:
                        event.value = midi_name
                    elif event.id == ChannelID.Type:
                        event.value = ChannelType.Sampler
                for event in channel_events:
                    fl_project.events.insert(len(fl_project.events) - 1, event)
                midi_channel = next(
                    (channel for channel in fl_project.channels if channel.iid == channel_iid), None
                )
            if midi_channel is None:
                raise FLPExportError("PyFLP did not create the provisional MIDI channel")
            midi_channel.name = midi_name

            note_records: list[bytes] = []
            note_positions: list[int] = []
            expected_notes: list[tuple[int, int, int, int, int, int]] = []
            for note in region.notes:
                key = int(note.pitch_candidate)
                velocity = int(note.velocity_candidate)
                if not 0 <= key <= 131 or not 0 <= velocity <= 127:
                    raise FLPExportError("a MIDI candidate pitch or velocity is outside FL Studio's supported range")
                position = _beats_to_ticks(note.onset_beats_candidate, ppq, "MIDI note onset")
                duration = max(1, _beats_to_ticks(note.duration_beats_candidate, ppq, "MIDI note duration"))
                if position < 0:
                    raise FLPExportError("negative MIDI note onsets are not supported")
                note_positions.append(position + duration)
                expected_notes.append((position, duration, key, velocity, channel_iid, 0x4000))
                note_records.append(_pack_midi_note_candidate(
                    position, duration, key, velocity, channel_iid
                ))
            if not note_records:
                continue
            raw_notes = b"".join(note_records)
            pattern_events = [
                U16Event(PatternID.New, struct.pack("<H", pattern_iid)),
                NotesEvent(PatternID.Notes, raw_notes),
                U16Event(PatternID.New, struct.pack("<H", pattern_iid)),
                UnicodeEvent(PatternID.Name, midi_name.encode("utf-16-le") + b"\0\0"),
                U32Event(PatternID.ChannelIID, struct.pack("<I", channel_iid)),
                U32Event(PatternID.Length, struct.pack("<I", max(note_positions))),
            ]
            for event in pattern_events:
                fl_project.events.insert(len(fl_project.events) - 1, event)

            playlist_row = first_midi_row + index
            if playlist_row >= max_tracks:
                raise FLPExportError("not enough empty FL Studio playlist tracks remain for MIDI candidates")
            storage_index = _fl_track_event_storage_index(playlist_row, max_tracks)
            fl_tracks[storage_index].events.insert(
                len(fl_tracks[storage_index].events) - 1,
                UnicodeEvent(TrackID.Name, midi_name.encode("utf-16-le") + b"\0\0"),
            )
            region_start = _beats_to_ticks(region.start_beats_candidate, ppq, "MIDI region start")
            if region_start < 0:
                raise FLPExportError("negative MIDI region starts are not supported")
            clip_length = max(note_positions)
            playlist.append({
                "position": region_start,
                "pattern_base": 20480,
                "item_index": 20480 + pattern_iid,
                "length": clip_length,
                "track_rvidx": (max_tracks - 1) - playlist_row,
                "group": 0,
                "_u1": bytes((120, 0)),
                "item_flags": 64,
                "_u2": bytes((64, 100, 128, 128)),
                "start_offset": -1.0,
                "end_offset": -1.0,
                "_u3": None,
            })
            midi_preview_items.append({
                "pattern_iid": pattern_iid,
                "channel_iid": channel_iid,
                "display_name": midi_name,
                "playlist_track_index": playlist_row,
                "position_ticks": region_start,
                "length_ticks": clip_length,
                "note_count": len(note_records),
                "_expected_notes": expected_notes,
                "source_mseq_chunk_index": region.source_mseq_chunk_index,
                "source_placement_chunk_index": region.source_placement_chunk_index,
                "source_placement_event_index": region.source_placement_event_index,
            })
        fl_project.channel_count = (
            len(source_iid) + len(midi_preview_items)
            if source_iid else len(channels) + max(0, len(midi_preview_items) - 1)
        )

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
                "track_rvidx": (max_tracks - 1) - _fl_playlist_track_index(track.index, max_tracks),
                "group": 0,
                "_u1": bytes((120, 0)),
                "item_flags": 64,
                "_u2": bytes((64, 100, 128, 128)),
                # Match the default clip-offset pair observed in
                # valid FL Studio audio playlist records.
                "start_offset": -1.0,
                "end_offset": -1.0,
                "_u3": None,
            })
            exported_items.append({
                "item_index": iid,
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
        expected_channel_count = (
            len(source_iid) + len(midi_preview_items)
            if source_iid else len(channels) + max(0, len(midi_preview_items) - 1)
        )
        flp_tmp.write_bytes(_place_audio_channels_before_playlist(flp_tmp.read_bytes(), expected_channel_count))
        roundtrip = pyflp.parse(str(flp_tmp))
        clock_report = _validate_clock_roundtrip(roundtrip, project)
        channels_by_iid = {channel.iid: channel for channel in roundtrip.channels}
        for source, iid in source_iid.items():
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
            _validate_sample_path_roundtrip(channel.sample_path, source_paths[source])
        roundtrip_playlist = next(
            event for event in roundtrip.arrangements[0].events
            if event.id == ArrangementID.Playlist
        )
        expected_playlist_count = len(exported_items) + len(midi_preview_items)
        if len(roundtrip_playlist) != expected_playlist_count:
            raise FLPExportError("PyFLP round-trip changed the playlist item count")
        if getattr(roundtrip_playlist, "_struct_size", None) != 32:
            raise FLPExportError("PyFLP round-trip did not preserve base-size playlist records")
        actual_playlist_by_index = {actual["item_index"]: actual for actual in roundtrip_playlist}
        expected_playlist_indices = {
            item["item_index"] for item in exported_items
        } | {
            20480 + item["pattern_iid"] for item in midi_preview_items
        }
        if set(actual_playlist_by_index) != expected_playlist_indices:
            raise FLPExportError("PyFLP round-trip changed the playlist item references")
        for expected in exported_items:
            actual = actual_playlist_by_index[expected["item_index"]]
            if actual["position"] != expected["start_ticks"] or actual["length"] != expected["length_ticks"]:
                raise FLPExportError("PyFLP round-trip changed a playlist position or length")
            if actual["item_index"] >= roundtrip.channel_count:
                raise FLPExportError("PyFLP round-trip left an audio clip without a channel")
        for expected in midi_preview_items:
            actual = actual_playlist_by_index[20480 + expected["pattern_iid"]]
            if (
                actual["position"] != expected["position_ticks"]
                or actual["length"] != expected["length_ticks"]
                or actual["item_index"] != 20480 + expected["pattern_iid"]
            ):
                raise FLPExportError("PyFLP round-trip changed a MIDI candidate playlist clip")
        patterns_by_iid = {pattern.iid: pattern for pattern in roundtrip.patterns}
        for expected in midi_preview_items:
            pattern = patterns_by_iid.get(expected["pattern_iid"])
            channel_iid_event = next(
                (event for event in pattern.events if event.id == PatternID.ChannelIID), None
            ) if pattern is not None else None
            if pattern is None or channel_iid_event is None or channel_iid_event.value != expected["channel_iid"]:
                raise FLPExportError("PyFLP round-trip lost a MIDI candidate pattern or channel link")
            notes = list(pattern.notes)
            if len(notes) != expected["note_count"]:
                raise FLPExportError("PyFLP round-trip changed a MIDI candidate note count")
            actual_notes = [
                (note.position, note.length, note["key"], note.velocity, note.rack_channel,
                 int(note["flags"]))
                for note in notes
            ]
            if actual_notes != expected["_expected_notes"]:
                raise FLPExportError("PyFLP round-trip changed MIDI candidate note data or channel assignment")

        report = {
            "flp_version": str(roundtrip.version),
            **clock_report,
            "ppq": roundtrip.ppq,
            "audio_channels": len(source_iid),
            "channel_count": roundtrip.channel_count,
            "midi_candidate_patterns": len(midi_preview_items),
            "playlist_items": expected_playlist_count,
            "playlist_record_size": roundtrip_playlist._struct_size,
            "duration_policy": length_policy,
            "compatibility_shim_used": shim_used,
            "project_warnings": list(project.warnings),
            "items": exported_items,
            "midi_candidates": [
                {key: value for key, value in item.items() if not key.startswith("_")}
                for item in midi_preview_items
            ],
            "warnings": ([
                "Full-source placeholder lengths do not represent GarageBand trims, loops, or playback stretching."
            ] if length_policy == "source-full" else []) + ([
                "MIDI candidate placement and note data are provisional; track assignment, velocity meaning, and instrument are unconfirmed."
            ] if midi_preview_items else []) + ([
                "MSeq text candidates are used as preview labels only; their role as a track or region name is unconfirmed."
            ] if any(" - " in item["display_name"] for item in midi_preview_items) else []),
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

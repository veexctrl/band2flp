"""Conservative package and metadata reader for GarageBand projects."""

from __future__ import annotations

import base64
import hashlib
import lzma
import math
import plistlib
import struct
import zipfile
import zlib
from datetime import date, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

from .model import MediaReference, MidiNoteCandidate, Project, Region, Track, UnplacedMidiRegionCandidate
from .caf import inspect_caf_loop_metadata

MAX_TOTAL_UNCOMPRESSED = 1_000_000_000
MAX_MEMBER_SIZE = 512_000_000


class BandFormatError(ValueError):
    """The input is not a readable GarageBand ZIP package."""


def _member_type(name: str, data: bytes) -> str:
    if name.endswith("projectData"):
        return "xml-plist"
    if name.endswith(".plist") or name.endswith("_cacheInfo"):
        return "binary-plist" if data.startswith(b"bplist") else "xml-plist"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    return "unknown"


def _find_member(names: list[str], suffix: str) -> str | None:
    matches = [name for name in names if name.endswith(suffix)]
    if len(matches) > 1:
        raise BandFormatError(f"ambiguous package member suffix: {suffix}")
    return matches[0] if matches else None


def _safe_plist(data: bytes, name: str) -> Any:
    try:
        return plistlib.loads(data)
    except Exception as exc:
        raise BandFormatError(f"cannot decode plist member {name!r}: {exc}") from exc


def _read_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    chunks: list[bytes] = []
    total = 0
    try:
        with archive.open(info) as stream:
            while True:
                chunk = stream.read(min(64 * 1024, MAX_MEMBER_SIZE - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_MEMBER_SIZE or total > info.file_size:
                    raise BandFormatError(f"decompressed member exceeds its declared size: {info.filename!r}")
                chunks.append(chunk)
    except (
        OSError, EOFError, zipfile.BadZipFile, RuntimeError,
        NotImplementedError, lzma.LZMAError, zlib.error,
    ) as exc:
        raise BandFormatError(f"cannot decompress package member {info.filename!r}: {exc}") from exc
    if total != info.file_size:
        raise BandFormatError(f"decompressed size does not match ZIP header: {info.filename!r}")
    return b"".join(chunks)


def _uid_index(value: Any) -> int | None:
    if isinstance(value, dict) and set(value) == {"CF$UID"}:
        index = value["CF$UID"]
        return index if isinstance(index, int) else None
    if isinstance(value, plistlib.UID):
        return value.data
    return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, plistlib.UID):
        return {"plist_uid": value.data}
    if isinstance(value, bytes):
        return {"base64": base64.b64encode(value).decode("ascii"), "length": len(value)}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _keyed_archive_summary(archive: Any) -> dict[str, Any]:
    if not isinstance(archive, dict) or not isinstance(archive.get("$objects"), list):
        return {"recognized": False, "format": "unrecognized plist root"}

    objects = archive["$objects"]
    class_names: list[str] = []
    for item in objects:
        if isinstance(item, dict) and isinstance(item.get("$classname"), str):
            class_names.append(item["$classname"])

    blobs: list[dict[str, Any]] = []
    for index, item in enumerate(objects):
        if isinstance(item, dict):
            data = item.get("NS.data")
            if isinstance(data, bytes):
                blobs.append({
                    "object_index": index,
                    "length": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "prefix_hex": data[:24].hex(),
                    # Retain the uninterpreted bytes so later format work can use them.
                    "base64": base64.b64encode(data).decode("ascii"),
                })

    top = archive.get("$top")
    top_keys = sorted(top) if isinstance(top, dict) else []
    return {
        "recognized": archive.get("$archiver") == "NSKeyedArchiver",
        "archiver": archive.get("$archiver"),
        "version": archive.get("$version"),
        "top_level_keys": top_keys,
        "class_names": class_names,
        "opaque_data_objects": blobs,
    }


def _archive_plist_with_blob_references(archive: dict[str, Any]) -> Any:
    """Preserve plist fields while keeping large NSData bytes in one JSON location."""
    objects = archive.get("$objects")
    if not isinstance(objects, list):
        return _json_safe(archive)
    safe_objects = []
    for index, item in enumerate(objects):
        if isinstance(item, dict) and isinstance(item.get("NS.data"), bytes):
            safe_item = {key: _json_safe(value) for key, value in item.items() if key != "NS.data"}
            blob = item["NS.data"]
            safe_item["NS.data"] = {
                "opaque_data_object_index": index,
                "length": len(blob),
                "sha256": hashlib.sha256(blob).hexdigest(),
            }
            safe_objects.append(safe_item)
        else:
            safe_objects.append(_json_safe(item))
    result = {key: _json_safe(value) for key, value in archive.items() if key != "$objects"}
    result["$objects"] = safe_objects
    return result


def _parse_chunk_stream(data: bytes) -> dict[str, Any]:
    """Split a validated Logic-family chunk stream while preserving raw headers."""
    if len(data) < 24 or data[:4] != bytes.fromhex("2347c0ab"):
        raise BandFormatError("logic-song data lacks the observed 24-byte chunk-stream header")
    chunks: list[dict[str, Any]] = []
    offset = 24
    while offset < len(data):
        remaining = len(data) - offset
        if remaining < 36:
            raise BandFormatError(f"truncated chunk header at logic-song offset {offset}")
        header = data[offset:offset + 36]
        payload_size = struct.unpack_from("<Q", header, 28)[0]
        if payload_size > remaining - 36:
            raise BandFormatError(f"chunk payload exceeds logic-song bounds at offset {offset}")
        raw_tag = header[:4]
        type_bytes = raw_tag[::-1]
        chunk_type = type_bytes.decode("ascii") if all(0x20 <= byte <= 0x7e for byte in type_bytes) else None
        payload_start = offset + 36
        chunks.append({
            "index": len(chunks),
            "offset": offset,
            "type": chunk_type,
            "raw_type_hex": raw_tag.hex(),
            "group_id_candidate": struct.unpack_from("<I", header, 8)[0],
            "opaque_header_fields_hex": header[4:28].hex(),
            "payload_size": payload_size,
            "payload_offset": payload_start,
            "header_hex": header.hex(),
        })
        offset = payload_start + payload_size
    if offset != len(data):
        raise BandFormatError("chunk stream does not end at the logic-song data boundary")
    counts: dict[str, int] = {}
    for chunk in chunks:
        label = chunk["type"] if chunk["type"] is not None else f"raw:{chunk['raw_type_hex']}"
        counts[label] = counts.get(label, 0) + 1
    return {
        "header_hex": data[:24].hex(),
        "header_size": 24,
        "chunk_header_size": 36,
        "payload_size_field": "unsigned 64-bit little-endian at chunk-header offset 28",
        "chunk_count": len(chunks),
        "end_offset": offset,
        "type_counts": counts,
        "chunks": chunks,
    }


def _match_audio_file_references(
    data: bytes, chunk_stream: dict[str, Any], assets: dict[str, Any]
) -> list[dict[str, Any]]:
    """Correlate literal audio basenames with UTF-16LE strings in AuFl chunks."""
    references = assets.get("AudioFiles")
    if not isinstance(references, list):
        return []
    chunks = chunk_stream["chunks"]
    file_chunks = [chunk for chunk in chunks if chunk["type"] == "AuFl"]
    matched: list[dict[str, Any]] = []
    for ref_index, reference in enumerate(references):
        if not isinstance(reference, str):
            continue
        basename = reference.rsplit("/", 1)[-1]
        needle = basename.encode("utf-16le")
        for chunk in file_chunks:
            start = chunk["payload_offset"]
            end = start + chunk["payload_size"]
            if needle not in data[start:end]:
                continue
            group_id = chunk["group_id_candidate"]
            related = [
                other["index"] for other in chunks
                if other["index"] != chunk["index"]
                and other["type"] == "AuRg"
                and other["group_id_candidate"] == group_id
            ]
            region_name = basename.rsplit(".", 1)[0]
            name_needle = region_name.encode("utf-8")
            name_matched = [
                other["index"] for other in chunks
                if other["index"] in related
                and any(
                    part == name_needle
                    for part in data[other["payload_offset"]:other["payload_offset"] + other["payload_size"]].split(b"\x00")
                )
            ]
            related_metadata = []
            for region_index in related:
                region_chunk = chunks[region_index]
                region_payload_start = region_chunk["payload_offset"]
                region_payload_end = region_payload_start + region_chunk["payload_size"]
                region_payload = data[region_payload_start:region_payload_end]
                related_metadata.append({
                    "chunk_index": region_index,
                    "payload_size": len(region_payload),
                    "filename_stem_matches": region_index in name_matched,
                    "payload_u32_at_0x06_candidate": (
                        struct.unpack_from("<I", region_payload, 0x06)[0]
                        if len(region_payload) >= 0x0A else None
                    ),
                    "payload_u32_at_0x16_candidate": (
                        struct.unpack_from("<I", region_payload, 0x16)[0]
                        if len(region_payload) >= 0x1A else None
                    ),
                    "payload_bytes_at_0x8a_candidate_hex": (
                        region_payload[0x8A:0x92].hex()
                        if len(region_payload) >= 0x92 else None
                    ),
                })
            matched.append({
                "asset_reference_index": ref_index,
                "asset_reference": reference,
                "chunk_index": chunk["index"],
                "chunk_offset": chunk["offset"],
                "group_id_candidate": group_id,
                "related_AuRg_chunk_indices": related,
                "name_matched_AuRg_chunk_indices": name_matched,
                "related_AuRg_metadata_candidates": related_metadata,
                "basename_encoding": "UTF-16LE",
                "region_name_match_encoding": "UTF-8 exact NUL-delimited string match",
                "confidence": "HIGH CONFIDENCE for literal AuFl basename match; same-group AuRg relationship is additionally checked against the filename stem when available",
            })
    return matched


def _mseq_label_candidates(data: bytes, chunk_stream: dict[str, Any]) -> list[dict[str, Any]]:
    """Preserve a length-framed MSeq string without assuming it names a track."""
    candidates: list[dict[str, Any]] = []
    for chunk in chunk_stream["chunks"]:
        if chunk["type"] != "MSeq":
            continue
        start, size = chunk["payload_offset"], chunk["payload_size"]
        payload = data[start:start + size]
        if len(payload) < 0x12:
            candidates.append({
                "chunk_index": chunk["index"],
                "group_id_candidate": chunk["group_id_candidate"],
                "status": "payload_too_short",
            })
            continue
        length = struct.unpack_from("<H", payload, 0x10)[0]
        raw = payload[0x12:0x12 + length]
        status = "empty" if length == 0 else "candidate"
        label: str | None = None
        if length > len(payload) - 0x12:
            status = "out_of_bounds"
        elif length > 0:
            try:
                decoded = raw.decode("utf-8")
            except UnicodeDecodeError:
                status = "invalid_utf8"
            else:
                if decoded.isprintable():
                    label = decoded
                else:
                    status = "nonprintable"
        candidates.append({
            "chunk_index": chunk["index"],
            "group_id_candidate": chunk["group_id_candidate"],
            "length_at_0x10_candidate": length,
            "text_at_0x12_candidate": label,
            "status": status,
            "interpretation": "HYPOTHESIS: MSeq label; track/region/instrument role unknown",
        })
    return candidates


def _link_mseq_labels_to_placements(
    placements: list[dict[str, Any]], labels: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Join already candidate-linked MSeq chunks to their framed text."""
    by_chunk = {item["chunk_index"]: item for item in labels}
    linked = []
    for placement in placements:
        candidates = [
            {
                "mseq_chunk_index": index,
                "text_candidate": by_chunk[index].get("text_at_0x12_candidate"),
                "status": by_chunk[index].get("status"),
            }
            for index in placement.get("candidate_mseq_chunk_indices", [])
            if index in by_chunk
        ]
        linked.append({
            **placement,
            "candidate_mseq_labels": candidates,
            "candidate_mseq_label_interpretation": (
                "HYPOTHESIS: same MSeq chunk as placement; label role and track mapping unknown"
            ),
        })
    return linked


def _media_references(
    assets: dict[str, Any], members: list[dict[str, Any]], audio_matches: list[dict[str, Any]]
) -> list[MediaReference]:
    match_by_index = {item["asset_reference_index"]: item for item in audio_matches}
    references: list[MediaReference] = []
    for category, values in assets.items():
        if not category.endswith("Files") or not isinstance(values, list):
            continue
        for index, reference in enumerate(values):
            if not isinstance(reference, str):
                continue
            basename = reference.rsplit("/", 1)[-1]
            member_matches = [item["path"] for item in members if item["path"].rsplit("/", 1)[-1] == basename]
            match = match_by_index.get(index) if category == "AudioFiles" else None
            references.append(MediaReference(
                index=index,
                category=category,
                reference=reference,
                package_member=member_matches[0] if len(member_matches) == 1 else None,
                source_chunk_index=match["chunk_index"] if match else None,
                group_id_candidate=match["group_id_candidate"] if match else None,
                related_region_chunk_indices=list(match["related_AuRg_chunk_indices"]) if match else [],
                name_matched_region_chunk_indices=list(match["name_matched_AuRg_chunk_indices"]) if match else [],
                region_chunk_metadata_candidates=list(match["related_AuRg_metadata_candidates"]) if match else [],
                unknown={"ambiguous_package_member_matches": member_matches} if len(member_matches) > 1 else {},
            ))
    return references


def _parse_event_sequences(data: bytes, chunk_stream: dict[str, Any]) -> dict[str, Any]:
    """Split 16-byte event atoms and retain all unknown event records verbatim."""
    records: list[dict[str, Any]] = []
    for chunk in chunk_stream["chunks"]:
        if chunk["type"] != "EvSq":
            continue
        start = chunk["payload_offset"]
        end = start + chunk["payload_size"]
        payload = data[start:end]
        if len(payload) % 16:
            raise BandFormatError(f"EvSq payload is not a whole number of 16-byte atoms at offset {chunk['offset']}")
        record_start: int | None = None
        event_index = 0
        for atom_offset in range(0, len(payload), 16):
            atom = payload[atom_offset:atom_offset + 16]
            if atom[7] & 0x80:
                if record_start is None:
                    raise BandFormatError(f"EvSq continuation atom has no preceding record at offset {chunk['offset'] + 36 + atom_offset}")
                continue
            if record_start is not None:
                raw = payload[record_start:atom_offset]
                records.append(_event_record(chunk, event_index, start, record_start, raw))
                event_index += 1
            record_start = atom_offset
        if record_start is not None:
            raw = payload[record_start:]
            records.append(_event_record(chunk, event_index, start, record_start, raw))

    event_counts: dict[str, int] = {}
    tempo_candidates: list[dict[str, Any]] = []
    meter_candidates: list[dict[str, Any]] = []
    for record in records:
        event_type = record["type_byte"]
        label = f"0x{event_type:02x}"
        event_counts[label] = event_counts.get(label, 0) + 1
        raw = bytes.fromhex(record["raw_hex"])
        if event_type == 0x60 and len(raw) >= 24 and raw[1] == 0 and raw[12:15] == b"\x7f\x00\x00" and raw[23] == 0x88:
            scaled_bpm = struct.unpack_from("<I", raw, 16)[0]
            if 0 < scaled_bpm <= 10_000_000:
                tempo_candidates.append({
                    "position_raw": struct.unpack_from("<I", raw, 4)[0],
                    "position_fraction_raw": struct.unpack_from("<H", raw, 2)[0],
                    "bpm": scaled_bpm / 10_000,
                    "bpm_raw": scaled_bpm,
                    "source_group_id_candidate": record["group_id_candidate"],
                    "source_chunk_index": record["chunk_index"],
                    "event_index": record["event_index"],
                    "raw_hex": record["raw_hex"],
                })
        elif event_type == 0x30 and len(raw) >= 24 and raw[1] == 0 and raw[8:11] == bytes(3) and raw[13:15] == bytes(2) and raw[16:18] == b"\x30\x00" and raw[23] == 0x88:
            denominator_power = raw[11]
            numerator = raw[12]
            if numerator > 0 and denominator_power <= 7:
                meter_candidates.append({
                    "position_raw": struct.unpack_from("<I", raw, 4)[0],
                    "position_fraction_raw": struct.unpack_from("<H", raw, 2)[0],
                    "numerator": numerator,
                    "denominator": 1 << denominator_power,
                    "source_group_id_candidate": record["group_id_candidate"],
                    "source_chunk_index": record["chunk_index"],
                    "event_index": record["event_index"],
                    "raw_hex": record["raw_hex"],
                })
    return {
        "atom_size": 16,
        "record_count": len(records),
        "event_type_counts": event_counts,
        "records": records,
        "tempo_candidates": tempo_candidates,
        "time_signature_candidates": meter_candidates,
    }


def _parse_audio_placements(event_sequences: dict[str, Any]) -> list[dict[str, Any]]:
    """Decode Logic-family audio placement events, retaining uncertain fields."""
    placements: list[dict[str, Any]] = []
    for record in event_sequences.get("records", []):
        if record.get("type_byte") != 0x24:
            continue
        raw = bytes.fromhex(record["raw_hex"])
        if len(raw) < 80 or raw[:4] != b"\x24\x00\x00\x00":
            continue
        # These two marker bytes match the published Logic placement record
        # and are present in all nine candidate placements in this fixture.
        if (raw[0x17], raw[0x27], raw[0x37], raw[0x47]) != (0x89, 0xBC, 0x8A, 0x89):
            continue
        position_raw = struct.unpack_from("<I", raw, 4)[0]
        position_origin_raw = 34_560
        ppq = 960
        placements.append({
            "source_chunk_index": record["chunk_index"],
            "source_event_index": record["event_index"],
            "source_group_id_candidate": record["group_id_candidate"],
            "event_id_candidate": struct.unpack_from("<I", raw, 0x10)[0],
            "position_raw": position_raw,
            "position_origin_raw": position_origin_raw,
            "position_ticks_from_origin": position_raw - position_origin_raw,
            "ppq_candidate": ppq,
            "start_beats": str(Fraction(position_raw - position_origin_raw, ppq)),
            "track_number_1_based_candidate": raw[0x14],
            "audio_link_candidate": struct.unpack_from("<I", raw, 0x2C)[0],
            "media_group_id_candidate": struct.unpack_from("<I", raw, 0x2C)[0] << 16,
            "bytes_at_0x28_candidate_hex": raw[0x28:0x30].hex(),
            "event_size": len(raw),
            "placement_record_size": 80,
            "trailing_u32_at_0_candidate": struct.unpack_from("<I", raw, 80)[0] if len(raw) >= 84 else None,
            "trailing_event_data_hex": raw[80:].hex(),
            "position_confidence": (
                "HYPOTHESIS for this project: Logic-derived 34,560 origin and 960 PPQ; "
                "preview agreement was observed in one research fixture only"
            ),
            "record_layout_confidence": "HYPOTHESIS transferred from Logic Pro and structurally corroborated in this GarageBand fixture",
            "u32_at_0x18_candidate": struct.unpack_from("<I", raw, 0x18)[0],
            "u32_at_0x18_interpretation": "UNKNOWN; preserved as a raw candidate, not used as duration or end position",
            "u32_at_0x1c_candidate": struct.unpack_from("<I", raw, 0x1C)[0],
            "u32_at_0x1c_interpretation": (
                "UNKNOWN; some finite values align to the candidate 960-PPQ grid and one matches a preview-measured extent; "
                "duration/end-position semantics and the 0x3FFFFFFF sentinel are unresolved; not used as duration"
            ),
        })
    return placements


def _parse_midi_note_candidates(
    event_sequences: dict[str, Any], chunk_stream: dict[str, Any]
) -> list[dict[str, Any]]:
    """Expose note-shaped event-family fields without assigning tracks/regions."""
    mseq_groups: dict[int, list[int]] = {}
    for chunk in chunk_stream.get("chunks", []):
        if chunk.get("type") == "MSeq":
            mseq_groups.setdefault(chunk["group_id_candidate"], []).append(chunk["index"])

    placements_by_mseq: dict[int, list[dict[str, int]]] = {}
    for placement in _parse_midi_region_placement_candidates(event_sequences, chunk_stream):
        for mseq_index in placement["candidate_mseq_chunk_indices"]:
            placements_by_mseq.setdefault(mseq_index, []).append({
                "source_chunk_index": placement["source_chunk_index"],
                "source_event_index": placement["source_event_index"],
                "position_raw": placement["position_raw"],
            })

    candidates: list[dict[str, Any]] = []
    for record in event_sequences.get("records", []):
        raw = bytes.fromhex(record["raw_hex"])
        # The observed 0x90..0x9e family shares this marker and candidate
        # field layout. These are not normalized MIDI notes without controlled
        # GarageBand note-edit fixtures.
        if len(raw) < 32 or not 0x90 <= raw[0] <= 0x9F or raw[0x17] != 0x89:
            continue
        group_id = record.get("group_id_candidate")
        mseq_indices = mseq_groups.get(group_id, [])
        placement_links = {
            (placement["source_chunk_index"], placement["source_event_index"])
            for mseq_index in mseq_indices
            for placement in placements_by_mseq.get(mseq_index, [])
        }
        position_raw = struct.unpack_from("<I", raw, 4)[0]
        duration_ticks = struct.unpack_from("<I", raw, 0x1C)[0]
        candidates.append({
            "source_chunk_index": record["chunk_index"],
            "source_event_index": record["event_index"],
            "source_group_id_candidate": group_id,
            "candidate_mseq_chunk_indices_for_group": mseq_indices,
            "candidate_midi_region_placements_for_group": [
                {"source_chunk_index": chunk_index, "source_event_index": event_index}
                for chunk_index, event_index in sorted(placement_links)
            ],
            "midi_region_link_interpretation": (
                "Candidate shared-MSeq link; note fields and GarageBand semantics remain unconfirmed"
            ),
            "event_size": len(raw),
            "event_type_byte": raw[0],
            "midi_channel_1_based_candidate": (raw[0] & 0x0F) + 1,
            "position_raw": position_raw,
            "position_fraction_raw": struct.unpack_from("<H", raw, 2)[0],
            "position_ticks_from_38400_candidate": position_raw - 38_400,
            "ppq_candidate": 960,
            "onset_beats_region_relative_candidate": str(Fraction(position_raw - 38_400, 960)),
            "fine_velocity_byte_candidate": raw[0x0A],
            "velocity_candidate": raw[0x0B],
            "pitch_candidate": raw[0x0C],
            "duration_ticks_candidate": duration_ticks,
            "duration_beats_candidate": str(Fraction(duration_ticks, 960)),
            "field_interpretation_confidence": "HYPOTHESIS transferred from Logic Pro; GarageBand note fixtures are not yet controlled",
            "position_scope_candidate": "unknown",
            "position_scope_confidence": "UNKNOWN; no unique linked placement comparison supports a scope yet",
            "raw_hex": record["raw_hex"],
        })

    candidates_by_group: dict[int, list[dict[str, Any]]] = {}
    for candidate in candidates:
        if isinstance(candidate["source_group_id_candidate"], int):
            candidates_by_group.setdefault(candidate["source_group_id_candidate"], []).append(candidate)
    for group_id, group_notes in candidates_by_group.items():
        mseq_indices = mseq_groups.get(group_id, [])
        linked_placements = {
            (placement["source_chunk_index"], placement["source_event_index"]): placement
            for mseq_index in mseq_indices
            for placement in placements_by_mseq.get(mseq_index, [])
        }
        if len(mseq_indices) != 1 or len(linked_placements) != 1:
            continue
        placement = next(iter(linked_placements.values()))
        # These origins/units come from Logic Pro and remain hypotheses in GB.
        region_start_ticks_candidate = placement["position_raw"] - 34_560
        note_absolute_ticks_candidates = [
            Fraction(note["position_ticks_from_38400_candidate"])
            + Fraction(note["position_fraction_raw"], 65_536)
            for note in group_notes
        ]
        if note_absolute_ticks_candidates and all(
            note_position < region_start_ticks_candidate
            for note_position in note_absolute_ticks_candidates
        ):
            for note in group_notes:
                note["position_scope_candidate"] = "region-relative"
                note["position_scope_confidence"] = (
                    "HYPOTHESIS for this group: every note position precedes its unique linked placement "
                    "under Logic-derived origins, so treating note positions as absolute would put them before the region"
                )
    return candidates


def _attach_unplaced_midi_region_candidates(project: Project) -> None:
    """Join uniquely linked note candidates without inventing arrange tracks."""
    placements = project.project_data.get("midi_region_placement_candidates", [])
    placement_by_location = {
        (item["source_chunk_index"], item["source_event_index"]): item
        for item in placements
    }
    grouped: dict[tuple[int, int, int], list[MidiNoteCandidate]] = {}
    for note in project.project_data.get("midi_note_event_candidates", []):
        mseq_links = note["candidate_mseq_chunk_indices_for_group"]
        placement_links = note["candidate_midi_region_placements_for_group"]
        if len(mseq_links) != 1 or len(placement_links) != 1:
            continue
        location = (
            placement_links[0]["source_chunk_index"],
            placement_links[0]["source_event_index"],
        )
        placement = placement_by_location.get(location)
        if placement is None or placement["candidate_mseq_chunk_indices"] != mseq_links:
            continue
        key = (mseq_links[0], *location)
        grouped.setdefault(key, []).append(MidiNoteCandidate(
            onset_beats_candidate=note["onset_beats_region_relative_candidate"],
            duration_beats_candidate=note["duration_beats_candidate"],
            pitch_candidate=note["pitch_candidate"],
            velocity_candidate=note["velocity_candidate"],
            channel_1_based_candidate=note["midi_channel_1_based_candidate"],
            source_chunk_index=note["source_chunk_index"],
            source_event_index=note["source_event_index"],
        ))
    regions: list[UnplacedMidiRegionCandidate] = []
    for (mseq_index, chunk_index, event_index), notes in grouped.items():
        placement = placement_by_location[(chunk_index, event_index)]
        labels = placement.get("candidate_mseq_labels", [])
        label = labels[0]["text_candidate"] if len(labels) == 1 and labels[0]["status"] == "candidate" else None
        notes.sort(key=lambda item: (Fraction(item.onset_beats_candidate), item.source_chunk_index, item.source_event_index))
        regions.append(UnplacedMidiRegionCandidate(
            start_beats_candidate=placement["start_beats_candidate"],
            label_candidate=label,
            notes=notes,
            source_mseq_chunk_index=mseq_index,
            source_placement_chunk_index=chunk_index,
            source_placement_event_index=event_index,
            unknown={
                "track_value_candidate": placement["track_value_candidate"],
                "confidence": "HYPOTHESIS for note timing, fields, label role, and placement track identity",
            },
        ))
    regions.sort(key=lambda item: (
        Fraction(item.start_beats_candidate),
        item.source_placement_chunk_index,
        item.source_placement_event_index,
    ))
    project.unplaced_midi_regions = regions


def _parse_midi_region_placement_candidates(
    event_sequences: dict[str, Any], chunk_stream: dict[str, Any]
) -> list[dict[str, Any]]:
    """Link Logic-shaped MIDI placements to MSeq chunks while preserving uncertainty."""
    mseq_groups: dict[int, list[int]] = {}
    trak_groups: dict[int, list[int]] = {}
    for chunk in chunk_stream.get("chunks", []):
        if chunk.get("type") == "MSeq":
            mseq_groups.setdefault(chunk["group_id_candidate"], []).append(chunk["index"])
        elif chunk.get("type") == "Trak":
            trak_groups.setdefault(chunk["group_id_candidate"], []).append(chunk["index"])

    placements: list[dict[str, Any]] = []
    for record in event_sequences.get("records", []):
        raw = bytes.fromhex(record["raw_hex"])
        if len(raw) < 80 or raw[:4] != b"\x20\x00\x00\x00":
            continue
        if (raw[0x17], raw[0x27], raw[0x37], raw[0x47]) != (0x89, 0x88, 0x8A, 0x88):
            continue
        region_cluster_candidate = struct.unpack_from("<I", raw, 0x20)[0]
        region_group_candidate = (region_cluster_candidate << 16) & 0xFFFFFFFF
        linked_mseq = mseq_groups.get(region_group_candidate, [])
        same_group_trak = trak_groups.get(region_group_candidate, [])
        position_raw = struct.unpack_from("<I", raw, 4)[0]
        placements.append({
            "source_chunk_index": record["chunk_index"],
            "source_event_index": record["event_index"],
            "event_size": len(raw),
            "event_id_candidate": struct.unpack_from("<I", raw, 0x10)[0],
            "position_raw": position_raw,
            "position_origin_raw_candidate": 34_560,
            "position_ticks_from_origin_candidate": position_raw - 34_560,
            "ppq_candidate": 960,
            "start_beats_candidate": str(Fraction(position_raw - 34_560, 960)),
            "track_value_candidate": raw[0x14],
            "region_cluster_candidate": region_cluster_candidate,
            "region_group_id_candidate": region_group_candidate,
            "candidate_mseq_chunk_indices": linked_mseq,
            "same_group_trak_chunk_indices_candidate": same_group_trak,
            "same_group_trak_confidence": (
                "HIGH CONFIDENCE for one same-group Trak chunk in inspected fixtures; semantics UNKNOWN"
                if len(same_group_trak) == 1 else "UNKNOWN; same-group Trak match is absent or ambiguous"
            ),
            "region_link_confidence": (
                "HIGH CONFIDENCE for a unique MSeq group match in this fixture"
                if len(linked_mseq) == 1 else "HYPOTHESIS; MSeq group match is absent or ambiguous"
            ),
            "position_confidence": "HYPOTHESIS transferred from Logic Pro; GarageBand position origin and units need controlled validation",
            "track_value_confidence": "UNKNOWN; preserved without a track-number or index interpretation",
            "raw_hex": record["raw_hex"],
        })
    return placements


def _unique_candidate_region_field_pairs(
    region_fields: list[bytes | None], placement_fields: list[bytes | None]
) -> list[tuple[int, int]]:
    """Keep unique nonzero field links and an anchored unique zero-valued slot.

    Zero is ambiguous in the inspected projects: it appears as repeated unset-like
    data in one fixture, but also as the first value in a complete one-to-one
    sequence in another. Only retain a zero pair when unique nonzero matches in
    the same source group provide an anchor.
    """
    width = 8
    valid_regions = [field if isinstance(field, bytes) and len(field) == width else None for field in region_fields]
    valid_placements = [field if isinstance(field, bytes) and len(field) == width else None for field in placement_fields]
    region_counts = {field: valid_regions.count(field) for field in set(valid_regions) if field is not None}
    placement_counts = {field: valid_placements.count(field) for field in set(valid_placements) if field is not None}

    pairs = [
        (region_index, placement_index)
        for region_index, field in enumerate(valid_regions)
        if field is not None and field != bytes(width)
        and region_counts[field] == 1 and placement_counts.get(field) == 1
        for placement_index, placement_field in enumerate(valid_placements)
        if placement_field == field
    ]
    zero_regions = [index for index, field in enumerate(valid_regions) if field == bytes(width)]
    zero_placements = [index for index, field in enumerate(valid_placements) if field == bytes(width)]
    if pairs and len(zero_regions) == 1 and len(zero_placements) == 1:
        pairs.append((zero_regions[0], zero_placements[0]))
    return sorted(pairs)


def _attach_audio_placements(project: Project, placements: list[dict[str, Any]]) -> None:
    """Create neutral audio tracks/regions from decoded placement candidates."""
    references = {
        reference.group_id_candidate: reference
        for reference in project.media_references
        if reference.category == "AudioFiles" and reference.group_id_candidate is not None
    }
    field_links_by_placement: dict[tuple[int, int], list[int]] = {}
    for group_id, reference in references.items():
        region_metadata = [
            item for item in reference.region_chunk_metadata_candidates
            if item.get("filename_stem_matches") and isinstance(item.get("chunk_index"), int)
        ]
        source_placements = [
            item for item in placements if item.get("media_group_id_candidate") == group_id
        ]
        region_fields = [
            bytes.fromhex(value)
            if isinstance(value, str) and len(value) == 16 else None
            for value in (
                item.get("payload_bytes_at_0x8a_candidate_hex") for item in region_metadata
            )
        ]
        placement_fields = [
            bytes.fromhex(value)
            if isinstance(value, str) and len(value) == 16 else None
            for value in (
                item.get("bytes_at_0x28_candidate_hex") for item in source_placements
            )
        ]
        for region_index, placement_index in _unique_candidate_region_field_pairs(
            region_fields, placement_fields
        ):
            placement = source_placements[placement_index]
            identity = (placement.get("source_chunk_index"), placement.get("source_event_index"))
            if all(isinstance(value, int) for value in identity):
                field_links_by_placement.setdefault(identity, []).append(
                    region_metadata[region_index]["chunk_index"]
                )
    tracks: dict[int, Track] = {}
    for placement in placements:
        track_number = placement["track_number_1_based_candidate"]
        if not isinstance(track_number, int) or track_number < 1:
            continue
        track_index = track_number - 1
        track = tracks.setdefault(track_index, Track(
            index=track_index,
            kind="audio",
            unknown={"garageband_track_number_1_based_candidate": track_number},
        ))
        reference = references.get(placement["media_group_id_candidate"])
        stem = reference.reference.rsplit("/", 1)[-1].rsplit(".", 1)[0] if reference else None
        region_chunk_indices = list(reference.name_matched_region_chunk_indices) if reference else []
        region_metadata = list(reference.region_chunk_metadata_candidates) if reference else []
        suffix_value = placement["trailing_u32_at_0_candidate"]
        suffix_matches = [
            item["chunk_index"] for item in region_metadata
            if suffix_value is not None
            and item["payload_u32_at_0x16_candidate"] == suffix_value
            and item["filename_stem_matches"]
        ]
        identity = (placement.get("source_chunk_index"), placement.get("source_event_index"))
        field_matches = field_links_by_placement.get(identity, [])
        track.regions.append(Region(
            name=stem,
            start_beats=placement["start_beats"],
            kind="audio",
            source=reference.reference if reference else None,
            unknown={
                "placement": placement,
                "candidate_region_chunk_indices_for_source": region_chunk_indices,
                "candidate_region_chunk_metadata_for_source": region_metadata,
                "region_chunk_indices_matching_trailing_u32_candidate": suffix_matches,
                "region_chunk_indices_matching_0x8a_to_0x28_candidate": field_matches,
                "region_chunk_field_link_confidence": (
                    "HYPOTHESIS; exact eight-byte equality linked unique nonzero pairs in one fixture "
                    "and a unique zero-valued pair when anchored by them; zero-only groups did not link"
                ),
                "duration": "unknown",
                "region_chunk_to_placement_ordinal": "unknown",
            },
        ))
    project.tracks = [tracks[index] for index in sorted(tracks)]


_MIDI_CHANNEL_VOICE_FAMILIES = {
    0x80: "note_off",
    0x90: "note_on",
    0xA0: "polyphonic_key_pressure",
    0xB0: "control_change",
    0xC0: "program_change",
    0xD0: "channel_pressure",
    0xE0: "pitch_bend",
}


def _event_record(chunk: dict[str, Any], event_index: int, payload_start: int, relative_start: int, raw: bytes) -> dict[str, Any]:
    record = {
        "chunk_index": chunk["index"],
        "chunk_offset": chunk["offset"],
        "group_id_candidate": chunk["group_id_candidate"],
        "event_index": event_index,
        "offset": payload_start + relative_start,
        "type_byte": raw[0],
        "length": len(raw),
        "raw_hex": raw.hex(),
    }
    family = _MIDI_CHANNEL_VOICE_FAMILIES.get(raw[0] & 0xF0)
    if family is not None:
        record["midi_status_candidate"] = {
            "family": family,
            "channel_1_based": (raw[0] & 0x0F) + 1,
            "confidence": "HYPOTHESIS: first record byte matches a MIDI 1.0 channel-voice status; wrapper fields are not decoded",
        }
    return record


def parse_band(path: str | Path) -> Project:
    """Read package inventory and high-confidence summary metadata.

    The parser intentionally does not infer arrangement records from opaque data.
    """
    path = Path(path)
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise BandFormatError(f"not a readable .band ZIP package: {path}") from exc

    with archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)):
            raise BandFormatError("package contains duplicate member names")
        total_size = sum(item.file_size for item in infos)
        if total_size > MAX_TOTAL_UNCOMPRESSED:
            raise BandFormatError("package exceeds the uncompressed size limit")
        if any(item.file_size > MAX_MEMBER_SIZE for item in infos):
            raise BandFormatError("package member exceeds the size limit")

        project = Project()
        project.package_members = []
        logic_payload: bytes | None = None
        info_by_name = {item.filename: item for item in infos}
        for item in infos:
            if item.flag_bits & 1:
                raise BandFormatError(f"encrypted package member is unsupported: {item.filename!r}")
            try:
                with archive.open(item) as stream:
                    prefix = stream.read(8)
            except (
                OSError, EOFError, zipfile.BadZipFile, RuntimeError,
                NotImplementedError, lzma.LZMAError, zlib.error,
            ) as exc:
                raise BandFormatError(f"cannot read package member {item.filename!r}: {exc}") from exc
            project.package_members.append({
                "path": item.filename,
                "size": item.file_size,
                "compressed_size": item.compress_size,
                "compression_method": item.compress_type,
                "crc32": f"{item.CRC:08x}",
                "kind": _member_type(item.filename, prefix),
            })

        pd_name = _find_member(names, "/projectData")
        if pd_name is None:
            project.warnings.append("No projectData member was found.")
        else:
            root = _safe_plist(_read_member(archive, info_by_name[pd_name]), pd_name)
            if isinstance(root, dict) and isinstance(root.get("$objects"), list):
                objects = root["$objects"]
                logic_uid = _uid_index(root.get("$top", {}).get("DfDocument logic model")) if isinstance(root.get("$top"), dict) else None
                logic_object = objects[logic_uid] if logic_uid is not None and 0 <= logic_uid < len(objects) else None
                song_uid = _uid_index(logic_object.get("DfLogicModelLogicSong")) if isinstance(logic_object, dict) else None
                song_object = objects[song_uid] if song_uid is not None and 0 <= song_uid < len(objects) else None
                project.project_data = {
                    **_keyed_archive_summary(root),
                    "keyed_archive_plist": {
                        "source_member": pd_name,
                        "archive": _archive_plist_with_blob_references(root),
                        "blob_reference_note": "NSData bytes are stored once in opaque_data_objects and referenced by object_index here.",
                    },
                    "logic_song_object_index": song_uid,
                    "logic_song_has_opaque_data": isinstance(song_object, dict) and isinstance(song_object.get("NS.data"), bytes),
                }
                if isinstance(song_object, dict) and isinstance(song_object.get("NS.data"), bytes):
                    logic_payload = song_object["NS.data"]
                    try:
                        project.project_data["logic_song_chunk_stream"] = _parse_chunk_stream(song_object["NS.data"])
                    except BandFormatError as exc:
                        project.warnings.append(f"Logic-song chunk stream was not decoded: {exc}")
                    else:
                        project.project_data["mseq_label_candidates"] = _mseq_label_candidates(
                            logic_payload, project.project_data["logic_song_chunk_stream"]
                        )
                        try:
                            events = _parse_event_sequences(logic_payload, project.project_data["logic_song_chunk_stream"])
                        except BandFormatError as exc:
                            project.warnings.append(f"EvSq events were not decoded: {exc}")
                        else:
                            project.project_data["event_sequences"] = events
                            project.project_data["audio_placements"] = _parse_audio_placements(events)
                            project.project_data["midi_note_event_candidates"] = _parse_midi_note_candidates(
                                events, project.project_data["logic_song_chunk_stream"]
                            )
                            project.project_data["midi_region_placement_candidates"] = _link_mseq_labels_to_placements(
                                _parse_midi_region_placement_candidates(
                                    events, project.project_data["logic_song_chunk_stream"]
                                ),
                                project.project_data["mseq_label_candidates"],
                            )
                        project.warnings.append(
                            "Chunk boundaries are validated for this logic-song payload; most chunk and event meanings remain unverified."
                        )
                project.warnings.append(
                    "Logic-song payload is retained as opaque bytes; MIDI placements, note fields, and their region/track associations remain candidates, while audio-region durations and track names/settings remain unknown."
                )
            else:
                project.project_data = {"recognized": False, "format": "unrecognized plist root"}
                project.warnings.append("projectData plist is not a recognized keyed archive.")

        meta_name = _find_member(names, "Output/metadata.plist")
        if meta_name is not None:
            metadata = _safe_plist(_read_member(archive, info_by_name[meta_name]), meta_name)
            if isinstance(metadata, dict):
                project.tempo_bpm = _number(metadata.get("com_apple_garageband_metadata_songTempo"))
                numerator = _integer(metadata.get("com_apple_garageband_metadata_songSignatureNominator"))
                denominator = _integer(metadata.get("com_apple_garageband_metadata_songSignatureDeNominator"))
                if numerator and denominator:
                    project.time_signature = (numerator, denominator)
                project.duration_value = _number(metadata.get("com_apple_garageband_metadata_songDuration"))
                project.declared_track_count = _integer(metadata.get("com_apple_garageband_metadata_numberOfArrangeTracks"))
                project.project_data["metadata_plist"] = {
                    "source_member": meta_name,
                    "tempo_key": "com_apple_garageband_metadata_songTempo",
                    "time_signature_keys": [
                        "com_apple_garageband_metadata_songSignatureNominator",
                        "com_apple_garageband_metadata_songSignatureDeNominator",
                    ],
                    "duration_key": "com_apple_garageband_metadata_songDuration",
                    "duration_unit": "unknown",
                    "arrange_track_count_key": "com_apple_garageband_metadata_numberOfArrangeTracks",
                    "values": _json_safe(metadata),
                }
                if project.duration_value is not None:
                    project.warnings.append("songDuration's numeric unit and duration semantics are not validated yet.")
        else:
            project.warnings.append("Output metadata.plist was not found; tempo and meter are unavailable.")

        assets_name = _find_member(names, "Output/assetsmetadata.plist")
        if assets_name is not None:
            assets = _safe_plist(_read_member(archive, info_by_name[assets_name]), assets_name)
            if isinstance(assets, dict):
                project.project_data["assetsmetadata_plist"] = {
                    "source_member": assets_name,
                    "values": _json_safe(assets),
                }
                chunk_stream = project.project_data.get("logic_song_chunk_stream")
                audio_matches: list[dict[str, Any]] = []
                if logic_payload is not None and isinstance(chunk_stream, dict):
                    audio_matches = _match_audio_file_references(
                        logic_payload, chunk_stream, assets
                    )
                    project.project_data["audio_file_reference_matches"] = audio_matches
                project.media_references = _media_references(assets, project.package_members, audio_matches)
                loop_metadata_by_member: dict[str, dict[str, object] | None] = {}
                for reference in project.media_references:
                    member = reference.package_member
                    if reference.category != "AudioFiles" or member is None or not member.lower().endswith(".caf"):
                        continue
                    if member not in loop_metadata_by_member:
                        try:
                            with archive.open(info_by_name[member]) as source:
                                loop_metadata_by_member[member] = inspect_caf_loop_metadata(source)
                        except (
                            OSError, EOFError, zipfile.BadZipFile, RuntimeError,
                            NotImplementedError, lzma.LZMAError, zlib.error,
                        ) as exc:
                            project.warnings.append(f"Could not inspect CAF metadata in {member!r}: {exc}")
                            loop_metadata_by_member[member] = None
                    reference.source_loop_metadata = loop_metadata_by_member[member]
                asset_track_count = _integer(assets.get("NumberOfTracks"))
                if asset_track_count is not None and project.declared_track_count is not None and asset_track_count != project.declared_track_count:
                    project.warnings.append(
                        "The asset plist and output metadata report different track counts; their definitions are unknown."
                    )
                project.warnings.append(
                    "Asset plist resource lists are preserved as references; placement is established only where arrangement events link a resource."
                )

        if project.declared_track_count is not None:
            project.warnings.append(
                "Arrange-track count comes from summary metadata; only tracks with recognized audio placement events are represented."
            )
        event_sequences = project.project_data.get("event_sequences")
        if isinstance(event_sequences, dict):
            global_tempo = [item for item in event_sequences["tempo_candidates"] if item["source_group_id_candidate"] == 0]
            global_meter = [item for item in event_sequences["time_signature_candidates"] if item["source_group_id_candidate"] == 0]
            project.tempo_map = [
                {
                    **item,
                    "position_unit": "unknown",
                    "matches_summary": project.tempo_bpm is not None and math.isclose(item["bpm"], project.tempo_bpm, rel_tol=0, abs_tol=0.0001),
                    "confidence": "HIGH CONFIDENCE" if project.tempo_bpm is not None and math.isclose(item["bpm"], project.tempo_bpm, rel_tol=0, abs_tol=0.0001) else "HYPOTHESIS",
                }
                for item in global_tempo
            ]
            project.time_signatures = [
                {
                    **item,
                    "position_unit": "unknown",
                    "matches_summary": project.time_signature == (item["numerator"], item["denominator"]),
                    "confidence": "HIGH CONFIDENCE" if project.time_signature == (item["numerator"], item["denominator"]) else "HYPOTHESIS",
                }
                for item in global_meter
            ]
            if any(item["source_group_id_candidate"] != 0 for item in event_sequences["tempo_candidates"]):
                project.warnings.append("Nonzero-group tempo candidates are preserved separately; their scope is unknown.")
        _attach_audio_placements(project, project.project_data.get("audio_placements", []))
        _attach_unplaced_midi_region_candidates(project)
        if project.project_data.get("audio_placements"):
            project.warnings.append(
                "Audio placement starts are beat candidates using a Logic-derived 34,560 origin and 960 PPQ; "
                "preview agreement was observed in one research fixture, not validated for this project."
            )
            project.warnings.append(
                "Audio track indices use an unconfirmed one-based event field; one research preview supports row grouping, "
                "but the mapping has not been validated for this project."
            )
        return project


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None

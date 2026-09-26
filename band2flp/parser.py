"""Conservative package and metadata reader for GarageBand projects."""

from __future__ import annotations

import base64
import hashlib
import math
import plistlib
import struct
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .model import Project

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
    except (OSError, EOFError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
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
            matched.append({
                "asset_reference_index": ref_index,
                "asset_reference": reference,
                "chunk_index": chunk["index"],
                "chunk_offset": chunk["offset"],
                "group_id_candidate": group_id,
                "related_AuRg_chunk_indices": related,
                "basename_encoding": "UTF-16LE",
                "confidence": "HIGH CONFIDENCE for literal basename match; group relationship is not yet semantically confirmed",
            })
    return matched


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


def _event_record(chunk: dict[str, Any], event_index: int, payload_start: int, relative_start: int, raw: bytes) -> dict[str, Any]:
    return {
        "chunk_index": chunk["index"],
        "chunk_offset": chunk["offset"],
        "group_id_candidate": chunk["group_id_candidate"],
        "event_index": event_index,
        "offset": payload_start + relative_start,
        "type_byte": raw[0],
        "length": len(raw),
        "raw_hex": raw.hex(),
    }


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
            except (OSError, EOFError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
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
                        try:
                            events = _parse_event_sequences(logic_payload, project.project_data["logic_song_chunk_stream"])
                        except BandFormatError as exc:
                            project.warnings.append(f"EvSq events were not decoded: {exc}")
                        else:
                            project.project_data["event_sequences"] = events
                        project.warnings.append(
                            "Chunk boundaries are validated for this logic-song payload; most chunk and event meanings remain unverified."
                        )
                project.warnings.append(
                    "Logic-song payload is retained as opaque bytes; region, note, and track records are not decoded."
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
                if logic_payload is not None and isinstance(chunk_stream, dict):
                    project.project_data["audio_file_reference_matches"] = _match_audio_file_references(
                        logic_payload, chunk_stream, assets
                    )
                asset_track_count = _integer(assets.get("NumberOfTracks"))
                if asset_track_count is not None and project.declared_track_count is not None and asset_track_count != project.declared_track_count:
                    project.warnings.append(
                        "The asset plist and output metadata report different track counts; their definitions are unknown."
                    )
                project.warnings.append(
                    "Asset plist resource lists are preserved as references; they do not establish arrangement placement."
                )

        if project.declared_track_count is not None:
            project.warnings.append(
                "Arrange-track count comes from summary metadata; track identities and regions remain unknown."
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
        return project


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None

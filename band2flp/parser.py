"""Conservative package and metadata reader for GarageBand projects."""

from __future__ import annotations

import base64
import hashlib
import plistlib
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
                    "logic_song_object_index": song_uid,
                    "logic_song_has_opaque_data": isinstance(song_object, dict) and isinstance(song_object.get("NS.data"), bytes),
                }
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
        return project


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None

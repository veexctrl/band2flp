"""Explicit extraction of audio members referenced by a GarageBand package."""

from __future__ import annotations

import lzma
from pathlib import Path
import re
import shutil
import tempfile
import zipfile
import zlib
from typing import Any

from .parser import MAX_MEMBER_SIZE, MAX_TOTAL_UNCOMPRESSED, BandFormatError, parse_band


class MediaExtractionError(ValueError):
    """A referenced media file could not be safely extracted."""


_SAFE_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,8}\Z")


def extract_referenced_audio(project_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    """Extract only uniquely matched ``AudioFiles`` references to a new directory.

    Output filenames are generated rather than derived from package paths. The
    destination must not already exist, and the output directory is published
    only after all selected members have been fully read and written.
    """
    project_path = Path(project_path)
    destination_arg = Path(output_dir).expanduser()
    if destination_arg.name in ("", ".", ".."):
        raise MediaExtractionError("output directory must name a new directory")

    project = parse_band(project_path)
    references = [
        ref for ref in project.media_references
        if ref.category == "AudioFiles"
    ]
    embedded_by_member: dict[str, list[Any]] = {}
    for reference in references:
        if reference.package_member is not None:
            embedded_by_member.setdefault(reference.package_member, []).append(reference)

    if not embedded_by_member:
        return {
            "extracted": [],
            "unresolved_audio_reference_count": len(references),
            "message": "No AudioFiles references uniquely matched package members.",
        }

    parent = destination_arg.parent.resolve()
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / destination_arg.name
    if destination.exists() or destination.is_symlink():
        raise MediaExtractionError("output directory already exists; choose a new path")

    temp_prefix = f".{destination.name}.band2flp-"
    staging = Path(tempfile.mkdtemp(prefix=temp_prefix, dir=parent))
    extracted: list[dict[str, Any]] = []
    try:
        try:
            archive = zipfile.ZipFile(project_path)
        except (OSError, zipfile.BadZipFile) as exc:
            raise BandFormatError(f"not a readable .band ZIP package: {project_path}") from exc

        with archive:
            listed_infos = archive.infolist()
            if len({info.filename for info in listed_infos}) != len(listed_infos):
                raise BandFormatError("package contains duplicate member names")
            if sum(info.file_size for info in listed_infos) > MAX_TOTAL_UNCOMPRESSED:
                raise BandFormatError("package exceeds the uncompressed size limit")
            if any(info.file_size > MAX_MEMBER_SIZE for info in listed_infos):
                raise BandFormatError("package member exceeds the size limit")
            infos = {info.filename: info for info in listed_infos}
            for index, (member, member_references) in enumerate(embedded_by_member.items(), start=1):
                info = infos.get(member)
                if info is None:
                    raise MediaExtractionError("a referenced package member disappeared after parsing")
                if info.flag_bits & 1:
                    raise MediaExtractionError("encrypted audio members are unsupported")
                if info.file_size > MAX_MEMBER_SIZE:
                    raise MediaExtractionError("referenced audio member exceeds the configured size limit")

                suffix = Path(member.replace("\\", "/")).suffix.lower()
                if not _SAFE_EXTENSION.fullmatch(suffix):
                    suffix = ".bin"
                output_name = f"audio-{index:03d}{suffix}"
                output_path = staging / output_name
                total = 0
                try:
                    with archive.open(info) as source, output_path.open("xb") as target:
                        while True:
                            block = source.read(min(64 * 1024, MAX_MEMBER_SIZE - total + 1))
                            if not block:
                                break
                            total += len(block)
                            if total > MAX_MEMBER_SIZE or total > info.file_size:
                                raise MediaExtractionError("decompressed audio member exceeds its declared size")
                            target.write(block)
                except (
                    OSError, EOFError, zipfile.BadZipFile, RuntimeError,
                    NotImplementedError, lzma.LZMAError, zlib.error,
                ) as exc:
                    raise MediaExtractionError("could not read a referenced audio member") from exc
                if total != info.file_size:
                    raise MediaExtractionError("decompressed audio size does not match its ZIP header")
                for reference in member_references:
                    extracted.append({
                        "reference_index": reference.index,
                        "reference": reference.reference,
                        "file": output_name,
                        "size": total,
                    })

        if destination.exists() or destination.is_symlink():
            raise MediaExtractionError("output directory appeared during extraction; no files were overwritten")
        staging.rename(destination)
    except Exception:
        resolved_staging = staging.resolve()
        if resolved_staging.parent == parent and resolved_staging.name.startswith(temp_prefix):
            shutil.rmtree(resolved_staging, ignore_errors=True)
        raise

    return {
        "output_directory": str(destination),
        "extracted": extracted,
        "unresolved_audio_reference_count": sum(ref.package_member is None for ref in references),
    }

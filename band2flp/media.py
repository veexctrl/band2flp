"""Explicit extraction of audio members referenced by a GarageBand package."""

from __future__ import annotations

import lzma
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import wave
import zipfile
import zlib
from typing import Any

from .parser import MAX_MEMBER_SIZE, MAX_TOTAL_UNCOMPRESSED, BandFormatError, parse_band


class MediaExtractionError(ValueError):
    """A referenced media file could not be safely extracted."""


_SAFE_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,8}\Z")


def _match_external_sources(
    references: list[Any], source_root: str | Path | None
) -> tuple[dict[Path, list[Any]], int, Path | None]:
    """Resolve external audio by unique basename inside an explicit source root."""
    if source_root is None:
        return {}, 0, None
    try:
        root = Path(source_root).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise MediaExtractionError("external source root is not accessible") from exc
    if not root.is_dir():
        raise MediaExtractionError("external source root must be a directory")

    external_references = [
        reference for reference in references if reference.package_member is None
    ]
    wanted = {
        reference.reference.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].casefold()
        for reference in external_references
    }
    wanted.discard("")
    if not wanted:
        return {}, 0, root

    by_name: dict[str, list[Path]] = {}
    try:
        for path in root.rglob("*"):
            if path.name.casefold() not in wanted or path.is_symlink() or not path.is_file():
                continue
            try:
                resolved = path.resolve(strict=True)
                resolved.relative_to(root)
            except (OSError, RuntimeError, ValueError):
                continue
            by_name.setdefault(path.name.casefold(), []).append(resolved)
    except OSError as exc:
        raise MediaExtractionError("could not scan the external source root") from exc

    matches: dict[Path, list[Any]] = {}
    ambiguous = 0
    for reference in external_references:
        basename = reference.reference.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        if basename in ("", ".", ".."):
            continue
        candidates = by_name.get(basename.casefold(), [])
        if len(candidates) == 1:
            matches.setdefault(candidates[0], []).append(reference)
        elif len(candidates) > 1:
            ambiguous += 1
    return matches, ambiguous, root


def extract_referenced_audio(
    project_path: str | Path,
    output_dir: str | Path,
    *,
    to_wav: bool = False,
    transcoder: str = "ffmpeg",
    source_root: str | Path | None = None,
) -> dict[str, Any]:
    """Extract only uniquely matched ``AudioFiles`` references to a new directory.

    Output filenames are generated rather than derived from source paths. The
    destination must not already exist, and the output directory is published
    only after all selected sources have been fully read and written. An
    explicit ``source_root`` may resolve otherwise external references by a
    unique basename; ambiguous names are left unresolved. When ``to_wav`` is
    true, a user-installed FFmpeg executable converts each source to 16-bit
    PCM WAV inside the staging directory.
    """
    project_path = Path(project_path)
    transcoder_path: str | None = None
    if to_wav:
        if not transcoder.strip():
            raise MediaExtractionError("transcoder executable path must not be empty")
        transcoder_path = shutil.which(transcoder)
        if transcoder_path is None:
            candidate = Path(transcoder).expanduser()
            if candidate.is_file():
                transcoder_path = str(candidate.resolve())
            else:
                raise MediaExtractionError(
                    "WAV conversion requires FFmpeg; install it or pass its executable path"
                )
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

    external_by_path, ambiguous_external_count, resolved_source_root = _match_external_sources(
        references, source_root
    )
    matched_external_indices = {
        reference.index
        for group in external_by_path.values()
        for reference in group
    }
    unresolved_count = sum(
        reference.package_member is None
        and reference.index not in matched_external_indices
        for reference in references
    )

    if not embedded_by_member and not external_by_path:
        return {
            "extracted": [],
            "unresolved_audio_reference_count": unresolved_count,
            "ambiguous_external_source_count": ambiguous_external_count,
            "message": (
                "No AudioFiles references uniquely matched package members or source-root files."
                if source_root is not None else
                "No AudioFiles references uniquely matched package members."
            ),
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
        selected_sources = [
            (member, None, member_references)
            for member, member_references in embedded_by_member.items()
        ] + [
            (None, source_path, source_references)
            for source_path, source_references in external_by_path.items()
        ]
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
            external_total = 0
            for index, (member, external_path, source_references) in enumerate(selected_sources, start=1):
                info = None
                resolved_path = None
                if member is not None:
                    info = infos.get(member)
                    if info is None:
                        raise MediaExtractionError("a referenced package member disappeared after parsing")
                    if info.flag_bits & 1:
                        raise MediaExtractionError("encrypted audio members are unsupported")
                    declared_size = info.file_size
                    suffix_source = member.replace("\\", "/")
                    read_error = (
                        OSError, EOFError, zipfile.BadZipFile, RuntimeError,
                        NotImplementedError, lzma.LZMAError, zlib.error,
                    )
                else:
                    assert external_path is not None
                    if resolved_source_root is None:
                        raise MediaExtractionError("external source root was not retained")
                    try:
                        resolved_path = external_path.resolve(strict=True)
                        resolved_path.relative_to(resolved_source_root)
                    except (OSError, RuntimeError, ValueError) as exc:
                        raise MediaExtractionError("external source changed or escaped its source root") from exc
                    if external_path.is_symlink() or not resolved_path.is_file():
                        raise MediaExtractionError("external audio source is not a regular file")
                    declared_size = resolved_path.stat().st_size
                    external_total += declared_size
                    if declared_size > MAX_MEMBER_SIZE:
                        raise MediaExtractionError("external audio source exceeds the configured size limit")
                    if external_total > MAX_TOTAL_UNCOMPRESSED:
                        raise MediaExtractionError("external audio sources exceed the configured total size limit")
                    suffix_source = resolved_path.name
                    read_error = (OSError, EOFError)

                if declared_size > MAX_MEMBER_SIZE:
                    raise MediaExtractionError("referenced audio source exceeds the configured size limit")

                suffix = Path(suffix_source).suffix.lower()
                if not _SAFE_EXTENSION.fullmatch(suffix):
                    suffix = ".bin"
                source_name = (
                    f"audio-{index:03d}.source{suffix}" if to_wav
                    else f"audio-{index:03d}{suffix}"
                )
                output_name = f"audio-{index:03d}.wav" if to_wav else source_name
                source_path = staging / source_name
                output_path = staging / output_name
                total = 0
                try:
                    source_context = (
                        archive.open(info)
                        if info is not None else resolved_path.open("rb")
                    )
                    with source_context as source, source_path.open("xb") as target:
                        while True:
                            block = source.read(min(64 * 1024, MAX_MEMBER_SIZE - total + 1))
                            if not block:
                                break
                            total += len(block)
                            if total > MAX_MEMBER_SIZE or total > declared_size:
                                raise MediaExtractionError("audio source exceeds its declared size")
                            target.write(block)
                except read_error as exc:
                    raise MediaExtractionError("could not read a referenced audio source") from exc
                if total != declared_size:
                    raise MediaExtractionError("audio source size does not match its declared size")
                if to_wav:
                    assert transcoder_path is not None
                    try:
                        result = subprocess.run(
                            [
                                transcoder_path, "-nostdin", "-v", "error", "-y",
                                "-i", str(source_path), "-map", "0:a:0", "-vn",
                                "-c:a", "pcm_s16le", "-fs", str(MAX_MEMBER_SIZE),
                                "-f", "wav", str(output_path),
                            ],
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            check=False,
                            shell=False,
                            timeout=300,
                        )
                    except subprocess.TimeoutExpired as exc:
                        raise MediaExtractionError("WAV transcoding exceeded the five-minute limit") from exc
                    except OSError as exc:
                        raise MediaExtractionError("could not start the requested WAV transcoder") from exc
                    if result.returncode != 0 or not output_path.is_file():
                        raise MediaExtractionError("the WAV transcoder could not convert a referenced audio file")
                    try:
                        with wave.open(str(output_path), "rb") as converted:
                            if converted.getnframes() <= 0 or converted.getframerate() <= 0:
                                raise MediaExtractionError("the WAV transcoder produced empty or invalid audio")
                    except (OSError, EOFError, wave.Error) as exc:
                        raise MediaExtractionError("the WAV transcoder did not produce a valid PCM WAV file") from exc
                    if output_path.stat().st_size >= MAX_MEMBER_SIZE:
                        raise MediaExtractionError("transcoded WAV exceeds the configured size limit")
                    source_path.unlink()
                for reference in source_references:
                    extracted.append({
                        "reference_index": reference.index,
                        "reference": reference.reference,
                        "file": output_name,
                        "size": output_path.stat().st_size if to_wav else total,
                        **({"transcoded_to": "WAVE PCM 16-bit"} if to_wav else {}),
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
        "unresolved_audio_reference_count": unresolved_count,
        "ambiguous_external_source_count": ambiguous_external_count,
    }


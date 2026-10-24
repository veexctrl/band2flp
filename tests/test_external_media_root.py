from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import zipfile

import pytest

from band2flp.media import MediaExtractionError, extract_referenced_audio
from band2flp.model import MediaReference, Project, Region, Track
from band2flp.cli import main


def _project_archive(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("projectData", b"synthetic project metadata")
    return path


def _audio_reference(value: str) -> MediaReference:
    return MediaReference(index=0, category="AudioFiles", reference=value)


def test_extracts_unique_external_source_to_generated_name(tmp_path: Path) -> None:
    project_path = _project_archive(tmp_path / "synthetic.band")
    source_root = tmp_path / "library"
    source = source_root / "nested" / "loop.caf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"synthetic sample placeholder")
    output_dir = tmp_path / "extracted"
    project = SimpleNamespace(media_references=[_audio_reference("loops/loop.caf")])

    with patch("band2flp.media.parse_band", return_value=project):
        report = extract_referenced_audio(project_path, output_dir, source_root=source_root)

    assert report["unresolved_audio_reference_count"] == 0
    assert report["ambiguous_external_source_count"] == 0
    assert len(report["extracted"]) == 1
    output_name = report["extracted"][0]["file"]
    assert output_name == "audio-001.caf"
    assert (output_dir / output_name).read_bytes() == b"synthetic sample placeholder"


def test_duplicate_external_basenames_remain_unresolved(tmp_path: Path) -> None:
    project_path = _project_archive(tmp_path / "synthetic.band")
    source_root = tmp_path / "library"
    for folder in ("one", "two"):
        directory = source_root / folder
        directory.mkdir(parents=True)
        (directory / "loop.caf").write_bytes(folder.encode())
    output_dir = tmp_path / "extracted"
    project = SimpleNamespace(media_references=[_audio_reference("loops/loop.caf")])

    with patch("band2flp.media.parse_band", return_value=project):
        report = extract_referenced_audio(project_path, output_dir, source_root=source_root)

    assert report["extracted"] == []
    assert report["unresolved_audio_reference_count"] == 1
    assert report["ambiguous_external_source_count"] == 1
    assert not output_dir.exists()


def test_source_root_must_be_a_directory(tmp_path: Path) -> None:
    project_path = _project_archive(tmp_path / "synthetic.band")
    source_root = tmp_path / "not-a-directory"
    source_root.write_text("synthetic", encoding="utf-8")
    project = SimpleNamespace(media_references=[_audio_reference("loop.caf")])

    with patch("band2flp.media.parse_band", return_value=project):
        with pytest.raises(MediaExtractionError, match="must be a directory"):
            extract_referenced_audio(
                project_path,
                tmp_path / "extracted",
                source_root=source_root,
            )


def test_extract_audio_cli_forwards_source_root() -> None:
    with patch("band2flp.cli.extract_referenced_audio", return_value={"extracted": []}) as extract:
        with patch("band2flp.cli._print_json"):
            assert main([
                "extract-audio", "project.band", "output", "--source-root", "library"
            ]) == 0

    extract.assert_called_once_with(
        "project.band",
        "output",
        to_wav=False,
        transcoder="ffmpeg",
        source_root="library",
    )


def test_export_cli_forwards_source_root_for_audio_regions() -> None:
    project = Project(tracks=[Track(index=0, regions=[Region(kind="audio", duration_beats="4")])])
    extraction_report = {"extracted": [], "unresolved_audio_reference_count": 1}
    with patch("band2flp.cli.parse_band", return_value=project):
        with patch("band2flp.cli.extract_referenced_audio", return_value=extraction_report) as extract:
            with patch("band2flp.cli.export_flp", return_value={"output": "synthetic.flp"}):
                with patch("band2flp.cli._print_json"):
                    assert main([
                        "export-flp", "project.band", "output.flp", "--template", "blank.flp",
                        "--media-dir", "media", "--source-root", "library",
                    ]) == 0

    extract.assert_called_once_with(
        "project.band",
        "media",
        to_wav=False,
        transcoder="ffmpeg",
        source_root="library",
    )


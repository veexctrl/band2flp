from __future__ import annotations

import json
import plistlib
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from research.scripts.binary_diff import compare, load_component
from band2flp.parser import BandFormatError, parse_band


def make_fixture(path: Path) -> None:
    archive = {
        "$archiver": "NSKeyedArchiver",
        "$version": 100000,
        "$top": {"DfDocument logic model": {"CF$UID": 1}},
        "$objects": ["$null", {"DfLogicModelLogicSong": {"CF$UID": 2}}, {"NS.data": b"opaque payload"}],
    }
    metadata = {
        "com_apple_garageband_metadata_songTempo": 120,
        "com_apple_garageband_metadata_songSignatureNominator": 3,
        "com_apple_garageband_metadata_songSignatureDeNominator": 4,
        "com_apple_garageband_metadata_songDuration": 12.5,
        "com_apple_garageband_metadata_numberOfArrangeTracks": 2,
    }
    assets = {
        "NumberOfTracks": 3,
        "BeatsPerMinute": 120.0,
        "SongSignatureNumerator": 3,
        "SongSignatureDenominator": 4,
        "AudioFiles": ["${CONTENT:loops/example.caf"],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("fixture.band/projectData", plistlib.dumps(archive))
        package.writestr("fixture.band/Output/metadata.plist", plistlib.dumps(metadata))
        package.writestr("fixture.band/Output/assetsmetadata.plist", plistlib.dumps(assets, fmt=plistlib.FMT_BINARY))
        package.writestr("fixture.band/Contents/PkgInfo", b"BNDLband")


class ParserTests(unittest.TestCase):
    def test_binary_diff_loads_a_unique_zip_member(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "fixture.band"
            make_fixture(fixture)
            data, member = load_component(fixture, "/projectData")
        self.assertEqual(member, "fixture.band/projectData")
        self.assertTrue(data.startswith(b"<?xml"))

    def test_binary_diff_reports_changed_ranges_and_candidate_values(self) -> None:
        report = compare(b"prefix\x01\x00suffix", b"prefix\x02\x00suffix")
        self.assertEqual(report["common_prefix_size"], 6)
        self.assertEqual(report["changed_range_count"], 1)
        change = report["changed_ranges"][0]
        self.assertEqual(change["offset_start"], 6)
        self.assertEqual(change["numeric_candidates_at_start"]["u16_little"], [1, 2])
        self.assertIn("insertions can shift", report["alignment_warning"])

    def test_extracts_summary_fields_and_preserves_opaque_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "fixture.band"
            make_fixture(fixture)
            project = parse_band(fixture)
        self.assertEqual(project.tempo_bpm, 120.0)
        self.assertEqual(project.time_signature, (3, 4))
        self.assertEqual(project.duration_value, 12.5)
        self.assertEqual(project.declared_track_count, 2)
        self.assertEqual(project.tracks, [])
        blob = project.project_data["opaque_data_objects"][0]
        self.assertEqual(blob["base64"], "b3BhcXVlIHBheWxvYWQ=")
        self.assertEqual(project.project_data["assetsmetadata_plist"]["values"]["AudioFiles"], ["${CONTENT:loops/example.caf"])
        self.assertIn("different track counts", " ".join(project.warnings))
        self.assertIn("track identities and regions remain unknown", " ".join(project.warnings))

    def test_rejects_non_zip_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "broken.band"
            fixture.write_bytes(b"not a zip")
            with self.assertRaises(BandFormatError):
                parse_band(fixture)

    def test_json_cli_emits_neutral_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "fixture.band"
            make_fixture(fixture)
            result = subprocess.run(
                [sys.executable, "-m", "band2flp.cli", "inspect", str(fixture), "--json"],
                cwd=Path(__file__).parents[1], capture_output=True, text=True, check=True,
            )
        decoded = json.loads(result.stdout)
        self.assertEqual(decoded["tempo_bpm"], 120.0)
        self.assertEqual(decoded["tracks"], [])
        self.assertEqual(decoded["project_data"]["opaque_data_objects"][0]["length"], 14)


if __name__ == "__main__":
    unittest.main()

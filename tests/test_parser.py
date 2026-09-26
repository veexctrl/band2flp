from __future__ import annotations

import json
import plistlib
import subprocess
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from research.scripts.auco_probe import probe_logic_payload
from research.scripts.binary_diff import compare, load_component
from research.scripts.projectdata_diff import compare_payloads, load_logic_payload
from band2flp.model import MediaReference, Project
from band2flp.parser import (
    BandFormatError,
    _attach_audio_placements,
    _match_audio_file_references,
    _parse_audio_placements,
    _parse_chunk_stream,
    _parse_event_sequences,
    parse_band,
)


def make_fixture(
    path: Path,
    include_events: bool = False,
    test_payload: bytes = b"abc",
    include_audio_placement: bool = False,
) -> None:
    summary_tempo = 160 if include_events else 120
    summary_numerator = 4 if include_events else 3
    chunk_data = bytes.fromhex("2347c0ab") + bytes(20)
    chunk_header = bytearray(36)
    chunk_header[:4] = b"tseT"
    struct.pack_into("<Q", chunk_header, 28, len(test_payload))
    logic_payload = chunk_data + bytes(chunk_header) + test_payload
    if include_events:
        logic_payload += make_chunk("EvSq", 0, make_tempo_event(160) + make_meter_event(4, 2))
        logic_payload += make_chunk("EvSq", 0x00040000, make_tempo_event(120))
    if include_audio_placement:
        logic_payload += make_chunk("AuFl", 0x00140000, "example.caf".encode("utf-16le"))
        logic_payload += make_chunk("AuRg", 0x00140000, b"\x07\x00example\x00")
        placement = bytearray(80)
        placement[:4] = b"\x24\x00\x00\x00"
        struct.pack_into("<I", placement, 4, 49_920)
        struct.pack_into("<I", placement, 0x10, 0x70)
        placement[0x14] = 3
        placement[0x17] = 0x89
        placement[0x27] = 0xBC
        struct.pack_into("<I", placement, 0x2C, 0x14)
        placement[0x37] = 0x8A
        placement[0x47] = 0x89
        logic_payload += make_chunk("EvSq", 0x00040000, bytes(placement))
    archive = {
        "$archiver": "NSKeyedArchiver",
        "$version": 100000,
        "$top": {"DfDocument logic model": {"CF$UID": 1}, "fixture_unknown": "preserve me"},
        "$objects": ["$null", {"DfLogicModelLogicSong": {"CF$UID": 2}}, {"NS.data": logic_payload}],
    }
    metadata = {
        "com_apple_garageband_metadata_songTempo": summary_tempo,
        "com_apple_garageband_metadata_songSignatureNominator": summary_numerator,
        "com_apple_garageband_metadata_songSignatureDeNominator": 4,
        "com_apple_garageband_metadata_songDuration": 12.5,
        "com_apple_garageband_metadata_numberOfArrangeTracks": 2,
    }
    assets = {
        "NumberOfTracks": 3,
        "BeatsPerMinute": float(summary_tempo),
        "SongSignatureNumerator": summary_numerator,
        "SongSignatureDenominator": 4,
        "AudioFiles": ["${CONTENT:loops/example.caf"],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("fixture.band/projectData", plistlib.dumps(archive))
        package.writestr("fixture.band/Output/metadata.plist", plistlib.dumps(metadata))
        package.writestr("fixture.band/Output/assetsmetadata.plist", plistlib.dumps(assets, fmt=plistlib.FMT_BINARY))
        package.writestr("fixture.band/Contents/PkgInfo", b"BNDLband")


def make_chunk(tag: str, group_id: int, payload: bytes) -> bytes:
    header = bytearray(36)
    header[:4] = tag[::-1].encode("ascii")
    struct.pack_into("<I", header, 8, group_id)
    struct.pack_into("<Q", header, 28, len(payload))
    return bytes(header) + payload


def make_tempo_event(bpm: int, position: int = 38400) -> bytes:
    event = bytearray(32)
    event[0] = 0x60
    struct.pack_into("<I", event, 4, position)
    event[12:15] = b"\x7f\x00\x00"
    struct.pack_into("<I", event, 16, bpm * 10_000)
    event[23] = 0x88
    return bytes(event)


def make_meter_event(numerator: int, denominator_power: int, position: int = 0) -> bytes:
    event = bytearray(48)
    event[0] = 0x30
    struct.pack_into("<I", event, 4, position)
    event[11] = denominator_power
    event[12] = numerator
    event[16] = 0x30
    event[23] = 0x88
    event[39] = 0x80
    return bytes(event)


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

    def test_projectdata_diff_aligns_chunks_and_reports_payload_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            before_path = Path(directory) / "before.band"
            after_path = Path(directory) / "after.band"
            make_fixture(before_path, include_events=True, test_payload=b"abc")
            make_fixture(after_path, include_events=True, test_payload=b"axc")
            before_project = parse_band(before_path)
            after_project = parse_band(after_path)
            before = load_logic_payload(before_path)
            after = load_logic_payload(after_path)
        report = compare_payloads(
            before_project.project_data, before, after_project.project_data, after,
        )
        self.assertIn("ordinal correspondence is not a semantic identity", report["alignment_confidence"])
        self.assertEqual(report["before_chunk_count"], 3)
        self.assertEqual(report["unchanged_matched_count"], 2)
        self.assertEqual(len(report["modified"]), 1)
        modified = report["modified"][0]
        self.assertEqual(modified["type"], "Test")
        self.assertEqual(modified["changed_ranges"][0]["offset_start"], 1)
        self.assertEqual(modified["changed_ranges"][0]["before_hex"], "62")
        self.assertEqual(modified["changed_ranges"][0]["after_hex"], "78")
        self.assertEqual(report["added"], [])
        self.assertEqual(report["removed"], [])

    def test_projectdata_diff_reports_new_and_removed_chunk_ordinals(self) -> None:
        header = bytes.fromhex("2347c0ab") + bytes(20)
        before = header + make_chunk("Test", 0, b"abc")
        after = before + make_chunk("Test", 0, b"xyz")
        before_data = {"logic_song_chunk_stream": _parse_chunk_stream(before)}
        after_data = {"logic_song_chunk_stream": _parse_chunk_stream(after)}
        report = compare_payloads(before_data, before, after_data, after)
        self.assertEqual(report["added"], [{
            "type": "Test", "group_id_candidate": 0, "ordinal": 1, "chunk_index": 1,
        }])
        self.assertEqual(report["removed"], [])
        reversed_report = compare_payloads(after_data, after, before_data, before)
        self.assertEqual(reversed_report["added"], [])
        self.assertEqual(reversed_report["removed"], [{
            "type": "Test", "group_id_candidate": 0, "ordinal": 1, "chunk_index": 1,
        }])

    def test_projectdata_diff_reports_opaque_header_changes(self) -> None:
        root = bytes.fromhex("2347c0ab") + bytes(20)
        before_chunk = make_chunk("Test", 0, b"same")
        after_chunk = bytearray(before_chunk)
        after_chunk[4] = 0x7F
        before = root + before_chunk
        after = root + bytes(after_chunk)
        report = compare_payloads(
            {"logic_song_chunk_stream": _parse_chunk_stream(before)}, before,
            {"logic_song_chunk_stream": _parse_chunk_stream(after)}, after,
        )
        self.assertEqual(len(report["modified"]), 1)
        self.assertEqual(report["modified"][0]["changed_header_ranges"][0]["offset_start"], 4)
        self.assertEqual(report["modified"][0]["changed_ranges"], [])

    def test_auco_probe_validates_candidate_record_without_emitting_name(self) -> None:
        payload = bytearray(84)
        payload[60] = 0x20
        payload[61:68] = b"Track X"
        payload[68:76] = bytes(8)
        chunk = bytearray(make_chunk("AuCO", 0x00240000, bytes(payload)))
        chunk[4:8] = bytes.fromhex("07000e00")
        struct.pack_into("<H", chunk, 14, 3)
        raw = bytes.fromhex("2347c0ab") + bytes(20) + bytes(chunk)
        result = probe_logic_payload(raw, _parse_chunk_stream(raw))
        self.assertEqual(result["marker_candidate_count"], 1)
        self.assertEqual(result["validated_record_count"], 1)
        self.assertEqual(result["strip_index_candidates"], [3])
        self.assertNotIn("Track X", json.dumps(result))
        self.assertIn("HYPOTHESIS", result["interpretation"])

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
        self.assertEqual(blob["length"], 63)
        self.assertTrue(blob["base64"].startswith("I0fAqw"))
        self.assertEqual(project.project_data["assetsmetadata_plist"]["values"]["AudioFiles"], ["${CONTENT:loops/example.caf"])
        chunk_stream = project.project_data["logic_song_chunk_stream"]
        self.assertEqual(chunk_stream["chunk_count"], 1)
        self.assertEqual(chunk_stream["end_offset"], 63)
        self.assertEqual(chunk_stream["chunks"][0]["type"], "Test")
        saved_archive = project.project_data["keyed_archive_plist"]["archive"]
        self.assertEqual(saved_archive["$top"]["fixture_unknown"], "preserve me")
        self.assertEqual(saved_archive["$objects"][2]["NS.data"]["opaque_data_object_index"], 2)
        self.assertEqual(project.project_data["metadata_plist"]["values"]["com_apple_garageband_metadata_songTempo"], 120)
        self.assertEqual(len(project.media_references), 1)
        self.assertEqual(project.media_references[0].category, "AudioFiles")
        self.assertEqual(project.media_references[0].reference, "${CONTENT:loops/example.caf")
        self.assertIsNone(project.media_references[0].package_member)
        self.assertIn("different track counts", " ".join(project.warnings))
        self.assertIn("only tracks with recognized audio placement events are represented", " ".join(project.warnings))

    def test_rejects_non_zip_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "broken.band"
            fixture.write_bytes(b"not a zip")
            with self.assertRaises(BandFormatError):
                parse_band(fixture)

    def test_chunk_parser_rejects_truncation_and_out_of_bounds_lengths(self) -> None:
        with self.assertRaises(BandFormatError):
            _parse_chunk_stream(bytes.fromhex("2347c0ab") + bytes(20) + b"short")
        header = bytearray(36)
        header[:4] = b"tseT"
        struct.pack_into("<Q", header, 28, 5)
        with self.assertRaises(BandFormatError):
            _parse_chunk_stream(bytes.fromhex("2347c0ab") + bytes(20) + bytes(header) + b"abc")

    def test_audio_asset_match_correlates_shared_chunk_group(self) -> None:
        name = "loops/example.caf"
        payload = bytes.fromhex("2347c0ab") + bytes(20)
        payload += make_chunk("AuFl", 0x00100000, name.rsplit("/", 1)[-1].encode("utf-16le"))
        payload += make_chunk("AuRg", 0x00100000, b"\x07\x00example\x00")
        payload += make_chunk("AuRg", 0x00100000, b"other\x00")
        payload += make_chunk("AuRg", 0x00140000, b"example\x00")
        stream = _parse_chunk_stream(payload)
        matches = _match_audio_file_references(payload, stream, {"AudioFiles": [name]})
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["group_id_candidate"], 0x00100000)
        self.assertEqual(matches[0]["related_AuRg_chunk_indices"], [1, 2])
        self.assertEqual(matches[0]["name_matched_AuRg_chunk_indices"], [1])

    def test_audio_placement_recovers_beats_track_and_external_source(self) -> None:
        event = bytearray(160)
        event[:4] = b"\x24\x00\x00\x00"
        struct.pack_into("<I", event, 4, 49_920)  # 34560 + 4 bars at 960 PPQ.
        struct.pack_into("<I", event, 0x10, 0x70)
        event[0x14] = 3
        event[0x17] = 0x89
        event[0x27] = 0xBC
        event[0x2C:0x30] = bytes.fromhex("14000000")
        event[0x37] = 0x8A
        event[0x47] = 0x89
        event[80:] = bytes([0xC7]) + bytes(79)
        decoded = _parse_audio_placements({"records": [{
            "type_byte": 0x24,
            "chunk_index": 5,
            "event_index": 2,
            "group_id_candidate": 0x40000,
            "raw_hex": event.hex(),
        }]})
        self.assertEqual(len(decoded), 1)
        self.assertEqual(decoded[0]["start_beats"], "16")
        self.assertEqual(decoded[0]["track_number_1_based_candidate"], 3)
        self.assertEqual(decoded[0]["media_group_id_candidate"], 0x140000)
        self.assertEqual(decoded[0]["trailing_event_data_hex"], (bytes([0xC7]) + bytes(79)).hex())

        project = Project(media_references=[MediaReference(
            index=0,
            category="AudioFiles",
            reference="loops/example.caf",
            group_id_candidate=0x140000,
            name_matched_region_chunk_indices=[10],
        )])
        _attach_audio_placements(project, decoded)
        self.assertEqual([(track.index, track.kind) for track in project.tracks], [(2, "audio")])
        region = project.tracks[0].regions[0]
        self.assertEqual(region.name, "example")
        self.assertEqual(region.start_beats, "16")
        self.assertIsNone(region.duration_beats)
        self.assertEqual(region.source, "loops/example.caf")
        self.assertEqual(region.unknown["candidate_region_chunk_indices_for_source"], [10])

    def test_package_parse_builds_audio_track_and_region_from_placement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "fixture.band"
            make_fixture(fixture, include_audio_placement=True)
            project = parse_band(fixture)
        self.assertEqual(len(project.project_data["audio_placements"]), 1)
        self.assertEqual(len(project.tracks), 1)
        track = project.tracks[0]
        self.assertEqual(track.index, 2)
        self.assertEqual(track.kind, "audio")
        self.assertEqual(len(track.regions), 1)
        self.assertEqual(track.regions[0].start_beats, "16")
        self.assertEqual(track.regions[0].source, "${CONTENT:loops/example.caf")

    def test_event_records_recover_tempo_and_meter_candidates(self) -> None:
        payload = bytes.fromhex("2347c0ab") + bytes(20)
        payload += make_chunk("EvSq", 0, make_tempo_event(160) + make_meter_event(4, 2))
        payload += make_chunk("EvSq", 0x00040000, make_tempo_event(120))
        chunk_stream = _parse_chunk_stream(payload)
        events = _parse_event_sequences(payload, chunk_stream)
        self.assertEqual([item["bpm"] for item in events["tempo_candidates"]], [160.0, 120.0])
        self.assertEqual(events["time_signature_candidates"][0]["numerator"], 4)
        self.assertEqual(events["time_signature_candidates"][0]["denominator"], 4)
        self.assertEqual(events["tempo_candidates"][1]["source_group_id_candidate"], 0x00040000)

    def test_parser_keeps_nonzero_group_tempo_out_of_global_map(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "fixture.band"
            make_fixture(fixture, include_events=True)
            project = parse_band(fixture)
        self.assertEqual([point["bpm"] for point in project.tempo_map], [160.0])
        self.assertTrue(project.tempo_map[0]["matches_summary"])
        self.assertEqual(len(project.time_signatures), 1)
        self.assertTrue(project.time_signatures[0]["matches_summary"])
        self.assertEqual([point["bpm"] for point in project.project_data["event_sequences"]["tempo_candidates"]], [160.0, 120.0])

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
        self.assertEqual(decoded["project_data"]["opaque_data_objects"][0]["length"], 63)

    def test_cli_groups_chunks_without_assigning_group_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "fixture.band"
            make_fixture(fixture, include_events=True)
            result = subprocess.run(
                [sys.executable, "-m", "band2flp.cli", "inspect", str(fixture), "--groups"],
                cwd=Path(__file__).parents[1], capture_output=True, text=True, check=True,
            )
        self.assertIn("Chunk groups (candidate field; meaning unknown):", result.stdout)
        self.assertIn("0x00040000 (1 chunk): EvSq=1", result.stdout)
        self.assertIn("indices: 2", result.stdout)


if __name__ == "__main__":
    unittest.main()

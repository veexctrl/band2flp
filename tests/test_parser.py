from __future__ import annotations

import json
import io
from contextlib import redirect_stdout
from types import SimpleNamespace
import plistlib
import subprocess
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid
import wave
import zipfile
from pathlib import Path

from research.scripts.auco_probe import probe_logic_payload
from research.scripts.audio_frame_probe import audio_frame_count, audio_sample_rate
from research.scripts.audio_name_chunk_probe import profile_audio_name_chunks
from research.scripts.arrange_ui_probe import profile_arrange_ui
from research.scripts.audio_track_index_probe import profile_audio_track_indices
from research.scripts.audio_placement_timing_probe import profile_candidates as profile_audio_timing_candidates
from research.scripts.binary_diff import compare, load_component
from research.scripts.event_inventory import inventory_records, profile_tempo_group_associations
from research.scripts.midi_event_family_probe import profile_midi_event_families
from research.scripts.midi_event_variation_probe import profile_records as profile_midi_event_variation
from research.scripts.flp_playlist_state_probe import parse_events as parse_flp_event_spans
from research.scripts.flp_playlist_bisect_probe import keep_playlist_rows
from research.scripts.midi_region_timing_probe import profile_record_relative_mseq_candidates
from research.scripts.keyed_archive_inventory import profile_archive as profile_keyed_archive
from research.scripts.mseq_probe import probe_logic_payload as probe_mseq_logic_payload, summarize_payloads
from research.scripts.flp_playlist_inventory import playlist_event_data, stride_hypotheses, _profile_metrics
from research.scripts.flp_playlist_tail_probe import replace_one_tail_byte, replace_opaque_tails
from research.scripts.track_uuid_probe import (
    find_uuid_payload_matches,
    selected_track_uuid,
    trak_uuid_field_profile,
)
from research.scripts.trak_uuid_archive_probe import profile_archive_references
from research.scripts.trak_uuid_logic_probe import additional_uuid_occurrences
from research.scripts.trak_group_probe import (
    profile_midi_track_value_ordinals,
    summarize_trak_groups,
)
from research.scripts.projectdata_diff import compare_payloads, load_logic_payload
from research.scripts.trak_probe import probe_logic_payload as probe_trak_logic_payload
from band2flp.model import MediaReference, Project, Region, Track
from band2flp.cli import main as cli_main
from band2flp.media import MediaExtractionError, extract_referenced_audio
from band2flp.flp_export import (
    _fl_playlist_track_index,
    _fl_track_event_storage_index,
    _place_audio_channels_before_playlist,
    AudioInfo,
    FLPExportError,
    _beats_to_ticks,
    _midi_candidate_display_name,
    _pack_midi_note_candidate,
    _select_base_playlist_record_layout,
    _validate_clock_roundtrip,
    _validate_sample_path_roundtrip,
    audio_info,
    export_flp,
)
from band2flp.parser import (
    BandFormatError,
    _attach_audio_placements,
    _attach_unplaced_midi_region_candidates,
    _match_audio_file_references,
    _link_mseq_labels_to_placements,
    _mseq_label_candidates,
    _parse_audio_placements,
    _parse_chunk_stream,
    _parse_event_sequences,
    _event_record,
    _parse_midi_note_candidates,
    _parse_midi_region_placement_candidates,
    _unique_candidate_region_field_pairs,
    parse_band,
)


def make_fixture(
    path: Path,
    include_events: bool = False,
    test_payload: bytes = b"abc",
    include_audio_placement: bool = False,
    embedded_audio: bytes | None = None,
    audio_reference: str | None = None,
    audio_file_name: str = "example.caf",
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
        audio_stem = Path(audio_file_name).stem
        logic_payload += make_chunk("AuFl", 0x00140000, audio_file_name.encode("utf-16le"))
        logic_payload += make_chunk("AuRg", 0x00140000, b"\x07\x00" + audio_stem.encode() + b"\x00")
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
        "AudioFiles": [audio_reference or f"${{CONTENT:loops/{audio_file_name}"],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("fixture.band/projectData", plistlib.dumps(archive))
        package.writestr("fixture.band/Output/metadata.plist", plistlib.dumps(metadata))
        package.writestr("fixture.band/Output/assetsmetadata.plist", plistlib.dumps(assets, fmt=plistlib.FMT_BINARY))
        package.writestr("fixture.band/Contents/PkgInfo", b"BNDLband")
        if embedded_audio is not None:
            package.writestr(f"fixture.band/Audio Files/{audio_file_name}", embedded_audio)


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
    def test_audio_region_field_links_include_unique_zero_slot_with_nonzero_anchor(self) -> None:
        zero = bytes(8)
        fields = [zero, *(value.to_bytes(8, "little") for value in (1, 2, 3))]
        placements = [fields[2], zero, fields[3], fields[1]]

        self.assertEqual(
            _unique_candidate_region_field_pairs(fields, placements),
            [(0, 1), (1, 3), (2, 0), (3, 2)],
        )

    def test_audio_region_field_links_reject_zero_only_ambiguity(self) -> None:
        zero = bytes(8)
        self.assertEqual(
            _unique_candidate_region_field_pairs([zero, zero], [zero, zero]),
            [],
        )

    def test_flp_playlist_tail_probe_changes_only_opaque_80_byte_tails(self) -> None:
        def varint(value: int) -> bytes:
            result = bytearray()
            while value >= 0x80:
                result.append((value & 0x7F) | 0x80)
                value >>= 7
            result.append(value)
            return bytes(result)

        original_tail = bytes([1]) + bytes(47)
        reference_tail = bytes([2]) + bytes(47)
        row = struct.pack("<IHHIHH", 0, 20480, 1, 960, 499, 0) + bytes(16) + original_tail
        payload = row
        event = bytes([233]) + varint(len(payload)) + payload
        header = bytearray(22)
        header[:4] = b"FLhd"
        header[14:18] = b"FLdt"
        struct.pack_into("<I", header, 18, len(event))

        rewritten, metrics = replace_opaque_tails(bytes(header) + event, [reference_tail])

        self.assertEqual(rewritten[22 + 2:22 + 2 + 32], row[:32])
        self.assertEqual(rewritten[22 + 2 + 32:22 + 2 + 80], reference_tail)
        self.assertEqual(metrics, {
            "playlist_rows": 1,
            "rows_with_changed_tails": 1,
            "changed_tail_bytes": 1,
        })

    def test_flp_playlist_tail_probe_rejects_wrong_tail_count(self) -> None:
        with self.assertRaises(FLPExportError):
            replace_opaque_tails(b"", [])

    def test_flp_playlist_tail_probe_can_isolate_one_byte(self) -> None:
        def varint(value: int) -> bytes:
            result = bytearray()
            while value >= 0x80:
                result.append((value & 0x7F) | 0x80)
                value >>= 7
            result.append(value)
            return bytes(result)

        row = struct.pack("<IHHIHH", 0, 20480, 1, 960, 499, 0) + bytes(64)
        event = bytes([233]) + varint(len(row)) + row
        header = bytearray(22)
        header[:4] = b"FLhd"
        header[14:18] = b"FLdt"
        struct.pack_into("<I", header, 18, len(event))
        original = bytes(header) + event
        source_tail = bytearray(48)
        source_tail[0] = 7

        rewritten, metrics = replace_one_tail_byte(original, [bytes(source_tail)], 0)

        differing = [i for i, (left, right) in enumerate(zip(original, rewritten)) if left != right]
        self.assertEqual(len(differing), 1)
        self.assertEqual(rewritten[differing[0]], 7)
        self.assertEqual(metrics["changed_tail_bytes"], 1)

    def test_flp_playlist_stride_probe_profiles_80_byte_candidates(self) -> None:
        def record(channel_id: int) -> bytes:
            return struct.pack("<IHHIHH", 120, 99, channel_id, 480, 497, 0) + bytes(64)

        profiles = stride_hypotheses([record(3) + record(5)], {3, 5})

        self.assertEqual(profiles["80"]["record_count"], 2)
        self.assertEqual(profiles["80"]["audio_channel_link_count"], 2)
        self.assertLess(profiles["32"]["audio_channel_link_count"], 2)
        self.assertEqual(profiles["60"]["record_count"], 0)

    def test_flp_playlist_profile_metrics_compare_only_supplied_stride_rows(self) -> None:
        fields = {
            "pattern_base": 20480,
            "item_index": 3,
            "length": 960,
            "track_rvidx": 498,
            "group": 0,
            "u1": bytes((120, 0)),
            "flags": 64,
            "u2": bytes((64, 100, 128, 128)),
            "start_offset": -1.0,
            "end_offset": -1.0,
        }
        candidate = {"size": 80, **fields}
        wrong_stride_reference = {"size": 32, **fields}
        matching_reference = {"size": 80, **fields}

        metrics = _profile_metrics([candidate], [matching_reference], 80)
        wrong_stride_metrics = _profile_metrics([candidate], [wrong_stride_reference], 80)

        self.assertEqual(metrics["candidate_rows_with_reference_static_profile"], 1)
        self.assertEqual(wrong_stride_metrics["candidate_rows_with_reference_static_profile"], 0)
        self.assertEqual(wrong_stride_metrics["reference_audio_rows"], 0)
        self.assertEqual(metrics["candidate_audio_rows"], 1)
        self.assertNotIn("item_index", json.dumps(metrics))

    def test_keyed_archive_inventory_reports_schema_without_values(self) -> None:
        private_value = "PRIVATE_TRACK_NAME_7ab3"
        archive = {
            "$objects": [
                "$null",
                {"$classname": "ExampleTrack", "$classes": ["ExampleTrack", "NSObject"]},
                {"$class": plistlib.UID(1), "displayName": private_value},
            ],
            "$top": {"root": plistlib.UID(2)},
        }

        report = profile_keyed_archive(archive)

        self.assertEqual(report["class_counts"], {"ExampleTrack": 1})
        self.assertEqual(report["fields_by_class"]["ExampleTrack"], {"displayName": 1})
        self.assertNotIn(private_value, json.dumps(report))
        self.assertNotIn("object_indices", json.dumps(report))

    def test_trak_uuid_logic_probe_finds_external_chunk_reference_without_value(self) -> None:
        identifier = uuid.UUID("00112233-4455-6677-8899-aabbccddeeff")
        trak = bytearray(58)
        trak[0x18:0x28] = identifier.bytes
        payload = bytes(trak) + identifier.bytes
        chunks = [
            {"index": 0, "type": "Trak", "payload_offset": 0, "payload_size": 58},
            {"index": 1, "type": "AuRg", "payload_offset": 58, "payload_size": 16},
        ]

        report = additional_uuid_occurrences(payload, chunks)

        self.assertEqual(report["track_uuid_field_count"], 1)
        self.assertEqual(report["distinct_track_uuid_count"], 1)
        self.assertEqual(report["track_uuid_fields_with_additional_payload_occurrences"], 1)
        self.assertEqual(report["additional_payload_occurrence_count"], 1)
        self.assertEqual(report["additional_occurrences_by_chunk_type"], {"AuRg": 1})
        self.assertNotIn(str(identifier), json.dumps(report))

    def test_trak_uuid_archive_probe_counts_references_without_values(self) -> None:
        identifier = uuid.UUID("00112233-4455-6677-8899-aabbccddeeff")
        other = uuid.UUID("ffeeddcc-bbaa-9988-7766-554433221100")
        objects = [
            "$null",
            {"CBData": plistlib.UID(2)},
            {"NS.keys": [plistlib.UID(3)], "NS.objects": [plistlib.UID(4)]},
            "previousCurrentTrackUUID",
            {"NS.string": "{" + str(identifier) + "}"},
        ]
        root = {
            "$objects": objects,
            "$top": {"DfDocument arrange model": plistlib.UID(1)},
        }
        report = profile_archive_references(
            root,
            {identifier, other},
            [{"identifier": str(identifier)}, {"opaque": other.bytes}],
        )

        self.assertEqual(report["track_uuid_count"], 2)
        self.assertEqual(report["projectdata_string_matched_uuid_count"], 1)
        self.assertTrue(report["previous_current_track_uuid_matches_trak_field"])
        self.assertEqual(report["companion_plist_count"], 2)
        self.assertEqual(report["companion_plist_string_matched_uuid_count"], 1)
        self.assertEqual(report["companion_plist_bytes_matched_uuid_count"], 1)
        self.assertNotIn(str(identifier), json.dumps(report))
        self.assertNotIn(str(other), json.dumps(report))

    def test_trak_group_probe_profiles_only_opaque_group_buckets(self) -> None:
        chunks = [
            {"type": "Trak", "payload_size": 58, "group_id_candidate": 10},
            {"type": "Trak", "payload_size": 58, "group_id_candidate": 10},
            {"type": "AuRg", "payload_size": 20, "group_id_candidate": 10},
            {"type": "AuCO", "payload_size": 24, "group_id_candidate": 20},
        ]
        events = [
            {"type_byte": 0x24, "group_id_candidate": 10},
            {"type_byte": 0x20, "group_id_candidate": 20},
        ]

        report = summarize_trak_groups(chunks, events)

        self.assertEqual(report["trak58_group_count"], 1)
        self.assertEqual(report["profiles"], [{
            "group_bucket": 1,
            "trak58_count": 2,
            "midi_type20_event_count": 0,
            "audio_type24_event_count": 1,
            "AuCO_chunk_count": 0,
            "AuFl_chunk_count": 0,
            "AuRg_chunk_count": 1,
            "MSeq_chunk_count": 0,
        }])
        self.assertNotIn("10", json.dumps(report))

    def test_midi_track_value_ordinal_probe_checks_zero_and_one_based_orders(self) -> None:
        chunks = [
            {"type": "MSeq", "index": 0, "group_id_candidate": 10, "payload_size": 100},
            {"type": "Trak", "index": 1, "group_id_candidate": 10, "payload_size": 0},
            {"type": "MSeq", "index": 2, "group_id_candidate": 20, "payload_size": 100},
            {"type": "Trak", "index": 3, "group_id_candidate": 20, "payload_size": 0},
        ]
        placements = [
            {
                "track_value_candidate": 0,
                "candidate_mseq_chunk_indices": [0],
                "same_group_trak_chunk_indices_candidate": [1],
            },
            {
                "track_value_candidate": 2,
                "candidate_mseq_chunk_indices": [2],
                "same_group_trak_chunk_indices_candidate": [3],
            },
        ]

        report = profile_midi_track_value_ordinals(chunks, placements)

        self.assertEqual(report["mseq_chunk_eligible_count"], 2)
        self.assertEqual(report["mseq_chunk_zero_based_exact_match_count"], 1)
        self.assertEqual(report["mseq_chunk_one_based_exact_match_count"], 1)
        self.assertEqual(report["empty_trak_chunk_zero_based_exact_match_count"], 1)
        self.assertEqual(report["empty_trak_chunk_one_based_exact_match_count"], 1)
        self.assertEqual(report["unique_mseq_group_zero_based_exact_match_count"], 1)
        self.assertEqual(report["unique_mseq_group_one_based_exact_match_count"], 1)

    def test_audio_track_index_probe_reports_bounds_without_project_values(self) -> None:
        project = SimpleNamespace(
            declared_track_count=4,
            tracks=[
                Track(index=1, regions=[Region(kind="audio")]),
                Track(index=3, regions=[Region(kind="audio"), Region(kind="audio")]),
                Track(index=2, regions=[Region(kind="midi")]),
            ],
        )

        report = profile_audio_track_indices(project)

        self.assertEqual(report["audio_track_count"], 2)
        self.assertEqual(report["audio_region_count"], 3)
        self.assertEqual(report["audio_track_index_min"], 1)
        self.assertEqual(report["audio_track_index_max"], 3)
        self.assertTrue(report["all_audio_indices_below_declared_count"])

    def test_audio_placement_timing_probe_profiles_unknown_word_without_semantics(self) -> None:
        report = profile_audio_timing_candidates([
            {"u32_at_0x1c_candidate": 122_880},
            {"u32_at_0x1c_candidate": 0x3FFFFFFF},
            {"u32_at_0x1c_candidate": 30_720},
            {"u32_at_0x1c_candidate": 17},
            {"other": "ignored"},
        ])

        self.assertEqual(report["placement_count"], 5)
        self.assertEqual(report["candidate_count"], 4)
        self.assertEqual(report["sentinel_count"], 1)
        self.assertEqual(report["finite_nonzero_count"], 3)
        self.assertEqual(report["finite_values_on_960_tick_grid"], 2)
        self.assertIn("UNKNOWN", report["interpretation"])
        self.assertNotIn("path", report)

    def test_audio_name_chunk_probe_counts_length_framed_strings_privately(self) -> None:
        name_alpha = "SyntheticLoopAlpha"
        name_beta = "SyntheticLoopBeta"
        name_false = "SyntheticLoopFalse"

        def loop_record(name: str, is_family_loop: bool) -> bytes:
            return plistlib.dumps(
                {"IsFamilyLoop": is_family_loop, "LoopFamilyName": name},
                fmt=plistlib.FMT_BINARY,
                sort_keys=False,
            )

        alpha_record = loop_record(name_alpha, True)
        beta_record = loop_record(name_beta, True)
        false_record = loop_record(name_false, False)
        payload = bytearray()
        chunks = []
        for index, (chunk_type, group, body) in enumerate([
            ("AuFl", 7, bytes((len(name_alpha),)) + name_alpha.encode()),
            ("AuRg", 7, name_alpha.encode()),
            ("SngO", 8, alpha_record + beta_record),
            ("GenM", 9, alpha_record + alpha_record),
            ("AuFl", 10, bytes((len(name_beta),)) + name_beta.encode()),
            ("TstF", 11, false_record),
        ], start=10):
            offset = len(payload)
            payload.extend(body)
            chunks.append({
                "index": index,
                "type": chunk_type,
                "group_id_candidate": group,
                "payload_offset": offset,
                "payload_size": len(body),
            })
        references = [
            MediaReference(
                index=0, category="AudioFiles", reference=f"external/{name_alpha}.caf",
                source_chunk_index=10,
            ),
            MediaReference(
                index=1, category="AudioFiles", reference=f"external/{name_beta}.caf",
                source_chunk_index=14,
            ),
            MediaReference(
                index=2, category="AudioFiles", reference=f"external/{name_false}.caf",
                source_chunk_index=15,
            ),
            MediaReference(index=3, category="OtherFiles", reference="external/Ignore.caf"),
        ]

        report = profile_audio_name_chunks(references, chunks, bytes(payload))

        self.assertEqual(report["audio_reference_count"], 3)
        self.assertEqual(report["unique_filename_stem_count"], 3)
        self.assertEqual(report["chunk_type_matches"]["AuFl"]["same_source_group_occurrence_count"], 2)
        self.assertEqual(report["chunk_type_matches"]["AuRg"]["same_source_group_occurrence_count"], 1)
        self.assertEqual(report["chunk_type_matches"]["SngO"]["matched_reference_count"], 2)
        self.assertEqual(report["chunk_type_matches"]["GenM"]["string_occurrence_count"], 2)
        self.assertEqual(report["chunk_type_matches"]["GenM"]["preceding_byte_equals_utf8_length_count"], 2)
        self.assertEqual(
            report["chunk_type_matches"]["SngO"]["bplist_extended_ascii_string_marker_match_count"],
            2,
        )
        self.assertEqual(
            report["chunk_type_matches"]["GenM"]["bplist_extended_ascii_string_marker_match_count"],
            2,
        )
        self.assertEqual(
            report["chunk_type_matches"]["SngO"]["name_after_bplist_true_marker_count"],
            2,
        )
        self.assertEqual(
            report["chunk_type_matches"]["GenM"]["name_after_bplist_true_marker_count"],
            2,
        )
        self.assertEqual(
            report["chunk_type_matches"]["SngO"]["loop_metadata_record_pattern_match_count"],
            2,
        )
        self.assertEqual(
            report["chunk_type_matches"]["GenM"]["loop_metadata_record_pattern_match_count"],
            2,
        )
        self.assertEqual(
            report["chunk_type_matches"]["TstF"]["name_after_bplist_false_marker_count"],
            1,
        )
        self.assertEqual(
            report["chunk_type_matches"]["TstF"]["loop_metadata_record_pattern_match_count"],
            0,
        )
        self.assertEqual(
            report["chunk_type_matches"]["SngO"]["matched_chunk_with_both_loop_keys_count"],
            1,
        )
        self.assertEqual(
            report["chunk_type_matches"]["GenM"]["matched_chunk_with_both_loop_keys_count"],
            1,
        )
        self.assertEqual(
            report["ordering_comparisons"]["SngO"]["pairwise_order_agreements_with_reference_list"],
            1,
        )
        self.assertEqual(
            report["ordering_comparisons"]["SngO"]["pairwise_order_agreements_with_source_chunks"],
            1,
        )
        self.assertEqual(
            report["group_candidate_intersections"]["GenM/SngO"]["common_stem_count"],
            1,
        )
        self.assertEqual(report["loop_family_source_join_candidates"], {
            "audio_reference_count": 3,
            "references_with_at_least_one_family_pattern_in_both_count": 1,
            "references_with_exactly_one_family_pattern_in_both_count": 0,
            "references_with_multiple_family_patterns_in_either_count": 1,
            "references_missing_a_family_pattern_in_either_count": 2,
        })
        self.assertEqual(
            report["group_candidate_intersections"]["GenM/SngO"]["stems_with_shared_group_candidate_count"],
            0,
        )
        self.assertNotIn(name_alpha, json.dumps(report))
        self.assertNotIn(name_beta, json.dumps(report))
        self.assertNotIn(name_false, json.dumps(report))

    def test_arrange_ui_probe_reports_inspector_shape_without_values(self) -> None:
        objects = [
            "$null",
            {"CBData": plistlib.UID(2)},
            {"NS.keys": [plistlib.UID(3)], "NS.objects": [plistlib.UID(4)]},
            "CbTrackInspectorInternalState",
            {"NS.keys": [plistlib.UID(5)], "NS.objects": [plistlib.UID(6)]},
            "CbMasterEffectsEchoSectionOpen",
            True,
        ]
        root = {
            "$objects": objects,
            "$top": {"DfDocument arrange model": plistlib.UID(1)},
        }

        report = profile_arrange_ui(root)

        self.assertTrue(report["track_inspector_state_found"])
        self.assertEqual(report["track_inspector_state_fields"], [
            {"key": "CbMasterEffectsEchoSectionOpen", "value_type": "bool"},
        ])
        self.assertNotIn("True", json.dumps(report))

    def test_selected_track_uuid_probe_resolves_keyed_archive_reference(self) -> None:
        selected = uuid.UUID("00112233-4455-6677-8899-aabbccddeeff")
        objects = [
            "$null",
            {"CBData": plistlib.UID(2)},
            {"NS.keys": [plistlib.UID(3)], "NS.objects": [plistlib.UID(4)]},
            "previousCurrentTrackUUID",
            {"NS.string": str(selected)},
        ]
        root = {
            "$objects": objects,
            "$top": {"DfDocument arrange model": plistlib.UID(1)},
        }

        self.assertEqual(selected_track_uuid(root), selected)

    def test_track_uuid_probe_matches_payload_bytes_without_returning_uuid(self) -> None:
        selected = uuid.UUID("00112233-4455-6677-8899-aabbccddeeff")
        payload = bytes(24) + selected.bytes + bytes(18)
        chunks = {"chunks": [{"type": "Trak", "payload_offset": 0, "payload_size": len(payload)}]}

        matches = find_uuid_payload_matches(payload, chunks, selected)

        self.assertEqual(matches, [{
            "chunk_index": 0,
            "chunk_type": "Trak",
            "chunk_payload_size": 58,
            "payload_offset": 24,
            "encoding": "uuid_bytes",
        }])
        self.assertNotIn(str(selected), repr(matches))

    def test_track_uuid_probe_finds_repeated_occurrences_in_one_chunk(self) -> None:
        selected = uuid.UUID("00112233-4455-6677-8899-aabbccddeeff")
        payload = bytes(24) + selected.bytes + bytes(2) + selected.bytes + bytes(16)
        chunks = {"chunks": [{"type": "Trak", "payload_offset": 0, "payload_size": len(payload)}]}

        matches = find_uuid_payload_matches(payload, chunks, selected)

        self.assertEqual([match["payload_offset"] for match in matches], [24, 42])

    def test_track_uuid_probe_scans_ascii_and_utf16_text_forms(self) -> None:
        selected = uuid.UUID("00112233-4455-6677-8899-aabbccddeeff")
        payload = str(selected).encode("ascii") + str(selected).encode("utf-16-le")
        chunks = {"chunks": [{"type": "Test", "payload_offset": 0, "payload_size": len(payload)}]}

        matches = find_uuid_payload_matches(payload, chunks, selected)

        self.assertEqual(
            [(match["payload_offset"], match["encoding"]) for match in matches],
            [(0, "uuid_ascii"), (36, "uuid_utf16le")],
        )

    def test_track_uuid_probe_profiles_trak_uuid_fields_without_values(self) -> None:
        identifier = uuid.UUID("00112233-4455-1677-8899-aabbccddeeff")
        payload = bytes(24) + identifier.bytes + bytes(18)
        chunks = {"chunks": [{"type": "Trak", "payload_offset": 0, "payload_size": len(payload)}]}

        profile = trak_uuid_field_profile(payload, chunks)

        self.assertEqual(profile["58_byte_trak_count"], 1)
        self.assertEqual(profile["unique_payload_0x18_values"], 1)
        self.assertEqual(profile["payload_0x18_uuid_variant_counts"], {"specified in RFC 4122": 1})
        self.assertEqual(profile["payload_0x18_uuid_version_counts"], {"1": 1})
        self.assertNotIn(str(identifier), repr(profile))

    def test_flp_playlist_event_reader_extracts_bounded_payload(self) -> None:
        events = bytes((233, 4)) + b"clip" + bytes((42, 7))
        header = b"FLhd" + struct.pack("<Ih2H", 6, 0, 0, 96)
        data = header + b"FLdt" + struct.pack("<I", len(events)) + events

        self.assertEqual(playlist_event_data(data), [b"clip"])

    def test_flp_playlist_event_reader_rejects_truncated_lengths(self) -> None:
        events = bytes((233, 5)) + b"clip"
        header = b"FLhd" + struct.pack("<Ih2H", 6, 0, 0, 96)
        data = header + b"FLdt" + struct.pack("<I", len(events)) + events

        with self.assertRaisesRegex(ValueError, "extends beyond the file boundary"):
            playlist_event_data(data)

    def test_flp_playlist_rows_reserve_row_zero_and_validate_range(self) -> None:
        self.assertEqual(_fl_playlist_track_index(0, 500), 1)
        self.assertEqual(_fl_playlist_track_index(5, 500), 6)
        self.assertEqual(_fl_track_event_storage_index(1, 500), 2)
        self.assertEqual(_fl_track_event_storage_index(6, 500), 7)
        with self.assertRaisesRegex(FLPExportError, "outside the template playlist range"):
            _fl_playlist_track_index(-1, 500)
        with self.assertRaisesRegex(FLPExportError, "outside the template playlist range"):
            _fl_playlist_track_index(499, 500)
        with self.assertRaisesRegex(FLPExportError, "outside the template playlist range"):
            _fl_track_event_storage_index(499, 500)

    def test_flp_export_selects_base_playlist_record_layout(self) -> None:
        playlist = SimpleNamespace(_kwds={"new": True})

        _select_base_playlist_record_layout(playlist)

        self.assertFalse(playlist._kwds["new"])
        with self.assertRaisesRegex(FLPExportError, "cannot select the base playlist"):
            _select_base_playlist_record_layout(SimpleNamespace())

    def test_flp_clock_roundtrip_checks_recovered_tempo_and_meter(self) -> None:
        roundtrip = SimpleNamespace(
            tempo=137.5,
            arrangements=SimpleNamespace(time_signature=SimpleNamespace(num=7, beat=8)),
        )
        project = Project(tempo_bpm=137.5, time_signature=(7, 8))

        report = _validate_clock_roundtrip(roundtrip, project)

        self.assertTrue(report["tempo_matches_input"])
        self.assertTrue(report["time_signature_matches_input"])
        self.assertEqual(report["time_signature"], [7, 8])

    def test_flp_clock_roundtrip_rejects_changed_tempo_or_meter(self) -> None:
        roundtrip = SimpleNamespace(
            tempo=120.0,
            arrangements=SimpleNamespace(time_signature=SimpleNamespace(num=4, beat=4)),
        )
        with self.assertRaisesRegex(FLPExportError, "changed or lost the project tempo"):
            _validate_clock_roundtrip(roundtrip, Project(tempo_bpm=121.0, time_signature=(4, 4)))
        with self.assertRaisesRegex(FLPExportError, "changed or lost the project time signature"):
            _validate_clock_roundtrip(roundtrip, Project(tempo_bpm=120.0, time_signature=(3, 4)))

    def test_flp_roundtrip_rejects_changed_audio_sample_path(self) -> None:
        expected = Path("media") / "audio-001.wav"
        _validate_sample_path_roundtrip(str(expected), expected)
        with self.assertRaisesRegex(FLPExportError, "changed an audio clip sample path"):
            _validate_sample_path_roundtrip("media/audio-006.caf", expected)

    def test_flp_beat_conversion_preserves_exact_fractional_ticks(self) -> None:
        self.assertEqual(_beats_to_ticks("1/3", 96, "start"), 32)
        self.assertEqual(_beats_to_ticks("1/192", 96, "start"), 0)
        with self.assertRaisesRegex(FLPExportError, "finite beat value"):
            _beats_to_ticks("not-a-beat", 96, "start")

    def test_flp_midi_note_record_targets_channel_iid(self) -> None:
        record = _pack_midi_note_candidate(96, 48, 65, 100, 7)
        decoded = struct.unpack("<IHHIHH8B", record)
        self.assertEqual(decoded[:6], (96, 0x4000, 7, 48, 65, 0))
        self.assertEqual(decoded[11], 100)

    def test_midi_preview_name_uses_bounded_candidate_label(self) -> None:
        labeled = SimpleNamespace(label_candidate="  Synth\nKeys  ")
        unlabeled = SimpleNamespace(label_candidate=None)
        long_label = SimpleNamespace(label_candidate="x" * 100)

        self.assertEqual(_midi_candidate_display_name(labeled, 0), "MIDI candidate 01 - Synth Keys")
        self.assertEqual(_midi_candidate_display_name(unlabeled, 1), "MIDI candidate 02")
        self.assertEqual(
            len(_midi_candidate_display_name(long_label, 2)),
            len("MIDI candidate 03 - ") + 80,
        )

    def test_flp_audio_info_reads_wave_frame_rate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "short.wav"
            with wave.open(str(path), "wb") as output:
                output.setparams((1, 2, 48_000, 12, "NONE", "not compressed"))
                output.writeframes(bytes(24))
            self.assertEqual(audio_info(path), AudioInfo(frames=12, sample_rate=48_000))

    def test_flp_audio_info_reads_caf_packet_table(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "short.caf"
            description = struct.pack(">d4sIIIIII", 44_100.0, b"aac ", 0, 0, 1024, 0, 1, 16)
            packet_table = bytes(8) + struct.pack(">q", 1234) + bytes(8)
            path.write_bytes(
                b"caff" + struct.pack(">HH", 1, 0)
                + b"desc" + struct.pack(">q", len(description)) + description
                + b"pakt" + struct.pack(">q", len(packet_table)) + packet_table
            )
            self.assertEqual(audio_info(path), AudioInfo(frames=1234, sample_rate=44_100))

    def test_flp_export_rejects_unknown_region_length_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template = root / "template.flp"
            template.write_bytes(b"template placeholder")
            project = Project(tracks=[Track(index=0, regions=[Region(kind="audio", source="asset", start_beats="0")])])
            with self.assertRaisesRegex(FLPExportError, "durations are unknown"):
                export_flp(
                    project,
                    template_path=template,
                    output_path=root / "out.flp",
                    media_by_reference={},
                    length_policy="reject-unknown",
                )

    def test_extract_referenced_audio_reports_unembedded_references_without_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_path = Path(directory) / "fixture.band"
            output_dir = Path(directory) / "not-created"
            make_fixture(project_path)

            report = extract_referenced_audio(project_path, output_dir)

            self.assertEqual(report["extracted"], [])
            self.assertEqual(report["unresolved_audio_reference_count"], 1)
            self.assertFalse(output_dir.exists())

    def test_extract_referenced_audio_uses_safe_generated_names_and_no_overwrite(self) -> None:
        payload = b"synthetic audio payload"
        with tempfile.TemporaryDirectory() as directory:
            project_path = Path(directory) / "fixture.band"
            output_dir = Path(directory) / "extracted"
            make_fixture(
                project_path,
                include_audio_placement=True,
                embedded_audio=payload,
                audio_reference="${CONTENT:../private/example.caf",
            )

            report = extract_referenced_audio(project_path, output_dir)

            self.assertEqual(report["unresolved_audio_reference_count"], 0)
            self.assertEqual(report["extracted"][0]["file"], "audio-001.caf")
            extracted_path = output_dir / report["extracted"][0]["file"]
            self.assertEqual(extracted_path.read_bytes(), payload)
            with self.assertRaises(MediaExtractionError):
                extract_referenced_audio(project_path, output_dir)
            self.assertEqual(extracted_path.read_bytes(), payload)

    def test_extract_referenced_audio_can_transcode_to_valid_wav(self) -> None:
        audio = io.BytesIO()
        with wave.open(audio, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(44_100)
            output.writeframes(bytes(32))
        wav_bytes = audio.getvalue()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "fixture.band"
            output_dir = root / "transcoded"
            transcoder = root / "ffmpeg-test.exe"
            transcoder.touch()
            make_fixture(
                project_path,
                include_audio_placement=True,
                embedded_audio=wav_bytes,
                audio_file_name="example.wav",
            )

            def fake_transcode(args: list[str], **kwargs: object) -> SimpleNamespace:
                source = Path(args[args.index("-i") + 1])
                destination = Path(args[-1])
                self.assertNotEqual(source, destination)
                destination.write_bytes(source.read_bytes())
                self.assertFalse(kwargs.get("shell"))
                self.assertIn("-nostdin", args)
                self.assertIn("pcm_s16le", args)
                self.assertIn("-fs", args)
                return SimpleNamespace(returncode=0)

            with patch("band2flp.media.subprocess.run", side_effect=fake_transcode):
                report = extract_referenced_audio(
                    project_path, output_dir, to_wav=True, transcoder=str(transcoder)
                )

            self.assertEqual(report["extracted"][0]["file"], "audio-001.wav")
            self.assertEqual(report["extracted"][0]["transcoded_to"], "WAVE PCM 16-bit")
            self.assertEqual(sorted(path.name for path in output_dir.iterdir()), ["audio-001.wav"])
            with wave.open(str(output_dir / "audio-001.wav"), "rb") as converted:
                self.assertEqual(converted.getnframes(), 16)

    def test_wav_transcode_failure_does_not_publish_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "fixture.band"
            output_dir = root / "transcoded"
            transcoder = root / "ffmpeg-test.exe"
            transcoder.touch()
            make_fixture(
                project_path,
                include_audio_placement=True,
                embedded_audio=b"synthetic audio payload",
            )
            with patch(
                "band2flp.media.subprocess.run",
                return_value=SimpleNamespace(returncode=1),
            ):
                with self.assertRaisesRegex(MediaExtractionError, "could not convert"):
                    extract_referenced_audio(
                        project_path, output_dir, to_wav=True, transcoder=str(transcoder)
                    )
            self.assertFalse(output_dir.exists())

    def test_wav_transcode_requires_explicitly_available_ffmpeg(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "fixture.band"
            output_dir = root / "transcoded"
            make_fixture(project_path)
            with self.assertRaisesRegex(MediaExtractionError, "requires FFmpeg"):
                extract_referenced_audio(
                    project_path, output_dir, to_wav=True,
                    transcoder="band2flp-test-transcoder-unavailable",
                )
            self.assertFalse(output_dir.exists())

    def test_wav_transcode_timeout_does_not_publish_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "fixture.band"
            output_dir = root / "transcoded"
            transcoder = root / "ffmpeg-test.exe"
            transcoder.touch()
            make_fixture(
                project_path,
                include_audio_placement=True,
                embedded_audio=b"synthetic audio payload",
            )
            timeout = subprocess.TimeoutExpired("ffmpeg-test", 300)
            with patch("band2flp.media.subprocess.run", side_effect=timeout):
                with self.assertRaisesRegex(MediaExtractionError, "five-minute limit"):
                    extract_referenced_audio(
                        project_path, output_dir, to_wav=True, transcoder=str(transcoder)
                    )
            self.assertFalse(output_dir.exists())

    def test_audio_frame_probe_reads_wave_sample_frames(self) -> None:
        fmt = struct.pack("<HHIIHH", 1, 2, 44_100, 176_400, 4, 16)
        data = bytes(40)
        body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
        body += b"data" + struct.pack("<I", len(data)) + data
        wave = b"RIFF" + struct.pack("<I", len(body)) + body
        self.assertEqual(audio_frame_count(wave), (10, "WAVE"))
        self.assertEqual(audio_sample_rate(wave), 44_100)

    def test_audio_frame_probe_reads_aiff_comm_count(self) -> None:
        comm = struct.pack(">HIH", 2, 1234, 16) + bytes.fromhex("400eac44000000000000")
        body = b"AIFF" + b"COMM" + struct.pack(">I", len(comm)) + comm
        aiff = b"FORM" + struct.pack(">I", len(body)) + body
        self.assertEqual(audio_frame_count(aiff), (1234, "AIFF"))
        self.assertEqual(audio_sample_rate(aiff), 44_100)

    def test_audio_frame_probe_reads_caf_valid_frame_count(self) -> None:
        packet_table = struct.pack(">qqii", 100, 9876, 0, 0)
        caf = b"caff" + struct.pack(">HH", 1, 0)
        caf += b"pakt" + struct.pack(">q", len(packet_table)) + packet_table
        self.assertEqual(audio_frame_count(caf), (9876, "CAF-packet-table"))
        self.assertEqual(audio_sample_rate(caf), None)

    def test_audio_frame_probe_reads_caf_fixed_packet_count(self) -> None:
        description = struct.pack(">d4sIIIII", 44_100.0, b"lpcm", 0, 2, 1, 2, 16)
        audio_data = struct.pack(">I", 0) + bytes(20)
        caf = b"caff" + struct.pack(">HH", 1, 0)
        caf += b"desc" + struct.pack(">q", len(description)) + description
        caf += b"data" + struct.pack(">q", len(audio_data)) + audio_data
        self.assertEqual(audio_frame_count(caf), (10, "CAF-fixed-packet"))
        self.assertEqual(audio_sample_rate(caf), 44_100)

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

    def test_trak_probe_reports_aggregate_shapes_without_payload_text(self) -> None:
        payloads = [
            b"\x01\x00\x14\x00\x00\x00\x00\x00" + b"Private Track Name".ljust(50, b"\x00"),
            b"\x01\x00\x14\x00\x00\x00\x00\x00" + b"Other Private Name".ljust(50, b"\x00"),
            b"\x01\x00\x15\x00\x00\x00\x00\x00" + bytes(50),
        ]
        raw = bytes.fromhex("2347c0ab") + bytes(20)
        for payload in (b"", *payloads):
            chunk = bytearray(make_chunk("Trak", 0, payload))
            struct.pack_into("<H", chunk, 14, 0xFFFF)
            raw += bytes(chunk)
        raw += make_chunk("MSeq", 0, b"midi-data")

        result = probe_trak_logic_payload(raw, _parse_chunk_stream(raw))

        self.assertEqual(result["trak_count"], 4)
        self.assertEqual(result["payload_size_counts"], {"0": 1, "58": 3})
        self.assertEqual(result["header_u16_at_0x0e_counts"], {"0xFFFF": 4})
        self.assertEqual(result["payload_prefix_summaries"]["58"], {
            "record_count": 3,
            "distinct_first_8_byte_prefixes": 2,
            "most_common_first_8_byte_prefix_count": 2,
            "longest_common_prefix_length": 2,
        })
        self.assertNotIn("Private Track Name", json.dumps(result))
        self.assertIn("UNKNOWN", result["interpretation"])
        self.assertTrue(result["mseq_empty_trak_group_candidates"]["group_value_multiplicities_match"])
        self.assertEqual(result["mseq_empty_trak_group_candidates"]["distinct_mseq_group_values"], 1)

        unmatched = raw + make_chunk("MSeq", 0x10000, b"more-midi-data")
        unmatched_result = probe_trak_logic_payload(unmatched, _parse_chunk_stream(unmatched))
        self.assertFalse(unmatched_result["mseq_empty_trak_group_candidates"]["group_value_multiplicities_match"])
        self.assertEqual(unmatched_result["mseq_empty_trak_group_candidates"]["mseq_groups_without_empty_trak"], 1)

    def test_event_inventory_reports_only_aggregate_shapes(self) -> None:
        records = [
            {"type_byte": 0x91, "length": 64, "group_id_candidate": 0x12340000,
             "raw_hex": "50524956415445204556454e542056414c5545"},
            {"type_byte": 0x91, "length": 80, "group_id_candidate": 0,
             "raw_hex": "534543524554204556454e542056414c5545"},
            {"type_byte": 0xF1, "length": 16, "group_id_candidate": 0,
             "raw_hex": "4e4f5420464f52205055424c49434154494f4e"},
        ]
        result = inventory_records(records)
        self.assertEqual(result["event_record_count"], 3)
        self.assertEqual(result["event_types"]["0x91"]["record_lengths"], {"64": 1, "80": 1})
        self.assertEqual(result["event_types"]["0x91"]["distinct_group_candidate_count"], 2)
        self.assertEqual(result["event_types"]["0x91"]["zero_group_record_count"], 1)
        rendered = json.dumps(result)
        self.assertNotIn("PRIVATE", rendered)
        self.assertNotIn("SECRET", rendered)
        self.assertNotIn("12340000", rendered)
        with self.assertRaises(BandFormatError):
            inventory_records([{**records[0], "length": 63}])

    def test_tempo_group_association_probe_links_only_source_events_and_counts(self) -> None:
        records = [
            {"type_byte": 0x60, "group_id_candidate": 7, "chunk_index": 1, "event_index": 0, "position_raw": 20},
            {"type_byte": 0x20, "group_id_candidate": 7, "chunk_index": 1, "event_index": 1, "position_raw": 20},
            {"type_byte": 0x24, "group_id_candidate": 7, "chunk_index": 1, "event_index": 2, "position_raw": 20},
        ]
        report = profile_tempo_group_associations(
            [{"source_group_id_candidate": 7, "bpm": 120.0, "position_raw": 20}],
            records,
            [{"source_chunk_index": 1, "source_event_index": 2, "position_raw": 20}],
            [{"source_chunk_index": 1, "source_event_index": 1, "position_raw": 20}],
            [
                {"type": "MSeq", "group_id_candidate": 7, "payload_size": 64},
                {"type": "Trak", "group_id_candidate": 7, "payload_size": 0},
            ],
            160.0,
        )

        nonzero = report["nonzero_group"]
        self.assertEqual(nonzero["tempo_candidate_count"], 1)
        self.assertEqual(nonzero["tempo_candidates_matching_summary_count"], 0)
        self.assertEqual(nonzero["source_type20_record_count"], 1)
        self.assertEqual(nonzero["source_type24_record_count"], 1)
        self.assertEqual(nonzero["linked_midi_placement_count"], 1)
        self.assertEqual(nonzero["linked_audio_placement_count"], 1)
        self.assertEqual(nonzero["tempo_position_matches_audio_start_count"], 1)
        self.assertEqual(nonzero["tempo_position_matches_midi_start_count"], 1)
        self.assertNotIn("120", json.dumps(report))

    def test_midi_event_family_probe_reports_unique_candidate_links_only(self) -> None:
        def status_record(status, length, velocity, pitch, duration):
            raw = bytearray(length)
            raw[0] = status
            raw[0x0B] = velocity
            raw[0x0C] = pitch
            raw[0x17] = 0x89
            struct.pack_into("<I", raw, 0x1C, duration)
            return {
                "type_byte": status,
                "length": length,
                "group_id_candidate": status,
                "raw_hex": raw.hex(),
            }

        records = [
            status_record(0x91, 64, 70, 60, 961),
            status_record(0x91, 80, 0, 128, 1920),
            status_record(0x92, 64, 100, 63, 0),
        ]
        records[0]["group_id_candidate"] = 0x10000
        records[1]["group_id_candidate"] = 0x20000
        records[2]["group_id_candidate"] = 0x30000
        chunks = [
            {"type": "MSeq", "index": 4, "group_id_candidate": 0x10000, "payload_size": 307},
            {"type": "MSeq", "index": 5, "group_id_candidate": 0x20000, "payload_size": 311},
            {"type": "MSeq", "index": 6, "group_id_candidate": 0x30000, "payload_size": 309},
            {"type": "MSeq", "index": 7, "group_id_candidate": 0x30000, "payload_size": 315},
        ]
        placements = [
            {"candidate_mseq_chunk_indices": [4], "source_chunk_index": 8, "source_event_index": 1},
            {"candidate_mseq_chunk_indices": [5], "source_chunk_index": 8, "source_event_index": 2},
            {"candidate_mseq_chunk_indices": [6, 7], "source_chunk_index": 9, "source_event_index": 1},
        ]

        report = profile_midi_event_families(records, chunks, placements, {0x10000})

        self.assertEqual(report["event_families"]["0x91"], {
            "record_count": 2,
            "record_length_counts": {"64": 1, "80": 1},
            "distinct_group_count": 2,
            "groups_with_one_MSeq_and_one_placement": 2,
        })
        self.assertEqual(
            report["event_families"]["0x92"]["groups_with_one_MSeq_and_one_placement"], 0
        )
        self.assertEqual(report["note_field_shape_candidates"], {
            "candidate_record_count": 3,
            "candidate_pitch_byte_in_midi_range_count": 2,
            "candidate_velocity_byte_in_nonzero_midi_range_count": 2,
            "candidate_duration_word_nonzero_count": 2,
            "candidate_duration_word_on_960_tick_grid_count": 1,
            "duration_ppq_divisibility_note": (
                "descriptive only; an integer tick duration need not be divisible by PPQ"
            ),
        })
        self.assertEqual(
            report["placed_mseq_clusters"]["payload_size_counts_by_event_presence"],
            {
                "both": {"group_count": 1, "payload_size_counts": {"307": 1}},
                "opaque_family_only": {"group_count": 1, "payload_size_counts": {"311": 1}},
            },
        )
        serialized = json.dumps(report)
        self.assertNotIn("65536", serialized)
        self.assertNotIn("group_id_candidate", serialized)
        self.assertNotIn("raw_hex", serialized)

    def test_midi_timing_probe_removes_chunk_header_from_logic_offsets(self) -> None:
        payload = bytearray(600)
        struct.pack_into("<I", payload, 100 + 0xF8, 0)
        struct.pack_into("<I", payload, 100 + 0x54, 0)
        struct.pack_into("<I", payload, 300 + 0xF8, 7)
        struct.pack_into("<I", payload, 300 + 0x54, 3840)
        chunks = [
            {"index": 1, "type": "MSeq", "payload_offset": 100, "payload_size": 0x120},
            {"index": 2, "type": "MSeq", "payload_offset": 300, "payload_size": 0x120},
        ]
        placements = [
            {"candidate_mseq_chunk_indices": [1], "position_ticks_from_origin_candidate": 0},
            {"candidate_mseq_chunk_indices": [2], "position_ticks_from_origin_candidate": 960},
        ]

        report = profile_record_relative_mseq_candidates(payload, chunks, placements)

        self.assertEqual(report, {
            "linked_mseqs_eligible_for_record_relative_fields": 2,
            "record_plus_0x11c_candidate_equals_placement_ticks": 1,
            "record_plus_0x11c_zero_to_zero_equalities": 1,
            "record_plus_0x11c_nonzero_position_equalities": 0,
            "record_relative_candidates_with_nonzero_placement_ticks": 1,
            "record_plus_0x78_candidate_zero_count": 1,
            "record_plus_0x78_candidate_distinct_value_count": 2,
        })

    def test_mseq_probe_reports_shapes_without_payload_bytes_or_values(self) -> None:
        first = b"A\x00B\x00C\x00D\x00" + bytes(292)
        second = b"A\x00B\x00C\x00D\x00" + bytes([1]) + bytes(291)
        result = summarize_payloads([first, second])
        self.assertEqual(result["mseq_count"], 2)
        self.assertEqual(result["longest_common_prefix_length"], 8)
        self.assertEqual(result["common_prefix_zero_byte_count"], 4)
        self.assertEqual(result["common_prefix_nonzero_byte_count"], 4)
        self.assertEqual(result["standard_midi_header_count"], 0)
        self.assertEqual(result["unassigned_tail_word_profiles"]["219"]["readable_count"], 2)
        serialized = json.dumps(result)
        self.assertNotIn("ABCDEFGH", serialized)

    def test_mseq_probe_rejects_out_of_bounds_payload(self) -> None:
        with self.assertRaises(BandFormatError):
            probe_mseq_logic_payload(b"short", {"chunks": [{"type": "MSeq", "payload_offset": 4, "payload_size": 2}]})

    def test_mseq_probe_profiles_common_prefix_outside_mseq_payloads(self) -> None:
        first = b"SHARED08first"
        second = b"SHARED08other"
        other = b"xxSHARED08"
        raw = first + second + other
        stream = {"chunks": [
            {"type": "MSeq", "payload_offset": 0, "payload_size": len(first)},
            {"type": "MSeq", "payload_offset": len(first), "payload_size": len(second)},
            {"type": "EvSq", "payload_offset": len(first) + len(second), "payload_size": len(other)},
        ]}

        result = probe_mseq_logic_payload(raw, stream)

        self.assertEqual(result["longest_common_prefix_length"], 8)
        self.assertEqual(result["other_chunk_payloads_starting_with_common_prefix"], 0)
        self.assertEqual(result["other_chunk_payloads_containing_common_prefix"], 1)
        self.assertEqual(result["logic_song_common_prefix_occurrence_count"], 3)
        self.assertEqual(result["common_prefix_occurrences_at_mseq_payload_starts"], 2)
        self.assertEqual(result["common_prefix_occurrences_outside_mseq_payload_starts"], 1)
        self.assertNotIn("SHARED08", json.dumps(result))

    def test_midi_event_variation_profiles_offsets_without_event_values(self) -> None:
        rows = [b"A" + bytes([value]) + bytes(14) for value in (1, 2, 2)]
        records = [
            {"type_byte": 0x90, "group_id_candidate": 7, "raw_hex": row.hex()}
            for row in rows
        ]
        records.append({"type_byte": 0x90, "group_id_candidate": 8, "raw_hex": rows[0].hex()})

        result = profile_midi_event_variation(records)

        family = result["families"]["0x90/16"]
        self.assertEqual(family["record_count"], 4)
        self.assertEqual(family["distinct_group_count"], 2)
        self.assertEqual(family["groups_with_multiple_records"], 1)
        self.assertEqual(family["varying_byte_offset_group_counts"], {"1": 1})
        self.assertNotIn(rows[0].hex(), json.dumps(result))

    def test_flp_playlist_state_probe_parses_bounded_event_spans(self) -> None:
        event_data = bytes([5, 9, 70, 1, 2, 128, 1, 2, 3, 4, 233, 3]) + b"abc"
        raw = bytearray(b"FLhd" + bytes(10) + b"FLdt" + struct.pack("<I", len(event_data)) + event_data)

        events = parse_flp_event_spans(bytes(raw))

        self.assertEqual([event["id"] for event in events], [5, 70, 128, 233])
        self.assertEqual([event["end"] - event["payload_start"] for event in events], [1, 2, 4, 3])
        self.assertNotIn(b"abc", json.dumps(events).encode())
        with self.assertRaises(FLPExportError):
            parse_flp_event_spans(bytes(raw[:-1]))

    def test_flp_playlist_bisect_preserves_selected_rows_and_other_events(self) -> None:
        rows = [bytes([index]) * 80 for index in (1, 2, 3)]
        payload = b"".join(rows)
        event_data = bytes((5, 9, 233, 0xf0, 0x01)) + payload + bytes((7, 4))
        source = b"FLhd" + bytes(10) + b"FLdt" + struct.pack("<I", len(event_data)) + event_data

        result = keep_playlist_rows(source, (0, 2))
        events = parse_flp_event_spans(result)
        self.assertEqual([event["id"] for event in events], [5, 233, 7])
        self.assertEqual(result[events[1]["payload_start"]:events[1]["end"]], rows[0] + rows[2])
        self.assertEqual(result[events[0]["payload_start"]:events[0]["end"]], b"\x09")
        self.assertEqual(result[events[2]["payload_start"]:events[2]["end"]], b"\x04")
        with self.assertRaises(FLPExportError):
            keep_playlist_rows(source, (1, 1))

    def test_flp_export_places_cloned_channel_before_playlist(self) -> None:
        event_data = bytes((64, 0, 0, 196, 1, 65, 233, 3)) + b"xyz" + bytes((64, 1, 0, 196, 1, 66, 47, 0))
        source = b"FLhd" + bytes(10) + b"FLdt" + struct.pack("<I", len(event_data)) + event_data

        result = _place_audio_channels_before_playlist(source, 2)
        events = parse_flp_event_spans(result)
        self.assertEqual([event["id"] for event in events], [64, 196, 64, 196, 233, 47])
        self.assertEqual(result[events[4]["payload_start"]:events[4]["end"]], b"xyz")
        self.assertEqual(len(result), len(source))
        with self.assertRaises(FLPExportError):
            _place_audio_channels_before_playlist(source, 3)

    def test_flp_export_places_silent_midi_channel_and_pattern_before_playlist(self) -> None:
        event_data = bytes((64, 0, 0, 233, 3)) + b"xyz" + bytes((64, 1, 0, 224, 1, 0, 47, 0))
        source = b"FLhd" + bytes(10) + b"FLdt" + struct.pack("<I", len(event_data)) + event_data

        result = _place_audio_channels_before_playlist(source, 2)
        events = parse_flp_event_spans(result)

        self.assertEqual([event["id"] for event in events], [64, 64, 224, 233, 47])
        self.assertEqual(result[events[3]["payload_start"]:events[3]["end"]], b"xyz")
        self.assertEqual(len(result), len(source))

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

    def test_corrupt_deflate_stream_raises_band_format_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "corrupt-deflate.band"
            make_fixture(fixture)
            raw = bytearray(fixture.read_bytes())
            with zipfile.ZipFile(fixture) as package:
                info = package.getinfo("fixture.band/projectData")
            filename_size, extra_size = struct.unpack_from("<HH", raw, info.header_offset + 26)
            compressed_start = info.header_offset + 30 + filename_size + extra_size
            # Deflate BTYPE=3 is reserved and forces the decompressor error path.
            raw[compressed_start] = 0x06
            fixture.write_bytes(raw)

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

    def test_mseq_length_framed_text_is_retained_as_a_candidate(self) -> None:
        label = "Synth A".encode("utf-8")
        region = bytearray(0x12 + len(label))
        struct.pack_into("<H", region, 0x10, len(label))
        region[0x12:] = label
        payload = bytes.fromhex("2347c0ab") + bytes(20)
        payload += make_chunk("MSeq", 0x00100000, bytes(region))
        payload += make_chunk("MSeq", 0x00140000, bytes(0x12))
        stream = _parse_chunk_stream(payload)
        candidates = _mseq_label_candidates(payload, stream)
        self.assertEqual(candidates[0]["length_at_0x10_candidate"], len(label))
        self.assertEqual(candidates[0]["text_at_0x12_candidate"], "Synth A")
        self.assertEqual(candidates[0]["status"], "candidate")
        self.assertIn("role unknown", candidates[0]["interpretation"])
        self.assertEqual(candidates[1]["status"], "empty")

    def test_mseq_label_join_keeps_track_role_unknown(self) -> None:
        placements = [{"candidate_mseq_chunk_indices": [4], "track_value_candidate": 9}]
        labels = [{"chunk_index": 4, "text_at_0x12_candidate": "Synth A", "status": "candidate"}]
        linked = _link_mseq_labels_to_placements(placements, labels)
        self.assertEqual(linked[0]["candidate_mseq_labels"], [{
            "mseq_chunk_index": 4,
            "text_candidate": "Synth A",
            "status": "candidate",
        }])
        self.assertIn("track mapping unknown", linked[0]["candidate_mseq_label_interpretation"])
        self.assertNotIn("track_name", linked[0])

    def test_audio_asset_match_correlates_shared_chunk_group(self) -> None:
        name = "loops/example.caf"
        payload = bytes.fromhex("2347c0ab") + bytes(20)
        payload += make_chunk("AuFl", 0x00100000, name.rsplit("/", 1)[-1].encode("utf-16le"))
        region = bytearray(0x92)
        struct.pack_into("<I", region, 0x06, 300)
        struct.pack_into("<I", region, 0x16, 1234)
        region[30:38] = b"example\x00"
        region[0x8A:0x92] = b"ABCD\x10\x00\x00\x00"
        payload += make_chunk("AuRg", 0x00100000, bytes(region))
        payload += make_chunk("AuRg", 0x00100000, b"other\x00")
        payload += make_chunk("AuRg", 0x00140000, b"example\x00")
        stream = _parse_chunk_stream(payload)
        matches = _match_audio_file_references(payload, stream, {"AudioFiles": [name]})
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["group_id_candidate"], 0x00100000)
        self.assertEqual(matches[0]["related_AuRg_chunk_indices"], [1, 2])
        self.assertEqual(matches[0]["name_matched_AuRg_chunk_indices"], [1])
        self.assertEqual(matches[0]["related_AuRg_metadata_candidates"][0]["payload_u32_at_0x06_candidate"], 300)
        self.assertEqual(matches[0]["related_AuRg_metadata_candidates"][0]["payload_u32_at_0x16_candidate"], 1234)
        self.assertEqual(
            matches[0]["related_AuRg_metadata_candidates"][0]["payload_bytes_at_0x8a_candidate_hex"],
            b"ABCD\x10\x00\x00\x00".hex(),
        )

    def test_audio_placement_recovers_beats_track_and_external_source(self) -> None:
        event = bytearray(160)
        event[:4] = b"\x24\x00\x00\x00"
        struct.pack_into("<I", event, 4, 49_920)  # 34560 + 4 bars at 960 PPQ.
        struct.pack_into("<I", event, 0x10, 0x70)
        event[0x14] = 3
        struct.pack_into("<I", event, 0x18, 0x12345678)
        struct.pack_into("<I", event, 0x1C, 122_880)
        event[0x17] = 0x89
        event[0x27] = 0xBC
        event[0x28:0x2C] = b"ABCD"
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
        self.assertEqual(decoded[0]["bytes_at_0x28_candidate_hex"], b"ABCD\x14\x00\x00\x00".hex())
        self.assertEqual(decoded[0]["u32_at_0x18_candidate"], 0x12345678)
        self.assertIn("not used as duration", decoded[0]["u32_at_0x18_interpretation"])
        self.assertEqual(decoded[0]["u32_at_0x1c_candidate"], 122_880)
        self.assertIn("not used as duration", decoded[0]["u32_at_0x1c_interpretation"])
        self.assertEqual(decoded[0]["trailing_event_data_hex"], (bytes([0xC7]) + bytes(79)).hex())

        project = Project(media_references=[MediaReference(
            index=0,
            category="AudioFiles",
            reference="loops/example.caf",
            group_id_candidate=0x140000,
            name_matched_region_chunk_indices=[10],
            region_chunk_metadata_candidates=[{
                "chunk_index": 10,
                "payload_size": 230,
                "filename_stem_matches": True,
                "payload_u32_at_0x16_candidate": 0xC7,
                "payload_bytes_at_0x8a_candidate_hex": b"ABCD\x14\x00\x00\x00".hex(),
            }],
        )])
        _attach_audio_placements(project, decoded)
        self.assertEqual([(track.index, track.kind) for track in project.tracks], [(2, "audio")])
        region = project.tracks[0].regions[0]
        self.assertEqual(region.name, "example")
        self.assertEqual(region.start_beats, "16")
        self.assertIsNone(region.duration_beats)
        self.assertEqual(region.unknown["placement"]["u32_at_0x1c_candidate"], 122_880)
        self.assertEqual(region.source, "loops/example.caf")
        self.assertEqual(region.unknown["candidate_region_chunk_indices_for_source"], [10])
        self.assertEqual(region.unknown["region_chunk_indices_matching_trailing_u32_candidate"], [10])
        self.assertEqual(region.unknown["region_chunk_indices_matching_0x8a_to_0x28_candidate"], [10])

    def test_package_parse_builds_audio_track_and_region_from_placement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "fixture.band"
            make_fixture(fixture, include_audio_placement=True)
            project = parse_band(fixture)
        self.assertEqual(len(project.project_data["audio_placements"]), 1)
        self.assertIn("HYPOTHESIS for this project", project.project_data["audio_placements"][0]["position_confidence"])
        self.assertEqual(len(project.tracks), 1)
        track = project.tracks[0]
        self.assertEqual(track.index, 2)
        self.assertEqual(track.index_confidence, "HYPOTHESIS")
        self.assertEqual(project.to_dict()["tracks"][0]["index_confidence"], "HYPOTHESIS")
        self.assertEqual(track.kind, "audio")
        self.assertEqual(len(track.regions), 1)
        self.assertEqual(track.regions[0].start_beats, "16")
        self.assertEqual(track.regions[0].source, "${CONTENT:loops/example.caf")
        self.assertTrue(any("not validated for this project" in warning for warning in project.warnings))

    def test_text_inspection_labels_audio_starts_as_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "fixture.band"
            make_fixture(fixture, include_audio_placement=True)
            result = subprocess.run(
                [sys.executable, "-m", "band2flp.cli", "inspect", str(fixture)],
                cwd=Path(__file__).parents[1], capture_output=True, text=True, check=True,
            )
        self.assertIn("candidate beat starts", result.stdout)
        self.assertIn("not validated for this project", result.stdout)

    def test_text_inspection_summarizes_candidate_midi_status_families(self) -> None:
        project = Project()
        project.unplaced_midi_regions = [
            SimpleNamespace(notes=[1, 2]),
            SimpleNamespace(notes=[3]),
            SimpleNamespace(notes=[]),
        ]
        project.project_data["event_sequences"] = {
            "record_count": 3,
            "records": [
                {"midi_status_candidate": {"family": "note_on"}},
                {"midi_status_candidate": {"family": "note_on"}},
                {"midi_status_candidate": {"family": "pitch_bend"}},
            ],
        }
        output = io.StringIO()
        with patch("band2flp.cli.parse_band", return_value=project), redirect_stdout(output):
            result = cli_main(["inspect", "synthetic.band"])
        self.assertEqual(result, 0)
        self.assertIn("MIDI-status-shaped records: note_on=2, pitch_bend=1", output.getvalue())
        self.assertIn("Unplaced MIDI region candidates: 3 (3 note candidates; 1 without recognized notes; "
                      "that does not confirm empty regions or track identity)", output.getvalue())
        self.assertIn("interpretation unconfirmed", output.getvalue())

    def test_midi_note_fields_are_exposed_as_unconfirmed_candidates(self) -> None:
        note = bytearray(80)
        note[0] = 0x90
        struct.pack_into("<I", note, 4, 39_360)
        note[0x0A] = 7
        note[0x0B] = 64
        note[0x0C] = 60
        note[0x17] = 0x89
        struct.pack_into("<I", note, 0x1C, 480)
        not_note = bytearray(note)
        not_note[0x17] = 0
        placement = bytearray(80)
        placement[:4] = b"\x20\x00\x00\x00"
        struct.pack_into("<I", placement, 4, 52_320)
        placement[0x20] = 0x10  # Resolves to the 0x00100000 MSeq group.
        placement[0x17] = 0x89
        placement[0x27] = 0x88
        placement[0x37] = 0x8A
        placement[0x47] = 0x88
        events = {"records": [
            {"type_byte": 0x90, "chunk_index": 9, "event_index": 0,
             "group_id_candidate": 0x00100000, "raw_hex": note.hex()},
            {"type_byte": 0x90, "chunk_index": 9, "event_index": 1,
             "group_id_candidate": 0x00100000, "raw_hex": not_note.hex()},
            {"type_byte": 0x20, "chunk_index": 10, "event_index": 3,
             "group_id_candidate": 0x00040000, "raw_hex": placement.hex()},
        ]}
        chunks = {"chunks": [
            {"type": "MSeq", "index": 5, "group_id_candidate": 0x00100000},
            {"type": "MSeq", "index": 6, "group_id_candidate": 0x00200000},
        ]}

        candidates = _parse_midi_note_candidates(events, chunks)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["candidate_mseq_chunk_indices_for_group"], [5])
        self.assertEqual(
            candidates[0]["candidate_midi_region_placements_for_group"],
            [{"source_chunk_index": 10, "source_event_index": 3}],
        )
        self.assertEqual(candidates[0]["position_ticks_from_38400_candidate"], 960)
        self.assertEqual(candidates[0]["onset_beats_region_relative_candidate"], "1")
        self.assertEqual(candidates[0]["pitch_candidate"], 60)
        self.assertEqual(candidates[0]["velocity_candidate"], 64)
        self.assertEqual(candidates[0]["duration_ticks_candidate"], 480)
        self.assertEqual(candidates[0]["duration_beats_candidate"], "1/2")
        self.assertEqual(candidates[0]["position_scope_candidate"], "region-relative")
        self.assertIn("HYPOTHESIS", candidates[0]["position_scope_confidence"])
        self.assertEqual(
            candidates[0]["field_interpretation_confidence"].split(";")[0],
            "HYPOTHESIS transferred from Logic Pro",
        )
        self.assertEqual(candidates[0]["raw_hex"], note.hex())

    def test_midi_note_shaped_family_retains_type_and_does_not_normalize(self) -> None:
        records = []
        for index, event_type in enumerate((0x90, 0x91, 0x9E, 0x9F)):
            raw = bytearray(64)
            raw[0] = event_type
            raw[1] = len(raw)
            raw[0x0B] = 90
            raw[0x0C] = 60 + index
            raw[0x17] = 0x89
            records.append({
                "type_byte": event_type,
                "chunk_index": 1,
                "event_index": index,
                "group_id_candidate": 0x10000,
                "raw_hex": raw.hex(),
            })
        invalid_marker = bytearray.fromhex(records[1]["raw_hex"])
        invalid_marker[0x17] = 0
        records.append({
            "type_byte": 0x91,
            "chunk_index": 1,
            "event_index": 4,
            "group_id_candidate": 0x10000,
            "raw_hex": invalid_marker.hex(),
        })

        candidates = _parse_midi_note_candidates(
            {"records": records}, {"chunks": [{"type": "MSeq", "index": 2, "group_id_candidate": 0x10000}]}
        )

        self.assertEqual([item["event_type_byte"] for item in candidates], [0x90, 0x91, 0x9E, 0x9F])
        self.assertEqual([item["midi_channel_1_based_candidate"] for item in candidates], [1, 2, 15, 16])
        self.assertEqual([item["pitch_candidate"] for item in candidates], [60, 61, 62, 63])
        self.assertTrue(all(item["position_scope_candidate"] == "unknown" for item in candidates))
        self.assertTrue(all("HYPOTHESIS" in item["field_interpretation_confidence"] for item in candidates))

    def test_unique_midi_links_form_unplaced_neutral_candidates(self) -> None:
        project = Project()
        placement_location = {"source_chunk_index": 7, "source_event_index": 2}
        project.project_data["midi_region_placement_candidates"] = [{
            **placement_location,
            "candidate_mseq_chunk_indices": [4],
            "candidate_mseq_labels": [
                {"text_candidate": "Synthetic keys", "status": "candidate"}
            ],
            "start_beats_candidate": "8",
            "track_value_candidate": 3,
        }]
        note_location = {"candidate_mseq_chunk_indices_for_group": [4],
                         "candidate_midi_region_placements_for_group": [placement_location]}
        project.project_data["midi_note_event_candidates"] = [
            {**note_location, "onset_beats_region_relative_candidate": "3/2",
             "duration_beats_candidate": "1/4", "pitch_candidate": 64,
             "velocity_candidate": 80, "midi_channel_1_based_candidate": 2,
             "source_chunk_index": 9, "source_event_index": 1},
            {**note_location, "onset_beats_region_relative_candidate": "0",
             "duration_beats_candidate": "1/2", "pitch_candidate": 60,
             "velocity_candidate": 90, "midi_channel_1_based_candidate": 1,
             "source_chunk_index": 9, "source_event_index": 0},
            {**note_location, "candidate_mseq_chunk_indices_for_group": [4, 5],
             "onset_beats_region_relative_candidate": "2",
             "duration_beats_candidate": "1", "pitch_candidate": 67,
             "velocity_candidate": 100, "midi_channel_1_based_candidate": 3,
             "source_chunk_index": 9, "source_event_index": 2},
        ]

        _attach_unplaced_midi_region_candidates(project)

        self.assertEqual(len(project.unplaced_midi_regions), 1)
        region = project.unplaced_midi_regions[0]
        self.assertEqual(region.start_beats_candidate, "8")
        self.assertEqual(region.label_candidate, "Synthetic keys")
        self.assertEqual([note.pitch_candidate for note in region.notes], [60, 64])
        self.assertEqual(region.unknown["track_value_candidate"], 3)
        self.assertEqual(project.tracks, [])
        self.assertEqual(project.to_dict()["unplaced_midi_regions"][0]["notes"][0]["duration_beats_candidate"], "1/2")

    def test_event_record_labels_midi_status_shapes_as_candidates(self) -> None:
        chunk = {"index": 2, "offset": 100, "group_id_candidate": 0}
        expected = {
            0x90: ("note_on", 1),
            0x9F: ("note_on", 16),
            0xB0: ("control_change", 1),
            0xD1: ("channel_pressure", 2),
            0xEE: ("pitch_bend", 15),
        }
        for status, (family, channel) in expected.items():
            record = _event_record(chunk, 0, 136, 0, bytes([status]) + bytes(15))
            self.assertEqual(record["midi_status_candidate"]["family"], family)
            self.assertEqual(record["midi_status_candidate"]["channel_1_based"], channel)
            self.assertIn("HYPOTHESIS", record["midi_status_candidate"]["confidence"])
        self.assertNotIn(
            "midi_status_candidate", _event_record(chunk, 0, 136, 0, b"\x20" + bytes(15))
        )

    def test_midi_placement_cluster_links_to_candidate_mseq_group(self) -> None:
        event = bytearray(80)
        event[:4] = b"\x20\x00\x00\x00"
        struct.pack_into("<I", event, 4, 49_920)
        struct.pack_into("<I", event, 0x10, 0x58)
        event[0x14] = 3
        event[0x17] = 0x89
        event[0x20] = 0x10
        event[0x27] = 0x88
        event[0x37] = 0x8A
        event[0x47] = 0x88
        events = {"records": [{
            "type_byte": 0x20, "chunk_index": 12, "event_index": 4,
            "group_id_candidate": 0x00040000, "raw_hex": event.hex(),
        }]}
        chunks = {"chunks": [
            {"type": "MSeq", "index": 23, "group_id_candidate": 0x00100000},
            {"type": "MSeq", "index": 24, "group_id_candidate": 0x00200000},
            {"type": "Trak", "index": 25, "group_id_candidate": 0x00100000},
        ]}

        placements = _parse_midi_region_placement_candidates(events, chunks)

        self.assertEqual(len(placements), 1)
        self.assertEqual(placements[0]["candidate_mseq_chunk_indices"], [23])
        self.assertEqual(placements[0]["same_group_trak_chunk_indices_candidate"], [25])
        self.assertIn("semantics UNKNOWN", placements[0]["same_group_trak_confidence"])
        self.assertEqual(
            placements[0]["region_link_confidence"],
            "HIGH CONFIDENCE for a unique MSeq group match in this fixture",
        )
        self.assertEqual(placements[0]["start_beats_candidate"], "16")
        self.assertEqual(placements[0]["track_value_candidate"], 3)
        self.assertIn("without a track-number or index interpretation", placements[0]["track_value_confidence"])

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
            unicode_reference = "${CONTENT:loops/cafe\u0301.caf"
            make_fixture(fixture, audio_reference=unicode_reference)
            result = subprocess.run(
                [sys.executable, "-m", "band2flp.cli", "inspect", str(fixture), "--json"],
                cwd=Path(__file__).parents[1], capture_output=True, text=True, check=True,
            )
        decoded = json.loads(result.stdout)
        self.assertEqual(decoded["tempo_bpm"], 120.0)
        self.assertEqual(decoded["tracks"], [])
        self.assertEqual(decoded["project_data"]["opaque_data_objects"][0]["length"], 63)
        self.assertIn(
            unicode_reference,
            decoded["project_data"]["assetsmetadata_plist"]["values"]["AudioFiles"],
        )

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

from __future__ import annotations

import json
import unittest

from band2flp.parser import BandFormatError
from research.scripts.f1_group_probe import profile_f1_groups


class F1GroupProbeTests(unittest.TestCase):
    def test_profiles_group_multiplicity_without_exposing_values_or_bytes(self) -> None:
        raw = bytes.fromhex("f1" * 16).hex()
        records = [
            {"type_byte": 0xF1, "group_id_candidate": 0x10000, "length": 16, "raw_hex": raw},
            {"type_byte": 0xF1, "group_id_candidate": 0x20000, "length": 16, "raw_hex": raw},
            {"type_byte": 0x20, "group_id_candidate": 0x10000, "length": 80, "raw_hex": "20" * 80},
        ]
        chunks = [
            {"type": "MSeq", "group_id_candidate": 0x10000},
            {"type": "MSeq", "group_id_candidate": 0x20000},
            {"type": "Trak", "group_id_candidate": 0x10000, "payload_size": 0},
            {"type": "Trak", "group_id_candidate": 0x20000, "payload_size": 0},
            {"type": "Trak", "group_id_candidate": 0x30000, "payload_size": 58},
        ]

        profile, payloads = profile_f1_groups(records, chunks)
        serialized = json.dumps(profile)

        self.assertEqual(profile["f1_record_count"], 2)
        self.assertEqual(profile["f1_record_length_counts"], {"16": 2})
        self.assertEqual(profile["distinct_f1_raw_record_count"], 1)
        self.assertEqual(profile["distinct_f1_group_count"], 2)
        self.assertTrue(profile["group_multiplicity_comparisons"]["MSeq"]["multiplicities_match"])
        self.assertTrue(profile["group_multiplicity_comparisons"]["empty_Trak"]["multiplicities_match"])
        self.assertTrue(profile["group_order_comparisons"]["MSeq"]["group_sequence_matches_in_order"])
        self.assertTrue(profile["group_order_comparisons"]["empty_Trak"]["group_sequence_matches_in_order"])
        self.assertEqual(payloads, {bytes.fromhex(raw)})
        self.assertNotIn("65536", serialized)
        self.assertNotIn(raw, serialized)

    def test_reports_group_multiplicity_mismatch(self) -> None:
        record = {"type_byte": 0xF1, "group_id_candidate": 7, "length": 16, "raw_hex": "f1" * 16}
        chunks = [{"type": "MSeq", "group_id_candidate": 8}]

        profile, _ = profile_f1_groups([record], chunks)

        self.assertFalse(profile["group_multiplicity_comparisons"]["MSeq"]["multiplicities_match"])
        self.assertEqual(profile["group_multiplicity_comparisons"]["MSeq"]["groups_in_both_families"], 0)

    def test_distinguishes_order_mismatch_from_matching_multiplicities(self) -> None:
        records = [
            {"type_byte": 0xF1, "group_id_candidate": group, "length": 16, "raw_hex": "f1" * 16}
            for group in (7, 8)
        ]
        chunks = [
            {"type": "MSeq", "group_id_candidate": group}
            for group in (8, 7)
        ]

        profile, _ = profile_f1_groups(records, chunks)

        self.assertTrue(profile["group_multiplicity_comparisons"]["MSeq"]["multiplicities_match"])
        self.assertFalse(profile["group_order_comparisons"]["MSeq"]["group_sequence_matches_in_order"])

    def test_rejects_malformed_f1_raw_record(self) -> None:
        record = {"type_byte": 0xF1, "group_id_candidate": 7, "length": 16, "raw_hex": "not-hex"}

        with self.assertRaisesRegex(BandFormatError, "malformed raw record"):
            profile_f1_groups([record], [])

    def test_scans_payload_occurrences_without_exposing_raw_bytes(self) -> None:
        raw = bytes([0xF1, *range(1, 16)])
        record = {
            "type_byte": 0xF1,
            "group_id_candidate": 7,
            "length": len(raw),
            "raw_hex": raw.hex(),
            "offset": 3,
        }
        profile, _ = profile_f1_groups([record], [], b"abc" + raw + b"xyz")
        self.assertEqual(profile["payload_occurrence_scan"], {
            "raw_record_occurrence_count": 1,
            "occurrences_at_f1_event_starts": 1,
            "all_occurrences_at_f1_event_starts": True,
        })
        self.assertNotIn(raw.hex(), json.dumps(profile))

    def test_reports_matching_marker_outside_f1_event_start(self) -> None:
        raw = bytes([0xF1, *range(1, 16)])
        record = {
            "type_byte": 0xF1,
            "group_id_candidate": 7,
            "length": len(raw),
            "raw_hex": raw.hex(),
            "offset": 0,
        }
        profile, _ = profile_f1_groups([record], [], raw + b"gap" + raw)
        self.assertEqual(profile["payload_occurrence_scan"]["raw_record_occurrence_count"], 2)
        self.assertEqual(profile["payload_occurrence_scan"]["occurrences_at_f1_event_starts"], 1)
        self.assertFalse(profile["payload_occurrence_scan"]["all_occurrences_at_f1_event_starts"])

    def test_rejects_f1_event_payload_offset_mismatch(self) -> None:
        record = {
            "type_byte": 0xF1,
            "group_id_candidate": 7,
            "length": 16,
            "raw_hex": "f1" * 16,
            "offset": 0,
        }
        with self.assertRaisesRegex(BandFormatError, "disagree"):
            profile_f1_groups([record], [], b"x" * 16)

    def test_rejects_duplicate_f1_event_offsets(self) -> None:
        raw = bytes([0xF1, *range(1, 16)])
        record = {
            "type_byte": 0xF1,
            "group_id_candidate": 7,
            "length": len(raw),
            "raw_hex": raw.hex(),
            "offset": 0,
        }
        with self.assertRaisesRegex(BandFormatError, "missing or duplicated"):
            profile_f1_groups([record, record], [], raw)


if __name__ == "__main__":
    unittest.main()


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
        self.assertEqual(payloads, {bytes.fromhex(raw)})
        self.assertNotIn("65536", serialized)
        self.assertNotIn(raw, serialized)

    def test_reports_group_multiplicity_mismatch(self) -> None:
        record = {"type_byte": 0xF1, "group_id_candidate": 7, "length": 16, "raw_hex": "f1" * 16}
        chunks = [{"type": "MSeq", "group_id_candidate": 8}]

        profile, _ = profile_f1_groups([record], chunks)

        self.assertFalse(profile["group_multiplicity_comparisons"]["MSeq"]["multiplicities_match"])
        self.assertEqual(profile["group_multiplicity_comparisons"]["MSeq"]["groups_in_both_families"], 0)

    def test_rejects_malformed_f1_raw_record(self) -> None:
        record = {"type_byte": 0xF1, "group_id_candidate": 7, "length": 16, "raw_hex": "not-hex"}

        with self.assertRaisesRegex(BandFormatError, "malformed raw record"):
            profile_f1_groups([record], [])


if __name__ == "__main__":
    unittest.main()

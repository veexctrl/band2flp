import json
import unittest

from band2flp.parser import BandFormatError
from research.scripts.mseq_event_scope_probe import inventory_scope


class MseqEventScopeProbeTests(unittest.TestCase):
    def test_separates_unique_ambiguous_and_unplaced_mseq_groups(self) -> None:
        chunks = [
            {"type": "MSeq", "index": 1, "group_id_candidate": 0xD001},
            *[
                {"type": "MSeq", "index": index, "group_id_candidate": 0xD002}
                for index in range(2, 7)
            ],
            {"type": "MSeq", "index": 7, "group_id_candidate": 0xD003},
            {"type": "MSeq", "index": 8, "group_id_candidate": 0xD004},
            {"type": "MSeq", "index": 9, "group_id_candidate": 0xD004},
            {"type": "MSeq", "index": 10, "group_id_candidate": 0xD005},
        ]
        placements = [
            {"candidate_mseq_chunk_indices": [1]},
            {"candidate_mseq_chunk_indices": [2, 3, 4, 5, 6]},
            {"candidate_mseq_chunk_indices": [7]},
            {"candidate_mseq_chunk_indices": [8, 9]},
            {"candidate_mseq_chunk_indices": [8]},
            {"candidate_mseq_chunk_indices": [7]},
        ]
        records = [
            {"group_id_candidate": 0xD001, "type_byte": 0x32, "length": 32},
            {"group_id_candidate": 0xD001, "type_byte": 0x90, "length": 32},
            {"group_id_candidate": 0xD002, "type_byte": 0x32, "length": 48},
            {"group_id_candidate": 0xD003, "type_byte": 0xF1, "length": 16},
            {"group_id_candidate": 0xD004, "type_byte": 0x32, "length": 32},
            {"group_id_candidate": 0xD005, "type_byte": 0x32, "length": 32},
        ]

        result = inventory_scope(records, chunks, placements, {0xD001})

        categories = result["scope_categories"]
        self.assertEqual(result["mseq_group_count"], 5)
        self.assertEqual(categories["unique_placement"]["mseq_group_count"], 1)
        self.assertEqual(categories["unique_placement"]["groups_with_type_32"], 1)
        self.assertEqual(categories["unique_placement"]["groups_with_note_candidates"], 1)
        self.assertEqual(categories["ambiguous_placement"]["groups_with_type_32"], 2)
        self.assertEqual(categories["ambiguous_placement"]["mseq_group_count"], 3)
        self.assertEqual(categories["ambiguous_placement"]["type_32_record_length_counts"], {"32": 1, "48": 1})
        self.assertEqual(categories["ambiguous_placement"]["mseq_chunk_multiplicity_counts_for_type_32_groups"], {"2": 1, "5": 1})
        self.assertEqual(categories["no_placement_candidate"]["groups_with_type_32"], 1)
        self.assertNotIn("D001", json.dumps(result))
        self.assertNotIn("53249", json.dumps(result))

    def test_rejects_placement_that_references_missing_mseq(self) -> None:
        with self.assertRaises(BandFormatError):
            inventory_scope([], [], [{"candidate_mseq_chunk_indices": [5]}])

    def test_profiles_repeated_payloads_and_varying_bytes_without_emitting_payloads(self) -> None:
        groups = [0xD101, 0xD202, 0xD303, 0xD404]
        chunks = [
            {"type": "MSeq", "index": index, "group_id_candidate": group}
            for index, group in enumerate(groups, 1)
        ]
        placements = [{"candidate_mseq_chunk_indices": [index]} for index in range(1, 5)]
        first = bytearray(32)
        first[0] = 0x32
        first[5] = 1
        second = bytearray(first)
        second[5] = 2
        payloads = [first, first, first, second]
        records = [
            {
                "group_id_candidate": group,
                "chunk_index": index,
                "event_index": index + 10,
                "type_byte": 0x32,
                "length": 32,
                "raw_hex": bytes(payload).hex(),
            }
            for index, (group, payload) in enumerate(zip(groups, payloads), 1)
        ]

        profile = inventory_scope(records, chunks, placements)["type_32_payload_profiles"]["32"]

        self.assertEqual(profile["record_count"], 4)
        self.assertEqual(profile["distinct_payload_count"], 2)
        self.assertEqual(profile["duplicate_record_count"], 2)
        self.assertEqual(profile["distinct_payload_multiplicity_counts"], {"1": 1, "3": 1})
        self.assertEqual(profile["varying_byte_positions"], [5])
        self.assertEqual(profile["varying_byte_candidate_field_matches"], [])
        self.assertNotIn(bytes(first).hex(), json.dumps(profile))

    def test_rejects_type_32_length_that_disagrees_with_raw_bytes(self) -> None:
        chunk = {"type": "MSeq", "index": 1, "group_id_candidate": 0xD001}
        placement = {"candidate_mseq_chunk_indices": [1]}
        record = {
            "group_id_candidate": 0xD001,
            "type_byte": 0x32,
            "length": 32,
            "raw_hex": "00",
        }
        with self.assertRaises(BandFormatError):
            inventory_scope([record], [chunk], [placement])


if __name__ == "__main__":
    unittest.main()

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


if __name__ == "__main__":
    unittest.main()

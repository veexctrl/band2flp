import json
import unittest

from band2flp.parser import BandFormatError
from research.scripts.midi_linked_event_inventory import inventory


class MidiLinkedEventInventoryTests(unittest.TestCase):
    def test_profiles_event_types_and_lengths_only_for_unique_midi_links(self) -> None:
        chunks = [
            {"type": "MSeq", "index": 1, "group_id_candidate": 0x1234},
            {"type": "MSeq", "index": 2, "group_id_candidate": 0x5678},
            {"type": "MSeq", "index": 3, "group_id_candidate": 0x5678},
        ]
        placements = [
            {"candidate_mseq_chunk_indices": [1]},
            {"candidate_mseq_chunk_indices": [2, 3]},
        ]
        records = [
            {"group_id_candidate": 0x1234, "type_byte": 0xB0, "length": 16},
            {"group_id_candidate": 0x1234, "type_byte": 0xB0, "length": 32},
            {"group_id_candidate": 0x1234, "type_byte": 0xD1, "length": 32},
            {"group_id_candidate": 0x5678, "type_byte": 0xE0, "length": 32},
            {"group_id_candidate": 0x9ABC, "type_byte": 0xF1, "length": 16},
        ]

        result = inventory(records, chunks, placements, {0x1234})

        self.assertEqual(result["distinct_uniquely_linked_midi_groups"], 1)
        self.assertEqual(result["placements_with_ambiguous_or_missing_mseq_link"], 1)
        self.assertEqual(result["linked_groups_with_note_candidates"], 1)
        self.assertEqual(result["linked_groups_without_note_candidates"], 0)
        self.assertEqual(result["linked_event_record_count"], 3)
        self.assertEqual(result["event_types"]["0xb0"], {
            "record_count": 2,
            "distinct_group_count": 1,
            "groups_with_note_candidates": 1,
            "groups_without_note_candidates": 0,
            "record_length_counts": {"16": 1, "32": 1},
        })
        self.assertNotIn("1234", json.dumps(result))
        self.assertNotIn("5678", json.dumps(result))
        self.assertNotIn("9abc", json.dumps(result))

    def test_rejects_placement_that_references_missing_mseq(self) -> None:
        with self.assertRaises(BandFormatError):
            inventory([], [], [{"candidate_mseq_chunk_indices": [5]}])


if __name__ == "__main__":
    unittest.main()

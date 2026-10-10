import json
import struct
import unittest

from band2flp.parser import BandFormatError
from research.scripts.trak_placement_link_probe import profile_links


def fixture(traks, placements, *, mseq_groups=(), note_groups=(), selected_uuid=None):
    raw = bytearray()
    chunks = []
    for index, (group, word) in enumerate(traks):
        payload = bytearray(58)
        struct.pack_into("<I", payload, 8, word)
        if selected_uuid is not None and index == 0:
            payload[0x18:0x28] = selected_uuid
        chunks.append({"type": "Trak", "index": len(chunks), "payload_offset": len(raw),
                       "payload_size": 58, "group_id_candidate": group, "offset": len(raw)})
        raw.extend(payload)
    for group in mseq_groups:
        chunks.append({"type": "MSeq", "index": len(chunks), "payload_offset": len(raw),
                       "payload_size": 0, "group_id_candidate": group, "offset": len(raw)})
    for group in note_groups:
        payload = bytearray(32)
        payload[0] = 0x90
        payload[23] = 0x89
        struct.pack_into("<I", payload, 4, 38400)
        struct.pack_into("<I", payload, 28, 1)
        chunks.append({"type": "EvSq", "index": len(chunks), "payload_offset": len(raw),
                       "payload_size": 32, "group_id_candidate": group, "offset": len(raw)})
        raw.extend(payload)
    for kind, word, track_byte, *cluster in placements:
        payload = bytearray(80)
        payload[0] = kind
        struct.pack_into("<I", payload, 4, 34560)
        struct.pack_into("<I", payload, 16, word)
        payload[20] = track_byte
        struct.pack_into("<I", payload, 32, cluster[0] if cluster else 0)
        for index, value in ((23, 0x89), (39, 0xBC if kind == 0x24 else 0x88),
                             (55, 0x8A), (71, 0x89 if kind == 0x24 else 0x88)):
            payload[index] = value
        chunks.append({"type": "EvSq", "index": len(chunks), "payload_offset": len(raw),
                       "payload_size": 80, "group_id_candidate": 0, "offset": len(raw)})
        raw.extend(payload)
    return bytes(raw), {"chunks": chunks}


class TrakPlacementLinkTests(unittest.TestCase):
    def test_selected_track_uuid_candidate_word_is_profiled_without_exposing_it(self):
        selected_uuid = bytes(range(1, 17))
        raw, stream = fixture(
            [(0x40000, 100), (0x80000, 100)],
            [(0x24, 100, 1), (0x20, 100, 2)],
            selected_uuid=selected_uuid,
        )

        report = profile_links(raw, stream, selected_uuid)

        selected = report["selected_track_candidate_link"]
        self.assertEqual(selected["uuid_matching_trak_count"], 1)
        self.assertTrue(selected["word_unique_in_family"])
        self.assertEqual(selected["word_occurrences_in_other_families"], 1)
        self.assertFalse(selected["word_unique_across_families"])
        self.assertEqual(selected["audio_placement_word_match_count"], 1)
        self.assertEqual(selected["audio_track_byte_matches_ordinal_count"], 1)
        self.assertEqual(selected["midi_placement_word_match_count"], 1)
        self.assertEqual(selected["midi_track_byte_matches_ordinal_count"], 0)
        self.assertNotIn(selected_uuid.hex(), json.dumps(report))

    def test_unique_word_links_can_conflict_with_track_bytes(self):
        report = profile_links(*fixture([(0x40000, 100), (0x80000, 100)],
                                        [(0x24, 100, 2), (0x20, 100, 3)]))
        self.assertEqual(report["group4_group8_unique_pair_count"], 1)
        self.assertEqual(report["combined_placement_word_groups_with_conflicting_track_bytes"], 1)
        matches = report["trak_families"]["0x00040000"]["placement_comparisons"]
        self.assertEqual(matches["audio"]["unique_nonzero_word_match_count"], 1)
        self.assertEqual(matches["midi"]["unique_nonzero_word_match_count"], 1)
        self.assertTrue(report["confidence"].startswith("UNKNOWN"))

    def test_duplicates_are_ambiguous_within_their_family(self):
        report = profile_links(*fixture([(0x40000, 100), (0x40000, 100), (0x80000, 100)],
                                        [(0x20, 100, 2)]))
        self.assertEqual(report["group4_group8_unique_pair_count"], 0)
        self.assertEqual(report["trak_families"]["0x00040000"]["placement_comparisons"]["midi"]
                         ["ambiguous_nonzero_word_match_count"], 1)
        self.assertEqual(report["trak_families"]["0x00080000"]["placement_comparisons"]["midi"]
                         ["unique_nonzero_word_match_count"], 1)

    def test_zero_is_excluded_and_unmatched_words_are_counted(self):
        report = profile_links(*fixture([(0x40000, 0), (0x80000, 0)],
                                        [(0x20, 0, 2), (0x20, 99, 2)]))
        self.assertEqual(report["group4_group8_shared_nonzero_word_count"], 0)
        counts = report["trak_families"]["0x00040000"]["placement_comparisons"]["midi"]
        self.assertEqual(counts["unique_nonzero_word_match_count"], 0)
        self.assertEqual(counts["unmatched_or_zero_word_count"], 2)

    def test_invalid_payload_bounds_are_rejected(self):
        raw, stream = fixture([(0x40000, 1)], [])
        stream["chunks"][0]["payload_size"] += 1
        with self.assertRaises(BandFormatError):
            profile_links(raw, stream)

    def test_note_subset_separates_conflicts_without_discarding_other_records(self):
        report = profile_links(*fixture(
            [(0x40000, 100)],
            [(0x24, 100, 1), (0x20, 100, 1, 1), (0x20, 100, 9, 2)],
            mseq_groups=(65536, 131072), note_groups=(65536,),
        ))
        counts = report["trak_families"]["0x00040000"]["placement_comparisons"]
        self.assertEqual(counts["midi"]["placement_count"], 2)
        self.assertEqual(counts["midi_with_note_candidates"]["placement_count"], 1)
        self.assertEqual(counts["midi_without_note_candidates"]["placement_count"], 1)
        self.assertEqual(counts["midi_with_note_candidates"]
                         ["unique_word_file_order_1_based_equals_track_byte_count"], 1)
        self.assertEqual(counts["midi_without_note_candidates"]
                         ["unique_word_file_order_1_based_equals_track_byte_count"], 0)
        self.assertEqual(report["combined_placement_word_groups_with_conflicting_track_bytes"], 1)
        self.assertEqual(report["audio_and_note_bearing_midi_word_groups_with_conflicting_track_bytes"], 0)
        self.assertEqual(report["note_bearing_midi_nonzero_word_group_count"], 1)

    def test_ambiguous_mseq_link_is_not_classified_as_note_bearing(self):
        report = profile_links(*fixture(
            [(0x40000, 100)], [(0x20, 100, 1, 1)],
            mseq_groups=(65536, 65536), note_groups=(65536,),
        ))
        counts = report["trak_families"]["0x00040000"]["placement_comparisons"]
        self.assertEqual(counts["midi_with_ambiguous_mseq_link"]["placement_count"], 1)
        self.assertEqual(counts["midi_with_note_candidates"]["placement_count"], 0)


if __name__ == "__main__":
    unittest.main()

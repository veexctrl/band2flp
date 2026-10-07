import struct
import unittest

from band2flp.parser import BandFormatError
from research.scripts.trak_placement_link_probe import profile_links


def fixture(traks, placements):
    raw = bytearray()
    chunks = []
    for group, word in traks:
        payload = bytearray(58)
        struct.pack_into("<I", payload, 8, word)
        chunks.append({"type": "Trak", "index": len(chunks), "payload_offset": len(raw),
                       "payload_size": 58, "group_id_candidate": group, "offset": len(raw)})
        raw.extend(payload)
    for kind, word, track_byte in placements:
        payload = bytearray(80)
        payload[0] = kind
        struct.pack_into("<I", payload, 4, 34560)
        struct.pack_into("<I", payload, 16, word)
        payload[20] = track_byte
        for index, value in ((23, 0x89), (39, 0xBC if kind == 0x24 else 0x88),
                             (55, 0x8A), (71, 0x89 if kind == 0x24 else 0x88)):
            payload[index] = value
        chunks.append({"type": "EvSq", "index": len(chunks), "payload_offset": len(raw),
                       "payload_size": 80, "group_id_candidate": 0, "offset": len(raw)})
        raw.extend(payload)
    return bytes(raw), {"chunks": chunks}


class TrakPlacementLinkTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

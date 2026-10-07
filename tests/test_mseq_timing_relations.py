"""Synthetic regression tests for exploratory timing comparisons."""

import struct
import unittest

from band2flp.parser import BandFormatError
from research.scripts.mseq_timing_relations_probe import profile_relations


def fixture(*, tail_length=100, offset=50, placement_word=100, size=300):
    mseq = bytearray(size)
    if size >= 219:
        struct.pack_into("<I", mseq, size - 219, tail_length)
        struct.pack_into("<i", mseq, size - 55, offset)
    note = bytearray(32)
    note[0] = 0x90
    struct.pack_into("<H", note, 2, 32768)
    struct.pack_into("<I", note, 4, 38410)
    note[23] = 0x89
    struct.pack_into("<I", note, 28, 20)
    placement = bytearray(80)
    placement[0] = 0x20
    struct.pack_into("<I", placement, 4, 34560 + offset)
    struct.pack_into("<I", placement, 28, placement_word)
    struct.pack_into("<I", placement, 32, 1)
    for index, value in ((23, 0x89), (39, 0x88), (55, 0x8A), (71, 0x88)):
        placement[index] = value
    raw = bytes(mseq + note + placement)
    chunks = [
        {"type": "MSeq", "index": 0, "payload_offset": 0,
         "payload_size": size, "group_id_candidate": 65536, "offset": 0},
        {"type": "EvSq", "index": 1, "payload_offset": size,
         "payload_size": 32, "group_id_candidate": 65536, "offset": size},
        {"type": "EvSq", "index": 2, "payload_offset": size + 32,
         "payload_size": 80, "group_id_candidate": 0, "offset": size + 32},
    ]
    return raw, {"chunks": chunks}


class MSeqTimingRelationsTests(unittest.TestCase):
    def test_nonzero_equalities_and_containment_are_distinct(self):
        report = profile_relations(*fixture())
        self.assertEqual(report["tail_offset_equals_nonzero_placement_integer_ticks"], 1)
        self.assertEqual(report["tail_length_equals_nonsentinel_placement_word"], 1)
        self.assertEqual(report["tail_length_equals_max_integer_note_end"], 0)
        self.assertEqual(report["tail_length_contains_all_integer_note_ends"], 1)
        self.assertEqual(report["tail_length_contains_all_offset_integer_note_ends"], 1)
        self.assertEqual(report["note_fraction_word_nonzero_count"], 1)
        self.assertTrue(report["confidence"].startswith("UNKNOWN"))
        self.assertNotIn("raw_hex", report)

    def test_negative_offset_is_signed_and_does_not_imply_containment(self):
        report = profile_relations(*fixture(offset=-15))
        self.assertEqual(report["tail_offset_equals_nonzero_placement_integer_ticks"], 1)
        self.assertEqual(report["tail_length_contains_all_integer_note_ends"], 1)
        self.assertEqual(report["tail_length_contains_all_offset_integer_note_ends"], 0)
        self.assertEqual(report["placed_integer_note_bounds_with_tail_shift_contained"], 1)
        self.assertIn("not a placed-region containment test", report["legacy_shifted_containment_scope_note"])

    def test_zero_match_and_sentinel_are_not_counted_as_nonzero_or_finite(self):
        report = profile_relations(*fixture(offset=0, placement_word=0x3FFFFFFF))
        self.assertEqual(report["tail_offset_equals_placement_integer_ticks"], 1)
        self.assertEqual(report["tail_offset_equals_nonzero_placement_integer_ticks"], 0)
        self.assertEqual(report["nonsentinel_placement_word_count"], 0)

    def test_note_extent_and_finite_word_mismatch(self):
        report = profile_relations(*fixture(tail_length=29, placement_word=30))
        self.assertEqual(report["tail_length_contains_all_integer_note_ends"], 0)
        self.assertEqual(report["tail_length_equals_nonsentinel_placement_word"], 0)

    def test_short_mseq_is_reported_without_reading_tail(self):
        report = profile_relations(*fixture(size=218))
        self.assertEqual(report["mseq_too_short_for_tail_words"], 1)
        self.assertEqual(report["unique_placement_tail_comparison_count"], 0)

    def test_invalid_chunk_bounds_are_rejected(self):
        raw, stream = fixture()
        stream["chunks"][0]["payload_offset"] = -1
        with self.assertRaises(BandFormatError):
            profile_relations(raw, stream)

    def test_finite_word_ratio_is_descriptive_without_assigning_repeat_semantics(self):
        report = profile_relations(*fixture(tail_length=40, placement_word=60))
        self.assertEqual(report["note_bearing_nonsentinel_word_three_halves_source_word"], 1)
        self.assertEqual(report["note_bearing_nonsentinel_word_greater_than_source_word"], 1)
        self.assertEqual(report["note_bearing_tail_length_word_multiple_of_960_count"], 0)
        self.assertEqual(report["note_bearing_source_word_below_placement_integer_start_count"], 1)
        self.assertTrue(report["confidence"].startswith("UNKNOWN"))

    def test_adjacent_same_reference_gap_uses_source_word_not_last_note_end(self):
        first, first_stream = fixture(tail_length=40, offset=0, placement_word=0x3FFFFFFF)
        second, second_stream = fixture(tail_length=40, offset=40, placement_word=0x3FFFFFFF)
        first, second = bytearray(first), bytearray(second)
        struct.pack_into("<I", first, first_stream["chunks"][-1]["payload_offset"] + 16, 100)
        struct.pack_into("<I", second, second_stream["chunks"][-1]["payload_offset"] + 16, 100)
        struct.pack_into("<I", second, second_stream["chunks"][-1]["payload_offset"] + 32, 2)
        for chunk in second_stream["chunks"]:
            if chunk["type"] in ("MSeq", "EvSq") and chunk["group_id_candidate"] == 65536:
                chunk["group_id_candidate"] = 131072
            chunk["index"] += len(first_stream["chunks"])
            chunk["payload_offset"] += len(first)
            chunk["offset"] += len(first)
        report = profile_relations(bytes(first + second), {
            "chunks": first_stream["chunks"] + second_stream["chunks"],
        })
        self.assertEqual(report["same_reference_consecutive_note_region_pair_count"], 1)
        self.assertEqual(report["same_reference_start_gap_equals_source_word_count"], 1)
        self.assertEqual(report["same_reference_start_gap_exceeds_note_end_count"], 1)
        self.assertEqual(report["placed_integer_note_bounds_with_tail_shift_contained"], 2)


if __name__ == "__main__":
    unittest.main()

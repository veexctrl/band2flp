import json
import unittest

from research.scripts.audio_frame_field_pair_probe import profile_frame_field_pairs


class AudioFrameFieldPairProbeTests(unittest.TestCase):
    def test_candidate_pair_ranks_against_all_nonoverlapping_offsets(self) -> None:
        payload = bytearray(36)
        payload[0x06:0x0A] = (20).to_bytes(4, "little")
        payload[0x16:0x1A] = (80).to_bytes(4, "little")

        report = profile_frame_field_pairs([(100, [bytes(payload)])])

        self.assertEqual(report["candidate_pair_rank"], 1)
        self.assertEqual(report["candidate_pair_record_match_count"], 1)
        self.assertEqual(report["candidate_pair_source_match_count"], 1)
        self.assertEqual(report["top_matching_offset_pairs"][0]["offsets"], [0x06, 0x16])
        self.assertNotIn(bytes(payload).hex(), json.dumps(report))

    def test_repeated_records_do_not_inflate_source_match_count(self) -> None:
        payload = bytearray(36)
        payload[0x06:0x0A] = (20).to_bytes(4, "little")
        payload[0x16:0x1A] = (80).to_bytes(4, "little")

        report = profile_frame_field_pairs([(100, [bytes(payload), bytes(payload)])])

        self.assertEqual(report["region_record_count"], 2)
        self.assertEqual(report["candidate_pair_record_match_count"], 2)
        self.assertEqual(report["candidate_pair_source_match_count"], 1)
        self.assertEqual(report["candidate_pair_payload_group_count"], 1)
        self.assertEqual(report["candidate_pair_distinct_payload_count"], 1)
        self.assertEqual(report["candidate_pair_groups_with_identical_payloads"], 1)
        self.assertEqual(report["candidate_pair_groups_with_distinct_payloads"], 0)

    def test_candidate_pair_records_can_differ_outside_the_candidate_words(self) -> None:
        first = bytearray(36)
        first[0x06:0x0A] = (20).to_bytes(4, "little")
        first[0x16:0x1A] = (80).to_bytes(4, "little")
        second = bytearray(first)
        second[0x02] = 1

        report = profile_frame_field_pairs([(100, [bytes(first), bytes(second)])])

        self.assertEqual(report["candidate_pair_record_match_count"], 2)
        self.assertEqual(report["candidate_pair_payload_group_count"], 1)
        self.assertEqual(report["candidate_pair_distinct_payload_count"], 2)
        self.assertEqual(report["candidate_pair_groups_with_identical_payloads"], 0)
        self.assertEqual(report["candidate_pair_groups_with_distinct_payloads"], 1)
        self.assertNotIn(bytes(first).hex(), json.dumps(report))
        self.assertNotIn(bytes(second).hex(), json.dumps(report))

    def test_rejects_invalid_source_counts_and_payload_types(self) -> None:
        with self.assertRaises(ValueError):
            profile_frame_field_pairs([(-1, [])])
        with self.assertRaises(ValueError):
            profile_frame_field_pairs([(100, [bytearray(32)])])

    def test_bounds_quadratic_scan_for_unexpectedly_large_records(self) -> None:
        report = profile_frame_field_pairs([(100, [bytes(4097)])])
        self.assertEqual(report["oversized_record_count"], 1)
        self.assertEqual(report["top_matching_offset_pairs"], [])


if __name__ == "__main__":
    unittest.main()


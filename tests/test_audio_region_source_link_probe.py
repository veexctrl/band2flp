from __future__ import annotations

import unittest

from research.scripts.audio_region_source_link_probe import (
    profile_candidate_region_payloads,
    profile_region_placement_field_links,
    profile_source_frame_window_candidates,
    profile_source_link_candidates,
)


class AudioRegionSourceLinkProbeTests(unittest.TestCase):
    def test_source_frame_window_sum_is_counted_without_assigning_trim_semantics(self) -> None:
        first = bytearray(0x1A)
        first[0x16:0x1A] = (100).to_bytes(4, "little")
        second = bytearray(first)
        second[0x06:0x0A] = (25).to_bytes(4, "little")
        second[0x16:0x1A] = (75).to_bytes(4, "little")
        result = profile_source_frame_window_candidates(100, [bytes(first), bytes(second)])
        self.assertEqual(result["candidate_pair_count"], 2)
        self.assertEqual(result["first_zero"], 1)
        self.assertEqual(result["first_nonzero"], 1)
        self.assertEqual(result["sum_equals_source_frames"], 2)
        self.assertEqual(result["nonzero_sum_equals_zero_baseline"], 1)

    def test_source_frame_window_reports_unavailable_source(self) -> None:
        result = profile_source_frame_window_candidates(None, [bytes(0x1A), b"short"])
        self.assertEqual(result["source_length_unknown"], 1)
        self.assertEqual(result["too_short"], 1)

    def test_source_frame_window_reports_shorter_window_with_unknown_source(self) -> None:
        whole = bytearray(0x1A)
        whole[0x16:0x1A] = (100).to_bytes(4, "little")
        shorter = bytearray(whole)
        shorter[0x06:0x0A] = (20).to_bytes(4, "little")
        shorter[0x16:0x1A] = (70).to_bytes(4, "little")
        result = profile_source_frame_window_candidates(None, [bytes(whole), bytes(shorter)])
        self.assertEqual(result["nonzero_sum_below_zero_baseline"], 1)

    def test_candidate_links_are_counted_without_assigning_region_semantics(self) -> None:
        result = profile_source_link_candidates(
            source_frames=100,
            region_frame_candidates=[100, 75, 75, 120],
            placement_suffix_candidates=[75, None, 19],
        )

        self.assertEqual(
            result["region_frame_candidate_relations"],
            {"above_source": 1, "below_source": 2, "equal_source": 1},
        )
        self.assertEqual(result["extended_placement_count"], 2)
        self.assertEqual(result["placement_suffixes_matching_source_region_candidates"], 1)
        self.assertEqual(result["matching_region_candidates_for_those_suffixes"], 2)
        self.assertEqual(result["suffix_matches_with_multiple_candidate_regions"], 1)
        self.assertIn("does not establish", result["interpretation"])

    def test_unknown_source_length_does_not_infer_frame_relation(self) -> None:
        result = profile_source_link_candidates(None, [10, 20], [None])

        self.assertEqual(result["region_frame_candidate_relations"], {"source_length_unknown": 2})
        self.assertEqual(result["extended_placement_count"], 0)

    def test_duplicate_frame_candidates_compare_payloads_without_exposing_bytes(self) -> None:
        result = profile_candidate_region_payloads(
            [(12, b"AAAA"), (12, b"BBBB"), (24, b"CCCC")],
        )

        self.assertEqual(result["repeated_frame_candidate_bucket_count"], 1)
        self.assertEqual(result["repeated_frame_candidate_pair_count"], 1)
        self.assertEqual(result["identical_payload_pair_count"], 0)
        self.assertEqual(result["distinct_payload_pair_count"], 1)
        self.assertEqual(result["unequal_payload_size_pair_count"], 0)
        self.assertEqual(result["pair_byte_difference_counts"], {"4": 1})
        self.assertNotIn("payload", result)
        self.assertNotIn("bytes", result)

    def test_equal_duplicate_payloads_are_not_reported_as_distinct(self) -> None:
        result = profile_candidate_region_payloads(
            [(12, b"same"), (12, b"same")]
        )

        self.assertEqual(result["identical_payload_pair_count"], 1)
        self.assertEqual(result["distinct_payload_pair_count"], 0)

    def test_fixed_field_link_is_counted_only_when_nonzero_and_unique(self) -> None:
        first = bytes(0x8A) + b"AAAAGGGG"
        second = bytes(0x8A) + b"BBBBGGGG"
        unset = bytes(0x92)
        first_placement = bytes(0x28) + b"AAAAGGGG"
        second_placement = bytes(0x28) + b"BBBBGGGG"
        result = profile_region_placement_field_links(
            [first, second, unset], [first_placement, second_placement]
        )

        self.assertEqual(result["region_field_count"], 3)
        self.assertEqual(result["zero_region_field_count"], 1)
        self.assertEqual(result["nonzero_region_field_count"], 2)
        self.assertEqual(result["same_source_field_match_count"], 2)
        self.assertEqual(result["one_to_one_field_match_count"], 2)
        self.assertNotIn("AAAAGGGG", str(result))

    def test_repeated_placement_field_cannot_claim_one_to_one_link(self) -> None:
        candidate = bytes(0x8A) + b"AAAAGGGG"
        placement = bytes(0x28) + b"AAAAGGGG"
        result = profile_region_placement_field_links(
            [candidate], [placement, placement]
        )

        self.assertEqual(result["same_source_field_match_count"], 2)
        self.assertEqual(result["one_to_one_field_match_count"], 0)


if __name__ == "__main__":
    unittest.main()

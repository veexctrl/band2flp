from __future__ import annotations

import unittest

from research.scripts.audio_region_source_link_probe import profile_source_link_candidates


class AudioRegionSourceLinkProbeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

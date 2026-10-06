from __future__ import annotations

import unittest
from types import SimpleNamespace

from research.scripts.caf_placement_spacing_probe import profile_spacing


class CafPlacementSpacingProbeTests(unittest.TestCase):
    def test_profiles_phrase_interval_counts_without_exposing_values(self) -> None:
        reference = SimpleNamespace(
            category="AudioFiles",
            source_loop_metadata={"beat_count": 4},
            group_id_candidate=7,
        )
        placements = [
            {"media_group_id_candidate": 7, "start_beats": start}
            for start in ("0", "4", "13", "17")
        ]
        result = profile_spacing([reference], placements)
        self.assertEqual(result["beat_tagged_source_count"], 1)
        self.assertEqual(result["tagged_sources_with_linked_placements"], 1)
        self.assertEqual(result["linked_placement_count"], 4)
        self.assertEqual(result["adjacent_start_interval_count"], 3)
        self.assertEqual(result["intervals_equal_integer_source_beat_count_multiples"], 2)
        self.assertNotIn("start_beats", result)
        self.assertNotIn("beat_count", result)
        self.assertNotIn("group_id_candidate", result)

    def test_ignores_non_audio_and_unlinked_references(self) -> None:
        audio_reference = SimpleNamespace(
            category="AudioFiles",
            source_loop_metadata={"beat_count": 4},
            group_id_candidate=None,
        )
        non_audio_reference = SimpleNamespace(
            category="SamplerInstrumentsFiles",
            source_loop_metadata={"beat_count": 4},
            group_id_candidate=8,
        )
        result = profile_spacing([audio_reference, non_audio_reference], [])
        self.assertEqual(result["beat_tagged_source_count"], 1)
        self.assertEqual(result["tagged_sources_with_linked_placements"], 0)
        self.assertEqual(result["linked_placement_count"], 0)


if __name__ == "__main__":
    unittest.main()

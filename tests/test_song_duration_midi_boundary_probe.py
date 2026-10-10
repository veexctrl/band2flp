from types import SimpleNamespace
import unittest

from research.scripts.song_duration_midi_boundary_probe import profile


class SongDurationMidiBoundaryProbeTests(unittest.TestCase):
    def test_profiles_note_and_extent_boundaries_without_exposing_values(self) -> None:
        note = SimpleNamespace(onset_beats_candidate="3", duration_beats_candidate="1")
        region = SimpleNamespace(
            start_beats_candidate="1",
            notes=[note],
            unknown={
                "extent_candidates": {
                    "source_duration_beats_candidate": "4",
                    "placement_extent_beats_candidate": "5",
                }
            },
        )
        project = SimpleNamespace(
            duration_value=2.5,
            tempo_bpm=120.0,
            unplaced_midi_regions=[region],
        )

        result = profile(project)

        self.assertEqual(result["candidate_boundary_count"], 3)
        self.assertTrue(result["matches_seconds_within_tolerance"])
        self.assertFalse(result["matches_milliseconds_within_tolerance"])
        self.assertNotIn("2.5", repr(result))

    def test_region_without_note_or_extent_candidates_reports_no_match(self) -> None:
        region = SimpleNamespace(start_beats_candidate="0", notes=[], unknown={})
        project = SimpleNamespace(
            duration_value=10.0,
            tempo_bpm=120.0,
            unplaced_midi_regions=[region],
        )

        result = profile(project)

        self.assertEqual(result["candidate_boundary_count"], 0)
        self.assertFalse(result["matches_seconds_within_tolerance"])
        self.assertFalse(result["matches_milliseconds_within_tolerance"])


if __name__ == "__main__":
    unittest.main()

import json
import unittest

from band2flp.parser import BandFormatError
from research.scripts.audio_frame_pair_start_order_probe import profile_pair_start_order


class AudioFramePairStartOrderProbeTests(unittest.TestCase):
    def test_compares_pair_order_to_linked_start_order_without_emitting_values(self) -> None:
        observations = [
            (0, 100, "0"),
            (0, 100, "8"),
            (20, 80, "4"),
            (20, 80, "12"),
        ]

        report = profile_pair_start_order(observations, 100)

        self.assertEqual(report["source_frame_valid_linked_record_count"], 4)
        self.assertEqual(report["distinct_source_frame_pair_count"], 2)
        self.assertEqual(report["record_order_concordant_count"], 3)
        self.assertEqual(report["record_order_discordant_count"], 1)
        self.assertEqual(report["record_order_tie_count"], 2)
        self.assertEqual(report["window_group_order_concordant_count"], 1)
        self.assertNotIn("0, 100", json.dumps(report))
        self.assertNotIn("20, 80", json.dumps(report))

    def test_ignores_pairs_that_do_not_match_the_source_frame_count(self) -> None:
        report = profile_pair_start_order([(20, 70, "4"), (0, 100, "8")], 100)

        self.assertEqual(report["source_frame_valid_linked_record_count"], 1)
        self.assertEqual(report["distinct_source_frame_pair_count"], 1)
        self.assertEqual(report["window_group_order_concordant_count"], 0)

    def test_rejects_invalid_frame_counts_and_pair_values(self) -> None:
        with self.assertRaises(BandFormatError):
            profile_pair_start_order([], True)
        with self.assertRaises(BandFormatError):
            profile_pair_start_order([(-1, 101, "0")], 100)

    def test_rejects_invalid_start_candidate(self) -> None:
        with self.assertRaises(BandFormatError):
            profile_pair_start_order([(0, 100, "invalid")], 100)


if __name__ == "__main__":
    unittest.main()


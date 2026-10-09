"""Synthetic cached-preview geometry, without source music or Pillow."""

from fractions import Fraction
import unittest

from research.scripts.midi_preview_timing_probe import (
    compare_starts, green_components, predicted_boxes,
)


class Pixels:
    width = height = 5

    def load(self):
        return self

    def __getitem__(self, point):
        return (1, 200, 1) if point in {(1, 1), (2, 1), (3, 2)} else (0, 0, 0)


class PreviewTimingTests(unittest.TestCase):
    def project(self, notes, **changes):
        values = dict(ppq=100, mode="single", source_ticks=400, placement_ticks=600,
                      anchors=[(0, Fraction(0)), (40, Fraction(4))],
                      viewport=(0, 80), minimum_width=1)
        values.update(changes)
        return predicted_boxes(notes, **values)

    def test_calibration_is_exact_and_duration_is_separate(self):
        self.assertEqual(self.project([(125, 25)]), [(Fraction(25, 2), Fraction(15))])

    def test_clipped_left_note_is_retained(self):
        self.assertEqual(self.project([(0, 200)], viewport=(10, 30)), [(10, 20)])

    def test_minimum_glyph_width_and_right_crop(self):
        self.assertEqual(self.project([(590, 0)], minimum_width=6), [(59, 60)])

    def test_repeat_and_stretch_are_distinct_hypotheses(self):
        self.assertEqual(self.project([(100, 100)], mode="repeat"), [(10, 20), (50, 60)])
        self.assertEqual(self.project([(100, 100)], mode="stretch"), [(15, 30)])

    def test_repetition_and_note_duration_stop_at_placement_end(self):
        self.assertEqual(self.project([(350, 100)], mode="repeat"), [(35, 45)])
        self.assertEqual(self.project([(350, 100)], placement_ticks=400), [(35, 40)])

    def test_matching_cannot_reuse_one_prediction(self):
        result = compare_starts([10, 11], [10], 2)
        self.assertEqual(result["one_to_one_matches"], 1)
        self.assertEqual(result["unmatched_observed"], 1)
        self.assertNotIn("observed", result)

    def test_sorted_matching_and_extra_predictions(self):
        result = compare_starts([20, 0], [1, 8, 21], 2)
        self.assertEqual(result["one_to_one_matches"], 2)
        self.assertEqual(result["unmatched_predicted"], 1)
        self.assertEqual(result["observed_residual"]["mean_pixels"], 1)

    def test_empty_residual_is_unavailable(self):
        self.assertIsNone(compare_starts([], [1], 2)["observed_residual"])

    def test_four_connected_components_and_bounds(self):
        self.assertEqual(green_components(Pixels(), (0, 0, 5, 5)),
                         [(1, 1, 3, 2), (3, 2, 4, 3)])
        with self.assertRaises(ValueError):
            green_components(Pixels(), (0, 0, 6, 5))

    def test_invalid_geometry_and_resource_limits(self):
        for changes in ({"ppq": 0}, {"mode": "unknown"}, {"source_ticks": 0},
                        {"placement_ticks": 0},
                        {"anchors": [(1, Fraction(0)), (0, Fraction(4))]},
                        {"viewport": (2, 1)}, {"minimum_width": 0},
                        {"mode": "repeat", "source_ticks": 1, "placement_ticks": 2_000_000,
                         "viewport": (0, 2_000_000)}):
            with self.assertRaises(ValueError):
                self.project([(1, 1)], **changes)
        with self.assertRaises(ValueError):
            self.project([(-1, 1)])
        with self.assertRaises(ValueError):
            compare_starts([1], [1], -1)


if __name__ == "__main__":
    unittest.main()

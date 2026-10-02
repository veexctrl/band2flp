from __future__ import annotations

import unittest

from research.scripts.audio_window_link_probe import scan_window_links


class AudioWindowLinkProbeTests(unittest.TestCase):
    def test_varying_one_to_one_matches_expose_offsets_only(self) -> None:
        regions = [b"XXXX" + b"ABCD1234" + b"zz", b"YYYY" + b"EFGH5678" + b"zz"]
        placements = [b"........" + b"ABCD1234", b"++++++++" + b"EFGH5678"]
        result = scan_window_links([(regions, placements)], widths=(8,), step=2)
        self.assertEqual(result, {"8": [{
            "region_payload_offset": 4,
            "placement_event_offset": 8,
            "one_to_one_matches": 2,
            "source_groups": 1,
        }]})
        self.assertNotIn("ABCD", str(result))

    def test_constant_and_zero_fields_are_not_links(self) -> None:
        regions = [bytes(8) + b"SAME", bytes(8) + b"SAME"]
        placements = [b"SAME" + bytes(8), b"SAME" + bytes(8)]
        self.assertEqual(scan_window_links([(regions, placements)], widths=(4, 8)), {"4": [], "8": []})

    def test_long_unaligned_identifier_windows_are_scanned(self) -> None:
        regions = [b"x" + bytes.fromhex("01" * 16), b"y" + bytes.fromhex("02" * 16)]
        placements = [b"123" + regions[0][1:], b"456" + regions[1][1:]]
        result = scan_window_links([(regions, placements)], widths=(16,), step=1)
        self.assertEqual(result, {"16": [{
            "region_payload_offset": 1,
            "placement_event_offset": 3,
            "one_to_one_matches": 2,
            "source_groups": 1,
        }]})

    def test_one_region_or_placement_cannot_establish_variation(self) -> None:
        self.assertEqual(scan_window_links([([b"AAAA"], [b"AAAA", b"BBBB"])], widths=(4,)), {"4": []})

    def test_invalid_scan_parameters_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            scan_window_links([], widths=(0,))
        with self.assertRaises(ValueError):
            scan_window_links([], step=0)


if __name__ == "__main__":
    unittest.main()

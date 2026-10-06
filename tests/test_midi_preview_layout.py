from __future__ import annotations

import struct
import unittest

from band2flp.flp_export import _flp_event_spans, _place_audio_channels_before_playlist


class MidiPreviewLayoutTests(unittest.TestCase):
    def test_places_silent_channel_and_pattern_before_playlist(self) -> None:
        event_data = bytes((64, 0, 0, 233, 3)) + b"xyz" + bytes((64, 1, 0, 224, 1, 0, 47, 0))
        source = b"FLhd" + bytes(10) + b"FLdt" + struct.pack("<I", len(event_data)) + event_data

        result = _place_audio_channels_before_playlist(source, 2)
        events = _flp_event_spans(result)

        self.assertEqual([event[0] for event in events], [64, 64, 224, 233, 47])
        self.assertEqual(result[events[3][2]:events[3][3]], b"xyz")
        self.assertEqual(len(result), len(source))


if __name__ == "__main__":
    unittest.main()
